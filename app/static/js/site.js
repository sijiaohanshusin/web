/* 全站基础交互：移动端菜单 + 懒加载图片淡入 + 导航滑动药丸
   （导航栏滚动态与黑白区反色在 motion-core.js） */
(function () {
    "use strict";

    var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

    var nav = document.getElementById("site-nav");
    var burger = document.getElementById("nav-burger");

    function closeNavGroups(except) {
        document.querySelectorAll("[data-nav-group][open]").forEach(function (d) {
            if (d !== except) d.open = false;
        });
    }

    function setBurger(open) {
        if (!nav || !burger) return;
        nav.classList.toggle("nav-open", open);
        burger.setAttribute("aria-expanded", open ? "true" : "false");
        if (!open) closeNavGroups();
    }

    if (burger && nav) {
        burger.addEventListener("click", function () {
            setBurger(!nav.classList.contains("nav-open"));
        });
    }

    /* ---------- 导航折叠组（了解协会 / 学习资源） ----------
       展开本身是原生 <details> 干的，没有 JS 也能用。这里只补三件在浮层菜单上
       缺了就会很别扭的事：同时只开一个、点外面关、按 Esc 关（并把焦点还给触发
       它的 summary，否则键盘用户关掉之后焦点掉到 body、要从头 Tab 一遍）。 */
    document.querySelectorAll("[data-nav-group]").forEach(function (group) {
        group.addEventListener("toggle", function () {
            if (group.open) closeNavGroups(group);
        });
    });

    document.addEventListener("click", function (e) {
        if (!e.target.closest("[data-nav-group]")) closeNavGroups();
        // 汉堡面板：点面板外面就收起来（触屏上没有别的关法）
        if (nav && nav.classList.contains("nav-open") && !e.target.closest(".site-nav")) {
            setBurger(false);
        }
    });

    document.addEventListener("keydown", function (e) {
        if (e.key !== "Escape") return;
        var openGroup = document.querySelector("[data-nav-group][open]");
        if (openGroup) {
            openGroup.open = false;
            var summary = openGroup.querySelector("summary");
            if (summary) summary.focus();
            return;
        }
        if (nav && nav.classList.contains("nav-open")) {
            setBurger(false);
            burger.focus();
        }
    });

    // 焦点离开整个折叠组就收起（Tab 走出去时）
    document.addEventListener("focusin", function (e) {
        var inside = e.target.closest("[data-nav-group]");
        document.querySelectorAll("[data-nav-group][open]").forEach(function (d) {
            if (d !== inside) d.open = false;
        });
    });

    // 导航栏滚动态（.scrolled）与黑白区反色（.nav-on-light）统一由
    // motion-core.js 的单个 rAF 节流滚动回调处理，这里不再重复监听 scroll。

    /* ---------- 懒加载图片淡入（只处理尚未加载完成的，缓存图不闪） ----------
       暴露成函数而不是只跑一次：任何往 DOM 里插入图片的代码（图片走廊的无缝
       循环要克隆一份内容）都必须回调它一次，否则新节点带着 .img-fade 的
       opacity:0 却没有 load 监听，会永久停在透明状态。
       真实踩过：走廊用 track.innerHTML += track.innerHTML 复制内容，innerHTML
       重新解析会把所有原始节点连监听器一起丢掉，只留下类名，于是整条走廊的
       懒加载图全都不可见 —— 而页面不报错、图片实际也下载成功了。 */
    function hydrateImageFades(root) {
        (root || document).querySelectorAll('img[loading="lazy"]').forEach(function (img) {
            // 已经完成的直接标成可见：可能是缓存命中，也可能是它的 load 事件
            // 早于本次调用就已经发生过（克隆节点插入时很常见）
            if (img.complete) {
                img.classList.remove("img-fade");
                return;
            }
            if (img.classList.contains("img-loaded")) return;
            img.classList.add("img-fade");
            function loaded() { img.classList.add("img-loaded"); }
            img.addEventListener("load", loaded, { once: true });
            img.addEventListener("error", loaded, { once: true });
        });
    }
    window.ESTA = window.ESTA || {};
    window.ESTA.hydrateImageFades = hydrateImageFades;
    hydrateImageFades(document);

    /* ---------- 招新截止倒计时 ----------
       首页 CTA 与招新落地页共用，所以放全站基础脚本里而不是 home.js。

       服务端已经渲染了截止日期的静态文字，这里只是把它升级成滴答的时钟：
       时钟初始 hidden，脚本没跑起来就不会露出一排 "--"，日期照常可读。 */
    var cdBox = document.querySelector("[data-countdown]");
    if (cdBox) {
        var deadline = new Date(cdBox.getAttribute("data-countdown")).getTime();
        var clock = cdBox.querySelector(".nf-countdown-clock");
        var cdCells = {};
        ["d", "h", "m", "s"].forEach(function (k) {
            cdCells[k] = clock && clock.querySelector('[data-cd="' + k + '"]');
        });

        // 截止时间解析不出来就别显示时钟，静态日期已经够用
        if (clock && cdCells.d && !isNaN(deadline)) {
            var cdTimer = 0;

            function cdPad(n) { return n < 10 ? "0" + n : String(n); }

            function cdTick() {
                var left = deadline - Date.now();
                if (left <= 0) {
                    // 招新状态在服务端缓存 5 分钟，客户端可能比它先跨过截止点。
                    // 与其继续倒数负数，直接换成一句话。
                    clock.textContent = "报名已截止";
                    clock.classList.add("is-over");
                    if (cdTimer) clearInterval(cdTimer);
                    cdTimer = 0;
                    return;
                }
                var s = Math.floor(left / 1000);
                cdCells.d.textContent = String(Math.floor(s / 86400));
                cdCells.h.textContent = cdPad(Math.floor(s / 3600) % 24);
                cdCells.m.textContent = cdPad(Math.floor(s / 60) % 60);
                cdCells.s.textContent = cdPad(s % 60);
            }

            cdTick();
            clock.hidden = false;
            cdTimer = setInterval(cdTick, 1000);
            // 切后台就停：一个每秒醒一次的定时器没必要在不可见的标签页里跑
            document.addEventListener("visibilitychange", function () {
                if (document.hidden) {
                    clearInterval(cdTimer);
                    cdTimer = 0;
                } else if (!cdTimer && !clock.classList.contains("is-over")) {
                    cdTick();
                    cdTimer = setInterval(cdTick, 1000);
                }
            });
        }
    }

    /* ---------- 导航滑动药丸：hover/键盘焦点时在链接间滑动 ---------- */
    var links = document.getElementById("nav-links");
    if (links && finePointer && !reducedMotion) {
        var pill = document.createElement("span");
        pill.className = "nav-pill";
        pill.setAttribute("aria-hidden", "true");
        links.prepend(pill);
        links.classList.add("has-pill");

        /* 用 rect 差值而不是 offsetLeft/offsetTop：折叠组是 position:relative
           （要给浮层菜单当锚点），于是它里面的 summary 的 offsetParent 是那个
           .nav-group 而不是 .nav-links —— 按 offsetLeft 算出来的药丸会跑到最
           左边去。rect 差值和 offsetParent 是谁无关。 */
        function moveTo(el) {
            var r = el.getBoundingClientRect();
            var base = links.getBoundingClientRect();
            pill.style.width = r.width + "px";
            pill.style.height = r.height + "px";
            pill.style.transform =
                "translate(" + (r.left - base.left) + "px," + (r.top - base.top) + "px)";
        }
        function show(a) {
            // 首次出现原地浮现，不从远处飞入；之后在链接间滑动
            if (!links.classList.contains("pill-visible")) {
                pill.style.transition = "none";
                moveTo(a);
                void pill.offsetWidth; // 强制 reflow，吃掉无过渡的定位
                pill.style.transition = "";
            } else {
                moveTo(a);
            }
            links.classList.add("pill-visible");
        }
        function hide() { links.classList.remove("pill-visible"); }

        /* 只认顶层条目：`querySelectorAll("a")` 会把折叠菜单里的链接也算进来，
           于是 hover 一个二级链接会把顶层药丸拽到浮层里去。 */
        links.querySelectorAll(":scope > a, :scope > .nav-group > summary")
            .forEach(function (el) {
                el.addEventListener("mouseenter", function () { show(el); });
                el.addEventListener("focus", function () { show(el); });
            });
        links.addEventListener("mouseleave", hide);
        links.addEventListener("focusout", function (e) {
            if (!links.contains(e.relatedTarget)) hide();
        });
    }
})();
