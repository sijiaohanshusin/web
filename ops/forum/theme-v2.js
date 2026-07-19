'use strict';
/* 论坛科协风格化 v2：全站皮肤（PCB 蓝背景 + 米黄纸张 + 铜色装饰）
   + 帖子页 MCBBS 式增强（楼层号 / 左侧作者信息栏）+ QQ 公告条 + 首页横幅
   幂等：docker exec -w /usr/src/app heuesta-forum-forum-1 node /opt/config/theme-v2.js
*/
const APP = '/usr/src/app';
const nconf = require(APP + '/node_modules/nconf');

nconf.file({ file: APP + '/config.json' });
nconf.defaults({
    base_dir: APP,
    views_dir: APP + '/build/public/templates',
    upload_path: 'public/uploads',
});

/* ============================ 皮肤 CSS ============================ */
const CUSTOM_CSS = `
/* ================= HEU ESTA 论坛皮肤 v2（MCBBS 气质 x 电路语言） =================
   调色只改这里 */
:root {
  --esta-navy: #0b1f3a;        /* PCB 深蓝底 */
  --esta-trace: #1d4e79;       /* 电路走线 */
  --esta-copper: #c98a3d;      /* 铜色装饰 */
  --esta-copper-dark: #a06a25;
  --esta-paper: #fdf6e3;       /* 米黄纸张 */
  --esta-paper-dark: #f4e8c9;  /* 纸张加深 */
  --esta-ink: #3b3226;         /* 纸上墨色 */
  --esta-blue: #0ea5e9;        /* ESTA 蓝 */
  --esta-blue-dark: #0369a1;
  --bs-body-bg: transparent;
  --bs-body-color: var(--esta-ink);
  --bs-link-color: var(--esta-blue-dark);
  --bs-link-hover-color: var(--esta-blue);
}

/* ---------- 背景：深蓝 PCB 电路纹理 ---------- */
body {
  background-color: var(--esta-navy) !important;
  background-image:
    radial-gradient(circle at 18% 12%, rgba(14,165,233,.10), transparent 42%),
    radial-gradient(circle at 85% 88%, rgba(201,138,61,.10), transparent 40%),
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'%3E%3Cg fill='none' stroke='%231d4e79' stroke-width='1.6' opacity='.55'%3E%3Cpath d='M20 0v34l18 18h44'/%3E%3Cpath d='M160 60h-44l-14 14v50'/%3E%3Cpath d='M0 120h30l16-16V70'/%3E%3Cpath d='M120 160v-28l14-14h26'/%3E%3C/g%3E%3Cg fill='%231d4e79' opacity='.8'%3E%3Ccircle cx='20' cy='34' r='3.4'/%3E%3Ccircle cx='82' cy='52' r='3.4'/%3E%3Ccircle cx='102' cy='74' r='3.4'/%3E%3Ccircle cx='46' cy='104' r='3.4'/%3E%3Ccircle cx='134' cy='118' r='3.4'/%3E%3C/g%3E%3Cg fill='%23c98a3d' opacity='.5'%3E%3Ccircle cx='20' cy='34' r='1.4'/%3E%3Ccircle cx='102' cy='74' r='1.4'/%3E%3Ccircle cx='134' cy='118' r='1.4'/%3E%3C/g%3E%3C/svg%3E") !important;
  background-attachment: fixed !important;
}

/* ---------- 主内容：米黄纸张卡片 + 铜色双线框（harmony 的主区是 main 内的 #content） ---------- */
main > #panel #content, main #content {
  background: var(--esta-paper);
  border: 2px solid var(--esta-copper);
  outline: 1px solid rgba(201,138,61,.4);
  outline-offset: 4px;
  border-radius: 10px;
  box-shadow: 0 14px 44px rgba(0,0,0,.45), inset 0 0 0 1px rgba(255,255,255,.5);
  padding: 1rem 1.1rem 1.4rem !important;
  margin-bottom: 30px;
  color: var(--esta-ink);
}

/* 顶部品牌条：纸张化，与内容区呼应 */
.brand-container {
  background: var(--esta-paper);
  border: 2px solid var(--esta-copper);
  border-radius: 10px;
  margin-top: 12px;
  box-shadow: 0 8px 26px rgba(0,0,0,.4);
}
.brand-container .border-bottom { border-color: rgba(201,138,61,.4) !important; }

/* ---------- 左侧栏：深蓝电路风 ---------- */
nav.sidebar {
  background: linear-gradient(180deg, #0d2547, var(--esta-navy)) !important;
  border-right: 2px solid var(--esta-copper) !important;
}
nav.sidebar .nav-link, nav.sidebar .nav-link i, nav.sidebar .sidebar-toggle i { color: #a9c3e8 !important; }
nav.sidebar .nav-link:hover, nav.sidebar .nav-link:hover i { color: #ffd794 !important; }
nav.sidebar .nav-link.active { background: rgba(14,165,233,.2) !important; }

/* ---------- 首页横幅 ---------- */
.esta-banner {
  margin: -1rem -1.1rem 1rem;
  border-bottom: 2px solid var(--esta-copper);
  border-radius: 8px 8px 0 0;
  overflow: hidden;
  line-height: 0;
}
.esta-banner img { width: 100%; height: auto; display: block; }

/* ---------- QQ 公告条 ---------- */
.esta-qq-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  background: var(--esta-paper-dark);
  border: 1px dashed var(--esta-copper);
  border-radius: 8px; padding: 9px 14px; margin-bottom: 4px;
  font-size: 14px; color: var(--esta-ink);
}
.esta-qq-bar .esta-qq-num { font-weight: 800; color: var(--esta-blue-dark); letter-spacing: 1px; }

/* ---------- 版块列表（categories 页）：MCBBS 式分区卡片 ---------- */
[component="categories/category"] {
  background: #fffdf4;
  border: 1px solid rgba(201,138,61,.5) !important;
  border-bottom: 1px solid rgba(201,138,61,.5) !important;
  border-radius: 10px !important;
  margin-bottom: 12px;
  padding: 14px 16px !important;
  transition: transform .15s, box-shadow .15s;
}
[component="categories/category"]:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(59,50,38,.16);
  border-color: var(--esta-copper) !important;
}
/* 分区标题（h2 链接）金属蓝 */
[component="categories/category"] h2 a { color: var(--esta-blue-dark); font-weight: 800; }
[component="categories/category"] h2 a:hover { color: var(--esta-blue); }

/* 子版块列表（ul.category-children）胶囊化 */
ul.category-children { margin-top: 6px; }
ul.category-children > li { margin: 3px 0; }
ul.category-children a {
  color: var(--esta-blue-dark) !important; font-size: 13.5px; font-weight: 600;
  background: rgba(14,165,233,.08);
  border: 1px solid rgba(14,165,233,.22);
  border-radius: 999px; padding: 2px 12px; display: inline-block;
  transition: background .15s, color .15s;
}
ul.category-children a:hover { background: var(--esta-blue-dark); color: #fff !important; }
ul.category-children a i { margin-right: 4px; }

/* 统计数字胶囊 */
[component="categories/category"] .stats span, .category-item .stats {
  color: #7a6b52;
}

/* ---------- 帖子列表 ---------- */
[component="category/topic"], [component="topic-list"] > li {
  border-bottom: 1px dashed rgba(201,138,61,.4) !important;
}
[component="category/topic"].pinned, [component="topic-list"] .pinned {
  background: linear-gradient(90deg, rgba(201,138,61,.14), transparent 70%);
  border-left: 3px solid var(--esta-copper);
}

/* ---------- 帖子页：纸张楼层卡片 ---------- */
[component="topic"] > [component="post"] {
  background: #fffdf4;
  border: 1px solid rgba(201,138,61,.45);
  border-radius: 8px;
  margin-bottom: 14px;
  padding: 0 !important;
  overflow: hidden;
}
[component="post"] > .d-flex { padding: 14px 16px; }

/* 楼层号徽章（右上角） */
.esta-floor {
  position: absolute; top: 0; right: 0;
  background: var(--esta-paper-dark);
  color: #8a6d3b; font-weight: 700; font-size: 12px;
  border-left: 1px solid rgba(201,138,61,.5);
  border-bottom: 1px solid rgba(201,138,61,.5);
  border-radius: 0 7px 0 8px;
  padding: 3px 12px; letter-spacing: 1px;
}
.esta-floor.esta-floor-op { background: var(--esta-copper); color: #fff; }
[component="post"] { position: relative; }

/* 左侧作者信息栏（桌面端） */
@media (min-width: 992px) {
  [component="post"] > .d-flex { gap: 18px !important; }
  .esta-side {
    flex: 0 0 150px; width: 150px;
    background: var(--esta-paper-dark);
    border-right: 1px solid rgba(201,138,61,.45);
    margin: -14px 0 -14px -16px;
    padding: 16px 12px;
    text-align: center;
    display: flex; flex-direction: column; align-items: center; gap: 6px;
    min-height: 100%;
  }
  /* 隐藏原本行内的小头像 */
  [component="post"] > .d-flex > div:first-child > [component="user/picture"],
  [component="post"] > .d-flex > a[component="user/picture"],
  [component="post"] > .d-flex > div.flex-shrink-0 { display: none !important; }
}
@media (max-width: 991.98px) {
  .esta-side { display: none !important; }
}
.esta-side .esta-avatar {
  width: 84px; height: 84px; border-radius: 10px;
  border: 2px solid var(--esta-copper);
  box-shadow: 0 3px 8px rgba(59,50,38,.2);
  display: flex; align-items: center; justify-content: center;
  font-size: 38px; color: #fff; overflow: hidden;
}
.esta-side .esta-avatar img { width: 100%; height: 100%; object-fit: cover; }
.esta-side .esta-name { font-weight: 800; color: var(--esta-blue-dark); font-size: 14.5px; word-break: break-all; }
.esta-side .esta-group {
  font-size: 11.5px; font-weight: 700; color: #fff;
  border-radius: 999px; padding: 2px 10px; letter-spacing: 1px;
}
.esta-side .esta-stats {
  width: 100%; margin-top: 4px; border-top: 1px dashed rgba(201,138,61,.5); padding-top: 8px;
  font-size: 12px; color: #7a6b52; text-align: left;
  display: flex; flex-direction: column; gap: 3px;
}
.esta-side .esta-stats b { color: #5b4c34; float: right; font-weight: 700; }
.esta-online { font-size: 11px; color: #2e9e5b; }
.esta-online.off { color: #a89f8d; }

/* 签名档 */
[component="post/signature"] {
  border-top: 1px dashed rgba(201,138,61,.5);
  margin-top: 12px; padding-top: 8px;
  color: #8d7d61; font-size: 12.5px;
}

/* 点赞按钮加大 */
[component="post/upvote"] { transform: scale(1.15); }

/* ---------- 右侧小部件卡片 ---------- */
.card { border: 1px solid rgba(201,138,61,.45); background: #fffdf4; }
.card > .card-header {
  background: linear-gradient(90deg, #10396b, #0d2547);
  color: #ffe4b3; font-weight: 700; letter-spacing: 1px;
  border-bottom: 1px solid var(--esta-copper);
}

/* ---------- 页脚 ---------- */
#footer, [component="footer"] { color: #9db7dc; }

/* ---------- 内测反馈浮动按钮 ---------- */
.esta-beta-fab {
  position: fixed; right: 20px; bottom: 76px; z-index: 1000;
  display: inline-flex; align-items: center; gap: 8px;
  padding: 11px 17px; border-radius: 999px;
  background: linear-gradient(135deg, #f97316, #ef4444);
  color: #fff !important; font-weight: 700; font-size: 14px;
  box-shadow: 0 10px 28px rgba(239,68,68,.45); text-decoration: none;
}
.esta-beta-fab:hover { transform: translateY(-2px); color: #fff !important; }
`;

/* ============================ 帖子页装饰 JS（注入每页 head） ============================ */
const CUSTOM_HTML = `
<script>
/* HEU ESTA 论坛装饰：楼层号 + 左侧作者栏 + 首页横幅 + QQ 公告条 */
(function () {
  'use strict';
  var FLOORS = { 0: '楼主', 1: '沙发', 2: '板凳', 3: '地板' };
  var GROUP_COLORS = { '管理员': '#ef4444', '干事': '#f59e0b', '会员': '#0ea5e9', 'administrators': '#ef4444' };
  var GROUP_LABELS = { '管理员': '管理组', '干事': '干事', '会员': '正式会员', 'administrators': '管理组' };

  function userMap() {
    var map = {};
    var d = window.ajaxify && ajaxify.data;
    if (!d) { return map; }
    (d.posts || []).forEach(function (p) { if (p && p.user) { map[p.user.uid] = p.user; } });
    return map;
  }

  function decoratePosts() {
    if (!window.ajaxify || !ajaxify.data || ajaxify.data.template.name !== 'topic') { return; }
    var users = userMap();
    document.querySelectorAll('[component="topic"] > [component="post"]').forEach(function (post) {
      var idx = parseInt(post.getAttribute('data-index'), 10);
      var uid = parseInt(post.getAttribute('data-uid'), 10);

      if (!post.querySelector('.esta-floor')) {
        var floor = document.createElement('span');
        floor.className = 'esta-floor' + (idx === 0 ? ' esta-floor-op' : '');
        floor.textContent = FLOORS[idx] !== undefined ? FLOORS[idx] : ('#' + (idx + 1) + '楼');
        post.appendChild(floor);
      }

      var row = post.querySelector(':scope > .d-flex');
      var u = users[uid];
      if (!row || !u || post.querySelector('.esta-side')) { return; }

      var side = document.createElement('div');
      side.className = 'esta-side';

      var avatar = document.createElement('a');
      avatar.className = 'esta-avatar';
      avatar.href = '/user/' + (u.userslug || uid);
      if (u.picture) {
        var img = document.createElement('img');
        img.src = u.picture; img.alt = u.displayname || u.username;
        avatar.appendChild(img);
      } else {
        avatar.textContent = (u['icon:text'] || '?');
        avatar.style.background = u['icon:bgColor'] || '#0ea5e9';
      }
      side.appendChild(avatar);

      var name = document.createElement('a');
      name.className = 'esta-name';
      name.href = '/user/' + (u.userslug || uid);
      name.textContent = u.displayname || u.username;
      side.appendChild(name);

      var groupName = null;
      (u.groupTitleArray || []).some(function (g) { if (GROUP_LABELS[g]) { groupName = g; return true; } return false; });
      if (groupName) {
        var badge = document.createElement('span');
        badge.className = 'esta-group';
        badge.style.background = GROUP_COLORS[groupName];
        badge.textContent = GROUP_LABELS[groupName];
        side.appendChild(badge);
      }

      var online = document.createElement('span');
      var isOn = u.status && u.status !== 'offline';
      online.className = 'esta-online' + (isOn ? '' : ' off');
      online.textContent = isOn ? '● 在线' : '○ 离线';
      side.appendChild(online);

      var stats = document.createElement('div');
      stats.className = 'esta-stats';
      stats.innerHTML =
        '<span>声望 <b>' + (u.reputation || 0) + '</b></span>' +
        '<span>帖子 <b>' + (u.postcount || 0) + '</b></span>' +
        '<span>主题 <b>' + (u.topiccount || 0) + '</b></span>';
      side.appendChild(stats);

      row.insertBefore(side, row.firstChild);
    });
  }

  function decorateHome() {
    if (!window.ajaxify || !ajaxify.data) { return; }
    var tpl = ajaxify.data.template.name;
    var content = document.getElementById('content');
    if (!content) { return; }
    var container = content.querySelector('.container') || content;

    if (tpl === 'categories' && !container.querySelector('.esta-banner')) {
      var banner = document.createElement('div');
      banner.className = 'esta-banner';
      banner.innerHTML = '<img src="/assets/uploads/system/banner.webp" alt="HEU ESTA 论坛">';
      container.insertBefore(banner, container.firstChild);
    }
    if (tpl === 'categories' && !container.querySelector('.esta-qq-bar')) {
      var bar = document.createElement('div');
      bar.className = 'esta-qq-bar';
      bar.innerHTML = '📢 欢迎加入科协招新 QQ 群：<span class="esta-qq-num">1015304209</span>' +
        '<span style="opacity:.75">丨官网 <a href="https://heuesta.cn">heuesta.cn</a> 丨内网资料库 <a href="http://192.168.1.112:8080">192.168.1.112:8080</a>（仅实验室内网）</span>';
      var ref = container.querySelector('.esta-banner');
      if (ref && ref.nextSibling) { container.insertBefore(bar, ref.nextSibling); } else { container.insertBefore(bar, container.firstChild); }
    }

    // 父版块行标记为"分区条"
    if (tpl === 'categories') {
      container.querySelectorAll('[component="categories/category"]').forEach(function (li) {
        if (li.querySelector('[component="category/children"]')) { li.classList.add('esta-section'); }
      });
    }
  }

  function betaFab() {
    if (document.querySelector('.esta-beta-fab')) { return; }
    var a = document.createElement('a');
    a.className = 'esta-beta-fab';
    a.href = '/topic/5';
    a.title = '内测反馈：提 Bug / 提建议';
    a.innerHTML = '<span>🐛</span> 内测反馈';
    document.body.appendChild(a);
  }

  function run() { try { decoratePosts(); decorateHome(); betaFab(); } catch (e) { console.warn('esta-theme', e); } }

  if (window.jQuery) {
    jQuery(window).on('action:ajaxify.end action:posts.loaded action:topic.loaded', run);
  }
  document.addEventListener('DOMContentLoaded', run);
})();
</script>
`;

(async () => {
    const db = require(APP + '/src/database');
    await db.init();
    const meta = require(APP + '/src/meta');
    await meta.configs.init();

    // 走正规配置流程：customCSS 会被 sass 编译为 renderedCustomCSS 再注入页面
    await meta.configs.setMultiple({
        customCSS: CUSTOM_CSS,
        useCustomCSS: 1,
        customHTML: CUSTOM_HTML,
        useCustomHTML: 1,
    });

    const rendered = await db.getObjectField('config', 'renderedCustomCSS');
    console.log('[theme-v2] 皮肤已编译，renderedCustomCSS 长度: ' + (rendered ? rendered.length : 0));
    console.log('[theme-v2] 重启论坛后生效');
    process.exit(0);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
