/* 全站基础交互：导航栏滚动态 + 移动端菜单 + 导航滑动药丸 */
(function () {
    "use strict";

    var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

    var nav = document.getElementById("site-nav");
    var burger = document.getElementById("nav-burger");

    if (burger && nav) {
        burger.addEventListener("click", function () {
            var open = nav.classList.toggle("nav-open");
            burger.setAttribute("aria-expanded", open ? "true" : "false");
        });
    }

    // 首页导航从透明渐变为实底
    if (nav) {
        var onScroll = function () {
            nav.classList.toggle("scrolled", window.scrollY > 40);
        };
        onScroll();
        window.addEventListener("scroll", onScroll, { passive: true });
    }

    /* ---------- 懒加载图片淡入（只处理尚未加载完成的，缓存图不闪） ---------- */
    document.querySelectorAll('img[loading="lazy"]').forEach(function (img) {
        if (img.complete) return;
        img.classList.add("img-fade");
        function loaded() { img.classList.add("img-loaded"); }
        img.addEventListener("load", loaded, { once: true });
        img.addEventListener("error", loaded, { once: true });
    });

    /* ---------- 导航滑动药丸：hover/键盘焦点时在链接间滑动 ---------- */
    var links = document.getElementById("nav-links");
    if (links && finePointer && !reducedMotion) {
        var pill = document.createElement("span");
        pill.className = "nav-pill";
        pill.setAttribute("aria-hidden", "true");
        links.prepend(pill);
        links.classList.add("has-pill");

        function moveTo(a) {
            pill.style.width = a.offsetWidth + "px";
            pill.style.height = a.offsetHeight + "px";
            pill.style.transform = "translate(" + a.offsetLeft + "px," + a.offsetTop + "px)";
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

        links.querySelectorAll("a").forEach(function (a) {
            a.addEventListener("mouseenter", function () { show(a); });
            a.addEventListener("focus", function () { show(a); });
        });
        links.addEventListener("mouseleave", hide);
        links.addEventListener("focusout", function (e) {
            if (!links.contains(e.relatedTarget)) hide();
        });
    }
})();
