'use strict';

// Copied into the disposable NodeBB checkout by prepare_forum_ci.py.
const assert = require('node:assert/strict');
const nconf = require('nconf');
assert.equal(process.env.HEUESTA_FORUM_AUDIT, '1');
assert.ok(!process.env.GMAIL_APP_PASSWORD && !process.env.GMAIL_OAUTH_CLIENT_SECRET);
nconf.file({file: './config.json'});
assert.equal(nconf.get('url'), 'http://127.0.0.1:4567');
assert.equal(nconf.get('postgres:host'), '127.0.0.1');
assert.equal(nconf.get('postgres:database'), 'heuesta_forum_ci');
nconf.defaults({base_dir: __dirname, views_dir: __dirname + '/build/public/templates', upload_path: 'public/uploads'});
(async () => {
    const db = require('./src/database');
    await db.init();
    const meta = require('./src/meta');
    const current = await meta.settings.get('session-sharing');
    // Retain the production behaviour/group policy; only redirect/cookie origins differ.
    await meta.settings.set('session-sharing', {...current,
        cookieDomain: '127.0.0.1',
        loginOverride: 'http://127.0.0.1:8814/accounts/login/',
        registerOverride: 'http://127.0.0.1:8814/accounts/register/',
    });
    for (const [key, value] of Object.entries({
        title: 'HEU ESTA 隔离演示论坛', defaultLang: 'zh-CN',
        allowGuestSearching: 1, emailConfirmRequired: 0, disableEmailSubscriptions: 1,
        postDelay: 0, newbiePostDelay: 0, newbiePostDelayThreshold: 0,
        minimumPostLength: 1, minimumTitleLength: 2, 'min:rep:post-links': 0,
        'activitypub:enabled': 0, 'email:notifications': 0,
    })) await meta.configs.set(key, value);
    process.exit(0);
})().catch(error => { console.error(error.message); process.exit(1); });
