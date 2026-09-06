(() => {
  'use strict';
  for (const group of document.querySelectorAll('[data-people-set]')) {
    const total = group.querySelector('[name="people-TOTAL_FORMS"]');
    const button = group.querySelector('[data-add-person]');
    const rows = group.querySelector('[data-people-rows]');
    const template = group.querySelector('[data-person-template]');
    const status = group.querySelector('[data-people-status]');
    const enhance = (root) => {
      for (const field of root.querySelectorAll('[name$="-username"]')) {
        if (field.dataset.lookupReady) continue;
        field.dataset.lookupReady = 'true';
        const list = document.createElement('datalist');
        list.id = `${field.id}-candidates`;
        field.setAttribute('list', list.id);
        field.setAttribute('autocomplete', 'off');
        field.after(list);
        let timer, pending, serial = 0;
        const lookup = (event) => {
          clearTimeout(timer);
          pending?.abort();
          const ticket = ++serial;
          list.replaceChildren();
          if (event?.isComposing || field.value.trim().length < 2) return;
          timer = setTimeout(async () => {
            pending = new AbortController();
            try {
              const url = new URL(group.dataset.lookup, location.origin);
              url.searchParams.set('q', field.value.trim());
              const response = await fetch(url, {signal: pending.signal, credentials: 'same-origin'});
              if (!response.ok) throw new Error('lookup');
              const data = await response.json();
              if (ticket !== serial) return;
              for (const username of data.usernames) {
                const option = document.createElement('option');
                option.value = username;
                list.append(option);
              }
            } catch (error) {
              if (error.name !== 'AbortError' && ticket === serial) status.textContent = '候选暂时不可用，仍可填写准确用户名或稍后再关联。';
            }
          }, 300);
        };
        field.addEventListener('input', lookup);
        field.addEventListener('compositionend', lookup);
      }
    };
    enhance(rows);
    button.hidden = false;
    button.addEventListener('click', () => {
      const index = Number(total.value);
      if (index >= 20) { status.textContent = '最多 20 人；可勾选移除后保存，再添加。'; return; }
      const fragment = template.content.cloneNode(true);
      for (const element of fragment.querySelectorAll('[name], [id], [for]')) {
        for (const attr of ['name', 'id', 'for']) {
          if (element.hasAttribute(attr)) element.setAttribute(attr, element.getAttribute(attr).replaceAll('__prefix__', String(index)));
        }
      }
      rows.append(fragment);
      enhance(rows);
      total.value = String(index + 1);
      rows.lastElementChild.querySelector('[name$="-name"]').focus();
      status.textContent = `已添加第 ${index + 1} 行，请填写公开署名。`;
    });
  }
})();
