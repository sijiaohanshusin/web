'use strict';

const crypto = require('crypto');
const { encryptString, decryptString } = require('./crypto');

const STATE_KEY = 'heuesta-mailbox:state';
const RETRIES_KEY = 'heuesta-mailbox:retries';
const SENDERS_KEY = 'heuesta-mailbox:senders';

class MailboxStore {
	constructor(db, encryptionKey) {
		this.db = db;
		this.encryptionKey = encryptionKey;
	}

	async getState() {
		return (await this.db.getObject(STATE_KEY)) || {};
	}

	async updateState(fields) {
		await this.db.setObject(STATE_KEY, fields);
		return this.getState();
	}

	async storeRefreshToken(token) {
		await this.db.setObjectField(STATE_KEY, 'encryptedRefreshToken', encryptString(token, this.encryptionKey));
	}

	async getRefreshToken() {
		const encrypted = await this.db.getObjectField(STATE_KEY, 'encryptedRefreshToken');
		return encrypted ? decryptString(encrypted, this.encryptionKey) : '';
	}

	async hasRefreshToken() {
		return Boolean(await this.db.getObjectField(STATE_KEY, 'encryptedRefreshToken'));
	}

	async saveOAuthState(state, uid) {
		const digest = crypto.createHash('sha256').update(state).digest('hex');
		await this.db.setObject(`heuesta-mailbox:oauth:${digest}`, {
			uid: Number(uid),
			expiresAt: Date.now() + 10 * 60 * 1000,
		});
	}

	async consumeOAuthState(state, uid) {
		if (!state) {
			return false;
		}
		const digest = crypto.createHash('sha256').update(state).digest('hex');
		const key = `heuesta-mailbox:oauth:${digest}`;
		const saved = await this.db.getObject(key);
		await this.db.delete(key);
		return Boolean(saved && Number(saved.uid) === Number(uid) && Number(saved.expiresAt) > Date.now());
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

	async addRetry(messageId, errorMessage) {
		let previous = {};
		try {
			previous = JSON.parse(await this.db.getObjectField(RETRIES_KEY, messageId) || '{}');
		} catch (err) {
			previous = {};
		}
		const attempts = Number(previous.attempts || 0) + 1;
		const delay = Math.min(6 * 60 * 60 * 1000, 30 * 1000 * (2 ** Math.min(attempts, 8)));
		await this.db.setObjectField(RETRIES_KEY, messageId, JSON.stringify({
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
