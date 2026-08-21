'use strict';
/* 论坛用户组 v3：正式等级组 + 固定职位组 + 受控双向同步（幂等）
   - 建齐正式等级组与五类固定职位组
   - 旧等级组隐藏保留一个迁移周期，并在用户重新登录时自动摘除
   - session-sharing 开启 syncGroups 白名单双向同步：晋升时旧等级徽章自动摘除
   docker exec -w /usr/src/app heuesta-forum-forum-1 node /opt/config/groups-v2.js
*/
const APP = '/usr/src/app';
const nconf = require(APP + '/node_modules/nconf');

nconf.file({ file: APP + '/config.json' });
nconf.defaults({
    base_dir: APP,
    views_dir: APP + '/build/public/templates',
    upload_path: 'public/uploads',
});

// 与主站 accounts/roles.py、accounts/models.Position 对齐
const LEVEL_GROUPS = [
    { name: '招新成员', color: '#41d8e8' },
    { name: '预备会员', color: '#0da9cd' },
    { name: '科协会员', color: '#2568c8' },
    { name: '站务管理', color: '#c98a3d' },
    { name: '系统管理员', color: '#e05450' },
];
const POSITION_GROUPS = [
    { name: '主席', color: '#b8860b' },
    { name: '硬件主席', color: '#c98a3d' },
    { name: '软件主席', color: '#0da9cd' },
    { name: '硬件副主席', color: '#d97706' },
    { name: '软件副主席', color: '#0284c7' },
];
const LEGACY_GROUPS = ['报名会员', '正式会员', '干事', '管理员'];

(async () => {
    const db = require(APP + '/src/database');
    await db.init();
    const meta = require(APP + '/src/meta');
    await meta.configs.init();
    const Groups = require(APP + '/src/groups');

    const all = [...LEVEL_GROUPS, ...POSITION_GROUPS];
    for (const g of all) {
        const exists = await Groups.exists(g.name);
        if (!exists) {
            await Groups.create({
                name: g.name,
                userTitle: g.name,
                userTitleEnabled: 1,
                labelColor: g.color,
                textColor: '#ffffff',
                hidden: 0,
                private: 1,
                disableJoinRequests: 1,
            });
            console.log('[groups-v2] 创建组: ' + g.name);
        } else {
            await Groups.update(g.name, {
                userTitleEnabled: 1,
                labelColor: g.color,
                textColor: '#ffffff',
            });
            console.log('[groups-v2] 更新组: ' + g.name);
        }
    }

    for (const name of LEGACY_GROUPS) {
        if (await Groups.exists(name)) {
            await Groups.update(name, {
                hidden: 1,
                userTitleEnabled: 0,
                disableJoinRequests: 1,
            });
            console.log('[groups-v2] 隐藏旧组: ' + name);
        }
    }

    // session-sharing 受控双向同步：只在白名单内增删，绝不动 administrators 等系统组
    const syncList = [...all.map(g => g.name), ...LEGACY_GROUPS].join(',');
    const current = await meta.settings.get('session-sharing');
    await meta.settings.set('session-sharing', {
        ...current,
        'payload:groups': 'groups',
        syncGroup: 'on',
        syncGroupList: 'on',
        syncGroups: syncList,
        syncGroupJoin: 'on',
        syncGroupLeave: 'on',   // 晋升后摘除旧等级徽章
    });
    console.log('[groups-v2] session-sharing 白名单双向同步已开启: ' + syncList);
    console.log('[groups-v2] 完成');
    process.exit(0);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
