/* ============================================================
   动效内核：能力探测 + 平滑滚动 + 滚动编排装配 + 场景注册表
   ------------------------------------------------------------
   全站唯一的动效入口。页面级动效不要自己 new Lenis / 自己注册
   ScrollTrigger，统一通过 ESTA.motion 拿到已装配好的实例。

   加载顺序（base.html，全部 defer，按文档顺序执行）：
       gsap.min.js → ScrollTrigger.min.js → SplitText.min.js
       → lenis.min.js → motion-core.js → 各页场景

   设计约定（与 tokens.css 对应）：
   - 缓动只有三条曲线，取值与 --ease-out / --ease-rise / --ease-damp
     逐位一致，见下方 EASE。别在场景里手写新的贝塞尔。
   - 时长用 DUR，对应 --t-fast/--t-base/--t-slow/--t-cine。

   降级策略（重要）：
   - 只按「能力」分支，不按设备档次。手机只要支持 WebGL 就跑完整效果，
     绝不因为是移动端而砍内容。
   - 唯一会关闭动效的情况是 prefers-reduced-motion（无障碍要求）。
   - 库加载失败时页面必须照常可读：任何"先隐藏再动画"的样式都必须挂在
     html.motion-ready 下面。这个类只有在 GSAP 就位后才会加上。
   ============================================================ */
(function () {
    "use strict";

    var html = document.documentElement;
    var win = window;

    /* ------------------------------------------------------------------
       cubic-bezier 求值：让 JS 动效与 CSS transition 手感完全一致。

       GSAP 允许把函数当 ease 用，所以这里自己解一遍贝塞尔，而不是拿
       power3.out 之类"差不多"的内置曲线凑，也省掉再引一个 CustomEase。
       解法是标准的先牛顿迭代、不收敛再二分。
       ------------------------------------------------------------------ */
    function cubicBezierEase(x1, y1, x2, y2) {
        // B(t) 的多项式系数（P0=0, P3=1）
        var cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
        var cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;

        function sampleX(t) { return ((ax * t + bx) * t + cx) * t; }
        function sampleY(t) { return ((ay * t + by) * t + cy) * t; }
        function slopeX(t) { return (3 * ax * t + 2 * bx) * t + cx; }

        function solveT(x) {
            var t = x, i, d, s;
            for (i = 0; i < 8; i++) {           // 牛顿迭代：绝大多数情况 3~4 次收敛
                d = sampleX(t) - x;
                if (Math.abs(d) < 1e-6) return t;
                s = slopeX(t);
                if (Math.abs(s) < 1e-6) break;  // 导数趋零，退化成二分
                t -= d / s;
            }
            var lo = 0, hi = 1;
            t = x;
            while (lo < hi) {                    // 二分兜底，固定 20 次足够 1e-6 精度
                d = sampleX(t);
                if (Math.abs(d - x) < 1e-6) return t;
                if (x > d) lo = t; else hi = t;
                t = (hi - lo) / 2 + lo;
                if (hi - lo < 1e-7) break;
            }
            return t;
        }

        return function (x) {
            if (x <= 0) return 0;
            if (x >= 1) return 1;
            return sampleY(solveT(x));
        };
    }

    // 与 tokens.css 的 --ease-* 逐位一致。改一边必须改另一边。
    var EASE = {
        out: cubicBezierEase(0.22, 1, 0.36, 1),      // --ease-out：既有组件默认曲线
        rise: cubicBezierEase(0.16, 1, 0.3, 1),      // --ease-rise：上升沿，入场/位移/揭示
        damp: cubicBezierEase(0.34, 1.56, 0.64, 1),  // --ease-damp：阻尼振荡，交互反馈
    };

    // 与 tokens.css 的 --t-* 一致（秒，GSAP 用秒）
    var DUR = { fast: 0.18, base: 0.35, slow: 0.6, cine: 1.1 };

    /* ------------------------------------------------------------------
       能力探测
       ------------------------------------------------------------------ */
    function mq(query) {
        return win.matchMedia ? win.matchMedia(query) : { matches: false, addEventListener: null };
    }

    var reducedQuery = mq("(prefers-reduced-motion: reduce)");

    function probeWebGL() {
        // 只探测能力，探完立刻释放上下文：某些移动 GPU 的并发上下文数很紧
        try {
            var c = document.createElement("canvas");
            var gl = c.getContext("webgl2") || c.getContext("webgl");
            if (!gl) return false;
            var lose = gl.getExtension("WEBGL_lose_context");
            if (lose) lose.loseContext();
            return true;
        } catch (e) {
            return false;
        }
    }

    var caps = {
        reduced: reducedQuery.matches,
        finePointer: mq("(hover: hover) and (pointer: fine)").matches,
        coarsePointer: mq("(hover: none), (pointer: coarse)").matches,
        webgl: probeWebGL(),
        // 省流模式不降级动效，只用来决定视频是否自动播放（见视频槽组件）
        saveData: !!(navigator.connection && navigator.connection.saveData),
        // 供 3D 场景决定渲染分辨率上限，不用来决定"要不要做效果"
        dpr: Math.min(win.devicePixelRatio || 1, 2),
        cores: navigator.hardwareConcurrency || 4,
    };

    var hasGsap = typeof win.gsap !== "undefined";
    var hasScrollTrigger = hasGsap && typeof win.ScrollTrigger !== "undefined";
    var hasLenis = typeof win.Lenis !== "undefined";

    if (!hasGsap) {
        // 不是致命错误：CSS 层的 reveal 动画与 site.js 的交互都不依赖 GSAP。
        // 但要留下痕迹，否则"动效全没了"会很难查。
        console.warn("[motion] GSAP 未加载，滚动编排类动效已跳过（页面内容不受影响）");
    }

    /* ------------------------------------------------------------------
       GSAP 装配
       ------------------------------------------------------------------ */
    var lenis = null;

    if (hasGsap) {
        if (hasScrollTrigger) win.gsap.registerPlugin(win.ScrollTrigger);
        if (typeof win.SplitText !== "undefined") win.gsap.registerPlugin(win.SplitText);
        win.gsap.defaults({ ease: EASE.rise, duration: DUR.slow });
    }

    /* ------------------------------------------------------------------
       平滑滚动（Lenis）

       触屏上刻意不接管手势（syncTouch: false）：JS 惯性滚动与系统原生动量
       打架的手感比不做更差。注意这不是"移动端降级"——Lenis 关掉后
       ScrollTrigger 仍然照常驱动全部滚动动画，只是滚动本身交回系统。
       ------------------------------------------------------------------ */
    function startLenis() {
        if (!hasLenis || !hasGsap || caps.reduced || lenis) return;
        lenis = new win.Lenis({
            duration: 1.05,
            easing: EASE.out,
            smoothWheel: true,
            syncTouch: false,
            autoRaf: false,   // 交给 gsap.ticker 统一驱动，避免两套 rAF 抢帧
        });
        if (hasScrollTrigger) lenis.on("scroll", win.ScrollTrigger.update);
        win.gsap.ticker.add(tickLenis);
        win.gsap.ticker.lagSmoothing(0);
    }

    function tickLenis(time) {
        if (lenis) lenis.raf(time * 1000);   // gsap.ticker 给的是秒，Lenis 要毫秒
    }

    function stopLenis() {
        if (!lenis) return;
        win.gsap.ticker.remove(tickLenis);
        lenis.destroy();
        lenis = null;
    }

    startLenis();

    /* ------------------------------------------------------------------
       reduced-motion 运行时切换：用户在系统设置里改了偏好，无需刷新
       ------------------------------------------------------------------ */
    function applyReduced(isReduced) {
        caps.reduced = isReduced;
        html.classList.toggle("motion-reduced", isReduced);
        if (isReduced) {
            stopLenis();
            if (hasScrollTrigger) win.ScrollTrigger.refresh();
        } else {
            startLenis();
        }
    }
    applyReduced(caps.reduced);

    if (reducedQuery.addEventListener) {
        reducedQuery.addEventListener("change", function (e) { applyReduced(e.matches); });
    }

    /* ------------------------------------------------------------------
       场景注册表

       每个页面的分镜写成一个场景模块，自己 ESTA.motion.scene(name, fn) 注册。
       内核负责：统一 try/catch（一个场景炸了不影响其他）、reduced 时跳过、
       以及在 GSAP 缺失时整体跳过。
       ------------------------------------------------------------------ */
    var scenes = [];
    var sceneNames = {};

    function runScene(entry) {
        if (sceneNames[entry.name] === "done") return;
        sceneNames[entry.name] = "done";
        try {
            entry.fn(api);
        } catch (err) {
            console.error("[motion] 场景「" + entry.name + "」初始化失败：", err);
        }
    }

    function scene(name, fn, options) {
        var opts = options || {};
        var entry = { name: name, fn: fn };
        if (!hasGsap && !opts.standalone) return;          // 需要 GSAP 但没有
        if (caps.reduced && !opts.keepWhenReduced) return;  // 尊重无障碍偏好
        if (opts.needsWebGL && !caps.webgl) return;
        scenes.push(entry);
        runScene(entry);
    }

    /* ------------------------------------------------------------------
       导航栏滚动态 + 黑白区反色

       首页每个区块都标了 data-nav="dark|light"（模板里早就埋好了，之前没有
       任何代码消费它）。这里读取当前压在导航栏下方的区块，给导航加
       .nav-on-light，让白区上的导航文字翻成深色。

       实现刻意不依赖 GSAP：导航可读性是基础功能，不能因为动效库没加载就坏掉。
       一个 rAF 节流的 scroll 回调里同时算 scrolled 与反色，全站只有这一个滚动
       监听在读布局。
       ------------------------------------------------------------------ */
    (function navState() {
        var nav = document.getElementById("site-nav");
        if (!nav) return;

        var zones = [].slice.call(document.querySelectorAll("[data-nav]"));
        var ticking = false;
        var lastLight = null;
        var lastScrolled = null;

        function measure() {
            ticking = false;

            var scrolled = win.scrollY > 40;
            if (scrolled !== lastScrolled) {
                lastScrolled = scrolled;
                nav.classList.toggle("scrolled", scrolled);
            }

            if (!zones.length) return;
            // 判定线取导航栏中线：区块跨过这条线时就算"压在导航下面"
            var line = nav.offsetHeight / 2;
            var onLight = false;
            for (var i = 0; i < zones.length; i++) {
                var r = zones[i].getBoundingClientRect();
                if (r.top <= line && r.bottom > line) {
                    onLight = zones[i].getAttribute("data-nav") === "light";
                    break;
                }
            }
            if (onLight !== lastLight) {
                lastLight = onLight;
                nav.classList.toggle("nav-on-light", onLight);
            }
        }

        function onScroll() {
            if (ticking) return;
            ticking = true;
            requestAnimationFrame(measure);
        }

        measure();
        win.addEventListener("scroll", onScroll, { passive: true });
        win.addEventListener("resize", onScroll, { passive: true });
    })();

    /* ------------------------------------------------------------------
       对外 API
       ------------------------------------------------------------------ */
    var api = {
        caps: caps,
        EASE: EASE,
        DUR: DUR,
        gsap: hasGsap ? win.gsap : null,
        ScrollTrigger: hasScrollTrigger ? win.ScrollTrigger : null,
        SplitText: typeof win.SplitText !== "undefined" ? win.SplitText : null,
        get lenis() { return lenis; },
        scene: scene,

        /** 滚到页面某处（Lenis 在时走平滑，否则走原生） */
        scrollTo: function (target, options) {
            if (lenis) { lenis.scrollTo(target, options); return; }
            var el = typeof target === "string" ? document.querySelector(target) : target;
            if (el && el.scrollIntoView) el.scrollIntoView({ behavior: caps.reduced ? "auto" : "smooth" });
        },

        /** 元素进入视口时执行一次，用完即弃。GSAP 缺席时也能用。 */
        once: function (el, fn, options) {
            var opts = options || {};
            if (!("IntersectionObserver" in win)) { fn(el); return; }
            var io = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (!entry.isIntersecting) return;
                    io.unobserve(entry.target);
                    fn(entry.target);
                });
            }, { threshold: opts.threshold || 0.15, rootMargin: opts.rootMargin || "0px 0px -10% 0px" });
            io.observe(el);
            return io;
        },
    };

    win.ESTA = win.ESTA || {};
    win.ESTA.motion = api;

    // 只有走到这里才说明动效链路完整。所有"先隐藏后动画"的 CSS 都必须
    // 写在 html.motion-ready 之下，这样库挂了页面也不会白屏。
    if (hasGsap) html.classList.add("motion-ready");
    html.classList.toggle("has-webgl", caps.webgl);
})();
