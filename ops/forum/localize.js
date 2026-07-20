'use strict';
/* NodeBB 本土化与账号互通配置脚本（幂等，可重复执行）
   用法（服务器上）：
   docker exec -w /usr/src/app -e NODEBB_JWT_SECRET=xxx heuesta-forum-forum-1 node /opt/config/localize.js
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
    const Categories = require(APP + '/src/categories');

    /* ---------- 1. 中文本土化 ---------- */
    await meta.configs.set('defaultLang', 'zh-CN');
    await meta.configs.set('title', 'HEU ESTA 论坛');
    await meta.configs.set('browserTitle', 'HEU ESTA 论坛');
    await meta.configs.set('description', '哈尔滨工程大学电子科技协会会员论坛：提问、晒作品、找队友');
    await meta.configs.set('showSiteTitle', 1);
    console.log('[localize] 站点信息与默认语言已设为中文');

    /* ---------- 2. session-sharing 账号互通 ---------- */
    if (!process.env.NODEBB_JWT_SECRET) {
        throw new Error('缺少 NODEBB_JWT_SECRET 环境变量');
    }
    await meta.settings.set('session-sharing', {
        name: 'heuesta',
        cookieName: 'heuesta_sso',
        cookieDomain: '.heuesta.cn',
        secret: process.env.NODEBB_JWT_SECRET,
        behaviour: 'trust',
        adminRevalidate: 'off',
        noRegistration: 'off',
        updateProfile: 'on',
        trustPayloadEmail: 'on',
        'payload:id': 'id',
        'payload:username': 'username',
        'payload:fullname': 'fullname',
        'payload:email': 'email',
        loginOverride: 'https://heuesta.cn/accounts/login/',
        registerOverride: 'https://heuesta.cn/accounts/register/',
    });
    console.log('[localize] session-sharing 配置完成');

    /* ---------- 3. 中文版块 ---------- */
    const existing = await Categories.getAllCidsFromSet('categories:cid');
    const current = await Categories.getCategoriesData(existing);
    const names = new Set(current.filter(Boolean).map(c => c.name));

    // 默认英文版块：1 改名保留，2/3/4 清除
    if (names.has('Announcements')) {
        await Categories.update({ 1: { name: '公告板', description: '协会通知与公告' } });
        console.log('[localize] Announcements -> 公告板');
    }
    for (const c of current) {
        if (c && ['General Discussion', 'Blogs', 'Comments & Feedback'].includes(c.name)) {
            await Categories.purge(c.cid, 1);
            console.log('[localize] 清除默认版块: ' + c.name);
        }
    }

    const wanted = [
        ['新生答疑', '萌新提问专区：不懂就问，没有蠢问题', 'fa-question-circle', '#0da9cd'],
        ['硬件电路', '模拟电路 · PCB 设计 · 电源 · 焊接工艺', 'fa-microchip', '#c98a3d'],
        ['嵌入式与软件', 'STM32 / MSPM0 / C 语言 / 上位机 / 算法', 'fa-code', '#10b981'],
        ['竞赛专区', '电赛与各类竞赛：组队、真题、经验分享', 'fa-trophy', '#e05450'],
        ['畅所欲言', '社团生活 · 作品展示 · 灌水闲聊', 'fa-comments', '#8b5cf6'],
    ];
    for (const [name, description, icon, bgColor] of wanted) {
        if (!names.has(name)) {
            await Categories.create({ name, description, icon, bgColor, color: '#ffffff' });
            console.log('[localize] 创建版块: ' + name);
        }
    }

    console.log('[localize] 全部完成');
    process.exit(0);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
