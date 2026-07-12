/* 全站基础交互：导航栏滚动态 + 移动端菜单 */
(function () {
    "use strict";

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
})();
