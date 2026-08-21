'use strict';
/* 正式招新发布收尾：旧内测公告与反馈楼取消置顶、锁定并标记归档（幂等）。 */
const APP = '/usr/src/app';
const nconf = require(APP + '/node_modules/nconf');

nconf.file({ file: APP + '/config.json' });
nconf.defaults({
    base_dir: APP,
    views_dir: APP + '/build/public/templates',
    upload_path: 'public/uploads',
});

const TARGET_TITLES = [
    '科协官网 & 论坛内测启动公告',
    '内测问题反馈 & 建议收集楼',
];

(async () => {
    const db = require(APP + '/src/database');
    await db.init();
    const meta = require(APP + '/src/meta');
    await meta.configs.init();
    const Categories = require(APP + '/src/categories');
    const Topics = require(APP + '/src/topics');

    const cids = await Categories.getAllCidsFromSet('categories:cid');
    for (const cid of cids) {
        const tids = await db.getSortedSetRange(`cid:${cid}:tids`, 0, -1);
        for (const tid of tids) {
            const data = await Topics.getTopicFields(tid, ['title', 'pinned', 'locked']);
            const title = String(data.title || '');
            if (!TARGET_TITLES.some(fragment => title.includes(fragment))) {
                continue;
            }
            if (Number(data.pinned)) {
                await Topics.tools.unpin(tid, 1);
            }
            if (!Number(data.locked)) {
                await Topics.tools.lock(tid, 1);
            }
            if (!title.startsWith('[已归档]')) {
                await Topics.setTopicFields(tid, { title: `[已归档] ${title}` });
            }
            console.log(`[formal-release] 已归档 tid=${tid}: ${title}`);
        }
    }
    console.log('[formal-release] 完成');
    process.exit(0);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
