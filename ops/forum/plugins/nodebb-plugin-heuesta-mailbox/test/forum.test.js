'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const {
	ForumArchive,
	BOT_USERNAME,
	BOT_GROUP,
	READ_GROUPS,
	DENIED_GROUPS,
	VIEW_PRIVILEGES,
} = require('../lib/forum');

test('provisions a distinct private bot group and read-only member ACLs', async () => {
	const rescinded = [];
	const given = [];
	const allPrivileges = ['groups:find', 'groups:read', 'groups:topics:read', 'groups:topics:create', 'groups:posts:upvote'];
	const storeState = { warningTid: 12 };
	const archive = new ForumArchive({
		user: {
			getUidByUsername: async username => username === BOT_USERNAME ? 7 : 0,
			setUserFields: async () => {},
		},
		groups: {
			getGroupData: async name => name === BOT_GROUP ? { name } : null,
			join: async () => {},
		},
		categories: {
			getAllCidsFromSet: async () => [2, 9],
			getCategoriesData: async () => [{ cid: 2, name: '站务中心' }, { cid: 9, name: '公共邮箱' }],
			update: async () => {},
		},
		privileges: {
			categories: {
				getGroupPrivilegeList: () => allPrivileges,
				rescind: async (privileges, cid, group) => rescinded.push({ privileges, cid, group }),
				give: async (privileges, cid, group) => given.push({ privileges, cid, group }),
			},
		},
		topics: {
			exists: async tid => Number(tid) === 12,
			getTopicFields: async () => ({ deleted: 0, cid: 9 }),
		},
		store: {
			getState: async () => storeState,
			updateState: async fields => Object.assign(storeState, fields),
		},
	});

	await archive.ensureInfrastructure();
	assert.notEqual(BOT_GROUP, BOT_USERNAME);
	for (const group of [...DENIED_GROUPS, ...READ_GROUPS, BOT_GROUP]) {
		assert.ok(rescinded.some(entry => entry.group === group && entry.privileges === allPrivileges));
	}
	for (const group of READ_GROUPS) {
		assert.ok(given.some(entry => entry.group === group && entry.privileges === VIEW_PRIVILEGES));
	}
	assert.ok(given.some(entry => entry.group === BOT_GROUP && entry.privileges.includes('groups:topics:reply')));
	assert.equal(archive.botUid, 7);
	assert.equal(archive.categoryCid, 9);
});

test('searches the topic main post as well as replies for archive markers', async () => {
	const archive = new ForumArchive({
		db: {
			getSortedSetRange: async key => key === 'tid:16:posts' ? [19] : [],
		},
		topics: {
			getTopicFields: async () => ({ mainPid: 18 }),
		},
		posts: {
			getPostsFields: async pids => pids.map(pid => ({
				pid,
				content: pid === 18 ? '<!-- heuesta-mailbox:gmail:123:0 -->' : 'reply',
			})),
		},
	});

	const post = await archive.findMarker(16, 'heuesta-mailbox:gmail:123:0');
	assert.equal(post.pid, 18);
});

function timestampArchive() {
	const topicData = new Map();
	const senders = new Map();
	const messages = new Map();
	const writes = [];
	const archive = new ForumArchive({
		store: {
			isMessageComplete: async id => messages.has(id),
			getSenderTopic: async hash => senders.get(hash),
			setSenderTopic: async (hash, tid) => senders.set(hash, tid),
			markMessage: async (id, record) => messages.set(id, record),
		},
		topics: {
			exists: async tid => topicData.has(tid),
			getTopicFields: async tid => topicData.get(tid),
			post: async options => {
				writes.push(options);
				const tid = topicData.size + 1;
				// NodeBB marks future topics scheduled/deleted instead of publishing now.
				topicData.set(tid, { cid: 9, deleted: Number(options.timestamp > Date.now()) });
				return { topicData: { tid }, postData: { pid: writes.length } };
			},
			reply: async options => {
				writes.push(options);
				return { pid: writes.length };
			},
		},
	});
	archive.categoryCid = 9;
	archive.findTopicBySenderMarker = async () => 0;
	archive.findMarkerInCategory = async () => null;
	archive.findMarker = async () => null;
	archive.updateTopicTitle = async () => {};
	return { archive, messages, writes, topicData };
}

function mailAt(id, internalDate, body = 'A synthetic mail') {
	return {
		id, internalDate, subject: 'Clock skew fixture', fromName: 'Fixture',
		fromEmail: 'sender@example.invalid', senderKey: 'sender@example.invalid',
		body, html: '', attachments: [],
	};
}

test('future received dates cannot schedule, hide, or split sender topics, including continued floors', async () => {
	const { archive, messages, writes, topicData } = timestampArchive();
	const received = Date.now() + 3600000;
	const first = await archive.publish(mailAt('first', received, 'Synthetic paragraph.\n\n'.repeat(2000)));
	const second = await archive.publish(mailAt('second', received + 1000));
	assert.equal(second.tid, first.tid);
	assert.equal(topicData.size, 1);
	assert.ok(writes.length > 2);
	assert.ok(writes.every(options => options.timestamp <= Date.now()));
	assert.equal(messages.get('first').internalDate, received);
	assert.equal(messages.get('second').internalDate, received + 1000);
});

test('normal received timestamps are preserved in forum posts', async () => {
	const { archive, writes, messages } = timestampArchive();
	const received = Date.now() - 3600000;
	await archive.publish(mailAt('normal', received));
	assert.equal(writes[0].timestamp, received);
	assert.equal(messages.get('normal').internalDate, received);
});
