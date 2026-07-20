/* 首页动效：滚动渐入 / 数字滚动 / 鼠标视差 / 3D 倾斜 / 可拖拽走廊 /
   时间轴进度 / 光斑跟随 / 磁性按钮 / 视频点击加载 / 复制群号 */
(function () {
    "use strict";

    var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

    /* ---------- 滚动渐入（交错延迟走 CSS 变量，动画结束零残留） ---------- */
    var revealObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add("is-visible");
                revealObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    document.querySelectorAll(".reveal").forEach(function (el, i) {
        el.style.setProperty("--reveal-delay", Math.min(i % 5, 3) * 90 + "ms");
        revealObserver.observe(el);
    });

    /* ---------- 数字滚动 ---------- */
    function animateCounter(el) {
        var target = parseInt(el.dataset.target, 10) || 0;
        if (reducedMotion || target <= 0) {
            el.textContent = target.toLocaleString();
            return;
        }
        var duration = 1800;
        var start = null;
        function step(ts) {
            if (!start) start = ts;
            var progress = Math.min((ts - start) / duration, 1);
            var eased = 1 - Math.pow(1 - progress, 4);
            el.textContent = Math.round(target * eased).toLocaleString();
            if (progress < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    }
    var counterObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                animateCounter(entry.target);
                counterObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.4 });
    document.querySelectorAll(".counter").forEach(function (el) { counterObserver.observe(el); });

    /* ---------- 指针跟随插值器：rAF + lerp ----------
       目标值由事件更新，动画帧向目标指数逼近；静止且归位后自动停帧、
       清掉内联 transform，把元素还给 CSS。比「直设 + transition 追赶」
       消除了快速移动时的滞后与抖动。 */
    function lerpFollow(el, apply) {
        var cur = null, target = null, rafId = 0;

        function frame() {
            var settled = true;
            for (var k in target) {
                cur[k] += (target[k] - cur[k]) * 0.16;
                if (Math.abs(target[k] - cur[k]) > 0.01) settled = false;
            }
            if (settled) {
                for (var j in target) cur[j] = target[j];
                apply(el, cur);
                rafId = 0;
                if (target.__rest) { el.style.transform = ""; cur = null; }
                return;
            }
            apply(el, cur);
            rafId = requestAnimationFrame(frame);
        }
        return {
            to: function (next, rest) {
                if (!cur) { cur = {}; for (var k in next) cur[k] = next.__from ? next.__from[k] : 0; }
                target = next;
                target.__rest = !!rest;
                if (!rafId) rafId = requestAnimationFrame(frame);
            },
        };
    }

    /* ---------- 照片卡 3D 倾斜（lerp 跟随） ---------- */
    document.querySelectorAll(".tilt-card").forEach(function (card) {
        if (!finePointer || reducedMotion) return;
        var follow = lerpFollow(card, function (el, s) {
            el.style.transform = "perspective(900px) rotateY(" + s.ry + "deg) rotateX(" + s.rx + "deg) scale(" + (1 + s.pop) + ")";
        });
        card.addEventListener("mousemove", function (e) {
            var rect = card.getBoundingClientRect();
            var px = (e.clientX - rect.left) / rect.width - 0.5;
            var py = (e.clientY - rect.top) / rect.height - 0.5;
            follow.to({ ry: px * 7, rx: py * -7, pop: 0.015 });
        });
        card.addEventListener("mouseleave", function () {
            follow.to({ ry: 0, rx: 0, pop: 0 }, true);
        });
    });

    /* ---------- 图片走廊：拖拽 + 惯性 + 自动漂移 + 无缝循环 ----------
       rAF 只在走廊可见时运行（IO 门控）；hover 时自动漂移平滑减速到 0，
       移开后再平滑恢复，拖拽结束的惯性也汇入同一速度模型 */
    var strip = document.getElementById("nf-strip");
    var track = document.getElementById("nf-strip-track");
    if (strip && track) {
        // 复制一份内容实现无缝循环
        track.innerHTML += track.innerHTML;

        var AUTO_V = reducedMotion ? 0 : -0.45;   // 自动漂移目标速度
        var x = 0;              // 当前位移
        var v = AUTO_V;         // 当前速度（惯性与自动漂移共用）
        var targetAuto = AUTO_V;
        var dragging = false;
        var hovering = false;
        var lastPointerX = 0;
        var half = 0;
        var running = false;
        var rafId = 0;

        function measure() { half = track.scrollWidth / 2; }
        measure();
        window.addEventListener("resize", measure);

        strip.addEventListener("pointerdown", function (e) {
            dragging = true;
            lastPointerX = e.clientX;
            v = 0;
            strip.classList.add("dragging");
            strip.setPointerCapture(e.pointerId);
        });
        strip.addEventListener("pointermove", function (e) {
            if (!dragging) return;
            var dx = e.clientX - lastPointerX;
            lastPointerX = e.clientX;
            x += dx;
            v = dx;             // 记录瞬时速度，松手后作为惯性初速
        });
        function endDrag() {
            dragging = false;
            strip.classList.remove("dragging");
        }
        strip.addEventListener("pointerup", endDrag);
        strip.addEventListener("pointercancel", endDrag);

        // hover 暂停自动漂移（细指针设备；拖拽中不受影响）
        if (finePointer) {
            strip.addEventListener("mouseenter", function () { hovering = true; });
            strip.addEventListener("mouseleave", function () { hovering = false; });
        }

        function stripTick() {
            if (!dragging) {
                targetAuto = hovering ? 0 : AUTO_V;
                // 速度向目标值指数逼近：惯性衰减与漂移启停共用一条曲线
                v += (targetAuto - v) * 0.055;
                x += v;
            }
            if (half > 0) {
                if (x <= -half) x += half;
                if (x > 0) x -= half;
            }
            track.style.transform = "translateX(" + x + "px)";
            if (running) rafId = requestAnimationFrame(stripTick);
        }
        function play() {
            if (running) return;
            running = true;
            rafId = requestAnimationFrame(stripTick);
        }
        function pause() {
            running = false;
            if (rafId) cancelAnimationFrame(rafId);
        }

        var inView = false;
        function syncRunning() {
            (inView && !document.hidden) ? play() : pause();
        }
        new IntersectionObserver(function (entries) {
            inView = entries[0].isIntersecting;
            syncRunning();
        }, { threshold: 0.02 }).observe(strip);
        document.addEventListener("visibilitychange", syncRunning);
    }

    /* ---------- 时间轴进度线（IO 门控 + rAF 节流：区块可见时才读布局） ---------- */
    var tlProgress = document.getElementById("nf-tl-progress");
    if (tlProgress) {
        var tlSection = tlProgress.closest(".nf-section");
        var tlTicking = false;

        function tlUpdate() {
            tlTicking = false;
            var rect = tlSection.getBoundingClientRect();
            var vh = window.innerHeight;
            var ratio = (vh * 0.85 - rect.top) / (rect.height + vh * 0.3);
            tlProgress.style.width = Math.max(0, Math.min(1, ratio)) * 100 + "%";
        }
        function tlOnScroll() {
            if (tlTicking) return;
            tlTicking = true;
            requestAnimationFrame(tlUpdate);
        }

        new IntersectionObserver(function (entries) {
            if (entries[0].isIntersecting) {
                window.addEventListener("scroll", tlOnScroll, { passive: true });
                tlOnScroll();
            } else {
                window.removeEventListener("scroll", tlOnScroll);
            }
        }, { rootMargin: "20% 0px 20% 0px" }).observe(tlSection);
    }

    /* ---------- 磁性按钮（lerp 跟随，离开时弹回） ---------- */
    document.querySelectorAll(".btn-magnet").forEach(function (btn) {
        if (!finePointer || reducedMotion) return;
        var follow = lerpFollow(btn, function (el, s) {
            el.style.transform = "translate(" + s.tx + "px," + s.ty + "px)";
        });
        btn.addEventListener("mousemove", function (e) {
            var rect = btn.getBoundingClientRect();
            follow.to({
                tx: (e.clientX - rect.left - rect.width / 2) * 0.22,
                ty: (e.clientY - rect.top - rect.height / 2) * 0.3,
            });
        });
        btn.addEventListener("mouseleave", function () { follow.to({ tx: 0, ty: 0 }, true); });
    });

    /* ---------- 招新视频：点击后才加载 B 站播放器 ---------- */
    var facade = document.getElementById("video-facade");
    if (facade) {
        facade.addEventListener("click", function load() {
            var iframe = document.createElement("iframe");
            iframe.src = facade.dataset.embed;
            iframe.allowFullscreen = true;
            iframe.setAttribute("allow", "autoplay; fullscreen");
            iframe.setAttribute("scrolling", "no");
            facade.innerHTML = "";
            facade.appendChild(iframe);
            facade.style.cursor = "default";
        }, { once: true });
    }

    /* ---------- 复制 QQ 群号 ---------- */
    var copyBtn = document.getElementById("copy-qq");
    if (copyBtn) {
        copyBtn.addEventListener("click", function () {
            var qq = copyBtn.dataset.qq;
            function done() {
                copyBtn.textContent = "已复制 ✓";
                if (!reducedMotion) {
                    copyBtn.classList.remove("copied");
                    void copyBtn.offsetWidth;
                    copyBtn.classList.add("copied");
                }
                setTimeout(function () {
                    copyBtn.textContent = "复制群号";
                    copyBtn.classList.remove("copied");
                }, 2000);
            }
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(qq).then(done);
            } else {
                var ta = document.createElement("textarea");
                ta.value = qq;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                done();
            }
        });
    }
})();
