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
    const { MailboxSynchronizer } = require('nodebb-plugin-heuesta-mailbox/lib/sync');
    const { ImapTestServer, syntheticMail } = require('nodebb-plugin-heuesta-mailbox/test/helpers/imap-server');
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
    const checks = [];
    const server = await new ImapTestServer().start();
    try {
        const createSync = () => new MailboxSynchronizer({
            imap: server.client(), store, archive, logger: {error: () => {}}, pollSeconds: 300,
        });
        const old = server.add(syntheticMail(1, {date: new Date('2020-01-01Z')}));
        const sync = createSync();
        assert.equal((await sync.syncNow()).baseline, true);
        assert.equal(await store.isMessageComplete(`gmail:${old.id}`), false);
        checks.push('verified loopback TLS IMAP records a baseline without importing history');
        server.add(syntheticMail(2, {sender: 'sender-one@example.invalid'}));
        server.add(syntheticMail(3, {sender: 'sender-two@example.invalid'}));
        server.add(syntheticMail(4, {sender: 'sender-one@example.invalid'}));
        assert.equal((await sync.syncNow()).published, 3);
        checks.push('real IMAP nested MIME reaches PostgreSQL archive through the production synchronizer');
        const restarted = createSync();
        assert.equal((await restarted.syncNow()).published, 0);
        server.add(syntheticMail(5, {id: '9000000000000000002', sender: 'sender-one@example.invalid'}));
        assert.equal((await restarted.syncNow()).published, 0);
        assert.equal(Number((await store.getState()).publishedCount), 3);
        checks.push('durable message ID deduplication after synchronizer restart and a changed IMAP UID');
        server.assertReadOnly();
        checks.push('wire transcript uses EXAMINE and BODY.PEEK; no attachments or write commands');
    } finally {
        await server.close();
    }
    const first = await db.getObject('heuesta-mailbox:message:gmail:9000000000000000002');
    const second = await db.getObject('heuesta-mailbox:message:gmail:9000000000000000003');
    const third = await db.getObject('heuesta-mailbox:message:gmail:9000000000000000004');
    assert.equal(Number(first.tid), Number(third.tid));
    assert.notEqual(Number(first.tid), Number(second.tid));
    fs.writeFileSync(target, JSON.stringify({
        discussionCid: discussion.cid, mailboxCid: archive.categoryCid,
        mailboxTid: first.tid, mailboxPid: JSON.parse(first.pids)[0], previewToken: first.previewToken,
        checks: [...checks, 'real archive keeps senders in separate topics', 'same sender appends a reply'],
    }));
};
