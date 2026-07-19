'use strict';
/* 内部事务版块：建在「站务中心」下，仅正式会员/干事/管理员可见可发（幂等）
   docker exec -w /usr/src/app heuesta-forum-forum-1 node /opt/config/internal-board.js
*/
const APP = '/usr/src/app';
const nconf = require(APP + '/node_modules/nconf');

nconf.file({ file: APP + '/config.json' });
nconf.defaults({
    base_dir: APP,
    views_dir: APP + '/build/public/templates',
    upload_path: 'public/uploads',
});

const ALLOWED = ['正式会员', '干事', '管理员'];
// 面向普通用户/游客需要撤销的读权限
const READ_PRIVS = ['groups:find', 'groups:read', 'groups:topics:read', 'groups:topics:create', 'groups:topics:reply'];
const PUBLIC_GROUPS = ['guests', 'registered-users', 'spiders', '报名会员', '预备会员'];

(async () => {
    const db = require(APP + '/src/database');
    await db.init();
    const meta = require(APP + '/src/meta');
    await meta.configs.init();
    const Categories = require(APP + '/src/categories');
    const privileges = require(APP + '/src/privileges');

    // 找站务中心 cid
    const cids = await Categories.getAllCidsFromSet('categories:cid');
    const cats = await Categories.getCategoriesData(cids);
    const byName = {};
    for (const c of cats) { if (c) { byName[c.name] = c; } }

    let board = byName['内部事务'];
    if (!board) {
        const parent = byName['站务中心'];
        board = await Categories.create({
            name: '内部事务',
            description: '正式会员及以上可见：内部讨论、干事事务',
            icon: 'fa-lock',
            bgColor: '#334155',
            color: '#ffffff',
            parentCid: parent ? parent.cid : 0,
        });
        console.log('[internal] 创建版块 内部事务 cid=' + board.cid);
    } else {
        console.log('[internal] 版块已存在 cid=' + board.cid);
    }
    const cid = board.cid;

    // 撤销普通/游客/低等级组的读权限
    for (const group of PUBLIC_GROUPS) {
        try { await privileges.categories.rescind(READ_PRIVS, cid, group); } catch (e) { /* 组可能不存在 */ }
    }
    // 授予允许组读+发权限
    for (const group of ALLOWED) {
        try {
            await privileges.categories.give(
                ['groups:find', 'groups:read', 'groups:topics:read', 'groups:topics:create', 'groups:topics:reply', 'groups:posts:upvote', 'groups:posts:downvote'],
                cid, group,
            );
        } catch (e) { console.warn('give 失败 ' + group, e.message); }
    }

    console.log('[internal] 权限配置完成：仅 ' + ALLOWED.join('/') + ' 可见');
    process.exit(0);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
