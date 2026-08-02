'use strict';

const crypto = require('crypto');
const { formatPosts, topicTitle } = require('./format');

const BOT_USERNAME = '公共邮箱机器人';
const BOT_GROUP = 'heuesta-mailbox-bot';
const CATEGORY_NAME = '公共邮箱';
const READ_GROUPS = ['正式会员', '干事', '管理员'];
const DENIED_GROUPS = [
	'guests', 'registered-users', 'spiders', 'fediverse', 'unverified-users', 'verified-users',
	'报名会员', '预备会员',
];
const VIEW_PRIVILEGES = ['groups:find', 'groups:read', 'groups:topics:read'];

class ForumArchive {
	constructor(deps) {
		Object.assign(this, deps);
		this.botUid = 0;
		this.categoryCid = 0;
	}

	async ensureInfrastructure() {
		this.botUid = Number(await this.user.getUidByUsername(BOT_USERNAME)) || 0;
		if (!this.botUid) {
			this.botUid = await this.user.create({
				username: BOT_USERNAME,
				password: crypto.randomBytes(48).toString('base64url'),
			}, { emailVerification: 'skip' });
		}
		await this.user.setUserFields(this.botUid, {
			status: 'offline',
			aboutme: '协会公共邮箱只读归档机器人，不接收私信。',
		});

		if (!await this.groups.getGroupData(BOT_GROUP)) {
			await this.groups.create({
				name: BOT_GROUP,
				hidden: 1,
				private: 1,
				disableJoinRequests: 1,
				disableLeave: 1,
			});
		}
		await this.groups.join(BOT_GROUP, this.botUid);

		const cids = await this.categories.getAllCidsFromSet('categories:cid');
		const categories = await this.categories.getCategoriesData(cids);
		const byName = new Map(categories.filter(Boolean).map(category => [category.name, category]));
		const parent = byName.get('站务中心');
		let category = byName.get(CATEGORY_NAME);
		if (!category) {
			category = await this.categories.create({
				name: CATEGORY_NAME,
				description: 'heuesta@gmail.com 的新邮件只读归档。内容可能含验证码、安全提醒等敏感信息，请勿转发。',
				icon: 'fa-envelope-open-text',
				bgColor: '#1f5c70',
				color: '#ffffff',
				parentCid: parent ? parent.cid : 0,
			});
		}
		this.categoryCid = Number(category.cid);
		await this.categories.update({
			[this.categoryCid]: {
				description: 'heuesta@gmail.com 的新邮件只读归档。内容可能含验证码、安全提醒等敏感信息，请勿转发。',
				parentCid: parent ? parent.cid : category.parentCid || 0,
			},
		});

		const allPrivileges = this.privileges.categories.getGroupPrivilegeList();
		for (const group of DENIED_GROUPS) {
			await this.privileges.categories.rescind(allPrivileges, this.categoryCid, group);
		}
		for (const group of READ_GROUPS) {
			await this.privileges.categories.rescind(allPrivileges, this.categoryCid, group);
			await this.privileges.categories.give(VIEW_PRIVILEGES, this.categoryCid, group);
		}
		await this.privileges.categories.rescind(allPrivileges, this.categoryCid, BOT_GROUP);
		await this.privileges.categories.give(
			[...VIEW_PRIVILEGES, 'groups:topics:create', 'groups:topics:reply'],
			this.categoryCid,
			BOT_GROUP
		);
		await this.privileges.categories.give(
			['groups:posts:delete', 'groups:topics:delete', 'groups:posts:view_deleted', 'groups:purge', 'groups:moderate'],
			this.categoryCid,
			'管理员'
		);

		await this.store.updateState({ botUid: this.botUid, categoryCid: this.categoryCid });
		await this.ensureWarningTopic();
		return { botUid: this.botUid, categoryCid: this.categoryCid };
	}

	async ensureWarningTopic() {
		const state = await this.store.getState();
		const existing = await this.activeTopic(state.warningTid);
		if (existing) {
			return;
		}
		const result = await this.topics.post({
			uid: this.botUid,
			cid: this.categoryCid,
			title: '公共邮箱阅读须知（含敏感邮件）',
			fromQueue: true,
			content: [
				'此版块自动归档 **heuesta@gmail.com** 在系统上线后收到的新邮件，仅供正式会员、干事和管理员查阅。',
				'',
				'- 邮件可能包含验证码、密码重置链接、账号安全提醒及其他敏感信息。',
				'- 请勿截图、转发或在协会工作之外使用这里的内容。',
				'- 附件仅显示名称、类型和大小，系统不会下载或保存附件文件。',
				'- 此处为只读档案；如需回复，请由邮箱负责人在 Gmail 中处理。',
			].join('\n'),
		});
		const tid = result.topicData.tid;
		await this.topics.tools.pin(tid, 'system');
		await this.store.updateState({ warningTid: tid });
	}

	async activeTopic(tid) {
		if (!tid || !await this.topics.exists(tid)) {
			return false;
		}
		const data = await this.topics.getTopicFields(tid, ['deleted', 'cid']);
		return !Number(data.deleted) && Number(data.cid) === Number(this.categoryCid);
	}

	async findTopicBySenderMarker(senderHash) {
		const tids = await this.db.getSortedSetRevRange(`cid:${this.categoryCid}:tids`, 0, -1);
		for (const tid of tids) {
			if (!await this.activeTopic(tid)) {
				continue;
			}
			const pids = await this.db.getSortedSetRange(`tid:${tid}:posts`, 0, 0);
			const post = pids.length ? await this.posts.getPostFields(pids[0], ['content']) : null;
			if (post && String(post.content || '').includes(`heuesta-mailbox-sender:${senderHash}`)) {
				return Number(tid);
			}
		}
		return 0;
	}

	async findMarker(tid, marker) {
		const pids = await this.db.getSortedSetRange(`tid:${tid}:posts`, 0, -1);
		const postData = await this.posts.getPostsFields(pids, ['pid', 'content']);
		return postData.find(post => String(post.content || '').includes(marker));
	}

	async updateTopicTitle(tid, title) {
		const existing = await this.topics.getTopicField(tid, 'title');
		if (existing === title) {
			return;
		}
		await this.topics.setTopicFields(tid, {
			title,
			slug: `${tid}/${this.slugify(title) || 'mail'}`,
		});
	}

	async publish(mail) {
		if (await this.store.isMessageComplete(mail.id)) {
			return { duplicate: true };
		}
		const senderHash = crypto.createHash('sha256').update(mail.senderKey).digest('hex');
		let tid = Number(await this.store.getSenderTopic(senderHash)) || 0;
		if (!await this.activeTopic(tid)) {
			tid = await this.findTopicBySenderMarker(senderHash);
		}
		const title = topicTitle(mail);
		const contents = formatPosts(mail, senderHash);
		const pids = [];

		if (!tid) {
			const existing = await this.findMarkerInCategory(`heuesta-mailbox:${mail.id}:0`);
			if (existing) {
				tid = existing.tid;
			} else {
				const result = await this.topics.post({
					uid: this.botUid,
					cid: this.categoryCid,
					title,
					content: contents[0],
					timestamp: mail.internalDate,
					fromQueue: true,
				});
				tid = Number(result.topicData.tid);
				pids.push(Number(result.postData.pid));
			}
			await this.store.setSenderTopic(senderHash, tid);
		} else {
			await this.updateTopicTitle(tid, title);
			const marker = `heuesta-mailbox:${mail.id}:0`;
			if (!await this.findMarker(tid, marker)) {
				const reply = await this.topics.reply({
					uid: this.botUid,
					tid,
					content: contents[0],
					timestamp: mail.internalDate,
					fromQueue: true,
				});
				pids.push(Number(reply.pid));
			}
		}

		for (let index = 1; index < contents.length; index += 1) {
			const marker = `heuesta-mailbox:${mail.id}:${index}`;
			if (await this.findMarker(tid, marker)) {
				continue;
			}
			const reply = await this.topics.reply({
				uid: this.botUid,
				tid,
				content: contents[index],
				timestamp: mail.internalDate + index,
				fromQueue: true,
			});
			pids.push(Number(reply.pid));
		}

		await this.store.markMessage(mail.id, {
			status: 'complete',
			tid,
			pids: JSON.stringify(pids),
			internalDate: mail.internalDate,
			completedAt: Date.now(),
		});
		return { duplicate: false, tid, pids };
	}

	async findMarkerInCategory(marker) {
		const tids = await this.db.getSortedSetRevRange(`cid:${this.categoryCid}:tids`, 0, -1);
		for (const tid of tids) {
			if (await this.activeTopic(tid)) {
				const post = await this.findMarker(tid, marker);
				if (post) {
					return { tid: Number(tid), pid: Number(post.pid) };
				}
			}
		}
		return null;
	}
}

module.exports = {
	ForumArchive,
	BOT_USERNAME,
	BOT_GROUP,
	CATEGORY_NAME,
	READ_GROUPS,
	DENIED_GROUPS,
	VIEW_PRIVILEGES,
};
