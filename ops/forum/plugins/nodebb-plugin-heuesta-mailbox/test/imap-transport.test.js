'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { GmailImap } = require('../lib/imap');
const { MailboxSynchronizer } = require('../lib/sync');
const { ImapTestServer, syntheticMail } = require('./helpers/imap-server');

function memoryArchive() {
	const state = {};
	const messages = new Map();
	const retries = new Map();
	const published = [];
	const store = {
		getState: async () => ({ ...state }),
		updateState: async patch => Object.assign(state, patch),
		isMessageComplete: async id => messages.get(id)?.status === 'complete',
		markMessage: async (id, value) => messages.set(id, value),
		listRetries: async () => [...retries.values()],
		addRetry: async (id, error, details) => retries.set(id, { ...details, messageId: id, error }),
		removeRetry: async id => retries.delete(id),
	};
	const archive = { publish: async mail => {
		if (await store.isMessageComplete(mail.id)) return { duplicate: true };
		published.push(mail);
		await store.markMessage(mail.id, { status: 'complete' });
		return { duplicate: false };
	} };
	return { state, messages, retries, published, store, archive };
}

function synchronizer(server, data) {
	return new MailboxSynchronizer({
		imap: server.client(), store: data.store, archive: data.archive,
		logger: { error: () => {} }, pollSeconds: 300,
	});
}

test('production transport retains strict Gmail TLS defaults and disabled protocol logging', () => {
	const client = new GmailImap({ appPassword: 'abcdefghijklmnop' }).createClient();
	assert.equal(client.host, 'imap.gmail.com');
	assert.equal(client.port, 993);
	assert.equal(client.options.secure, true);
	assert.equal(client.options.logger, false);
	assert.equal(client.options.tls.minVersion, 'TLSv1.2');
	assert.notEqual(client.options.tls.rejectUnauthorized, false);
	assert.equal(client.options.tls.ca, undefined);
	client.close();
});

test('real TLS IMAP baselines history, decodes nested MIME, preserves IDs, and survives restart', { timeout: 20000 }, async t => {
	const server = await new ImapTestServer().start();
	t.after(() => server.close());
	const old = server.add(syntheticMail(1, { date: new Date('2020-01-01Z') }));
	const data = memoryArchive();
	const sync = synchronizer(server, data);
	assert.equal((await sync.syncNow()).baseline, true);
	assert.equal(data.state.imapLastUid, 1);
	assert.equal(data.published.length, 0);
	server.add(syntheticMail(2, { date: new Date(Date.now() + 90000) }));
	server.add(syntheticMail(3, { htmlOnly: true, date: new Date(Date.now() + 80000) }));
	assert.equal((await sync.syncNow()).published, 2);
	assert.deepEqual(data.published.map(mail => mail.id), ['gmail:9000000000000000003', 'gmail:9000000000000000002']);
	assert.match(data.published[0].body, /活动安排仅用于验证私密版块/);
	assert.doesNotMatch(data.published[0].body, /alert\(1\)|tracking.invalid/);
	const mixed = data.published[1];
	assert.equal(mixed.fromName, '手册演示发件人');
	assert.equal(mixed.subject, '手册演示：活动安排');
	assert.equal(mixed.fromEmail, 'sender.one+test@example.invalid');
	assert.match(mixed.body, /合成邮件/);
	assert.equal(mixed.attachments[0].filename, 'fixture.pdf');
	assert.equal(mixed.attachments[0].size, 1024);
	assert.equal((await sync.syncNow()).published, 0);
	const restarted = synchronizer(server, data);
	assert.equal((await restarted.syncNow()).published, 0);
	// Gmail can give an already archived message a new UID when it re-enters INBOX.
	server.add(syntheticMail(4, { id: '9000000000000000002' }));
	assert.equal((await restarted.syncNow()).published, 0);
	assert.equal(data.published.length, 2);
	assert.equal(data.messages.has(`gmail:${old.id}`), false);
	server.assertReadOnly();
});

test('real authentication failure stops after one attempt and stores a credential-update status', { timeout: 15000 }, async t => {
	const server = await new ImapTestServer().start();
	t.after(() => server.close());
	server.rejectAuth = true;
	const data = memoryArchive();
	await assert.rejects(synchronizer(server, data).syncNow(), /应用专用密码/);
	assert.equal(server.authAttempts, 1);
	assert.equal(data.state.needsCredentialUpdate, 1);
	assert.doesNotMatch(JSON.stringify(data.state), /SYNTHETIC-PRIVATE-CANARY/);
	assert.deepEqual(server.unexpected, []);
});

test('untrusted TLS certificate is rejected rather than weakening verification', { timeout: 15000 }, async t => {
	const server = await new ImapTestServer().start();
	t.after(() => server.close());
	const data = memoryArchive();
	const sync = synchronizer(server, data);
	sync.imap = server.client({ trusted: false, attempts: 1 });
	await assert.rejects(sync.syncNow(), /证书/);
	assert.equal(server.authAttempts, 0);
	assert.equal(data.state.needsCredentialUpdate, 0);
});

test('dropped TLS greetings retry without rerunning the INBOX callback', { timeout: 15000 }, async t => {
	const server = await new ImapTestServer().start();
	t.after(() => server.close());
	server.dropGreetings = 2;
	let called = 0;
	await server.client().withInbox(async (client, mailbox) => {
		called += 1;
		assert.equal(mailbox.readOnly, true);
		assert.equal(client.socket.authorized, true);
	});
	assert.equal(server.connections, 3);
	assert.equal(called, 1);
	server.assertReadOnly();
});

test('failed body fetch queues only that message and recovers on the next poll', { timeout: 20000 }, async t => {
	const server = await new ImapTestServer().start();
	t.after(() => server.close());
	const data = memoryArchive();
	const sync = synchronizer(server, data);
	await sync.syncNow();
	const broken = server.add(syntheticMail(1));
	server.add(syntheticMail(2));
	server.failBodyOnce.add(1);
	assert.equal((await sync.syncNow()).published, 1);
	assert.equal(data.state.imapLastUid, 2);
	assert.equal(data.retries.size, 1);
	assert.doesNotMatch(JSON.stringify([...data.retries.values()]), /SYNTHETIC-PRIVATE-CANARY/);
	assert.equal((await sync.syncNow()).published, 1);
	assert.equal(data.retries.size, 0);
	assert.equal(data.published.filter(mail => mail.id === `gmail:${broken.id}`).length, 1);
	server.assertReadOnly();
});

test('UIDVALIDITY reset rebaselines; a missing retry is skipped without deleting archives', { timeout: 20000 }, async t => {
	const server = await new ImapTestServer().start();
	t.after(() => server.close());
	const data = memoryArchive();
	const sync = synchronizer(server, data);
	await sync.syncNow();
	const gone = server.add(syntheticMail(1));
	server.failBodyOnce.add(1);
	await sync.syncNow();
	server.messages = [];
	await sync.syncNow();
	assert.equal(data.retries.size, 0);
	assert.equal(data.messages.get(`gmail:${gone.id}`).skipped, 'left-inbox');
	server.add(syntheticMail(2));
	await sync.syncNow();
	server.uidValidity += 1;
	server.add(syntheticMail(3));
	assert.equal((await sync.syncNow()).reset, true);
	assert.equal(data.published.length, 1);
	assert.equal((await sync.syncNow()).published, 0);
	server.assertReadOnly();
});

test('disconnect during body download survives synchronizer restart without losing queued mail', { timeout: 20000 }, async t => {
	const server = await new ImapTestServer().start();
	t.after(() => server.close());
	const data = memoryArchive();
	const sync = synchronizer(server, data);
	await sync.syncNow();
	server.add(syntheticMail(1));
	server.add(syntheticMail(2));
	server.dropBodyOnce.add(1);
	assert.equal((await sync.syncNow()).published, 0);
	assert.equal(data.retries.size, 2);
	assert.equal(data.state.imapLastUid, 2);
	assert.equal((await synchronizer(server, data).syncNow()).published, 2);
	assert.equal(data.retries.size, 0);
	assert.equal((await synchronizer(server, data).syncNow()).published, 0);
	server.assertReadOnly();
});
