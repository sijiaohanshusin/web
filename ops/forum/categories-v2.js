'use strict';
/* 版块体系 v2：6 大分区 + 14 子版块（幂等，带帖迁移不丢数据）
   docker exec -w /usr/src/app heuesta-forum-forum-1 node /opt/config/categories-v2.js
*/
const APP = '/usr/src/app';
const nconf = require(APP + '/node_modules/nconf');

nconf.file({ file: APP + '/config.json' });
nconf.defaults({
    base_dir: APP,
    views_dir: APP + '/build/public/templates',
    upload_path: 'public/uploads',
});

/* 目标结构：分区 -> 子版块。exist 表示由现有版块改名/迁移而来 */
const STRUCTURE = [
    {
        section: { name: '站务中心', icon: 'fa-landmark', bgColor: '#475569', description: '公告、版务与意见反馈' },
        children: [
            { exist: '公告板', name: '公告板', icon: 'fa-bullhorn', bgColor: '#ef4444', description: '协会与论坛官方公告' },
            { name: '意见反馈', icon: 'fa-comment-medical', bgColor: '#f97316', description: '网站与论坛的 Bug 反馈、功能建议' },
        ],
    },
    {
        section: { name: '新人专区', icon: 'fa-seedling', bgColor: '#22c55e', description: '从这里开始你的科协之旅' },
        children: [
            { name: '新人报到', icon: 'fa-hand-wave', bgColor: '#10b981', description: '新同学报到刷存在感，混个脸熟' },
            { exist: '新生答疑', name: '新生答疑', icon: 'fa-question-circle', bgColor: '#0ea5e9', description: '萌新提问专区：不懂就问，没有蠢问题' },
        ],
    },
    {
        section: { name: '硬件天地', icon: 'fa-microchip', bgColor: '#f59e0b', description: '从元件到整机的硬件世界' },
        children: [
            { exist: '硬件电路', name: '模拟电路', icon: 'fa-wave-square', bgColor: '#f59e0b', description: '运放、滤波器、信号链设计与调试' },
            { name: 'PCB 与焊接', icon: 'fa-bezier-curve', bgColor: '#d97706', description: '原理图、Layout、打样与焊接工艺' },
            { name: '电源与功率', icon: 'fa-bolt', bgColor: '#eab308', description: '线性电源、开关电源、功率电子' },
            { name: '仪器仪表', icon: 'fa-gauge-high', bgColor: '#a16207', description: '示波器、信号源、万用表使用与选购' },
        ],
    },
    {
        // 旧版块「嵌入式与软件」(无帖子) 直接升级为本分区，子版块全部新建
        section: { name: '嵌入式与软件', icon: 'fa-code', bgColor: '#10b981', description: '让硬件跑起来的代码' },
        children: [
            { name: 'STM32 与单片机', icon: 'fa-memory', bgColor: '#10b981', description: 'STM32 / MSPM0 / 各类 MCU 开发' },
            { name: 'FPGA 与数字电路', icon: 'fa-diagram-project', bgColor: '#059669', description: 'Verilog、时序逻辑、数字系统设计' },
            { name: '上位机与算法', icon: 'fa-laptop-code', bgColor: '#14b8a6', description: '串口上位机、Python 工具、信号处理算法' },
        ],
    },
    {
        section: { name: '竞赛与项目', icon: 'fa-trophy', bgColor: '#ef4444', description: '以赛促学，以项目会友' },
        children: [
            { exist: '竞赛专区', name: '电赛专区', icon: 'fa-trophy', bgColor: '#ef4444', description: '全国大学生电子设计竞赛：真题、备赛、经验' },
            { name: '组队招募', icon: 'fa-people-group', bgColor: '#f43f5e', description: '找队友、找项目，车队在此发车' },
            { name: '作品展示', icon: 'fa-lightbulb', bgColor: '#e11d48', description: '晒出你的作品：电路、程序、整活皆可' },
        ],
    },
    {
        section: { name: '生活广场', icon: 'fa-mug-hot', bgColor: '#8b5cf6', description: '技术之外的科协生活' },
        children: [
            { exist: '畅所欲言', name: '畅所欲言', icon: 'fa-comments', bgColor: '#8b5cf6', description: '灌水闲聊，无话不谈' },
            { name: '器材漂流', icon: 'fa-arrows-rotate', bgColor: '#7c3aed', description: '闲置器材转让 / 求购 / 交换' },
            { name: '学习生活', icon: 'fa-book-open-reader', bgColor: '#6d28d9', description: '课程、保研考研、校园生活经验' },
        ],
    },
];

(async () => {
    const db = require(APP + '/src/database');
    await db.init();
    const meta = require(APP + '/src/meta');
    await meta.configs.init();
    const Categories = require(APP + '/src/categories');

    async function allByName() {
        const cids = await Categories.getAllCidsFromSet('categories:cid');
        const cats = await Categories.getCategoriesData(cids);
        const map = {};
        for (const c of cats) { if (c && !c.disabled) { map[c.name] = c; } }
        return map;
    }

    let existing = await allByName();
    let sectionOrder = 0;

    for (const group of STRUCTURE) {
        sectionOrder += 1;
        // 1. 分区（父版块）
        let section = existing[group.section.name];
        if (!section) {
            section = await Categories.create({
                name: group.section.name,
                description: group.section.description,
                icon: group.section.icon,
                bgColor: group.section.bgColor,
                color: '#ffffff',
            });
            console.log('[cats] 创建分区: ' + group.section.name);
            existing = await allByName();
            section = existing[group.section.name];
        }
        await Categories.update({
            [section.cid]: {
                order: sectionOrder,
                parentCid: 0,
                description: group.section.description,
                icon: group.section.icon,
                bgColor: group.section.bgColor,
            },
        });

        // 2. 子版块
        let childOrder = 0;
        for (const child of group.children) {
            childOrder += 1;
            let cat = child.exist ? existing[child.exist] || existing[child.name] : existing[child.name];
            if (!cat) {
                cat = await Categories.create({
                    name: child.name,
                    description: child.description,
                    icon: child.icon,
                    bgColor: child.bgColor,
                    color: '#ffffff',
                    parentCid: section.cid,
                });
                console.log('[cats] 创建子版块: ' + group.section.name + ' / ' + child.name);
                existing = await allByName();
            } else {
                await Categories.update({
                    [cat.cid]: {
                        name: child.name,
                        description: child.description,
                        icon: child.icon,
                        bgColor: child.bgColor,
                        parentCid: section.cid,
                        order: childOrder,
                    },
                });
                if (child.exist && child.exist !== child.name) {
                    console.log('[cats] 迁移改名: ' + child.exist + ' -> ' + group.section.name + ' / ' + child.name);
                } else {
                    console.log('[cats] 归位: ' + group.section.name + ' / ' + child.name);
                }
                continue;
            }
            const fresh = existing[child.name];
            await Categories.update({ [fresh.cid]: { order: childOrder } });
        }
    }

    console.log('[cats] 版块体系 v2 完成');
    process.exit(0);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
