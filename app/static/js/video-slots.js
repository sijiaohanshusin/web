/* 视频槽的播放控制。
   ------------------------------------------------------------------
   为什么播放要交给 JS 而不是直接写 autoplay：

   1. `prefers-reduced-motion` 下不该自动播一段循环画面，而 CSS 拦不住 autoplay，
      HTML 属性也没法条件化。
   2. 省流模式（navigator.connection.saveData）下不该偷偷下几百 KB 的视频。
      注意这条只影响「视频是否自动播」，**不降级页面动效** —— 两件事不要混。
   3. 不在视口里的视频没有任何理由解码。一页上放三四段循环片段时，这一条直接
      决定页面是不是还能用。

   JS 没跑起来（加载失败、报错）时，<video> 停在 poster 帧上 —— 是个能看的状态，
   不是白屏。这跟站内 motion-ready 的降级契约是同一个思路：不要把内容藏在
   「必须有 JS」的后面。

   手动入口：不自动播时显示一个播放按钮，用户想看还能点。 */
(function () {
    "use strict";

    var figures = document.querySelectorAll("[data-slot-video]");
    if (!figures.length) return;

    var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    var saveData = !!(conn && conn.saveData);
    // 自动播的前提：用户没要求减少动效，也没开省流
    var mayAutoplay = !reduced && !saveData;

    function setup(figure) {
        var video = figure.querySelector("video");
        var button = figure.querySelector(".slot-video-play");
        if (!video) return;

        var manual = false;      // 用户点过播放按钮就不再被视口逻辑暂停

        function play() {
            // play() 返回 Promise 且可能被浏览器拒绝（自动播放策略）。
            // 必须 catch：未处理的 rejection 会污染控制台，让真正的报错更难找。
            var p = video.play();
            if (p && typeof p.catch === "function") {
                p.catch(function () { showButton(); });
            }
        }

        function showButton() {
            if (button) button.hidden = false;
        }

        function hideButton() {
            if (button) button.hidden = true;
        }

        if (button) {
            button.addEventListener("click", function (e) {
                e.stopPropagation();   // facade 那种整块可点的容器不要跟着触发
                manual = true;
                hideButton();
                play();
            });
        }

        if (!mayAutoplay) {
            // 只显示封面 + 一个手动入口。preload=metadata 已经限制了预取量，
            // 这里再把它压到 none，省流模式下一个字节的视频都不下。
            if (saveData) video.preload = "none";
            showButton();
            return;
        }

        if (!("IntersectionObserver" in window)) {
            play();
            return;
        }

        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) play();
                else if (!manual) video.pause();
            });
        }, { threshold: 0.25 });
        io.observe(figure);
    }

    figures.forEach(setup);
})();
