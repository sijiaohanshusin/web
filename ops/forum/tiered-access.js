'use strict';

// Native category ACLs are the visibility boundary, including direct topic/API access.
// Dry-run by default. Save the previous ACLs before applying; never touch the mailbox.
const fs = require('node:fs');
const LEVELS = ['招新成员', '预备会员', '科协会员', '站务管理', '系统管理员'];
const PUBLIC_BOARDS = [
  '站务中心', '公告板', '意见反馈', '新人专区', '新人报到', '新生答疑',
  '硬件天地', '模拟电路', 'PCB 与焊接', '电源与功率', '仪器仪表',
  '嵌入式与软件', 'STM32 与单片机', 'FPGA 与数字电路', '上位机与算法',
  '竞赛与项目', '电赛专区', '组队招募', '作品展示', '生活广场', '畅所欲言', '器材漂流', '学习生活',
];
const TIERS = [
  {level: 2, name: '研习交流（预备会员及以上）'},
  {level: 3, name: '内部事务（科协会员及以上）', legacyName: '内部事务'},
  {level: 4, name: '站务协作（站务及以上）'},
];
const READ = ['find', 'read', 'topics:read'];
const WRITE = ['topics:create', 'topics:reply', 'topics:tag', 'posts:edit', 'posts:history',
  'posts:delete', 'topics:delete', 'posts:upvote', 'posts:downvote'];

async function snapshotAcl({groups, privileges}, cid) {
  const acl = {};
  for (const key of await privileges.categories.getPrivilegeList()) {
    acl[key] = await groups.getMembers(`cid:${cid}:privileges:${key}`, 0, -1);
  }
  return acl;
}

async function applyPolicy(api, {apply = false, snapshot} = {}) {
  const {categories, privileges} = api;
  const cats = (await categories.getCategoriesData(await categories.getAllCidsFromSet('categories:cid'))).filter(Boolean);
  function find(name) {
    const matches = cats.filter(cat => cat.name === name);
    if (matches.length > 1) throw Error('Ambiguous category: ' + name);
    return matches[0];
  }
  const parent = find('站务中心');
  if (!parent) throw Error('Run categories-v2.js first');
  const targets = TIERS.map(tier => ({...tier, existing: find(tier.name) || (tier.legacyName && find(tier.legacyName))}));
  const publicCats = PUBLIC_BOARDS.map(find).filter(Boolean);
  // Never make an accidentally restricted category public just because its name matches.
  for (const cat of publicCats) {
    if (!await privileges.categories.can('read', cat.cid, 0)) throw Error('Expected public category: ' + cat.name);
  }
  const before = [];
  for (const cat of [...publicCats, ...targets.map(t => t.existing).filter(Boolean)]) {
    before.push({category: cat, acl: await snapshotAcl(api, cat.cid)});
  }
  const plan = targets.map(t => ({name: t.name, cid: t.existing?.cid || null, allowed: LEVELS.slice(t.level - 1)}));
  if (!apply) return {plan, publicBoards: publicCats.length};
  if (!snapshot) throw Error('--snapshot path required');
  fs.writeFileSync(snapshot, JSON.stringify({before, plan}, null, 2), {flag: 'wx', mode: 0o600});

  // New users get the same normal discussion actions; existing moderation is retained.
  for (const cat of publicCats) {
    await privileges.categories.give([...READ, ...WRITE].map(p => 'groups:' + p), cat.cid, LEVELS);
  }
  const result = [];
  for (const tier of targets) {
    let cat = tier.existing;
    const description = `仅${LEVELS[tier.level - 1]}及以上可见、发帖和回复。发帖选择本板块即限定可见范围；论坛管理员仍可管理。`;
    if (!cat) cat = await categories.create({name: tier.name, description, parentCid: parent.cid,
      disabled: 1, icon: 'fa-lock', bgColor: '#164e63', color: '#ffffff'});
    // Fail closed while replacing defaults, including fediverse/custom groups and direct-user grants.
    await categories.update({[cat.cid]: {disabled: 1}});
    const acl = await snapshotAcl(api, cat.cid);
    for (const [key, members] of Object.entries(acl)) {
      if (members.length) await privileges.categories.rescind([key], cat.cid, members);
    }
    const allowed = LEVELS.slice(tier.level - 1);
    await privileges.categories.give([...READ, ...WRITE].map(p => 'groups:' + p), cat.cid, allowed);
    await categories.update({[cat.cid]: {name: tier.name, description, disabled: 0}});
    result.push({cid: cat.cid, name: tier.name, level: tier.level});
  }
  return {tiers: result, publicBoards: publicCats.length};
}

async function main() {
  const APP = process.env.NODEBB_APP_DIR || '/usr/src/app';
  const nconf = require(APP + '/node_modules/nconf');
  nconf.file({file: APP + '/config.json'});
  nconf.defaults({base_dir: APP, views_dir: APP + '/build/public/templates', upload_path: 'public/uploads'});
  const db = require(APP + '/src/database'); await db.init();
  await require(APP + '/src/meta').configs.init();
  const i = process.argv.indexOf('--snapshot');
  const result = await applyPolicy({db, categories: require(APP + '/src/categories'),
    groups: require(APP + '/src/groups'), privileges: require(APP + '/src/privileges')},
  {apply: process.argv.includes('--apply'), snapshot: i < 0 ? null : process.argv[i + 1]});
  console.log(JSON.stringify(result, null, 2));
}
module.exports = {applyPolicy, TIERS, LEVELS, main};
if (require.main === module) main().then(() => process.exit(0)).catch(error => {console.error(error); process.exit(1);});
