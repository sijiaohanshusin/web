'use strict';

const { ImapFlow } = require('imapflow');

const EXPECTED_ACCOUNT = 'heuesta@gmail.com';

function normalizeAppPassword(value) {
	return String(value || '').replace(/\s+/g, '');
}

class GmailImap {
	constructor(options = {}) {
		this.user = String(options.user || EXPECTED_ACCOUNT).trim().toLowerCase();
		this.appPassword = normalizeAppPassword(options.appPassword);
		this.host = 'imap.gmail.com';
		this.port = 993;
		this.connectAttempts = Math.max(1, Number(options.connectAttempts) || 3);
		this.retryDelayMs = options.retryDelayMs === undefined ? 2000 : Math.max(0, Number(options.retryDelayMs) || 0);
	}

	isConfigured() {
		return this.user === EXPECTED_ACCOUNT && /^[a-z]{16}$/i.test(this.appPassword);
	}

	createClient() {
		if (!this.isConfigured()) {
			throw new Error('Gmail IMAP account or 16-character app password is missing');
		}
		const client = new ImapFlow({
			host: this.host,
			port: this.port,
			secure: true,
			servername: this.host,
			auth: { user: this.user, pass: this.appPassword },
			logger: false,
			connectionTimeout: 45000,
			greetingTimeout: 30000,
			socketTimeout: 60000,
			disableAutoIdle: true,
			tls: { minVersion: 'TLSv1.2' },
		});
		client.on('error', () => {});
		return client;
	}

	async connectClient() {
		let lastError;
		for (let attempt = 1; attempt <= this.connectAttempts; attempt += 1) {
			const client = this.createClient();
			try {
				await client.connect();
				return client;
			} catch (error) {
				client.close();
				lastError = error;
				const code = String(error && (error.code || error.responseCode) || '').toUpperCase();
				if (code.includes('AUTH') || attempt === this.connectAttempts) {
					throw error;
				}
				await new Promise(resolve => setTimeout(resolve, this.retryDelayMs * attempt));
			}
		}
		throw lastError;
	}

	async withInbox(callback) {
		const client = await this.connectClient();
		let lock;
		try {
			lock = await client.getMailboxLock('INBOX', {
				readOnly: true,
				description: 'heuesta-mailbox synchronization',
			});
			return await callback(client, client.mailbox);
		} finally {
			if (lock) {
				lock.release();
			}
			if (client.usable) {
				await client.logout().catch(() => client.close());
			} else {
				client.close();
			}
		}
	}
}

module.exports = { GmailImap, EXPECTED_ACCOUNT, normalizeAppPassword };
