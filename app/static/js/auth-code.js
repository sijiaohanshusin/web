/* 邮箱验证码发送：点按钮 → AJAX → 60 秒冷却。
   ==================================================================
   这段的全部价值在于**把服务端说的话显示出来**。/accounts/send-code/ 会返回
   「该邮箱已注册」「当前网络请求验证码过多」「发送失败」这些真正有用的信息，
   而它们决定用户下一步该干什么。

   修掉的三个真实缺陷：

   1. 旧版把消息写进全局 `#code-msg`。注册表单里**没有这个元素**，于是所有失败
      原因在注册页一律不可见 —— 用户只看到按钮闪一下就恢复了，完全不知道是
      邮箱重了还是网断了。现在消息位就近找（`[data-code-msg]` 或按钮所在
      .form-group 里的 .form-help），找不到就地插一个。
   2. 冷却只存在内存里，刷新页面按钮就恢复可点，而服务端还在 60 秒冷却中 ——
      点了必然失败。现在把截止时间写进 sessionStorage，刷新后接着倒计时。
   3. 用 alert() 提示「请先填邮箱」。移动端 alert 是个模态框，还会把焦点抢走。
      改成就地提示 + 聚焦到邮箱框。 */
(function () {
    "use strict";

    var COOLDOWN = 60;
    var STORE_PREFIX = "esta:code:";

    function getCsrf() {
        var m = document.cookie.match(/csrftoken=([^;]+)/);
        if (m) { return m[1]; }
        var el = document.querySelector("input[name=csrfmiddlewaretoken]");
        return el ? el.value : "";
    }

    /** 就近找到（或建出）这颗按钮的消息位。 */
    function messageSlot(btn) {
        var group = btn.closest(".form-group") || btn.parentNode;
        var slot = group.querySelector("[data-code-msg]");
        if (slot) return slot;
        slot = document.createElement("small");
        slot.className = "form-help";
        slot.setAttribute("data-code-msg", "");
        // 放在错误提示之前，视觉上和字段说明同一层
        group.appendChild(slot);
        return slot;
    }

    function say(btn, text, ok) {
        var slot = messageSlot(btn);
        slot.textContent = text || "";
        slot.className = "form-help " + (ok ? "code-msg-ok" : "code-msg-err");
        // 服务端消息是操作结果，读屏软件要念出来
        slot.setAttribute("role", "status");
    }

    document.querySelectorAll("[data-send-code]").forEach(function (btn) {
        var purpose = btn.getAttribute("data-send-code");
        var emailSel = btn.getAttribute("data-email") || "#id_email";
        var label = btn.textContent.trim() || "获取验证码";
        var storeKey = STORE_PREFIX + purpose;
        var timer = null;

        function remaining() {
            var until = 0;
            try { until = parseInt(sessionStorage.getItem(storeKey) || "0", 10); } catch (e) { until = 0; }
            return Math.max(0, Math.ceil((until - Date.now()) / 1000));
        }

        function tick() {
            var left = remaining();
            if (left <= 0) {
                btn.disabled = false;
                btn.textContent = label;
                if (timer) { clearInterval(timer); timer = null; }
                return;
            }
            btn.disabled = true;
            btn.textContent = left + " 秒后重试";
        }

        function startCooldown() {
            try {
                sessionStorage.setItem(storeKey, String(Date.now() + COOLDOWN * 1000));
            } catch (e) { /* 隐私模式下写不进去，退化成仅本次有效 */ }
            tick();
            if (!timer) timer = setInterval(tick, 1000);
        }

        btn.addEventListener("click", function () {
            var emailEl = document.querySelector(emailSel);
            var email = emailEl ? emailEl.value.trim() : "";
            if (!email || email.indexOf("@") === -1) {
                say(btn, "请先填写有效的邮箱地址。", false);
                if (emailEl) emailEl.focus();
                return;
            }
            btn.disabled = true;
            btn.textContent = "发送中…";
            say(btn, "", true);

            fetch("/accounts/send-code/", {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrf(),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body: new URLSearchParams({ email: email, purpose: purpose }).toString(),
                credentials: "same-origin",
            }).then(function (r) {
                return r.json().then(function (d) { return { ok: r.ok, d: d }; });
            }).then(function (res) {
                say(btn, res.d.msg || "", !!res.d.ok);
                if (res.d.ok) {
                    startCooldown();
                } else {
                    btn.disabled = false;
                    btn.textContent = label;
                }
            }).catch(function () {
                btn.disabled = false;
                btn.textContent = label;
                say(btn, "网络错误，请稍后再试。", false);
            });
        });

        // 刷新后接着倒计时（服务端的冷却并不会因为刷新而重置）
        if (remaining() > 0) { tick(); timer = setInterval(tick, 1000); }
    });
})();
