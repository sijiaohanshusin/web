'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { MailboxSynchronizer, collectHistoryMessageIds, safeError } = require('../lib/sync');

test('collects only messages that entered INBOX and removes duplicates', () => {
	const ids = collectHistoryMessageIds([
		{
			messagesAdded: [
				{ message: { id: 'a', labelIds: ['INBOX'] } },
				{ message: { id: 'spam', labelIds: ['SPAM'] } },
			],
			labelsAdded: [{ message: { id: 'a' }, labelIds: ['INBOX'] }],
		},
		{ labelsAdded: [{ message: { id: 'b' }, labelIds: ['INBOX'] }] },
	]);
	assert.deepEqual(ids.sort(), ['a', 'b']);
});

test('sanitizes common Gmail errors without serializing OAuth responses', () => {
	assert.match(safeError({ code: 429, message: 'quota' }), /rate limit/);
	assert.match(safeError({ code: 401, message: 'invalid_grant', response: { data: { access_token: 'secret' } } }), /reauthorization/);
	assert.doesNotMatch(safeError({ code: 401, response: { data: { access_token: 'secret' } } }), /secret/);
});

test('sorts messages by internalDate and advances the cursor after publishing', async () => {
	const updates = [];
	const published = [];
	const store = {
		isMessageComplete: async () => false,
		markMessage: async () => {},
		addRetry: async () => {},
		removeRetry: async () => {},
		updateState: async value => updates.push(value),
	};
	const synchronizer = new MailboxSynchronizer({
		store,
		oauth: {},
		archive: {},
		logger: { error: () => {} },
		pollSeconds: 300,
	});
	synchronizer.fetchMessage = async (gmail, id) => ({ id, internalDate: id === 'later' ? 200 : 100 });
	synchronizer.processFetchedMessage = async (message) => {
		published.push(message.id);
		return true;
	};
	const gmail = {
		users: {
			history: {
				list: async () => ({
					data: {
						history: [{ messagesAdded: [
							{ message: { id: 'later', labelIds: ['INBOX'] } },
							{ message: { id: 'earlier', labelIds: ['INBOX'] } },
						] }],
						historyId: '202',
					},
				}),
			},
		},
	};

	const result = await synchronizer.syncHistory(gmail, { historyId: '101', startedAt: 0 });
	assert.deepEqual(published, ['earlier', 'later']);
	assert.equal(result.published, 2);
	assert.deepEqual(updates.at(-1), { historyId: '202' });
});

test('queues a malformed message without blocking later messages', async () => {
	const retries = [];
	const published = [];
	const store = {
		isMessageComplete: async () => false,
		markMessage: async () => {},
		addRetry: async (id, error) => retries.push({ id, error }),
		removeRetry: async () => {},
	};
	const synchronizer = new MailboxSynchronizer({
		store,
		oauth: {},
		archive: {},
		logger: { error: () => {} },
		pollSeconds: 300,
	});
	synchronizer.fetchMessage = async (gmail, id) => {
		if (id === 'bad') {
			throw new Error('malformed MIME');
		}
		return { id, internalDate: 200 };
	};
	synchronizer.processFetchedMessage = async (message) => {
		published.push(message.id);
		return true;
	};

	const count = await synchronizer.processMessageIds({}, ['bad', 'good'], 0);
	assert.equal(count, 1);
	assert.deepEqual(published, ['good']);
	assert.equal(retries[0].id, 'bad');
});
