'use strict';

const { parseImapMessage, stableMessageId } = require('./mail-parser');

const UID_WINDOW_SIZE = 500;

function errorCode(error) {
	return String(error && (error.code || error.responseCode || error.serverResponseCode) || '').toUpperCase();
}

function isCredentialError(error) {
	const code = errorCode(error);
	const message = String(error && error.message || '').toLowerCase();
	return code.includes('AUTH') || message.includes('invalid credentials') ||
		message.includes('application-specific password required') || message.includes('username and password not accepted');
}

function safeError(error) {
	const code = errorCode(error);
	if (isCredentialError(error)) {
		return 'Gmail IMAP 登录失败，请检查账号、两步验证和应用专用密码';
	}
	if (['CONNECT_TIMEOUT', 'GREETING_TIMEOUT', 'ETIMEDOUT', 'ECONNRESET', 'ECONNREFUSED', 'EAI_AGAIN', 'ENETUNREACH'].includes(code)) {
		return `Gmail IMAP 暂时无法连接（${code}），稍后自动重试`;
	}
	if (code === 'MESSAGE_MISSING') {
		return '邮件在重试前已离开收件箱，已跳过';
	}
	const message = String(error && error.message || '未知同步错误')
		.replace(/[\r\n]+/g, ' ')
		.slice(0, 240);
	return code ? `Gmail IMAP 错误 ${code}: ${message}` : `Gmail IMAP 错误: ${message}`;
}

class MailboxSynchronizer {
	constructor(options) {
		Object.assign(this, options);
		this.pollSeconds = Math.max(60, Number(options.pollSeconds) || 300);
		this.running = null;
		this.timer = null;
		this.initialTimer = null;
	}

	start() {
		if (this.timer) {
			return;
		}
		this.initialTimer = setTimeout(() => {
			this.syncNow().catch(error => this.logger.error(`[heuesta-mailbox] initial sync failed: ${safeError(error)}`));
		}, 20000);
		this.initialTimer.unref();
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
		if (!this.imap.isConfigured()) {
			return { skipped: true, reason: 'not-configured' };
		}

		try {
			return await this.imap.withInbox(async (client, mailbox) => {
				const state = await this.store.getState();
				const uidValidity = String(mailbox.uidValidity || '');
				const latestUid = Math.max(0, Number(mailbox.uidNext || 1) - 1);

				if (!state.imapUidValidity) {
					await this.store.updateState({
						connectedEmail: this.imap.user,
						imapUidValidity: uidValidity,
						imapLastUid: latestUid,
						startedAt: Date.now(),
						lastSuccessAt: Date.now(),
						lastError: '',
						needsCredentialUpdate: 0,
					});
					return { baseline: true, candidates: 0, published: 0, remaining: 0 };
				}

				if (String(state.imapUidValidity) !== uidValidity) {
					await this.store.updateState({
						imapUidValidity: uidValidity,
						imapLastUid: latestUid,
						lastSuccessAt: Date.now(),
						lastError: 'Gmail INBOX 游标已变化，系统已安全重建基线；未回溯导入历史邮件',
						needsCredentialUpdate: 0,
					});
					return { reset: true, candidates: 0, published: 0, remaining: 0 };
				}

				const retryPublished = await this.processRetries(client, uidValidity);
				const result = await this.syncInbox(client, mailbox, state, uidValidity);
				const current = await this.store.getState();
				await this.store.updateState({
					connectedEmail: this.imap.user,
					lastSuccessAt: Date.now(),
					lastError: '',
					needsCredentialUpdate: 0,
					syncCount: Number(current.syncCount || 0) + 1,
					publishedCount: Number(current.publishedCount || 0) + result.published + retryPublished,
				});
				return { ...result, published: result.published + retryPublished };
			});
		} catch (error) {
			const message = safeError(error);
			await this.store.updateState({
				lastError: message,
				needsCredentialUpdate: isCredentialError(error) ? 1 : 0,
			});
			throw new Error(message);
		}
	}

	async syncInbox(client, mailbox, state, uidValidity) {
		const startUid = Math.max(1, Number(state.imapLastUid || 0) + 1);
		const latestUid = Math.max(0, Number(mailbox.uidNext || 1) - 1);
		if (startUid > latestUid) {
			return { candidates: 0, published: 0, remaining: 0 };
		}

		const upperUid = Math.min(latestUid, startUid + UID_WINDOW_SIZE - 1);
		const metadata = await client.fetchAll(`${startUid}:${upperUid}`, {
			uid: true,
			envelope: true,
			bodyStructure: true,
			internalDate: true,
		}, { uid: true });
		const published = await this.processMetadata(client, metadata, uidValidity, Number(state.startedAt || 0));
		await this.store.updateState({ imapLastUid: upperUid });
		return {
			candidates: metadata.length,
			published,
			remaining: Math.max(0, latestUid - upperUid),
		};
	}

	async processMetadata(client, metadata, uidValidity, startedAt) {
		const messages = [...metadata].sort((left, right) => (
			new Date(left.internalDate || 0).getTime() - new Date(right.internalDate || 0).getTime()
		));
		let published = 0;
		for (const item of messages) {
			const messageId = stableMessageId(item, uidValidity);
			if (await this.store.isMessageComplete(messageId)) {
				continue;
			}
			const internalDate = new Date(item.internalDate || item.envelope && item.envelope.date || 0).getTime();
			if (startedAt && internalDate && internalDate < startedAt) {
				await this.store.markMessage(messageId, { status: 'complete', skipped: 'before-baseline', completedAt: Date.now() });
				continue;
			}
			try {
				const message = await parseImapMessage(client, item, uidValidity);
				const result = await this.archive.publish(message);
				if (!result.duplicate) {
					published += 1;
				}
				await this.store.removeRetry(messageId);
			} catch (error) {
				await this.store.addRetry(messageId, safeError(error), {
					transport: 'imap',
					uid: Number(item.uid),
					uidValidity,
				});
			}
		}
		return published;
	}

	async processRetries(client, uidValidity) {
		const retries = await this.store.listRetries();
		let published = 0;
		for (const retry of retries.filter(item => Number(item.nextAttemptAt || 0) <= Date.now())) {
			if (retry.transport !== 'imap' || !retry.uid) {
				continue;
			}
			if (String(retry.uidValidity) !== uidValidity) {
				await this.store.removeRetry(retry.messageId);
				continue;
			}
			if (await this.store.isMessageComplete(retry.messageId)) {
				await this.store.removeRetry(retry.messageId);
				continue;
			}
			try {
				const item = await client.fetchOne(Number(retry.uid), {
					uid: true,
					envelope: true,
					bodyStructure: true,
					internalDate: true,
				}, { uid: true });
				if (!item) {
					await this.store.markMessage(retry.messageId, { status: 'complete', skipped: 'left-inbox', completedAt: Date.now() });
					await this.store.removeRetry(retry.messageId);
					continue;
				}
				const message = await parseImapMessage(client, item, uidValidity);
				const result = await this.archive.publish(message);
				if (!result.duplicate) {
					published += 1;
				}
				await this.store.removeRetry(retry.messageId);
			} catch (error) {
				await this.store.addRetry(retry.messageId, safeError(error), retry);
			}
		}
		return published;
	}
}

module.exports = {
	MailboxSynchronizer,
	UID_WINDOW_SIZE,
	isCredentialError,
	safeError,
};
