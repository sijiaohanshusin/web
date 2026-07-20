/* Markdown 编辑器图片上传（公告/活动表单共用） */
(function () {
    "use strict";
    var input = document.getElementById("md-img-input");
    var status = document.getElementById("md-img-status");
    var body = document.getElementById("post-body");
    if (!input || !body) return;

    input.addEventListener("change", function () {
        var file = input.files[0];
        if (!file) return;
        status.textContent = "上传中…";
        var data = new FormData();
        data.append("image", file);
        fetch(input.getAttribute("data-upload-url"), {
            method: "POST",
            credentials: "same-origin",
            headers: { "X-CSRFToken": document.querySelector('input[name="csrfmiddlewaretoken"]').value },
            body: data
        }).then(function (r) { return r.json(); }).then(function (res) {
            if (!res.ok) { status.textContent = res.msg || "上传失败"; return; }
            var md = "\n![图片](" + res.url + ")\n";
            var start = body.selectionStart || body.value.length;
            body.value = body.value.slice(0, start) + md + body.value.slice(start);
            status.textContent = "已插入图片";
            input.value = "";
        }).catch(function () { status.textContent = "上传失败，请重试"; });
    });
})();
