'use strict';
/* Update only association-owned existing seed posts. Dry run unless --apply.
   Existing public IDs/replies remain; before-images are saved before any edits. */
const fs = require('fs');
const APP = process.env.NODEBB_APP_DIR || '/usr/src/app';
const nconf = require(APP + '/node_modules/nconf');
nconf.file({ file: APP + '/config.json' });
nconf.defaults({ base_dir: APP, views_dir: APP + '/build/public/templates', upload_path: 'public/uploads' });
const changes = [
  ['科协官网 & 论坛内测启动公告', '官网与论坛使用说明', `官网提供协会介绍、学习入口、招新报名和个人中心，论坛用于提问与交流。

- 新同学：在[官网](https://heuesta.cn/accounts/register/)选择新会员注册，完成邮箱验证后可报名，无需人工审核账号。
- 新会员注册并验证邮箱后即可在公共板块发帖、回复，不必等到预备会员。新用户发帖审核用于防垃圾信息，与入会面试无关。
- 论坛按等级开放：预备会员及以上可用“研习交流”，科协会员及以上可用“内部事务”，站务及以上可用“站务协作”。发帖时选择带有等级标注的板块，即限定帖子可见范围；论坛管理员仍可管理。公开交流始终向所有已激活会员开放。
- 会员资料与活动另按页面标明的等级开放；完整操作见[论坛使用说明](https://heuesta.cn/help/member/forum/)。
- 老会员：选择老会员通道，提交原身份信息，由管理组核验。
- 具体培训与面试安排以[招新页](https://heuesta.cn/recruitment/)和正式通知为准。
- 使用问题可先看[帮助中心](https://heuesta.cn/help/)；Bug、改进意见和学习交流中的使用建议，都欢迎在[反馈页](https://heuesta.cn/feedback/)提交。

本文已按现行流程更新。早期回复保留为历史记录。`],
  ['模拟电路学习导航', '📚 模拟电路学习导航：指南与培训回放', `从[硬件基础指南](https://heuesta.cn/recruit/#hardware)认识元件和工具，再结合实际电路学习。

1. [运算放大器培训](https://www.bilibili.com/video/BV1zDsRzPEAm)
2. [滤波器培训](https://www.bilibili.com/video/BV1pDyEBTEpJ)
3. [学习入口与课件](https://heuesta.cn/resources/)

回放公开可看；文件按资料页标明的会员等级开放。原电子学教材正在校对，暂未开放。提问时请附电路图、测量条件与波形。`],
  ['STM32 入门导航', '📚 STM32 入门导航：培训视频清单', `先完成[C语言与开发环境准备](https://heuesta.cn/recruit/#software)，再按需要学习：

1. [GPIO](https://www.bilibili.com/video/BV16K4vzJEyh)
2. [定时器与中断](https://www.bilibili.com/video/BV12myaB1Eny)
3. [时钟、屏幕、UART与调试](https://www.bilibili.com/video/BV1Qo1DBLERG)
4. [通信协议](https://www.bilibili.com/video/BV1VSCeBFEiX)
5. [ADC](https://www.bilibili.com/video/BV1pLUsBFEGn)

这些是既有培训回放，本届任务和日程以正式通知为准。卡住时附报错信息、开发板型号和工程配置。更多见[学习入口](https://heuesta.cn/resources/)。`],
  ['电赛备赛索引', '🏆 电赛备赛索引：从基础到题目实践', `备赛从基础电路、单片机和测试方法开始，再通过组队练习理解完整系统。

- [2025简易数字存储示波器选拔题解析](https://www.bilibili.com/video/BV1PjSdB9Eh9)
- [往届培养路线](https://heuesta.cn/recruit/#training)
- [学习入口与现有资料](https://heuesta.cn/resources/)
- [协会荣誉档案](https://heuesta.cn/honors/)

往届录像和路线不等于本届赛程。选拔、集训和实验室使用安排以正式通知为准。`],
];

(async () => {
  const db = require(APP + '/src/database'); await db.init();
  const meta = require(APP + '/src/meta'); await meta.configs.init();
  const Topics = require(APP + '/src/topics');
  const Posts = require(APP + '/src/posts');
  const tids = await db.getSortedSetRange('topics:tid', 0, -1);
  const pending = [];
  for (const tid of tids) {
    const topic = await Topics.getTopicFields(tid, ['title', 'mainPid', 'uid', 'deleted', 'pinned', 'locked']);
    if (Number(topic.uid) !== 1 || Number(topic.deleted)) continue;
    const change = changes.find(([match, title]) => String(topic.title).includes(match) || topic.title === title);
    if (!change) continue;
    const post = await Posts.getPostFields(topic.mainPid, ['content', 'uid']);
    if (Number(post.uid) !== 1) throw Error('Unexpected main-post owner: ' + tid);
    pending.push({tid, pid:topic.mainPid, before:{...topic, content:post.content}, title:change[1], content:change[2]});
  }
  console.log(JSON.stringify(pending.map(({tid,pid,title})=>({tid,pid,title})),null,2));
  if (!process.argv.includes('--apply')) { console.log('Dry run; no posts changed.'); process.exit(0); }
  const i=process.argv.indexOf('--snapshot');
  if (i<0 || !process.argv[i+1]) throw Error('--snapshot path required');
  fs.writeFileSync(process.argv[i+1],JSON.stringify(pending,null,2),{flag:'wx',mode:0o600});
  for (const row of pending) {
    if (row.before.content !== row.content || row.before.title !== row.title) {
      await Posts.edit({pid:row.pid,uid:1,content:row.content,title:row.title});
      console.log('Updated existing topic ' + row.tid);
    }
  }
  process.exit(0);
})().catch(error => {console.error(error);process.exit(1);});
