/* 表单渐进增强：分步 fieldset + 条件字段 + 确认页回显。
   ==================================================================
   这是**纯增强**。被它接管的表单在 HTML 里本来就是完整可用的：所有 fieldset
   全部展开、一个提交按钮、一次 POST。脚本做的只有「一次只显示一段」。

   三条自我约束（踩过才写下来的）：

   1. **提交按钮始终在 DOM 里且始终可提交。** 绝不把「下一步」做成必经之路，
      也绝不 disabled 它 —— 脚本挂了、或者某一步的判断写错一次，用户就彻底
      交不了表。收起来（hidden）和禁用是两件事。
   2. **不依赖隐藏字段的原生校验。** 浏览器对 display:none 里的 required 会报
      "An invalid form control is not focusable"：有报错、界面上没有任何提示、
      用户只看到点了提交没反应。所以推进时自己校验当前段，提交时再全量兜一次，
      不合法就跳回出问题的那一段。
   3. **服务端回来的错误必须能被看见。** 表单 POST 失败重渲染时，出错的字段
      可能在第二段里 —— 如果初始化一律停在第一段，用户看到的是一张「没有任何
      问题」的表。所以初始化时定位到第一个带错误的段。

   ------------------------------------------------------------------
   标记契约：

     <form data-stepped-form>
       <ol data-step-dots><li>选方向</li><li>说说你</li><li>确认</li></ol>
       <fieldset data-step>…</fieldset>
       <fieldset data-step>…</fieldset>
       <fieldset data-step>
         <dl><dt>方向</dt><dd data-review-for="department"></dd></dl>
       </fieldset>
       <button type="button" data-step-prev hidden>上一步</button>
       <button type="button" data-step-next hidden>下一步</button>
       <button type="submit" data-step-submit>提交</button>
     </form>

   条件字段（和分步无关，可单独用）：

     <div data-show-when="id_specialty=custom">…</div>

   默认可见，脚本按当前值决定显隐 —— 同样是「没有 JS 时信息不丢」。 */
(function () {
    "use strict";

    var ERROR_HINTS = ".form-error, .has-error, [aria-invalid='true']";

    /** 一段里所有会参与校验的控件（隐藏域不算，它们没有可见的提示位置）。 */
    function fieldsOf(scope) {
        return [].slice.call(scope.querySelectorAll("input, select, textarea"))
            .filter(function (el) { return el.type !== "hidden" && !el.disabled; });
    }

    /** 找出这一组控件里第一个不合法的，并让浏览器把提示指到它上面。 */
    function firstInvalid(scope) {
        var bad = null;
        fieldsOf(scope).forEach(function (el) {
            if (!bad && !el.checkValidity()) bad = el;
        });
        return bad;
    }

    /** 把一个字段的当前值读成人话，用于确认页回显。 */
    function readable(form, name) {
        var nodes = [].slice.call(form.querySelectorAll('[name="' + name + '"]'));
        if (!nodes.length) return "";
        var first = nodes[0];

        if (first.type === "radio") {
            var picked = nodes.filter(function (el) { return el.checked; })[0];
            return picked ? labelTextFor(picked) : "";
        }
        if (first.type === "checkbox") {
            if (nodes.length > 1) {
                return nodes.filter(function (el) { return el.checked; })
                    .map(labelTextFor).join("、");
            }
            return first.checked ? "已勾选" : "";
        }
        if (first.tagName === "SELECT") {
            var opt = first.options[first.selectedIndex];
            // 「请选择学院」这类占位项的 value 是空串，不能当成填好了
            return opt && opt.value ? opt.textContent.trim() : "";
        }
        // 密码不回显原文，但要让用户知道确实填了
        if (first.type === "password") return first.value ? "已设置" : "";
        return (first.value || "").trim();
    }

    /** 取一个控件对应的可读文字：优先包裹它的 label，其次同 id 的 label。 */
    function labelTextFor(el) {
        var wrap = el.closest("label");
        if (wrap) return wrap.textContent.trim();
        if (el.id) {
            var lab = document.querySelector('label[for="' + el.id + '"]');
            if (lab) return lab.textContent.trim();
        }
        return (el.value || "").trim();
    }

    /* ---------------- 条件字段 ---------------- */

    function wireConditional(root) {
        var boxes = [].slice.call(root.querySelectorAll("[data-show-when]"));
        if (!boxes.length) return;

        boxes.forEach(function (box) {
            var spec = box.getAttribute("data-show-when") || "";
            var cut = spec.indexOf("=");
            if (cut < 0) return;
            var control = document.getElementById(spec.slice(0, cut));
            if (!control) return;
            var wanted = spec.slice(cut + 1).split("|");

            var apply = function () {
                var on = wanted.indexOf(control.value) !== -1;
                box.hidden = !on;
                // 藏起来的段不能参与原生校验（见文件头第 2 条）
                fieldsOf(box).forEach(function (el) {
                    if (on) {
                        if (el.dataset.wasRequired === "1") el.required = true;
                    } else {
                        el.dataset.wasRequired = el.required ? "1" : "0";
                        el.required = false;
                    }
                });
            };
            control.addEventListener("change", apply);
            apply();
        });
    }

    /* ---------------- 分步 ---------------- */

    function wireStepped(form) {
        var steps = [].slice.call(form.querySelectorAll("[data-step]"));
        if (steps.length < 2) return;

        var dotBox = form.querySelector("[data-step-dots]");
        var dots = dotBox ? [].slice.call(dotBox.children) : [];
        var btnPrev = form.querySelector("[data-step-prev]");
        var btnNext = form.querySelector("[data-step-next]");
        var btnSubmit = form.querySelector("[data-step-submit]");
        if (!btnPrev || !btnNext || !btnSubmit) return;

        var current = 0;

        function render() {
            steps.forEach(function (step, i) { step.hidden = i !== current; });
            dots.forEach(function (dot, i) {
                dot.classList.toggle("is-current", i === current);
                dot.classList.toggle("is-done", i < current);
            });
            var last = current === steps.length - 1;
            btnPrev.hidden = current === 0;
            btnNext.hidden = last;
            // 只是收起来，不是禁用 —— 见文件头第 1 条
            btnSubmit.hidden = !last;
            if (last) fillReview();
        }

        function fillReview() {
            [].slice.call(form.querySelectorAll("[data-review-for]")).forEach(function (cell) {
                var text = readable(form, cell.getAttribute("data-review-for"));
                // textContent 而不是 innerHTML：回显的是用户自己输入的内容
                cell.textContent = text || "（没填）";
                cell.classList.toggle("is-blank", !text);
            });
        }

        function go(delta) {
            var next = current + delta;
            if (next < 0 || next >= steps.length) return;
            if (delta > 0) {
                var bad = firstInvalid(steps[current]);
                if (bad) { bad.reportValidity(); return; }
            }
            current = next;
            render();
            // 分步之后表单变短，切换时把视线带回表单顶部
            form.scrollIntoView({ block: "nearest" });
        }

        btnPrev.addEventListener("click", function () { go(-1); });
        btnNext.addEventListener("click", function () { go(1); });

        // 兜底：真的提交时再全量校验一次，不合法就跳回出问题的那一段。
        // 正常流程走不到这里（推进时已逐段拦过），但错一次就是「点提交没反应」。
        form.addEventListener("submit", function (e) {
            for (var i = 0; i < steps.length; i++) {
                var bad = firstInvalid(steps[i]);
                if (bad) {
                    e.preventDefault();
                    current = i;
                    render();
                    bad.reportValidity();
                    return;
                }
            }
        });

        // 服务端错误优先：停在第一个带错误的段（见文件头第 3 条）
        for (var i = 0; i < steps.length; i++) {
            if (steps[i].querySelector(ERROR_HINTS)) { current = i; break; }
        }

        // 接管之后才关掉原生校验。**顺序很重要**：没有 JS 时三段全部展开，
        // 原生校验是可用且有用的，所以 HTML 里不能写 novalidate；一旦开始
        // 藏段落，原生校验就会去校验看不见的字段并报「not focusable」——
        // 有报错、没提示。校验从这一刻起由上面两处自己负责。
        form.noValidate = true;
        form.classList.add("is-stepped");
        render();
    }

    wireConditional(document);
    [].slice.call(document.querySelectorAll("[data-stepped-form]")).forEach(wireStepped);
})();
