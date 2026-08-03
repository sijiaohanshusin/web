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

	async withInbox(callback) {
		const client = this.createClient();
		let lock;
		try {
			await client.connect();
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
