'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

exports.init = async () => {
    const nconf = module.parent.require('nconf');
    assert.equal(process.env.HEUESTA_FORUM_AUDIT, '1');
    assert.equal(nconf.get('url'), 'http://127.0.0.1:4567');
    assert.equal(nconf.get('postgres:host'), '127.0.0.1');
    assert.equal(nconf.get('postgres:database'), 'heuesta_forum_ci');
    assert.equal(nconf.get('postgres:username'), 'heuesta_forum_ci');
    assert.ok(!process.env.GMAIL_APP_PASSWORD && !process.env.GMAIL_OAUTH_CLIENT_SECRET);
    const target = path.resolve(process.env.HEUESTA_FORUM_FIXTURE);
    assert.equal(path.basename(path.dirname(target)), 'forum-evidence');
    assert.equal(path.basename(path.dirname(path.dirname(target))), '.shots');

    const db = require.main.require('./src/database');
    const categories = require.main.require('./src/categories');
    const privileges = require.main.require('./src/privileges');
    const MailboxStore = require('nodebb-plugin-heuesta-mailbox/lib/store');
    const { ForumArchive } = require('nodebb-plugin-heuesta-mailbox/lib/forum');
    const store = new MailboxStore(db);
    const archive = new ForumArchive({
        store, db, categories, privileges,
        user: require.main.require('./src/user'),
        groups: require.main.require('./src/groups'),
        topics: require.main.require('./src/topics'),
        posts: require.main.require('./src/posts'),
        slugify: require.main.require('./src/slugify'),
    });
    await archive.ensureInfrastructure();
    const discussion = await categories.create({name: '手册演示交流', description: '隔离测试，非正式站数据'});
    const all = privileges.categories.getGroupPrivilegeList();
    await privileges.categories.rescind(all, discussion.cid, ['guests', 'registered-users', 'verified-users', 'unverified-users']);
    await privileges.categories.give(['groups:find', 'groups:read', 'groups:topics:read'], discussion.cid, ['guests']);
    await privileges.categories.give([
        'groups:find', 'groups:read', 'groups:topics:read', 'groups:topics:create', 'groups:topics:reply',
    ], discussion.cid, ['预备会员', '科协会员', '站务管理', '系统管理员']);
    const mail = (id, address) => ({
        id, senderKey: address, fromName: '手册演示发件人', fromEmail: address,
        subject: '手册演示：活动安排', internalDate: Date.now(),
        body: '这是一封隔离环境的合成邮件，不包含真实邮箱内容。',
        html: '<h2>手册演示</h2><p>活动安排仅用于验证私密版块。</p><script>alert(1)</script><img src="https://tracking.invalid/pixel">',
        attachments: [{filename: '演示附件.pdf', mimeType: 'application/pdf', size: 1024}],
    });
    await archive.publish(mail('ci-mail-1', 'sender-one@example.invalid'));
    await archive.publish(mail('ci-mail-2', 'sender-two@example.invalid'));
    await archive.publish(mail('ci-mail-3', 'sender-one@example.invalid'));
    const duplicate = await archive.publish(mail('ci-mail-1', 'sender-one@example.invalid'));
    assert.equal(duplicate.duplicate, true);
    const first = await db.getObject('heuesta-mailbox:message:ci-mail-1');
    const second = await db.getObject('heuesta-mailbox:message:ci-mail-2');
    const third = await db.getObject('heuesta-mailbox:message:ci-mail-3');
    assert.equal(Number(first.tid), Number(third.tid));
    assert.notEqual(Number(first.tid), Number(second.tid));
    fs.writeFileSync(target, JSON.stringify({
        discussionCid: discussion.cid, mailboxCid: archive.categoryCid,
        mailboxTid: first.tid, mailboxPid: JSON.parse(first.pids)[0], previewToken: first.previewToken,
        checks: ['real archive keeps senders in separate topics', 'same sender appends a reply', 'message ID deduplication'],
    }));
};
