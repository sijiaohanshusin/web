'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { GmailImap, normalizeAppPassword } = require('../lib/imap');

test('normalizes grouped app passwords without accepting the regular Gmail password', () => {
	assert.equal(normalizeAppPassword('abcd efgh ijkl mnop'), 'abcdefghijklmnop');
	assert.equal(new GmailImap({ user: 'heuesta@gmail.com', appPassword: 'abcd efgh ijkl mnop' }).isConfigured(), true);
	assert.equal(new GmailImap({ user: 'heuesta@gmail.com', appPassword: 'regular-password' }).isConfigured(), false);
	assert.equal(new GmailImap({ user: 'other@gmail.com', appPassword: 'abcdefghijklmnop' }).isConfigured(), false);
});

test('retries transient connection failures without rerunning mailbox callbacks', async () => {
	let created = 0;
	const imap = new GmailImap({
		user: 'heuesta@gmail.com',
		appPassword: 'abcdefghijklmnop',
		connectAttempts: 3,
		retryDelayMs: 0,
	});
	imap.createClient = () => {
		created += 1;
		return {
			connect: async () => {
				if (created < 3) {
					const error = new Error('temporary timeout');
					error.code = 'CONNECT_TIMEOUT';
					throw error;
				}
			},
			close: () => {},
		};
	};
	const client = await imap.connectClient();
	assert.ok(client);
	assert.equal(created, 3);
});

test('does not retry ImapFlow authenticationFailed errors with a generic command code', async () => {
	let attempts = 0;
	const imap = new GmailImap({ appPassword: 'abcdefghijklmnop', retryDelayMs: 0 });
	imap.createClient = () => ({
		connect: async () => {
			attempts += 1;
			throw Object.assign(new Error('Command failed'), {
				code: 'CommandFailed', authenticationFailed: true, serverResponseCode: 'AUTHENTICATIONFAILED',
			});
		},
		close: () => {},
	});
	await assert.rejects(imap.connectClient());
	assert.equal(attempts, 1);
});
