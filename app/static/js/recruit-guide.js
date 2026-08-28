/* 新生指南的阅读辅助：顶部进度线 + 目录通电。
   ==================================================================
   这一页是全站最长的一页，读者的真实问题不是「好不好看」而是**会不会迷路**：
   进来时不知道有多长、读到一半不知道在哪、划过去了也不知道还剩多少。

   两件事：
     1. 顶部进度线按整页滚动比例填充
     2. 目录是一段竖着的 PCB 走线，章节是焊盘 —— 读过的焊盘通电（.is-read），
        当前那一章额外高亮（.is-current），走线填到最后一个已读焊盘

   **纯增强**：目录链接本身是锚点，没有这个脚本照样能跳转；进度线在没有 JS 时
   保持 0 宽，不留残迹。所以这里不需要（也不应该）走 motion-core —— 它既不用
   GSAP 也不用 ScrollTrigger，只读 getBoundingClientRect。

   节流方式跟首页时间轴一致：scroll 里只排一个 rAF，真正的布局读取放在帧里。
   `window.scrollY` 在 Lenis 下依然有效（Lenis 做的是真实滚动，不是 transform）。 */
(function () {
    "use strict";

    var toc = document.getElementById("recruit-toc");
    var barFill = document.getElementById("rg-bar-fill");
    if (!toc && !barFill) return;

    var links = toc ? [].slice.call(toc.querySelectorAll("a")) : [];
    var sections = links.map(function (a) {
        var id = a.getAttribute("href") || "";
        return id.charAt(0) === "#" ? document.getElementById(id.slice(1)) : null;
    });

    // 走线主干：插在目录里，高度由「读到第几章」决定。用元素而不是渐变背景，
    // 因为要能独立做 transition 而不影响目录自身的背景。
    var trunk = null;
    if (toc) {
        trunk = document.createElement("span");
        trunk.className = "rg-trunk";
        trunk.setAttribute("aria-hidden", "true");
        toc.appendChild(trunk);
        toc.classList.add("rg-live");
    }

    var ticking = false;

    function update() {
        ticking = false;

        // ---- 顶部进度线：整页滚动比例 ----
        if (barFill) {
            var doc = document.documentElement;
            var max = doc.scrollHeight - window.innerHeight;
            var ratio = max > 0 ? window.scrollY / max : 0;
            barFill.style.width = Math.max(0, Math.min(1, ratio)) * 100 + "%";
        }

        if (!toc || !links.length) return;

        // ---- 目录通电 ----
        // 判定线放在视口上方 35% 处：一章的标题过了这条线就算「在读」。用固定
        // 比例而不是 IntersectionObserver 的原因是这里要的是**前缀语义**（读过
        // 的都亮），而 IO 只告诉你「谁现在可见」—— 长章节滚过去之后就不可见了，
        // 靠 IO 会把已读的章节又熄掉。
        var line = window.innerHeight * 0.35;
        var current = -1;
        for (var i = 0; i < sections.length; i++) {
            var sec = sections[i];
            if (!sec) continue;
            if (sec.getBoundingClientRect().top <= line) current = i;
        }
        // 还没滚到第一章标题时，当前章节就是第一章（页面顶部是 Hero）
        if (current < 0) current = 0;

        for (var j = 0; j < links.length; j++) {
            links[j].classList.toggle("is-read", j <= current);
            links[j].classList.toggle("is-current", j === current);
        }

        if (trunk) {
            // 主干从**第一个焊盘的中心**起、止于当前焊盘的中心 —— 焊盘之前
            // 没有东西可连，从 top:0 起会在第一个焊盘上方露出一小截悬空的线。
            // 两端都实测：目录项高度会随字号和换行变，写死就会错位。
            var tocTop = toc.getBoundingClientRect().top;
            var from = padCenter(links[0]) - tocTop;
            var to = padCenter(links[current]) - tocTop;
            trunk.style.top = from + "px";
            trunk.style.height = Math.max(0, to - from) + "px";
        }
    }

    /** 一个目录项里焊盘的竖直中心（视口坐标）。 */
    function padCenter(link) {
        var pad = link.querySelector(".rg-pad") || link;
        var box = pad.getBoundingClientRect();
        return box.top + box.height / 2;
    }

    function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(update);
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);

    // 文档高度变了就重算。**不要只监听 details 的 toggle** —— 折叠块有 .45s 的
    // 高度过渡，toggle 在 open 翻转的那一刻就触发，那时内容高度还是 0，算出来的
    // 比例是过渡中间态，过渡结束后再没人重算，进度线就永久停在一个错的值上。
    // （实测：展开一块之后 DOM 里是 38.6%，正确值是 31.2%。）
    //
    // 用 ResizeObserver 盯 body 一次覆盖所有让文档变高的原因：折叠过渡的每一帧、
    // 69 张图片陆续落地、字体 swap。update() 只改固定定位的进度线和绝对定位的
    // 走线，不影响 body 高度，所以不会自激。
    if (window.ResizeObserver) {
        new ResizeObserver(onScroll).observe(document.body);
    } else {
        document.querySelectorAll("details.fold").forEach(function (d) {
            d.addEventListener("toggle", onScroll);
        });
    }
    update();
})();
