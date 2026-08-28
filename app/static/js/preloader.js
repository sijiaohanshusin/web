/* ============================================================
   开场加载动画的进度与退场
   ------------------------------------------------------------
   分工（重要）：描线动画在 includes/preloader.html 的内联 CSS 里，纯 CSS
   驱动，本文件挂了也照样播。这里只做三件事：
     1. 把真实加载进度映射到底部进度条与百分比
     2. 加载完成 + 描线播完 后揭幕
     3. 同一会话内二次进入直接跳过

   为什么进度要"真实"：用户明确说过首访可以慢，那就不能拿一个假的定时动画
   糊弄——进度条走完了页面还没好，比没有进度条更糟。这里跟踪的是字体就绪、
   window load，以及由页面自己登记的额外任务（例如 3D 会标就绪）。

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
        var task = { label: label, progress: 0 };
        tasks.push(task);
        var start = performance.now();
        (function step() {
            task.progress = Math.min(1, (performance.now() - start) / ms);
            if (task.progress < 1) requestAnimationFrame(step);
        })();
        return new Promise(function (res) { setTimeout(res, ms); });
    }

    /* ---------- 默认跟踪项 ---------- */
    // 字体：中文标题用的是自托管子集，没就绪就揭幕会看到一次字体跳变
    track(
        document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve(),
        "fonts"
    );

    // window load：图片、样式、脚本全部落地
    track(new Promise(function (res) {
        if (document.readyState === "complete") res();
        else win.addEventListener("load", res, { once: true });
    }), "load");

    // 描线动画本身也是"内容"，没播完就揭幕等于白做。
    // 时长与内联 CSS 的最后一段（order=5，延迟 1.22s + 时长 1.05s）对齐。
    var DRAW_MS = 2320;
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
                // 动画结束后从 DOM 移除，避免一个全屏元素常驻影响命中测试
                setTimeout(function () {
                    if (el.parentNode) el.parentNode.removeChild(el);
                }, 900);
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

    // 硬超时：无论如何 7 秒必须放人进来。比内联 CSS 的 9 秒兜底更早，
    // 所以正常路径下用户看到的是这条，兜底那条只在 JS 整体失效时生效。
    setTimeout(lift, 7000);

    win.ESTA.preload = { add: track, done: donePromise, skipped: false };
})();
