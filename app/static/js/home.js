/* 首页动效：滚动渐入 / 数字滚动 / 鼠标视差 / 3D 倾斜 / 可拖拽走廊 /
   时间轴进度 / 光斑跟随 / 磁性按钮 / 视频点击加载 / 复制群号 */
(function () {
    "use strict";

    var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

    /* ---------- 滚动渐入（带交错延迟） ---------- */
    var revealObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add("is-visible");
                revealObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    document.querySelectorAll(".reveal").forEach(function (el, i) {
        el.style.transitionDelay = Math.min(i % 5, 3) * 90 + "ms";
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

    /* ---------- 照片卡 3D 倾斜 ---------- */
    document.querySelectorAll(".tilt-card").forEach(function (card) {
        if (!finePointer || reducedMotion) return;
        card.addEventListener("mousemove", function (e) {
            var rect = card.getBoundingClientRect();
            var px = (e.clientX - rect.left) / rect.width - 0.5;
            var py = (e.clientY - rect.top) / rect.height - 0.5;
            card.style.transform = "perspective(900px) rotateY(" + px * 7 + "deg) rotateX(" + py * -7 + "deg) scale(1.015)";
        });
        card.addEventListener("mouseleave", function () {
            card.style.transform = "";
        });
    });

    /* ---------- 图片走廊：拖拽 + 惯性 + 自动漂移 + 无缝循环 ---------- */
    var strip = document.getElementById("nf-strip");
    var track = document.getElementById("nf-strip-track");
    if (strip && track) {
        // 复制一份内容实现无缝循环
        track.innerHTML += track.innerHTML;

        var x = 0;             // 当前位移
        var vx = reducedMotion ? 0 : -0.45;  // 自动漂移速度
        var dragging = false;
        var lastPointerX = 0;
        var dragVx = 0;
        var half = 0;

        function measure() { half = track.scrollWidth / 2; }
        measure();
        window.addEventListener("resize", measure);

        strip.addEventListener("pointerdown", function (e) {
            dragging = true;
            lastPointerX = e.clientX;
            dragVx = 0;
            strip.classList.add("dragging");
            strip.setPointerCapture(e.pointerId);
        });
        strip.addEventListener("pointermove", function (e) {
            if (!dragging) return;
            var dx = e.clientX - lastPointerX;
            lastPointerX = e.clientX;
            x += dx;
            dragVx = dx;
        });
        function endDrag() {
            dragging = false;
            strip.classList.remove("dragging");
        }
        strip.addEventListener("pointerup", endDrag);
        strip.addEventListener("pointercancel", endDrag);

        (function stripTick() {
            if (!dragging) {
                // 惯性衰减 + 回归自动漂移
                dragVx *= 0.94;
                var auto = reducedMotion ? 0 : -0.45;
                x += Math.abs(dragVx) > 0.3 ? dragVx : auto;
            }
            if (half > 0) {
                if (x <= -half) x += half;
                if (x > 0) x -= half;
            }
            track.style.transform = "translateX(" + x + "px)";
            requestAnimationFrame(stripTick);
        })();
    }

    /* ---------- 时间轴进度线 ---------- */
    var tlProgress = document.getElementById("nf-tl-progress");
    if (tlProgress) {
        var tlSection = tlProgress.closest(".nf-section");
        window.addEventListener("scroll", function () {
            var rect = tlSection.getBoundingClientRect();
            var vh = window.innerHeight;
            var ratio = (vh * 0.85 - rect.top) / (rect.height + vh * 0.3);
            tlProgress.style.width = Math.max(0, Math.min(1, ratio)) * 100 + "%";
        }, { passive: true });
    }

    /* ---------- 资源卡：光斑跟随鼠标 ---------- */
    document.querySelectorAll(".nf-res-card").forEach(function (card) {
        if (!finePointer) return;
        card.addEventListener("mousemove", function (e) {
            var rect = card.getBoundingClientRect();
            card.style.setProperty("--mx", (e.clientX - rect.left) + "px");
            card.style.setProperty("--my", (e.clientY - rect.top) + "px");
        });
    });

    /* ---------- 磁性按钮 ---------- */
    document.querySelectorAll(".btn-magnet").forEach(function (btn) {
        if (!finePointer || reducedMotion) return;
        btn.addEventListener("mousemove", function (e) {
            var rect = btn.getBoundingClientRect();
            var px = e.clientX - rect.left - rect.width / 2;
            var py = e.clientY - rect.top - rect.height / 2;
            btn.style.transform = "translate(" + px * 0.22 + "px," + py * 0.3 + "px)";
        });
        btn.addEventListener("mouseleave", function () { btn.style.transform = ""; });
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
                setTimeout(function () { copyBtn.textContent = "复制群号"; }, 2000);
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
