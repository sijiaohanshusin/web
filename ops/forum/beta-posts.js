'use strict';
/* 内测启动：发布公告帖 + 问题反馈收集楼（幂等）
   用法：docker exec -w /usr/src/app heuesta-forum-forum-1 node /opt/config/beta-posts.js
*/
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
    const Categories = require(APP + '/src/categories');
    const Topics = require(APP + '/src/topics');

    const cids = await Categories.getAllCidsFromSet('categories:cid');
    const cats = await Categories.getCategoriesData(cids);
    const byName = {};
    for (const c of cats) { if (c) byName[c.name] = c.cid; }

    async function findTopicByTitle(cid, title) {
        const tids = await db.getSortedSetRange('cid:' + cid + ':tids', 0, -1);
        for (const tid of tids) {
            const t = await Topics.getTopicField(tid, 'title');
            if (t === title) { return tid; }
        }
        return null;
    }

    async function ensureTopic(catName, title, content) {
        const cid = byName[catName];
        if (!cid) { throw new Error('版块不存在: ' + catName); }
        let tid = await findTopicByTitle(cid, title);
        if (tid) { return tid; }
        const result = await Topics.post({ uid: 1, cid, title, content });
        tid = result.topicData.tid;
        await Topics.tools.pin(tid, 1);
        console.log('[beta] 发帖并置顶: ' + title + ' (tid=' + tid + ')');
        return tid;
    }

    /* ---------- 1. 反馈收集楼（畅所欲言，人人可回） ---------- */
    const feedbackTid = await ensureTopic('畅所欲言', '🛠️ 内测问题反馈 & 建议收集楼（盖楼即可）',
`欢迎来到反馈楼！**网站和论坛哪里不好用、不好看、想要什么新功能，直接回帖盖楼。**

## 反馈格式（复制着填，遇到 Bug 尽量截图）

> **类型**：Bug / 建议 / 吐槽
> **哪个页面**：比如"官网首页"、"资料站"、"论坛发帖页"
> **设备**：电脑 / 手机（什么浏览器）
> **描述**：做了什么操作，预期是什么，实际发生了什么
> **截图**：有就贴（论坛支持直接粘贴图片）

## 几个提示

- 提 Bug 之前可以先试试**强制刷新**（电脑 Ctrl+F5），排除缓存问题
- 建议类的想法不用怕"太小"或"太异想天开"，都想听
- 被采纳的反馈会在本楼回复标记 ✅

感谢每一位参与内测的同学！`);

    /* ---------- 2. 内测启动公告（公告板） ---------- */
    await ensureTopic('公告板', '📢 科协官网 & 论坛内测启动公告',
`各位同学：

科协新版官网与会员论坛即日起进入**内部测试阶段**，欢迎大家把每个角落都点一遍、用力找茬！

## 测试范围

| 站点 | 地址 | 测什么 |
| --- | --- | --- |
| 官网 | https://heuesta.cn | 首页动效、新生指南、学习中心、资料站、注册登录 |
| 论坛 | https://bbs.heuesta.cn | 发帖回帖、表情、图片上传、通知 |

## 怎么参与

1. 在官网右上角**注册**（填学号、姓名、学院、年级）
2. 注册后在群里说一声，管理员会尽快**通过审核**
3. 审核通过后登录官网 —— **论坛会自动登录，无需再注册**
4. 开始探索，发现问题去反馈楼盖楼：[🛠️ 内测问题反馈 & 建议收集楼](/topic/${feedbackTid})

## 注意事项

- 修改密码、完善资料都在官网[个人中心](https://heuesta.cn/accounts/profile/)进行
- 内测期间数据可能会调整清理，重要内容请自己留底
- 论坛已开启每日自动备份，但也别故意搞破坏啦 😉

—— HEU ESTA 技术组`);

    console.log('[beta] 完成');
    process.exit(0);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
