'use strict';

const assert = require('node:assert/strict');
const { Readable } = require('node:stream');
const test = require('node:test');
const { MailboxSynchronizer, safeError } = require('../lib/sync');

function synchronizer(overrides = {}) {
	return new MailboxSynchronizer({
		store: {},
		imap: {},
		archive: {},
		logger: { error: () => {} },
		pollSeconds: 300,
		...overrides,
	});
}

function metadata(uid, date = uid * 1000) {
	return {
		uid,
		emailId: `email-${uid}`,
		internalDate: new Date(date),
		envelope: { subject: `Mail ${uid}`, from: [{ address: `sender${uid}@example.com` }] },
		bodyStructure: { part: '1', type: 'text/plain', size: 4 },
	};
}

test('sanitizes credential and connection failures', () => {
	assert.match(safeError({ code: 'AUTHENTICATIONFAILED', message: 'secret response' }), /应用专用密码/);
	assert.doesNotMatch(safeError({ code: 'AUTHENTICATIONFAILED', message: 'secret response' }), /secret/);
	assert.match(safeError({ code: 'ETIMEDOUT' }), /稍后自动重试/);
	assert.match(safeError({ code: 'CONNECT_TIMEOUT' }), /稍后自动重试/);
});

test('first successful connection records a baseline without importing history', async () => {
	const updates = [];
	const store = {
		getState: async () => ({}),
		updateState: async value => updates.push(value),
	};
	const imap = {
		user: 'heuesta@gmail.com',
		isConfigured: () => true,
		withInbox: async callback => callback({}, { uidValidity: 123n, uidNext: 51 }),
	};
	const result = await synchronizer({ store, imap }).runSync();
	assert.equal(result.baseline, true);
	assert.equal(updates[0].imapUidValidity, '123');
	assert.equal(updates[0].imapLastUid, 50);
});

test('fetches a bounded UID range and advances the cursor after processing', async () => {
	const updates = [];
	const ranges = [];
	const store = { updateState: async value => updates.push(value) };
	const sync = synchronizer({ store });
	sync.processMetadata = async (client, items) => items.length;
	const client = {
		fetchAll: async (range) => {
			ranges.push(range);
			return [metadata(11), metadata(12)];
		},
	};
	const result = await sync.syncInbox(client, { uidNext: 13 }, { imapLastUid: 10, startedAt: 0 }, '123');
	assert.deepEqual(ranges, ['11:12']);
	assert.equal(result.published, 2);
	assert.deepEqual(updates.at(-1), { imapLastUid: 12 });
});

test('queues a malformed message without blocking later messages', async () => {
	const retries = [];
	const published = [];
	const store = {
		isMessageComplete: async () => false,
		markMessage: async () => {},
		addRetry: async (id, error, details) => retries.push({ id, error, details }),
		removeRetry: async () => {},
	};
	const archive = {
		publish: async (mail) => {
			published.push(mail.id);
			return { duplicate: false };
		},
	};
	const client = {
		download: async (uid) => {
			if (uid === 1) {
				throw new Error('malformed MIME');
			}
			return { content: Readable.from(['body']) };
		},
	};
	const count = await synchronizer({ store, archive }).processMetadata(
		client,
		[metadata(1, 100), metadata(2, 200)],
		'123',
		0
	);
	assert.equal(count, 1);
	assert.deepEqual(published, ['gmail:email-2']);
	assert.equal(retries[0].id, 'gmail:email-1');
	assert.equal(retries[0].details.uid, 1);
});
