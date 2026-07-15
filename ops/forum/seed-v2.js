'use strict';
/* 内容填充 v2：新版块导航/规则/模板置顶帖 + 旧帖归位（幂等）
   docker exec -w /usr/src/app heuesta-forum-forum-1 node /opt/config/seed-v2.js
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
    for (const c of cats) { if (c) { byName[c.name] = c.cid; } }

    async function findTopicByTitleAnywhere(keyword) {
        const tids = await db.getSortedSetRange('topics:tid', 0, -1);
        for (const tid of tids) {
            const title = await Topics.getTopicField(tid, 'title');
            if (title && title.includes(keyword)) { return parseInt(tid, 10); }
        }
        return null;
    }

    async function moveTopic(keyword, catName) {
        const tid = await findTopicByTitleAnywhere(keyword);
        const cid = byName[catName];
        if (!tid || !cid) { return; }
        const cur = await Topics.getTopicField(tid, 'cid');
        if (parseInt(cur, 10) !== cid) {
            await Topics.tools.move(tid, { cid, uid: 1 });
            console.log('[seed] 帖子迁移: 「' + keyword + '」 -> ' + catName);
        }
    }

    async function ensureTopic(catName, title, content) {
        const cid = byName[catName];
        if (!cid) { console.log('[seed] 缺版块: ' + catName); return; }
        const existTid = await findTopicByTitleAnywhere(title.slice(0, 12));
        if (existTid) { return; }
        const result = await Topics.post({ uid: 1, cid, title, content });
        await Topics.tools.pin(result.topicData.tid, 1);
        console.log('[seed] 发帖: [' + catName + '] ' + title);
    }

    /* ---------- 旧帖归位 ---------- */
    await moveTopic('新人报到楼', '新人报到');
    await moveTopic('内测问题反馈', '意见反馈');

    /* ---------- 新版块置顶帖 ---------- */
    await ensureTopic('组队招募', '📋 组队招募发帖模板（复制即用）',
`想找队友？按这个模板发帖，匹配效率翻倍：

> **【招募】队伍目标**：如"2027 电赛控制题冲国奖" / "做一个桌面时钟练手"
> **已有成员**：1 名硬件（本人，会画板子）
> **缺少角色**：软件 1 名（会 STM32 优先）、算法 1 名
> **时间投入**：每周约 X 小时，寒假是否集中开发
> **联系方式**：站内私信 / QQ

温馨提示：
- 组队前先看对方的「作品展示」帖，比简历真实一百倍
- 新生队伍缺经验？可以在帖子里 @ 干事求一位学长学姐当顾问`);

    await ensureTopic('作品展示', '🎨 作品展示发帖指南：让你的作品被看见',
`欢迎晒作品！不管是第一块洞洞板还是电赛获奖作品，都值得一帖。

**推荐结构**：

1. **成品图/视频**放最前面（一图胜千言，视频可传 B 站贴链接）
2. **功能简介**：它是干什么的，哪里好玩
3. **技术要点**：原理图截图、关键电路/代码片段、翻过的车
4. **复刻信息**（可选）：BOM、开源仓库链接

优秀作品会被加精置顶，并有机会登上协会 B 站和官网首页轮播。冲！`);

    await ensureTopic('器材漂流', '♻️ 器材漂流规则：闲置流转三原则',
`实验室的老朋友值得第二春。发帖前请阅读三原则：

1. **如实描述**：成色、功能是否正常、缺什么配件，照片实拍
2. **格式清晰**：标题写明【转让】/【求购】/【交换】+ 物品名 + 期望价格
3. **一手交钱一手交货**：建议实验室当面交易；出校交易风险自负

> 示例标题：【转让】DS100 示波器探头 x2，9 成新，30 元/根

禁止：倒卖协会公共器材、代购刷单、任何形式的广告。违者删帖 + 警告。`);

    await ensureTopic('模拟电路', '📚 模拟电路学习导航（教材 + 视频一站式）',
`本版块配套资源索引，边学边讨论：

**系统教材**（协会自编，21 章 + 6 附录）
- [电子学学习中心](https://heuesta.cn/learn/electronics/)：从电路理论基础到数据转换器
- 重点章节：第 2-4 章运放、第 8-12 章晶体管与放大器、第 17 章电源管理

**培训视频**（B 站）
- [点击就送的运放知识](https://www.bilibili.com/video/BV1zDsRzPEAm)（第二次硬件培训）
- [硬件第三次培训：滤波器](https://www.bilibili.com/video/BV1pDyEBTEpJ)
- 更多见 [协会 B 站主页](https://space.bilibili.com/70859324)

**提问须知**：贴上电路图 + 实测波形截图，回答速度 x10。`);

    await ensureTopic('STM32 与单片机', '📚 STM32 入门导航：培训视频清单',
`按顺序刷完这套培训，你就能独立做小项目了：

1. [STM32 GPIO](https://www.bilibili.com/video/BV16K4vzJEyh)
2. [定时器 / 中断](https://www.bilibili.com/video/BV12myaB1Eny)
3. [时钟 / 屏幕 / UART / debug](https://www.bilibili.com/video/BV1Qo1DBLERG)
4. [通信协议](https://www.bilibili.com/video/BV1VSCeBFEiX)
5. [ADC](https://www.bilibili.com/video/BV1pLUsBFEGn)

**环境搭建**：见官网[新生指南](https://heuesta.cn/recruit/)的"嵌入式开发环境"一节（KEIL / CubeMX / CLion 全都有）。

卡住了就在本版发帖，贴出报错信息和工程配置截图。`);

    await ensureTopic('电赛专区', '🏆 电赛备赛索引：从萌新到国奖的路线图',
`**赛程认知**：校赛选拔 → 暑期集训 → 省赛/国赛（四天三夜）

**备赛路线**
- 大一：打好模电/单片机基础，完成协会全部培训任务
- 大一暑假：进入集训队，分方向强化（控制/仪器/电源/信号）
- 真题练习：历年题目 + 测评标准见[资料站](https://heuesta.cn/resources/)竞赛分类

**协会资源**
- [简易数字存储示波器题目解析](https://www.bilibili.com/video/BV1PjSdB9Eh9)（2025 选拔题讲解）
- 实验室器件库对集训队全开放

有备赛问题直接发帖，学长学姐都在。`);

    await ensureTopic('学习生活', '☕ 本版导读：技术之外，也聊聊生活',
`这里聊什么都行（除了违规内容）：

- 课程避雷与选课心得
- 保研 / 考研 / 就业的经验与纠结
- 实验室趣事、社团活动照片
- 好书好剧好游戏安利

放轻松，科协不只有烙铁和代码。`);

    console.log('[seed] 内容填充 v2 完成');
    process.exit(0);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
