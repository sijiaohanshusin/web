(() => {
    'use strict';
    const editor = document.querySelector('[data-work-form]');
    if (!editor) return;
    let dirty = false;
    const status = document.querySelector('[data-save-status]');
    editor.addEventListener('input', () => {
        dirty = true;
        status.textContent = '有未保存修改';
    });
    editor.addEventListener('submit', () => {
        dirty = false;
        status.textContent = '正在保存，请稍候';
        // Do not disable the submitter: its name/value selects save or preview.
    });
    window.addEventListener('beforeunload', event => {
        if (!dirty) return;
        event.preventDefault();
        event.returnValue = '';
    });
    document.querySelectorAll('[data-confirm]').forEach(form => {
        form.addEventListener('submit', event => {
            if (dirty) {
                event.preventDefault();
                window.alert('编辑区有未保存修改，请先保存，再操作撤回或删除。');
            } else if (!window.confirm(form.dataset.confirm)) {
                event.preventDefault();
            }
        });
    });
})();
