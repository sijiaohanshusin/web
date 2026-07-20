/* 导航栏通知铃铛：点击展开下拉，首次展开时懒加载最近通知 */
(function () {
    "use strict";

    var wrap = document.getElementById("nav-bell-wrap");
    var bell = document.getElementById("nav-bell");
    var menu = document.getElementById("bell-menu");
    var list = document.getElementById("bell-menu-list");
    if (!wrap || !bell || !menu || !list) return;

    // 移动端汉堡菜单里直接跳列表页，不做下拉
    var isMobile = window.matchMedia("(max-width: 720px)").matches;
    if (isMobile) return;

    var loaded = false;

    function esc(s) {
        var d = document.createElement("div");
        d.textContent = s == null ? "" : String(s);
        return d.innerHTML;
    }

    function render(data) {
        if (!data.items.length) {
            list.innerHTML = '<div class="bell-menu-empty">还没有收到任何通知</div>';
            return;
        }
        list.innerHTML = data.items.map(function (n) {
            return '<a class="bell-item' + (n.read ? "" : " bell-item-unread") + '" href="/notify/' + n.id + '/go/">' +
                '<span class="bell-item-title">' + esc(n.title) + "</span>" +
                (n.body ? '<span class="bell-item-body">' + esc(n.body) + "</span>" : "") +
                '<span class="bell-item-meta">' + esc(n.kind) + " · " + esc(n.time) + "</span>" +
                "</a>";
        }).join("");
    }

    function load() {
        if (loaded) return;
        loaded = true;
        fetch(bell.getAttribute("data-latest-url"), { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(render)
            .catch(function () {
                list.innerHTML = '<div class="bell-menu-empty">加载失败，点铃铛进通知中心看吧</div>';
                loaded = false;
            });
    }

    function close() {
        menu.hidden = true;
        bell.setAttribute("aria-expanded", "false");
        document.removeEventListener("click", onDocClick);
    }

    function onDocClick(e) {
        if (!wrap.contains(e.target)) close();
    }

    bell.addEventListener("click", function (e) {
        e.preventDefault();
        if (menu.hidden) {
            menu.hidden = false;
            bell.setAttribute("aria-expanded", "true");
            load();
            setTimeout(function () { document.addEventListener("click", onDocClick); }, 0);
        } else {
            close();
        }
    });

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !menu.hidden) close();
    });
})();
