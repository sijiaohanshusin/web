(() => {
    'use strict';

    document.querySelectorAll('[data-member-picker]').forEach((picker) => {
        const input = picker.querySelector('[name="user_id"]');
        const list = picker.querySelector('[role="listbox"]');
        const status = picker.querySelector('[role="status"]');
        const filters = [...picker.querySelectorAll('[data-filter]')];
        let candidates = [];
        let active = -1;
        let timer;
        let controller;
        let generation = 0;
        let composing = false;
        let selected = false;

        picker.querySelector('[data-member-filters]').hidden = false;
        input.setAttribute('role', 'combobox');
        input.setAttribute('aria-autocomplete', 'list');
        input.setAttribute('aria-controls', list.id);
        input.setAttribute('aria-expanded', 'false');

        function close() {
            clearTimeout(timer);
            controller?.abort();
            generation += 1;
            list.hidden = true;
            input.setAttribute('aria-expanded', 'false');
            input.removeAttribute('aria-activedescendant');
            active = -1;
        }

        function highlight(index) {
            active = index;
            [...list.children].forEach((item, i) => item.setAttribute('aria-selected', String(i === index)));
            const item = list.children[index];
            if (item) {
                input.setAttribute('aria-activedescendant', item.id);
                item.scrollIntoView({block: 'nearest'});
            }
        }

        function choose(index) {
            const member = candidates[index];
            if (!member) return;
            // Canonical usernames are unique; never submit a display name for a chosen candidate.
            input.value = member.username;
            selected = true;
            close();
            status.textContent = `已选择：${member.name} · @${member.username}`
                + (member.student_id ? ` · 学号 ${member.student_id}` : '')
                + (member.is_active ? '' : ' · 账号已停用，任命不会激活账号');
            input.focus();
        }

        async function search() {
            clearTimeout(timer);
            controller?.abort();
            controller = new AbortController();
            const request = ++generation;
            const url = new URL(picker.dataset.searchUrl, window.location.origin);
            url.searchParams.set('q', input.value.trim());
            filters.forEach((filter) => url.searchParams.set(filter.dataset.filter, filter.value));
            status.textContent = '正在查找成员…';
            try {
                const response = await fetch(url, {
                    signal: controller.signal, credentials: 'same-origin', cache: 'no-store',
                    headers: {Accept: 'application/json'},
                });
                if (!response.ok || response.redirected) throw new Error('search-unavailable');
                const data = await response.json();
                // Ignore responses for older queries, including requests cancelled during JSON parsing.
                if (request !== generation) return;
                candidates = data.members;
                list.replaceChildren();
                active = -1;
                candidates.forEach((member, index) => {
                    const item = document.createElement('li');
                    item.id = `${list.id}-${index}`;
                    item.className = 'member-picker__option';
                    item.setAttribute('role', 'option');
                    item.setAttribute('aria-selected', 'false');
                    const name = document.createElement('span');
                    name.className = 'member-picker__name';
                    name.textContent = `${member.name} · @${member.username}`;
                    const detail = document.createElement('span');
                    detail.className = 'member-picker__detail';
                    detail.textContent = [
                        member.student_id ? `学号 ${member.student_id}` : '未填学号',
                        member.grade ? `${member.grade} 级` : '', member.college,
                        member.position ? `${member.position}（${member.term}）` : '尚未任命',
                        member.is_active ? '' : '账号已停用',
                    ].filter(Boolean).join(' · ');
                    item.append(name, detail);
                    item.addEventListener('mousedown', (event) => event.preventDefault());
                    item.addEventListener('click', () => choose(index));
                    list.append(item);
                });
                list.hidden = candidates.length === 0;
                input.setAttribute('aria-expanded', String(!list.hidden));
                input.removeAttribute('aria-activedescendant');
                status.textContent = candidates.length
                    ? `找到 ${data.has_more ? '超过 ' : ''}${candidates.length} 位成员，点击候选或用方向键选择。`
                        + (data.has_more ? '请继续输入或筛选以缩小范围。' : '')
                    : '没有符合条件的成员，请调整关键词或筛选条件。';
            } catch (error) {
                if (request !== generation || error.name === 'AbortError') return;
                close();
                status.textContent = '候选暂时无法加载。仍可手动填写完整用户名、学号或姓名后任命。';
            }
        }

        function schedule() {
            close();
            selected = false;
            status.textContent = '正在查找成员…';
            timer = setTimeout(search, 250);
        }

        input.addEventListener('compositionstart', () => { composing = true; close(); });
        input.addEventListener('compositionend', () => { composing = false; schedule(); });
        input.addEventListener('input', () => { if (!composing) schedule(); });
        input.addEventListener('focus', () => { if (!selected) schedule(); });
        filters.forEach((filter) => filter.addEventListener('change', () => {
            if (selected) input.value = '';
            schedule();
        }));
        input.addEventListener('keydown', (event) => {
            if (event.isComposing || composing) return;
            if (event.key === 'Escape') {
                close();
            } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                if (list.hidden) { search(); return; }
                const step = event.key === 'ArrowDown' ? 1 : -1;
                highlight(active < 0
                    ? (step > 0 ? 0 : candidates.length - 1)
                    : (active + step + candidates.length) % candidates.length);
            } else if (event.key === 'Enter' && !list.hidden && active >= 0) {
                event.preventDefault();
                choose(active);
            }
        });
        picker.addEventListener('focusout', (event) => {
            if (!picker.contains(event.relatedTarget)) close();
        });
    });
})();
