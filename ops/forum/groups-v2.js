'use strict';
/* 论坛用户组 v2：等级组 + 职位组 + 受控双向同步（幂等）
   - 建齐等级组（报名/预备/正式会员，各配徽章色）与职位组（主席/硬件主席/软件主席）
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
    { name: '报名会员', color: '#38bdf8' },
    { name: '预备会员', color: '#0ea5e9' },
    { name: '正式会员', color: '#2563eb' },
    { name: '干事', color: '#f59e0b' },
    { name: '管理员', color: '#ef4444' },
];
const POSITION_GROUPS = [
    { name: '主席', color: '#b8860b' },
    { name: '硬件主席', color: '#c98a3d' },
    { name: '软件主席', color: '#c98a3d' },
];

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

    // session-sharing 受控双向同步：只在白名单内增删，绝不动 administrators 等系统组
    const syncList = all.map(g => g.name).join(',');
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
