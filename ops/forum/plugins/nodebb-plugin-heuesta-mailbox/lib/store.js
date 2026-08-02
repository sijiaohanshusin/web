'use strict';

const STATE_KEY = 'heuesta-mailbox:state';
const RETRIES_KEY = 'heuesta-mailbox:retries';
const SENDERS_KEY = 'heuesta-mailbox:senders';

class MailboxStore {
	constructor(db) {
		this.db = db;
	}

	async getState() {
		return (await this.db.getObject(STATE_KEY)) || {};
	}

	async updateState(fields) {
		await this.db.setObject(STATE_KEY, fields);
		return this.getState();
	}

	async isMessageComplete(messageId) {
		return (await this.db.getObjectField(`heuesta-mailbox:message:${messageId}`, 'status')) === 'complete';
	}

	async markMessage(messageId, fields) {
		await this.db.setObject(`heuesta-mailbox:message:${messageId}`, fields);
	}

	async getSenderTopic(senderHash) {
		return await this.db.getObjectField(SENDERS_KEY, senderHash);
	}

	async setSenderTopic(senderHash, tid) {
		await this.db.setObjectField(SENDERS_KEY, senderHash, Number(tid));
	}

	async addRetry(messageId, errorMessage, metadata = {}) {
		let previous = {};
		try {
			previous = JSON.parse(await this.db.getObjectField(RETRIES_KEY, messageId) || '{}');
		} catch (err) {
			previous = {};
		}
		const attempts = Number(previous.attempts || 0) + 1;
		const delay = Math.min(6 * 60 * 60 * 1000, 30 * 1000 * (2 ** Math.min(attempts, 8)));
		await this.db.setObjectField(RETRIES_KEY, messageId, JSON.stringify({
			...metadata,
			attempts,
			nextAttemptAt: Date.now() + delay,
			lastError: errorMessage,
		}));
		await this.updateState({ recentError: errorMessage, recentErrorAt: Date.now() });
	}

	async removeRetry(messageId) {
		await this.db.deleteObjectField(RETRIES_KEY, messageId);
	}

	async listRetries() {
		const values = (await this.db.getObject(RETRIES_KEY)) || {};
		return Object.entries(values).map(([messageId, raw]) => {
			try {
				return { messageId, ...JSON.parse(raw) };
			} catch (err) {
				return { messageId, attempts: 0, nextAttemptAt: 0, lastError: 'invalid retry record' };
			}
		});
	}
}

module.exports = MailboxStore;
