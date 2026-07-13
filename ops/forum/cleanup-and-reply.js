'use strict';
/* 内测演习清理 + 反馈楼回帖：删除模拟测试账号，并在反馈楼公告修复结果 */
const APP = '/usr/src/app';
const nconf = require(APP + '/node_modules/nconf');

nconf.file({ file: APP + '/config.json' });
nconf.defaults({
    base_dir: APP,
    views_dir: APP + '/build/public/templates',
    upload_path: 'public/uploads',
});

(async () => {
    const db = require(APP + '/src/database');
    await db.init();
    const meta = require(APP + '/src/meta');
    await meta.configs.init();
    const User = require(APP + '/src/user');
    const Topics = require(APP + '/src/topics');

    // 删除模拟新用户（remote id 99901）
    const uid = await db.sortedSetScore('heuesta:uid', 99901);
    if (uid) {
        await User.delete(1, parseInt(uid, 10));
        await db.sortedSetRemove('heuesta:uid', 99901);
        console.log('test user deleted uid=' + uid);
    } else {
        console.log('no test user');
    }

    // 反馈楼回帖告知修复
    const FIX_NOTE = '✅ **已修复**：新账号首次进入论坛时出现的「补充信息」页面（还没填完就被跳回主站）已经取消——邮箱和资料统一由主站管理，论坛不再弹这个页面。感谢反馈！';
    const tids = await db.getSortedSetRange('topics:tid', 0, -1);
    let feedbackTid = null;
    for (const tid of tids) {
        const title = await Topics.getTopicField(tid, 'title');
        if (title && title.includes('内测问题反馈')) { feedbackTid = tid; break; }
    }
    if (feedbackTid) {
        const posts = await Topics.getTopicPosts({ tid: feedbackTid }, 'tid:' + feedbackTid + ':posts', 0, -1, 1, true);
        const already = (posts || []).some(p => p && p.content && p.content.includes('已修复'));
        if (!already) {
            await Topics.reply({ uid: 1, tid: feedbackTid, content: FIX_NOTE });
            console.log('reply posted to tid=' + feedbackTid);
        } else {
            console.log('reply already exists');
        }
    } else {
        console.log('feedback topic not found');
    }
    process.exit(0);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
