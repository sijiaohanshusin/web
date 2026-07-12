'use strict';
/* 论坛"热闹化"配置脚本（幂等）：
   彩色头衔组 + 角色同步、侧边栏小部件、种子帖、品牌外观、友好度设置
   用法：docker exec -w /usr/src/app -e NODEBB_JWT_SECRET=xxx heuesta-forum-forum-1 node /opt/config/lively.js
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
    const Groups = require(APP + '/src/groups');
    const Categories = require(APP + '/src/categories');
    const Topics = require(APP + '/src/topics');
    const User = require(APP + '/src/user');

    /* ---------- 1. 彩色头衔组（MCBBS 风格用户组徽章） ---------- */
    const groupDefs = [
        { name: '管理员', userTitle: '管理组', labelColor: '#ef4444', icon: 'fa-shield-halved' },
        { name: '干事', userTitle: '干事', labelColor: '#f59e0b', icon: 'fa-screwdriver-wrench' },
        { name: '会员', userTitle: '正式会员', labelColor: '#0ea5e9', icon: 'fa-bolt' },
    ];
    for (const def of groupDefs) {
        const exists = await Groups.exists(def.name);
        if (!exists) {
            await Groups.create({
                name: def.name,
                userTitle: def.userTitle,
                userTitleEnabled: 1,
                labelColor: def.labelColor,
                textColor: '#ffffff',
                icon: def.icon,
                hidden: 0,
                private: 1,
                disableJoinRequests: 1,
            });
            console.log('[lively] 创建用户组: ' + def.name);
        }
    }

    /* ---------- 2. session-sharing 角色同步（只加入，不移除，安全） ---------- */
    const current = await meta.settings.get('session-sharing');
    await meta.settings.set('session-sharing', {
        ...current,
        'payload:groups': 'groups',
        syncGroupJoin: 'on',
        syncGroupLeave: 'off',
    });
    console.log('[lively] 角色同步已开启（join-only）');

    /* ---------- 3. 首页侧边栏小部件 ---------- */
    const card = (title) => (
        '<div class="card mb-3"><h6 class="card-header">' + title + '</h6>' +
        '<div class="card-body p-2">{{body}}</div></div>'
    );
    const sidebarWidgets = [
        { widget: 'recenttopics', data: { numTopics: '6', duration: '30', container: card('🔥 最新主题'), title: '' } },
        { widget: 'activeusers', data: { numUsers: '12', container: card('👋 活跃用户'), title: '' } },
        { widget: 'forumstats', data: { container: card('📊 论坛统计'), title: '' } },
    ];
    // harmony 主题的 categories 页侧边栏区域
    for (const location of ['sidebar', 'right']) {
        await db.setObjectField('widgets:categories.tpl', location, JSON.stringify(sidebarWidgets));
    }
    console.log('[lively] 首页小部件已配置');

    /* ---------- 4. 友好度与外观设置 ---------- */
    await meta.configs.setMultiple({
        'downvote:disabled': 1,           // 不要"踩"，社区更友好
        allowSignatures: 1,
        maximumSignatureLength: 255,
        signatures: 1,
        'reputation:disabled': 0,
        allowProfileImageUploads: 1,
        teaserPost: 'last-post',
        showSiteTitle: 1,
        useCustomCSS: 1,
        customCSS: [
            '/* 品牌色微调，与主站呼应 */',
            ':root { --bs-link-color: #0284c7; --bs-link-hover-color: #0ea5e9; }',
            '.pinned-topic-highlight, [component="category/topic"].pinned { background: rgba(14,165,233,.05); }',
        ].join('\n'),
    });
    console.log('[lively] 外观与友好度设置完成');

    /* ---------- 5. 种子帖（置顶开版内容） ---------- */
    const cids = await Categories.getAllCidsFromSet('categories:cid');
    const cats = await Categories.getCategoriesData(cids);
    const byName = {};
    for (const c of cats) { if (c) byName[c.name] = c.cid; }

    async function seedTopic(catName, title, content, pin) {
        const cid = byName[catName];
        if (!cid) { console.log('[lively] 找不到版块: ' + catName); return; }
        const existingTids = await db.getSortedSetRange('cid:' + cid + ':tids', 0, -1);
        const titles = await Promise.all(existingTids.map(tid => Topics.getTopicField(tid, 'title')));
        if (titles.includes(title)) { return; }
        const result = await Topics.post({ uid: 1, cid, title, content });
        if (pin) { await Topics.tools.pin(result.topicData.tid, 1); }
        console.log('[lively] 发帖: [' + catName + '] ' + title);
    }

    await seedTopic('公告板', '🎉 HEU ESTA 论坛开版公告',
`欢迎来到**哈尔滨工程大学电子科技协会论坛**！

这里是科协成员交流技术、分享作品、互帮互助的地方。

## 账号说明

- 论坛与 [协会官网](https://heuesta.cn) 账号互通：**在官网注册并通过审核后，登录官网即自动登录论坛**，无需重复注册
- 修改资料、改密码请前往 [官网个人中心](https://heuesta.cn/accounts/profile/)

## 简明版规

1. 友善交流，尊重每一位提问的萌新——大佬也是从点亮第一颗 LED 开始的
2. 技术贴发对应版块，灌水去「畅所欲言」
3. 禁止广告、刷屏、人身攻击
4. 提问前先看「新生答疑」置顶的提问指南

祝大家玩得开心，卷得快乐！⚡`, true);

    await seedTopic('新生答疑', '📖 提问之前：如何让你的问题更快得到解答',
`欢迎提问！为了让学长学姐能更快帮到你，提问时请做到：

1. **标题写清楚问题本身**，不要只写"求助""急急急"
2. **贴出完整的报错信息 / 现象照片**：一张示波器截图胜过千言万语
3. **说明你已经尝试过什么**：改过哪些参数、查过哪些资料
4. 代码用 Markdown 代码块包起来（三个反引号），别发代码截图
5. 解决后回帖说一下最终方案，帮助后来遇到同样问题的同学

强烈推荐阅读：[《提问的智慧》](https://github.com/ryanhanwu/How-To-Ask-Questions-The-Smart-Way/blob/main/README-zh_CN.md)

配套自学资源：[电子学学习中心](https://heuesta.cn/learn/electronics/)（21 章 + 6 附录）、[资料站](https://heuesta.cn/resources/)`, true);

    await seedTopic('畅所欲言', '👋 新人报到楼：来这里刷个存在感！',
`新同学看过来！回帖格式参考（不强制）：

> **昵称**：
> **年级/学院**：
> **方向**：硬件 / 软件 / 还在纠结
> **一句话介绍**：比如"点亮过 LED""焊接小白""想做机器人"

我先来：我是论坛管理员，负责维护这片自留地。欢迎大家常来玩！🎉`, true);

    console.log('[lively] 全部完成');
    process.exit(0);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
