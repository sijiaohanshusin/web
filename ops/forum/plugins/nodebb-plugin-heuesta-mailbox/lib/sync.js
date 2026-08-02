'use strict';

const { parseMessage } = require('./mail-parser');

const EXCLUDED_LABELS = new Set(['SPAM', 'TRASH', 'SENT', 'DRAFT']);

function safeError(error) {
	const status = Number(error && (error.code || (error.response && error.response.status))) || 0;
	if (status === 401 || String(error && error.message || '').includes('invalid_grant')) {
		return 'Gmail authorization is invalid; administrator reauthorization is required';
	}
	if (status === 429) {
		return 'Gmail API rate limit reached; the message will be retried';
	}
	if (status >= 500) {
		return `Gmail API temporary error (${status}); retry scheduled`;
	}
	const message = String(error && error.message || 'unknown synchronization error')
		.replace(/[\r\n]+/g, ' ')
		.slice(0, 240);
	return status ? `Gmail API error ${status}: ${message}` : message;
}

function statusCode(error) {
	return Number(error && (error.code || (error.response && error.response.status))) || 0;
}

function collectHistoryMessageIds(histories) {
	const ids = new Set();
	for (const history of histories || []) {
		for (const added of history.messagesAdded || []) {
			const message = added.message || {};
			if ((message.labelIds || []).includes('INBOX') && message.id) {
				ids.add(message.id);
			}
		}
		for (const labeled of history.labelsAdded || []) {
			if ((labeled.labelIds || []).includes('INBOX') && labeled.message && labeled.message.id) {
				ids.add(labeled.message.id);
			}
		}
	}
	return [...ids];
}

class MailboxSynchronizer {
	constructor(options) {
		Object.assign(this, options);
		this.pollSeconds = Math.max(60, Number(options.pollSeconds) || 300);
		this.running = null;
		this.timer = null;
	}

	start() {
		if (this.timer) {
			return;
		}
		this.timer = setInterval(() => {
			this.syncNow().catch(error => this.logger.error(`[heuesta-mailbox] poll failed: ${safeError(error)}`));
		}, this.pollSeconds * 1000);
		this.timer.unref();
	}

	async syncNow() {
		if (this.running) {
			return this.running;
		}
		this.running = this.runSync().finally(() => {
			this.running = null;
		});
		return this.running;
	}

	async runSync() {
		if (!this.oauth.isConfigured() || !await this.store.hasRefreshToken()) {
			return { skipped: true, reason: 'not-connected' };
		}
		const state = await this.store.getState();
		if (!state.historyId) {
			return { skipped: true, reason: 'missing-history-baseline' };
		}

		try {
			const gmail = await this.oauth.gmail();
			const retryPublished = await this.processRetries(gmail);
			let result;
			try {
				result = await this.syncHistory(gmail, state);
			} catch (error) {
				if (statusCode(error) !== 404) {
					throw error;
				}
				result = await this.recoverExpiredHistory(gmail, state);
			}
			const current = await this.store.getState();
			await this.store.updateState({
				lastSuccessAt: Date.now(),
				lastError: '',
				needsReauthorization: 0,
				syncCount: Number(current.syncCount || 0) + 1,
				publishedCount: Number(current.publishedCount || 0) + result.published + retryPublished,
			});
			return { ...result, published: result.published + retryPublished };
		} catch (error) {
			const message = safeError(error);
			await this.store.updateState({
				lastError: message,
				needsReauthorization: statusCode(error) === 401 || message.includes('reauthorization') ? 1 : 0,
			});
			throw new Error(message);
		}
	}

	async syncHistory(gmail, state) {
		let pageToken;
		let latestHistoryId = String(state.historyId);
		const ids = new Set();
		do {
			const response = await gmail.users.history.list({
				userId: 'me',
				startHistoryId: String(state.historyId),
				historyTypes: ['messageAdded', 'labelAdded'],
				maxResults: 500,
				pageToken,
			});
			for (const id of collectHistoryMessageIds(response.data.history)) {
				ids.add(id);
			}
			latestHistoryId = String(response.data.historyId || latestHistoryId);
			pageToken = response.data.nextPageToken;
		} while (pageToken);

		const published = await this.processMessageIds(gmail, [...ids], Number(state.startedAt || 0));
		await this.store.updateState({ historyId: latestHistoryId });
		return { candidates: ids.size, published, recovered: false };
	}

	async recoverExpiredHistory(gmail, state) {
		const floor = Math.max(Number(state.startedAt || 0), Number(state.lastSuccessAt || state.startedAt || Date.now()) - 5 * 60 * 1000);
		const ids = [];
		let pageToken;
		do {
			const response = await gmail.users.messages.list({
				userId: 'me',
				q: `in:inbox after:${Math.floor(floor / 1000)}`,
				maxResults: 500,
				pageToken,
			});
			ids.push(...(response.data.messages || []).map(message => message.id));
			pageToken = response.data.nextPageToken;
		} while (pageToken);
		const published = await this.processMessageIds(gmail, [...new Set(ids)], Number(state.startedAt || 0));
		const profile = await gmail.users.getProfile({ userId: 'me' });
		await this.store.updateState({ historyId: String(profile.data.historyId || state.historyId) });
		return { candidates: ids.length, published, recovered: true };
	}

	async processMessageIds(gmail, ids, startedAt) {
		const messages = [];
		for (const id of ids) {
			if (await this.store.isMessageComplete(id)) {
				continue;
			}
			try {
				const message = await this.fetchMessage(gmail, id);
				if (Number(message.internalDate) >= startedAt) {
					messages.push(message);
				} else {
					await this.store.markMessage(id, { status: 'complete', skipped: 'before-baseline', completedAt: Date.now() });
				}
			} catch (error) {
				await this.store.addRetry(id, safeError(error));
			}
		}
		messages.sort((left, right) => Number(left.internalDate) - Number(right.internalDate));

		let published = 0;
		for (const message of messages) {
			try {
				if (await this.processFetchedMessage(message)) {
					published += 1;
				}
				await this.store.removeRetry(message.id);
			} catch (error) {
				await this.store.addRetry(message.id, safeError(error));
			}
		}
		return published;
	}

	async processRetries(gmail) {
		const retries = await this.store.listRetries();
		let published = 0;
		for (const retry of retries.filter(item => Number(item.nextAttemptAt || 0) <= Date.now())) {
			if (await this.store.isMessageComplete(retry.messageId)) {
				await this.store.removeRetry(retry.messageId);
				continue;
			}
			try {
				const message = await this.fetchMessage(gmail, retry.messageId);
				if (await this.processFetchedMessage(message)) {
					published += 1;
				}
				await this.store.removeRetry(retry.messageId);
			} catch (error) {
				await this.store.addRetry(retry.messageId, safeError(error));
			}
		}
		return published;
	}

	async fetchMessage(gmail, id) {
		const response = await gmail.users.messages.get({ userId: 'me', id, format: 'full' });
		return parseMessage(response.data);
	}

	async processFetchedMessage(message) {
		if ((message.labelIds || []).some(label => EXCLUDED_LABELS.has(label))) {
			await this.store.markMessage(message.id, { status: 'complete', skipped: 'excluded-label', completedAt: Date.now() });
			return false;
		}
		const result = await this.archive.publish(message);
		return !result.duplicate;
	}
}

module.exports = {
	MailboxSynchronizer,
	EXCLUDED_LABELS,
	collectHistoryMessageIds,
	safeError,
};
