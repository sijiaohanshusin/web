/* Hero 宣传片级动画：三维投影的「信号海洋」粒子波场
   - 数千个发光粒子组成起伏的波面，带景深透视与雾化
   - 周期性信号脉冲从远处扫来（亮波前）
   - 鼠标划过产生涟漪与高亮，点击激起扩散冲击波
   - 标签页隐藏 / 滚出视口时自动暂停，prefers-reduced-motion 时只画静帧 */
(function () {
    "use strict";

    var canvas = document.getElementById("hero-canvas");
    var hero = document.getElementById("nf-hero");
    if (!canvas || !hero) return;

    var ctx = canvas.getContext("2d");
    var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

    var DPR = Math.min(window.devicePixelRatio || 1, 1.5);
    var W = 0, H = 0;           // CSS 像素
    var horizonY = 0, focal = 0, camH = 150;

    var COLS = 0, ROWS = 0;
    var Z_NEAR = 110, Z_FAR = 1500;
    var worldW = 0;
    var grid = [];              // {x, z}

    /* ---------- 发光粒子贴图（预渲染，性能关键） ---------- */
    function makeSprite(r, g, b) {
        var s = document.createElement("canvas");
        var size = 64;
        s.width = s.height = size;
        var c = s.getContext("2d");
        var grad = c.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
        grad.addColorStop(0, "rgba(" + r + "," + g + "," + b + ",1)");
        grad.addColorStop(0.28, "rgba(" + r + "," + g + "," + b + ",.55)");
        grad.addColorStop(1, "rgba(" + r + "," + g + "," + b + ",0)");
        c.fillStyle = grad;
        c.fillRect(0, 0, size, size);
        return s;
    }
    var spriteCyan = makeSprite(65, 216, 232);
    var spriteWhite = makeSprite(235, 248, 255);

    /* ---------- 布局 ---------- */
    function resize() {
        var rect = hero.getBoundingClientRect();
        W = rect.width;
        H = rect.height;
        canvas.width = Math.round(W * DPR);
        canvas.height = Math.round(H * DPR);
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

        horizonY = H * 0.34;
        focal = Math.max(W * 0.36, 300);
        worldW = W * 3.6;

        var dense = W > 900;
        COLS = dense ? 128 : 84;
        ROWS = dense ? 52 : 38;

        grid = [];
        for (var iz = 0; iz < ROWS; iz++) {
            // 深度按指数分布：近处行距密，远处稀
            var tz = iz / (ROWS - 1);
            var z = Z_NEAR + (Z_FAR - Z_NEAR) * Math.pow(tz, 1.55);
            for (var ix = 0; ix < COLS; ix++) {
                var x = (ix / (COLS - 1) - 0.5) * worldW;
                grid.push({ x: x, z: z });
            }
        }
    }

    /* ---------- 波面高度场 ---------- */
    function waveY(x, z, t) {
        return (
            34 * Math.sin(x * 0.0021 + t * 0.9 + z * 0.0012) +
            22 * Math.sin(z * 0.004 - t * 0.65) +
            14 * Math.sin((x * 0.55 + z) * 0.0035 + t * 1.35) +
            7 * Math.sin(x * 0.008 - t * 0.5)
        );
    }

    /* ---------- 交互状态 ---------- */
    var mouseX = -9999, mouseY = -9999;
    var shocks = [];            // 点击冲击波 {x, y, t0}

    if (finePointer) {
        hero.addEventListener("mousemove", function (e) {
            var rect = canvas.getBoundingClientRect();
            mouseX = e.clientX - rect.left;
            mouseY = e.clientY - rect.top;
        });
        hero.addEventListener("mouseleave", function () { mouseX = mouseY = -9999; });
    }
    hero.addEventListener("pointerdown", function (e) {
        // 点在按钮/链接上时不触发冲击波
        if (e.target.closest("a,button")) return;
        var rect = canvas.getBoundingClientRect();
        shocks.push({ x: e.clientX - rect.left, y: e.clientY - rect.top, t0: performance.now() / 1000 });
        if (shocks.length > 5) shocks.shift();
    });

    /* ---------- 主渲染 ---------- */
    var running = false;
    var rafId = 0;
    var start = performance.now() / 1000;

    function frame() {
        var t = performance.now() / 1000 - start;

        ctx.clearRect(0, 0, W, H);
        ctx.globalCompositeOperation = "lighter";

        // 信号脉冲波前：每 6.5 秒从远处扫到眼前
        var cycle = 6.5;
        var pt = (t % cycle) / cycle;
        var pulseZ = Z_FAR - (Z_FAR - Z_NEAR + 300) * pt;

        var now = t;
        var i, p;

        for (i = 0; i < grid.length; i++) {
            p = grid[i];

            var y = waveY(p.x, p.z, t);

            // 脉冲波前提升
            var dz = p.z - pulseZ;
            var pulse = Math.exp(-(dz * dz) / (2 * 130 * 130));
            y += pulse * 26;

            var scale = focal / p.z;
            var sx = W * 0.5 + p.x * scale;
            if (sx < -30 || sx > W + 30) continue;
            var sy = horizonY + (camH - y) * scale;

            // 基础亮度：近亮远暗
            var depthFade = Math.min(1, Math.max(0, 1.25 - p.z / Z_FAR * 1.35));
            var alpha = 0.05 + depthFade * 0.34 + pulse * 0.42;

            // 鼠标涟漪（屏幕空间）
            var boost = 0;
            if (mouseX > -999) {
                var dx = sx - mouseX, dy = sy - mouseY;
                var d2 = dx * dx + dy * dy;
                if (d2 < 32400) {
                    boost = Math.exp(-d2 / (2 * 78 * 78));
                    sy -= boost * 16;
                    alpha += boost * 0.55;
                }
            }

            // 点击冲击波（扩散圆环）
            for (var s = 0; s < shocks.length; s++) {
                var sh = shocks[s];
                var age = now - sh.t0;
                if (age > 1.8) continue;
                var r = age * 620;
                var ddx = sx - sh.x, ddy = sy - sh.y;
                var dist = Math.sqrt(ddx * ddx + ddy * ddy);
                var band = Math.exp(-((dist - r) * (dist - r)) / (2 * 46 * 46)) * (1 - age / 1.8);
                if (band > 0.01) {
                    sy -= band * 22;
                    alpha += band * 0.8;
                }
            }

            if (alpha < 0.02) continue;

            var size = (0.8 + depthFade * 1.8) * (1 + pulse * 0.8 + boost * 0.7);

            ctx.globalAlpha = Math.min(alpha, 0.95);
            ctx.drawImage(spriteCyan, sx - size * 2, sy - size * 2, size * 4, size * 4);

            // 高亮热核（脉冲/涟漪处泛白）
            var hot = pulse * 0.7 + boost;
            if (hot > 0.25) {
                ctx.globalAlpha = Math.min(hot * 0.5, 0.85);
                ctx.drawImage(spriteWhite, sx - size, sy - size, size * 2, size * 2);
            }
        }

        // 清理过期冲击波
        shocks = shocks.filter(function (sh) { return now - sh.t0 <= 1.8; });

        ctx.globalAlpha = 1;
        ctx.globalCompositeOperation = "source-over";

        if (running) rafId = requestAnimationFrame(frame);
    }

    function play() {
        if (running || reducedMotion) return;
        running = true;
        rafId = requestAnimationFrame(frame);
    }
    function pause() {
        running = false;
        if (rafId) cancelAnimationFrame(rafId);
    }

    resize();
    window.addEventListener("resize", function () { resize(); if (reducedMotion) frame(); });

    if (reducedMotion) {
        frame(); // 静帧
        return;
    }

    // 滚出视口 / 切后台自动暂停
    new IntersectionObserver(function (entries) {
        entries[0].isIntersecting ? play() : pause();
    }, { threshold: 0.02 }).observe(hero);

    document.addEventListener("visibilitychange", function () {
        document.hidden ? pause() : play();
    });

    play();
})();
