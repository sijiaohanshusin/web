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
