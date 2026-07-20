/* 内测反馈弹窗：打开/关闭 + AJAX 提交到 /feedback/ */
(function () {
    "use strict";
    var fab = document.getElementById("beta-fab");
    var mask = document.getElementById("fb-mask");
    if (!fab || !mask) { return; }

    var form = document.getElementById("fb-form");
    var content = document.getElementById("fb-content");
    var msg = document.getElementById("fb-msg");
    var submitBtn = document.getElementById("fb-submit");

    function open() {
        mask.classList.remove("closing");
        mask.hidden = false;
        document.body.style.overflow = "hidden";
        setTimeout(function () { content.focus(); }, 50);
    }
    function close() {
        if (mask.hidden || mask.classList.contains("closing")) return;
        var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        function finish() {
            mask.classList.remove("closing");
            mask.hidden = true;
            document.body.style.overflow = "";
            msg.hidden = true;
        }
        if (reduced) { finish(); return; }
        // 播放缩退动画，结束后再真正隐藏（超时兜底）
        mask.classList.add("closing");
        var done = false;
        mask.addEventListener("animationend", function handler() {
            if (done) return;
            done = true;
            mask.removeEventListener("animationend", handler);
            finish();
        });
        setTimeout(function () { if (!done) { done = true; finish(); } }, 320);
    }

    fab.addEventListener("click", open);
    document.getElementById("fb-close").addEventListener("click", close);
    mask.addEventListener("click", function (e) { if (e.target === mask) { close(); } });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !mask.hidden) { close(); } });

    function show(text, ok) {
        msg.hidden = false;
        msg.textContent = text;
        msg.className = "fb-msg " + (ok ? "fb-msg-ok" : "fb-msg-err");
    }

    form.addEventListener("submit", function (e) {
        e.preventDefault();
        var text = content.value.trim();
        if (text.length < 5) { show("内容太短了，请描述得具体一点。", false); return; }

        submitBtn.disabled = true;
        submitBtn.textContent = "提交中…";

        var body = new URLSearchParams();
        body.set("content", text);
        body.set("page", location.href);
        var contact = document.getElementById("fb-contact");
        if (contact) { body.set("contact", contact.value.trim()); }
        var csrf = form.querySelector('input[name=csrfmiddlewaretoken]');

        fetch("/feedback/", {
            method: "POST",
            headers: {
                "X-CSRFToken": csrf ? csrf.value : "",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: body.toString(),
            credentials: "same-origin",
        }).then(function (r) { return r.json(); })
          .then(function (d) {
              show(d.msg, d.ok);
              if (d.ok) {
                  content.value = "";
                  setTimeout(close, 1600);
              }
          })
          .catch(function () { show("网络错误，请稍后再试。", false); })
          .finally(function () {
              submitBtn.disabled = false;
              submitBtn.textContent = "提交反馈";
          });
    });
})();
