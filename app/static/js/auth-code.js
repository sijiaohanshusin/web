/* 邮箱验证码发送：按钮点击 -> AJAX -> 60 秒倒计时 */
(function () {
    "use strict";
    function getCsrf() {
        var m = document.cookie.match(/csrftoken=([^;]+)/);
        if (m) { return m[1]; }
        var el = document.querySelector('input[name=csrfmiddlewaretoken]');
        return el ? el.value : "";
    }

    document.querySelectorAll("[data-send-code]").forEach(function (btn) {
        var purpose = btn.getAttribute("data-send-code");
        var emailSel = btn.getAttribute("data-email") || "#id_email";
        var cooldown = 0, timer = null;

        function tick() {
            if (cooldown <= 0) {
                btn.disabled = false;
                btn.textContent = "获取验证码";
                clearInterval(timer); timer = null;
                return;
            }
            btn.textContent = cooldown + " 秒后重试";
            cooldown -= 1;
        }

        btn.addEventListener("click", function () {
            var emailEl = document.querySelector(emailSel);
            var email = emailEl ? emailEl.value.trim() : "";
            if (!email || email.indexOf("@") === -1) {
                alert("请先填写有效的邮箱地址");
                if (emailEl) { emailEl.focus(); }
                return;
            }
            btn.disabled = true;
            btn.textContent = "发送中…";
            var body = new URLSearchParams({ email: email, purpose: purpose });
            fetch("/accounts/send-code/", {
                method: "POST",
                headers: { "X-CSRFToken": getCsrf(), "Content-Type": "application/x-www-form-urlencoded" },
                body: body.toString(),
                credentials: "same-origin",
            }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
              .then(function (res) {
                  var msg = document.getElementById("code-msg");
                  if (msg) {
                      msg.textContent = res.d.msg || "";
                      msg.className = "form-help " + (res.d.ok ? "code-msg-ok" : "code-msg-err");
                  }
                  if (res.d.ok) {
                      cooldown = 60; tick(); timer = setInterval(tick, 1000);
                  } else {
                      btn.disabled = false; btn.textContent = "获取验证码";
                  }
              }).catch(function () {
                  btn.disabled = false; btn.textContent = "获取验证码";
                  alert("网络错误，请稍后再试");
              });
        });
    });
})();
