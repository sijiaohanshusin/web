/* ============================================================
   分镜 01「会标是一块真的电路板」
   ------------------------------------------------------------
   滚动驱动 3D 会标按真实 PCB 工艺逐层被造出来：
       基板 → 蚀刻铜箔 → 沉金焊盘 → 覆阻焊 → 印丝印 → 通电
   左侧文案随之逐条点亮，最后一段让电流跑一遍走线。

   两个刻意的做法：

   1) 钉住用 CSS position:sticky，不用 ScrollTrigger 的 pin。
      pin 会插入 pin-spacer 改动 DOM 结构，与 Lenis 平滑滚动配合时容易出
      尺寸抖动；sticky 是浏览器原生行为，ScrollTrigger 只负责报进度。

   2) 姿态与脉冲全部用 immediate 模式写入，不走阻尼。
      滚动位置就是权威值，再叠一层阻尼会让模型滞后于滚动条，
      快速滚动或往回拖时表现为"追不上"。

   降级：本场景标了 needsWebGL，所以 WebGL 不可用或 prefers-reduced-motion
   时整段不注册 —— 区块保持普通文档流高度，显示内联 SVG 会标与完整的工艺
   清单，信息一条不少。3D 真正挂载成功后才给舞台加 .is-3d 隐藏 SVG，
   所以模块加载失败也不会两头空。
   ============================================================ */
(function () {
    "use strict";

    var motion = window.ESTA && window.ESTA.motion;
    if (!motion) return;

    motion.scene("logo-forge", function (m) {
        var section = document.getElementById("nf-forge");
        var stage = document.getElementById("nf-forge-stage");
        if (!section || !stage || !m.ScrollTrigger) return;

        var steps = [].slice.call(section.querySelectorAll("[data-forge-step]"));
        var handle = null;
        var progress = 0;

        // 制造阶段占前 84%，最后 16% 留给通电
        var FORGE_END = 0.84;

        function apply(p) {
            progress = p;
            if (!handle) return;

            var forge = Math.min(1, p / FORGE_END);
            handle.setAssembly(forge);

            // 起手带一点俯仰与偏转看得出是立体的，收尾转正对着观众
            var settle = Math.max(0, (p - 0.62) / 0.38);   // 后段逐渐归正
            var ease = settle * settle * (3 - 2 * settle);
            handle.setOrientation(-0.34 * (1 - ease), 0.30 * (1 - ease), true);

            // 收尾通电：脉冲头随滚动推进，可来回擦洗
            if (p > FORGE_END) {
                var t = (p - FORGE_END) / (1 - FORGE_END);
                handle.setPulse(-0.06 + t * 1.16);
            } else {
                handle.setPulse(-1);
            }

            highlight(forge);
        }

        /**
         * 按制造进度点亮工艺步骤。
         *
         * 3D 的阶段窗口是刻意重叠的（避免出现某层停住等下一层的死点），
         * 但文字清单同时高亮两条会像 bug。所以文字用"最后一个已开始的阶段"
         * 这条单一归属规则：当前只有一条，之前的全部记为已完成，
         * 读起来就是一份正在推进的工序单。
         */
        function highlight(forge) {
            if (!handle) return;
            var stages = handle.assemblyStages;

            var activeIndex = -1;
            for (var i = 0; i < steps.length; i++) {
                var range = stages[steps[i].getAttribute("data-forge-step")];
                if (range && forge >= range[0]) activeIndex = i;
            }
            // 全部走完后不再保留"当前"，整份清单都是已完成
            var lastRange = stages[steps[steps.length - 1].getAttribute("data-forge-step")];
            var allDone = lastRange && forge >= lastRange[1];

            for (var j = 0; j < steps.length; j++) {
                steps[j].classList.toggle("is-active", !allDone && j === activeIndex);
                steps[j].classList.toggle("is-done", allDone || j < activeIndex);
            }
        }

        m.ScrollTrigger.create({
            trigger: section,
            start: "top top",
            end: "bottom bottom",
            scrub: true,
            onUpdate: function (self) { apply(self.progress); },
        });

        // 3D 按需加载。失败不影响页面：舞台不会加 .is-3d，内联 SVG 继续显示。
        import("esta/logo-3d").then(function (mod) {
            return mod.mountLogo3D(stage, {
                // 会标 SVG 就在舞台里（作为兜底显示），直接拿它当几何来源，
                // 不用再发一次网络请求
                source: "#nf-forge-stage [data-esta-logo]",
                dpr: m.caps.dpr,
                autoRotate: false,
                showBoard: true,
            });
        }).then(function (h) {
            handle = h;
            stage.classList.add("is-3d");
            apply(progress);            // 立刻对齐当前滚动位置，避免闪一下初始态
            m.ScrollTrigger.refresh();
        }).catch(function (err) {
            if (window.console) {
                console.warn("[logo-forge] 3D 会标加载失败，保留 SVG 兜底：", err);
            }
        });
    }, { needsWebGL: true });
})();
