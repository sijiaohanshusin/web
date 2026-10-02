/* ============================================================
   开场加载动画的进度与退场
   ------------------------------------------------------------
   分工（重要）：描线动画在 includes/preloader.html 的内联 CSS 里，纯 CSS
   驱动，本文件挂了也照样播。这里只做三件事：
     1. 把真实加载进度映射到底部进度条与百分比
     2. 加载完成 + 描线播完 后揭幕
     3. 同一会话内二次进入直接跳过

   跟踪首屏必要字体与描线动画；屏外字体、媒体和 3D 不阻塞阅读。

   对外接口：
     ESTA.preload.add(promise, label)  登记一个必须等的任务
     ESTA.preload.done                 一个在揭幕后 resolve 的 Promise，
                                       Hero 分镜用它决定何时开始演
   ============================================================ */
(function () {
    "use strict";

    var el = document.getElementById("esta-preloader");
    var win = window;
    var html = document.documentElement;

    win.ESTA = win.ESTA || {};

    // reduced-motion 下遮罩本来就 display:none（CSS 决定），这里不必再管，
    // 但仍要把 done 兑现，否则等它的分镜会一直挂着。
    var reduced = win.matchMedia && win.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function loadDetailFonts() {
        // Enabling a pending stylesheet before defer scripts execute blocks those
        // scripts too. Let navigation bind and paint before starting more fonts.
        function activate() {
            requestAnimationFrame(function () { requestAnimationFrame(function () {
                var styles = document.getElementById("font-detail-styles");
                if (styles) styles.media = "all";
            }); });
        }
        function afterOpeningPaint() { setTimeout(activate, el && !alreadySeen && !reduced ? 700 : 0); }
        if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", afterOpeningPaint, {once:true});
        else afterOpeningPaint();
    }

    var resolveDone;
    var donePromise = new Promise(function (res) { resolveDone = res; });

    // 会话内只演一次。刷新首页、从内页返回首页都不该再被拦一次。
    var SEEN_KEY = "esta:preloader-seen";
    var alreadySeen = false;
    try {
        alreadySeen = sessionStorage.getItem(SEEN_KEY) === "1";
    } catch (e) {
        // 隐私模式下 sessionStorage 可能抛异常，当作没看过处理
    }

    if (!el || reduced || alreadySeen) {
        if (el) el.parentNode.removeChild(el);
        html.classList.remove("esta-pre-lock");
        resolveDone();
        loadDetailFonts();
        win.ESTA.preload = { add: function () {}, done: donePromise, skipped: true };
        return;
    }

    html.classList.add("esta-pre-lock");

    var bar = document.getElementById("esta-pre-bar");
    var pct = document.getElementById("esta-pre-pct");

    /* ---------- 进度模型 ----------
       每个任务一份权重，但允许上报小数进度。这一点很重要：把"描线动画播完"
       当成二元任务时，进度条会在 67% 干等 1.6 秒再跳到 100%，观感很差。
       让它按时间连续上报，读数才是平滑的。

       显示值只允许单调递增，杜绝"倒退"这种廉价观感。 */
    var tasks = [];          // 每项 { label, progress: 0..1 }
    var shown = -1;
    var rafId = 0;

    function total() {
        var sum = 0;
        for (var i = 0; i < tasks.length; i++) sum += tasks[i].progress;
        return tasks.length ? sum / tasks.length : 1;
    }

    var painting = true;

    function paint() {
        var target = Math.round(total() * 100);
        if (target > shown) {
            shown = target;
            if (bar) bar.style.width = shown + "%";
            if (pct) pct.textContent = ("00" + shown).slice(-3);
        }
        if (painting) rafId = requestAnimationFrame(paint);
    }

    function track(promise, label) {
        var task = { label: label || "task", progress: 0 };
        tasks.push(task);
        // 任何任务失败都不该卡住揭幕：失败也算完成，页面照常进入
        Promise.resolve(promise).catch(function (err) {
            if (win.console) console.warn("[preload] " + task.label + " 失败，继续：", err);
        }).then(function () {
            task.progress = 1;
        });
        return promise;
    }

    /** 登记一个按时间线性推进的任务（用于已知时长的动画）。 */
    function trackTimed(ms, label) {
        if (ms <= 0) return Promise.resolve();
        var task = { label: label, progress: 0 };
        tasks.push(task);
        var start = performance.now();
        (function step() {
            task.progress = Math.min(1, (performance.now() - start) / ms);
            if (task.progress < 1) requestAnimationFrame(step);
        })();
        return new Promise(function (res) { setTimeout(res, ms); });
    }

    /* Only critical hero type is part of the opening. Below-fold fonts and
       media never hold navigation or scrolling hostage. */
    if (document.fonts && document.fonts.load) {
        track(document.fonts.load('700 16px "ESTA Sans"', '电子科技协会'), 'brand');
        track(document.fonts.load('900 48px "ESTA Display"', '焊接每一个奇思妙想'), 'title');
    }

    // 描线动画本身也是"内容"，没播完就揭幕等于白做。
    // 与完整六段描线的最后一段（延迟 .76s + 时长 .65s）对齐。
    var DRAW_MS = Math.max(0, Math.min(1450 - (performance.now() - (win.ESTAOpeningStarted || performance.now())), 2800 - performance.now()));
    trackTimed(DRAW_MS, "draw");

    paint();

    /* ---------- 揭幕 ---------- */
    var lifted = false;

    function lift() {
        if (lifted) return;
        lifted = true;

        // 进度条补满再走，视觉上不留断口，然后停掉 rAF
        for (var i = 0; i < tasks.length; i++) tasks[i].progress = 1;
        painting = false;
        if (rafId) cancelAnimationFrame(rafId);
        paint();

        try {
            sessionStorage.setItem(SEEN_KEY, "1");
        } catch (e) { /* 隐私模式，忽略 */ }

        // 让补满的那一帧先画出来
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                el.classList.add("is-done");
                html.classList.remove("esta-pre-lock");
                resolveDone();
                loadDetailFonts();
                // 动画结束后从 DOM 移除，避免一个全屏元素常驻影响命中测试
                setTimeout(function () {
                    if (el.parentNode) el.parentNode.removeChild(el);
                }, 600);
            });
        });
    }

    // 所有任务落地即揭幕。用轮询而不是 Promise.all，因为任务可以在初始化
    // 之后被页面动态登记（例如 3D 会标就绪），数组长度是会变的。
    var waitAll = function () {
        return new Promise(function (res) {
            var check = function () {
                if (total() >= 1) res();
                else setTimeout(check, 60);
            };
            check();
        });
    };
    waitAll().then(lift);

    // Critical resources have a bounded wait; the opening remains skippable.
    setTimeout(lift, Math.max(0, 3000 - performance.now()));
    var skip = document.getElementById("esta-pre-skip");
    if (skip) skip.addEventListener("click", lift);

    win.ESTA.preload = { add: track, done: donePromise, skipped: false };
})();
