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
                // 区块里的数字跟着同一个触发源启动。分镜 02 的叙事是「扫描线扫过、
                // 数值定格」，而扫描线是挂在 .is-visible 上的 CSS 动画 —— 如果数字
                // 用另一个 IntersectionObserver（阈值还不一样）自己触发，两者的先后
                // 就不确定了，慢慢滚和快速滚会看到完全不同的顺序。
                startCountersIn(entry.target);
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
        // 幂等：同一个数字可能被「所在区块可见」和「数字自己可见」两条路都点到
        if (el.dataset.counted) return;
        el.dataset.counted = "1";
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

    /** 启动某个区块里的所有数字。data-delay 用来对齐扫描线的节拍。 */
    function startCountersIn(root) {
        var list = root.classList.contains("counter")
            ? [root] : root.querySelectorAll(".counter");
        Array.prototype.forEach.call(list, function (el) {
            var delay = parseInt(el.dataset.delay, 10) || 0;
            if (delay > 0 && !reducedMotion) {
                setTimeout(function () { animateCounter(el); }, delay);
            } else {
                animateCounter(el);
            }
        });
    }

    // 兜底：不在任何 .reveal 区块里的数字仍然按自身可见性触发
    var counterObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                animateCounter(entry.target);
                counterObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.4 });
    document.querySelectorAll(".counter").forEach(function (el) {
        // 在 .reveal 区块里的数字由区块的可见性统一驱动，这里必须让开。
        // 否则两个观察器抢着触发，而这一个不带 data-delay —— 大数字体量很大，
        // 它的 0.4 阈值往往比区块的 0.12 先满足，于是 820ms 的延迟被整个绕过，
        // 扫描线和数字同时开始（实测间隔只有 28ms，叙事全丢）。
        if (el.closest(".reveal")) return;
        counterObserver.observe(el);
    });

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
        /* 复制一份内容实现无缝循环。
           用 cloneNode 而不是 track.innerHTML += track.innerHTML：后者会把整个
           子树重新解析一遍，原有节点连同监听器全部作废，只剩下类名 —— 懒加载
           淡入的 .img-fade（opacity:0）就此永久留在那儿，整条走廊的图片不可见。
           克隆保留原节点及其监听器；克隆出来的那批再交给 hydrateImageFades
           重新接线。 */
        Array.prototype.slice.call(track.children).forEach(function (node) {
            track.appendChild(node.cloneNode(true));
        });
        if (window.ESTA && window.ESTA.hydrateImageFades) {
            window.ESTA.hydrateImageFades(track);
        }

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

        var tlLine = tlProgress.parentElement;
        var tlPads = tlSection.querySelectorAll(".nf-tl-num");

        function tlUpdate() {
            tlTicking = false;
            var rect = tlSection.getBoundingClientRect();
            var vh = window.innerHeight;
            var ratio = (vh * 0.85 - rect.top) / (rect.height + vh * 0.3);
            ratio = Math.max(0, Math.min(1, ratio));
            tlProgress.style.width = ratio * 100 + "%";

            // 电流流过哪个焊盘，那个就点亮。位置靠实测而不是按列数算：
            // 栅格列宽、间距、两端 2% 内缩都会影响焊盘落在主干的哪个比例上，
            // 写死数字改一次布局就错一次。
            var trunk = tlLine.getBoundingClientRect();
            if (trunk.width <= 0) return;   // 窄屏主干是 display:none，交给 .reveal
            Array.prototype.forEach.call(tlPads, function (pad) {
                var box = pad.getBoundingClientRect();
                var at = (box.left + box.width / 2 - trunk.left) / trunk.width;
                pad.classList.toggle("is-live", ratio >= at);
            });
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

    /* ---------- 招新视频：点击后才加载 B 站播放器 ----------
       监听器挂在**那颗真按钮**上，外层 div 只是顺带给鼠标一个大靶子。
       原来只挂在 div 上：键盘用户按 Enter 其实也能用（button 的 click 冒泡上去），
       但无障碍树里这一块的入口是个没有角色的 div，读屏软件读不出「这是可以按的」，
       而按钮自己反倒没有任何行为。真按钮是入口，div 是便利 —— 顺序不能倒。 */
    var facade = document.getElementById("video-facade");
    if (facade) {
        var facadeLoaded = false;
        function loadBiliPlayer(e) {
            if (facadeLoaded) return;
            facadeLoaded = true;
            if (e) e.preventDefault();
            var iframe = document.createElement("iframe");
            iframe.src = facade.dataset.embed;
            iframe.allowFullscreen = true;
            iframe.setAttribute("allow", "autoplay; fullscreen");
            iframe.setAttribute("scrolling", "no");
            iframe.setAttribute("title", "招新宣传视频");
            facade.innerHTML = "";
            facade.appendChild(iframe);
            facade.style.cursor = "default";
        }
        var playBtn = facade.querySelector("[data-video-play]");
        if (playBtn) playBtn.addEventListener("click", loadBiliPlayer);
        // div 上仍然挂一份：点封面任意位置都能播。按钮的 click 冒泡到这里时
        // facadeLoaded 已经是 true，所以不会装两个 iframe。
        facade.addEventListener("click", loadBiliPlayer);
    }

    /* 招新截止倒计时挪到 site.js：招新落地页也要用，而 home.js 只在首页加载。 */

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
