/* motion-core 冒烟测试：用最小 DOM 桩在 Node 里跑一遍动效内核。
 *
 * 跑法： node scripts/motion_smoke.js      （退出码非 0 表示有失败项）
 *
 * 为什么需要它：动效的失败模式大多"不报错"——库没加载、能力探测判错、
 * reduced-motion 没生效，页面看起来只是"效果没了"，浏览器控制台可能一片
 * 干净。这里用桩把五种组合固定下来，改内核时能立刻知道有没有踩到。
 *
 * 最关键的一条断言是「GSAP 缺失时绝不能加 motion-ready」：所有"先隐藏
 * 后动画"的 CSS 都挂在 html.motion-ready 之下，这个类误加就等于白屏。
 *
 * 用手写桩而不是 jsdom，是为了不引入 node_modules（本项目无构建链）。
 * 桩只实现 motion-core 实际用到的那部分 DOM，加新能力时按需补。
 *
 * 输出里出现「场景「boom」初始化失败」和「GSAP 未加载」是预期的：
 * 这两条正是在验证错误隔离与降级路径。
 */
"use strict";
const fs = require("fs");
const vm = require("vm");

const SRC = fs.readFileSync("app/static/js/motion-core.js", "utf8");

function makeClassList() {
    const set = new Set();
    return {
        _set: set,
        add: (...c) => c.forEach((x) => set.add(x)),
        remove: (...c) => c.forEach((x) => set.delete(x)),
        contains: (c) => set.has(c),
        toggle: (c, force) => {
            const on = force === undefined ? !set.has(c) : !!force;
            on ? set.add(c) : set.delete(c);
            return on;
        },
    };
}

function makeEl(attrs = {}) {
    return {
        classList: makeClassList(),
        offsetHeight: attrs.offsetHeight || 74,
        attributes: attrs.data || {},
        getAttribute(name) { return this.attributes[name] || null; },
        getBoundingClientRect: () => attrs.rect || { top: 0, bottom: 100 },
        addEventListener() {},
        style: {},
    };
}

function buildEnv(opts) {
    const nav = makeEl({ offsetHeight: 74 });
    // 两个区块：dark 覆盖导航线，light 在下方
    const zones = [
        makeEl({ data: { "data-nav": "dark" }, rect: { top: -200, bottom: 300 } }),
        makeEl({ data: { "data-nav": "light" }, rect: { top: 300, bottom: 900 } }),
    ];
    const rafQueue = [];
    const listeners = {};
    const mqListeners = [];

    const win = {
        scrollY: 0,
        devicePixelRatio: 2,
        navigator: { hardwareConcurrency: 8, connection: { saveData: false } },
        matchMedia(q) {
            const matches =
                (q.includes("prefers-reduced-motion") && !!opts.reduced) ||
                (q.includes("hover: hover") && !opts.touch) ||
                (q.includes("hover: none") && !!opts.touch);
            return {
                matches,
                addEventListener: (_e, fn) => mqListeners.push({ q, fn }),
            };
        },
        requestAnimationFrame: (fn) => { rafQueue.push(fn); return rafQueue.length; },
        cancelAnimationFrame() {},
        addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
        console,
    };
    win.window = win;

    const doc = {
        documentElement: makeEl(),
        addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
        getElementById: (id) => (id === "site-nav" ? nav : null),
        querySelectorAll: (sel) => (sel === "[data-nav]" ? zones : []),
        querySelector: () => null,
        createElement: (tag) => {
            if (tag !== "canvas") return makeEl();
            return {
                getContext: (type) =>
                    opts.webgl && (type === "webgl2" || type === "webgl")
                        ? { getExtension: () => ({ loseContext() {} }) }
                        : null,
            };
        },
    };

    // GSAP / Lenis 桩
    let tickerFns = [];
    const gsap = {
        _defaults: null,
        _plugins: [],
        registerPlugin(...p) { this._plugins.push(...p); },
        defaults(d) { this._defaults = d; },
        ticker: {
            add: (fn) => tickerFns.push(fn),
            remove: (fn) => { tickerFns = tickerFns.filter((f) => f !== fn); },
            lagSmoothing() {},
        },
    };
    const lenisCalls = { raf: 0, destroy: 0, on: [], scrollTo: 0 };
    function Lenis(config) {
        this.config = config;
        this.on = (ev, fn) => lenisCalls.on.push(ev);
        this.raf = () => lenisCalls.raf++;
        this.destroy = () => lenisCalls.destroy++;
        this.scrollTo = () => lenisCalls.scrollTo++;
    }

    if (opts.gsap !== false) {
        win.gsap = gsap;
        win.ScrollTrigger = { update() {}, refresh() {} };
        win.SplitText = function () {};
    }
    if (opts.lenis !== false) win.Lenis = Lenis;

    win.document = doc;
    return { win, doc, nav, zones, rafQueue, listeners, mqListeners, gsap, lenisCalls, tickerFns: () => tickerFns };
}

function run(name, opts, assertions) {
    const env = buildEnv(opts);
    const ctx = vm.createContext(env.win);
    // 让脚本里的 window / document / navigator / console 都能解析
    Object.assign(env.win, { globalThis: env.win });
    let error = null;
    try {
        vm.runInContext(SRC, ctx, { filename: "motion-core.js" });
        // 冲刷一次 rAF，触发 navState 的 measure()
        env.rafQueue.splice(0).forEach((fn) => fn(0));
    } catch (e) {
        error = e;
    }
    const problems = [];
    if (error) problems.push("抛异常: " + error.message);
    else {
        try { assertions(env, problems); } catch (e) { problems.push("断言崩溃: " + e.message); }
    }
    const ok = problems.length === 0;
    console.log(`${ok ? "OK  " : "FAIL"} ${name}`);
    problems.forEach((p) => console.log("       " + p));
    return ok;
}

function expect(problems, cond, msg) { if (!cond) problems.push(msg); }

let pass = true;

pass &= run("完整能力（GSAP + Lenis + WebGL）", { webgl: true }, (env, p) => {
    const api = env.win.ESTA.motion;
    expect(p, !!api, "未挂载 ESTA.motion");
    expect(p, api.caps.webgl === true, "webgl 能力探测应为 true");
    expect(p, api.caps.reduced === false, "reduced 应为 false");
    expect(p, api.caps.dpr === 2, "dpr 应被截到 2");
    expect(p, !!api.lenis, "应创建 Lenis 实例");
    expect(p, api.lenis.config.syncTouch === false, "触屏不应接管手势");
    expect(p, api.lenis.config.autoRaf === false, "应由 gsap.ticker 驱动而非 autoRaf");
    expect(p, env.lenisCalls.on.includes("scroll"), "应把 lenis scroll 接到 ScrollTrigger.update");
    expect(p, env.gsap._plugins.length >= 2, "应注册 ScrollTrigger 与 SplitText");
    expect(p, typeof env.gsap._defaults.ease === "function", "gsap 默认 ease 应是我们的贝塞尔函数");
    expect(p, Math.abs(env.gsap._defaults.ease(0.5) - 0.972) < 0.01, "默认 ease 应为 rise 曲线");
    expect(p, env.doc.documentElement.classList.contains("motion-ready"), "应加 motion-ready");
    expect(p, env.doc.documentElement.classList.contains("has-webgl"), "应加 has-webgl");
    // 导航：dark 区块压在判定线上 -> 不应有 nav-on-light
    expect(p, !env.nav.classList.contains("nav-on-light"), "dark 区块下不应反色");
    // 场景注册应被执行
    let ran = false;
    api.scene("smoke", () => { ran = true; });
    expect(p, ran, "场景应立即执行");
    // 场景抛错不应冒泡
    api.scene("boom", () => { throw new Error("intentional"); });
});

pass &= run("无 WebGL（应仍完整装配动效）", { webgl: false }, (env, p) => {
    const api = env.win.ESTA.motion;
    expect(p, api.caps.webgl === false, "webgl 应为 false");
    expect(p, !!api.lenis, "无 WebGL 不影响平滑滚动");
    expect(p, env.doc.documentElement.classList.contains("motion-ready"), "仍应加 motion-ready");
    expect(p, !env.doc.documentElement.classList.contains("has-webgl"), "不应加 has-webgl");
    let ran = false;
    api.scene("needs3d", () => { ran = true; }, { needsWebGL: true });
    expect(p, !ran, "needsWebGL 的场景应被跳过");
});

pass &= run("prefers-reduced-motion", { webgl: true, reduced: true }, (env, p) => {
    const api = env.win.ESTA.motion;
    expect(p, api.caps.reduced === true, "reduced 应为 true");
    expect(p, !api.lenis, "reduced 下不应启用平滑滚动");
    expect(p, env.doc.documentElement.classList.contains("motion-reduced"), "应加 motion-reduced");
    let ran = false;
    api.scene("anim", () => { ran = true; });
    expect(p, !ran, "reduced 下普通场景应被跳过");
    let kept = false;
    api.scene("keep", () => { kept = true; }, { keepWhenReduced: true });
    expect(p, kept, "标了 keepWhenReduced 的场景仍应执行");
});

pass &= run("GSAP 加载失败（页面必须不受影响）", { webgl: true, gsap: false }, (env, p) => {
    const api = env.win.ESTA.motion;
    expect(p, !!api, "即使没有 GSAP 也应挂载 ESTA.motion");
    expect(p, api.gsap === null, "api.gsap 应为 null");
    expect(p, !api.lenis, "没有 GSAP 时不应启动 Lenis");
    expect(p, !env.doc.documentElement.classList.contains("motion-ready"),
        "关键：GSAP 缺失时绝不能加 motion-ready，否则依赖它的隐藏样式会让内容不可见");
    let ran = false;
    api.scene("x", () => { ran = true; });
    expect(p, !ran, "需要 GSAP 的场景应跳过");
    let standalone = false;
    api.scene("y", () => { standalone = true; }, { standalone: true });
    expect(p, standalone, "standalone 场景不依赖 GSAP，应执行");
    // 导航状态是基础功能，不能依赖 GSAP
    expect(p, typeof env.listeners.scroll !== "undefined", "导航滚动监听应照常注册");
});

pass &= run("导航反色：light 区块压在判定线上", { webgl: true }, (env, p) => {
    // 把 light 区块挪到覆盖导航中线的位置，再触发一次 scroll
    env.zones[0].getBoundingClientRect = () => ({ top: -900, bottom: -1 });
    env.zones[1].getBoundingClientRect = () => ({ top: -1, bottom: 800 });
    env.listeners.scroll.forEach((fn) => fn());
    env.rafQueue.splice(0).forEach((fn) => fn(0));
    expect(p, env.nav.classList.contains("nav-on-light"), "light 区块下导航应反色");
    env.win.scrollY = 100;
    env.listeners.scroll.forEach((fn) => fn());
    env.rafQueue.splice(0).forEach((fn) => fn(0));
    expect(p, env.nav.classList.contains("scrolled"), "滚过 40px 应加 scrolled");
});

console.log(pass ? "\nmotion-core 冒烟测试全部通过" : "\nmotion-core 有失败项");
process.exit(pass ? 0 : 1);
