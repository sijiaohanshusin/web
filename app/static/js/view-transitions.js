/* 跨页转场：命名元素连续过渡（MPA View Transitions）

   根级的淡入淡出由 tokens.css 的 `@view-transition { navigation: auto }` 负责，
   纯 CSS、不支持的浏览器忽略。这个文件只做一件 CSS 做不到的事：**把「列表里那张
   卡片的封面」和「详情页顶部那张大图」认成同一个东西**，于是点进去时图片是长大的，
   不是整页闪一下换掉。

   为什么必须用 JS：`view-transition-name` 在一个文档里**必须唯一**。列表页上有
   十几张卡片，给它们全都命名会让浏览器直接跳过整个转场（控制台报重名）。所以名字
   只能在导航发生的那一刻、只给参与这次导航的那一张卡片。

   标记契约（模板侧）：
     列表页   <a data-vt-card href="/works/12/"> … <figure data-vt-part="cover">
     详情页   <figure data-vt-part="cover">        （不在 [data-vt-card] 里）
   判据就是「在不在卡片里」：详情页自己的那张图不在卡片里，而详情页底部的推荐卡片
   在。于是同一段代码两边都能用，不需要给每一页写规则。

   名字通过 `data-vt-name` 属性交给 CSS 映射（见 tokens.css），不写内联 style ——
   这样收尾只要摘掉一个属性，不用去还原 style 的原值。

   **这段代码绝不能挡住导航。** 全部包在 try/catch 里：转场是锦上添花，出错了页面
   照常跳转，只是没有动画。
*/
(function () {
    "use strict";

    // 这两个事件是跨文档转场唯一的介入点。不支持就什么都不做 ——
    // 根级淡入淡出照旧，只是没有命名元素的连续感。
    if (!("onpageswap" in window) || !("onpagereveal" in window)) return;
    // 减动效偏好下整段不参与：tokens.css 已经把根级动画关掉了，这里不命名，
    // 结果就是干净的瞬切。
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    // 目前只配封面。标题不配：卡片标题 18px、详情页 h1 到 50px，
    // 默认的形变会把文字拉变形，比直接淡入难看。
    var PARTS = ["cover"];

    function samePath(a, b) {
        try {
            return new URL(a, location.href).pathname === new URL(b, location.href).pathname;
        } catch (err) {
            return false;
        }
    }

    /** 这一页「自己的」命名元素：不在任何卡片里的那些（= 详情页顶部那张图）。 */
    function ownParts() {
        return [].filter.call(
            document.querySelectorAll("[data-vt-part]"),
            function (el) { return !el.closest("[data-vt-card]"); }
        );
    }

    /** 找到指向某个地址的那张卡片。按 pathname 比，绕开 querystring 与站点前缀。 */
    function cardFor(url) {
        var cards = document.querySelectorAll("a[data-vt-card][href]");
        for (var i = 0; i < cards.length; i++) {
            if (samePath(cards[i].getAttribute("href"), url)) return cards[i];
        }
        return null;
    }

    function partsIn(root) {
        return [].slice.call(root.querySelectorAll("[data-vt-part]"));
    }

    function tag(elements) {
        var tagged = [];
        elements.forEach(function (el) {
            if (PARTS.indexOf(el.getAttribute("data-vt-part")) === -1) return;
            el.setAttribute("data-vt-name", el.getAttribute("data-vt-part"));
            tagged.push(el);
        });
        return tagged;
    }

    /** 转场结束就把名字摘掉。**留着会让下一次导航重名、整个转场被跳过。** */
    function cleanup(transition, tagged) {
        if (!tagged.length) return;
        function drop() {
            tagged.forEach(function (el) { el.removeAttribute("data-vt-name"); });
        }
        var done = transition && transition.finished;
        if (done && typeof done.then === "function") {
            done.then(drop, drop);
        } else {
            setTimeout(drop, 1200);
        }
    }

    // ---------- 离开这一页 ----------
    window.addEventListener("pageswap", function (e) {
        if (!e.viewTransition) return;
        try {
            var to = e.activation && e.activation.entry && e.activation.entry.url;
            if (!to) return;
            var card = cardFor(to);
            // 点了某张卡片 → 只给这一张命名；
            // 从详情页退回列表（点「返回」而不是卡片）→ 给自己那张大图命名。
            var tagged = tag(card ? partsIn(card) : ownParts());
            cleanup(e.viewTransition, tagged);
        } catch (err) {
            /* 转场失败不能影响跳转 */
        }
    });

    // ---------- 到达这一页 ----------
    window.addEventListener("pagereveal", function (e) {
        if (!e.viewTransition) return;
        try {
            var mine = ownParts();
            var tagged;
            if (mine.length) {
                // 详情页：给自己顶部那张图命名，和来处那张卡片配上
                tagged = tag(mine);
            } else {
                // 列表页（多半是浏览器后退）：给「来处对应的那张卡片」命名
                var nav = window.navigation;
                var from = nav && nav.activation && nav.activation.from
                    && nav.activation.from.url;
                var card = from ? cardFor(from) : null;
                tagged = card ? tag(partsIn(card)) : [];
            }
            cleanup(e.viewTransition, tagged);
        } catch (err) {
            /* 同上 */
        }
    });
})();
