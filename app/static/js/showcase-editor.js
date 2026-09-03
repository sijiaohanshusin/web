(() => {
    'use strict';
    const root = document.getElementById('showcase-editor');
    if (!root) return;
    const initial = JSON.parse(document.getElementById('showcase-bootstrap').textContent);
    let design = initial.draft;
    let revision = initial.revision;
    let assets = initial.assets;
    let target = 'card';
    let device = 'desktop';
    let dirty = false;
    let busy = false;
    let timer;
    let previewSequence = 0;
    let previewController;
    const form = document.getElementById('design-form');
    const message = document.getElementById('editor-message');
    const frame = document.getElementById('preview-frame');
    const container = document.getElementById('preview-container');
    const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
    const opts = initial.options;
    const el = (tag, text, attrs = {}) => {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
        return node;
    };
    function say(text, error = false) {
        message.textContent = text;
        message.dataset.error = String(error);
    }
    async function request(url, data, signal) {
        const isForm = data instanceof FormData;
        const response = await fetch(url, {method: 'POST', credentials: 'same-origin', cache: 'no-store', signal,
            headers: {'X-CSRFToken': csrf, ...(isForm ? {} : {'Content-Type': 'application/json'})},
            body: isForm ? data : JSON.stringify(data)});
        const result = await response.json().catch(() => ({error: '会话已失效或服务暂不可用，请保留当前内容后重新登录。'}));
        if (!response.ok) throw new Error(result.error || '操作未完成，请重试。');
        return result;
    }
    function changed() {
        dirty = true;
        document.getElementById('showcase-state').textContent = '有未保存修改 · 公开版本未改变';
        document.getElementById('publish-consent').checked = false;
        clearTimeout(timer);
        timer = setTimeout(() => preview().catch(handleError), 400);
    }
    function handleError(error) {
        if (error.name !== 'AbortError') say(error.message, true);
    }
    function select(choices, value, update) {
        const node = el('select');
        for (const [key, label] of Object.entries(choices)) node.append(el('option', label, {value: key}));
        node.value = value;
        node.addEventListener('change', () => { update(node.value); changed(); });
        return node;
    }
    function label(text, node) {
        const wrapper = el('label', text);
        wrapper.append(node);
        return wrapper;
    }
    function renderDesign(which) {
        const host = document.getElementById(`design-${which}`);
        host.replaceChildren();
        const model = design[which];
        const thumbnails = el('div', undefined, {class: 'se-templates'});
        for (const [value, title] of Object.entries(opts.templates)) {
            const radio = el('input', undefined, {type: 'radio', name: `${which}-template`, value});
            radio.checked = value === model.template;
            radio.addEventListener('change', () => { model.template = value; changed(); });
            const thumb = el('span', undefined, {class: `se-thumb se-thumb--${value}`, 'aria-hidden': 'true'});
            for (let i = 0; i < 4; i++) thumb.append(el('i'));
            const choice = el('label', undefined, {class: 'se-template'});
            choice.append(radio, thumb, el('span', title));
            thumbnails.append(choice);
        }
        host.append(thumbnails);
        const pair = el('div', undefined, {class: 'se-pair'});
        for (const [key, title, choices] of [['palette','配色',opts.palettes], ['texture','纹理',opts.textures], ['focus','图片焦点',opts.focus], ['avatar_shape','头像样式',opts.shapes]]) {
            pair.append(label(`${which === 'card' ? '卡片' : '个人页'}${title}`, select(choices, model[key], v => { model[key] = v; })));
        }
        host.append(pair, el('h3', '内容模块'));
        const all = which === 'card' ? opts.cardModules : opts.pageModules;
        const list = el('ul', undefined, {class: 'se-modules', 'aria-label': '启用模块并排序'});
        const ordered = [...model.modules, ...Object.keys(all).filter(k => !model.modules.includes(k))];
        let dragKey;
        function move(key, to) {
            const from = model.modules.indexOf(key);
            if (from < 0 || to < 0 || to >= model.modules.length) return;
            model.modules.splice(from, 1);
            model.modules.splice(to, 0, key);
            renderDesign(which);
            document.getElementById(`${which}-module-${key}`).focus();
            changed();
        }
        for (const key of ordered) {
            const index = model.modules.indexOf(key);
            const row = el('li', undefined, {class: 'se-module', draggable: index >= 0 ? 'true' : 'false'});
            const checkbox = el('input', undefined, {type: 'checkbox', id: `${which}-module-${key}`});
            checkbox.checked = index >= 0;
            checkbox.addEventListener('change', () => {
                if (checkbox.checked && model.modules.length >= (which === 'card' ? 2 : 8)) {
                    checkbox.checked = false; say('请先关闭一个模块，再启用新的模块。', true); return;
                }
                model.modules = checkbox.checked ? [...model.modules, key] : model.modules.filter(m => m !== key);
                renderDesign(which); changed();
            });
            const checkLabel = el('label'); checkLabel.append(checkbox, el('span', all[key])); row.append(checkLabel);
            for (const [offset, title] of [[-1,'上移'],[1,'下移']]) {
                const button = el('button', title, {type: 'button', 'aria-label': `${all[key]}${title}`});
                button.disabled = index < 0 || index + offset < 0 || index + offset >= model.modules.length;
                button.addEventListener('click', () => move(key, index + offset)); row.append(button);
            }
            row.addEventListener('dragstart', event => { dragKey = key; event.dataTransfer.setData('text/plain', key); });
            row.addEventListener('dragover', event => { if (index >= 0) event.preventDefault(); });
            row.addEventListener('drop', event => { event.preventDefault(); if (dragKey) move(dragKey, index); });
            list.append(row);
        }
        host.append(list);
    }
    function assetOptions(node, value) {
        node.replaceChildren(el('option', '不使用图片', {value: ''}));
        assets.forEach((asset, index) => node.append(el('option', `素材 ${index + 1} · ${asset.width} × ${asset.height}`, {value: asset.id})));
        node.value = value;
    }
    function field(title, value, update, maximum, multiline = false) {
        const node = el(multiline ? 'textarea' : 'input', undefined, {maxlength: String(maximum)});
        node.value = value;
        node.addEventListener('input', () => { update(node.value); changed(); });
        return label(title, node);
    }
    function imageSelect(value, update) {
        const node = el('select'); assetOptions(node, value);
        node.addEventListener('change', () => { update(node.value); changed(); });
        return label('选择素材', node);
    }
    function renderItems(kind) {
        const host = document.getElementById(`${kind}-list`); host.replaceChildren();
        design.content[kind].forEach((item, index) => {
            const row = el('div', undefined, {class:'se-row'}); row.append(el('h3', `第 ${index + 1} 项`));
            if (kind === 'works') {
                row.append(field('作品标题',item.title,v => {item.title=v;},60), field('作品说明',item.description,v => {item.description=v;},240,true), imageSelect(item.image,v => {item.image=v;}), field('作品外部链接（HTTPS）',item.url,v => {item.url=v;},600));
                const projects = document.getElementById('project-options').cloneNode(true); projects.removeAttribute('id'); projects.hidden = false; projects.value = item.project;
                projects.addEventListener('change', () => {item.project=projects.value; changed();}); row.append(label('或关联已公开站内作品',projects));
            } else if (kind === 'gallery') {
                row.append(imageSelect(item.image,v => {item.image=v;}), field('图片说明',item.caption,v => {item.caption=v;},100));
            } else {
                row.append(field('链接名称',item.label,v => {item.label=v;},40),field('HTTPS 地址',item.url,v => {item.url=v;},600));
            }
            const remove = el('button','移除这项',{type:'button'});
            remove.addEventListener('click', () => { design.content[kind].splice(index,1); renderItems(kind); changed(); }); row.append(remove); host.append(row);
        });
        document.querySelector(`[data-add=${kind}]`).disabled = design.content[kind].length >= 6;
    }
    function renderAssets() {
        for (const key of ['avatar','cover']) assetOptions(form.elements[key],design.content[key]);
        for (const kind of ['works','gallery']) renderItems(kind);
        const host = document.getElementById('asset-library'); host.replaceChildren();
        assets.forEach((asset,index) => {
            const item = el('div',undefined,{class:'se-asset'});
            item.append(el('img',undefined,{src:asset.url,alt:`素材 ${index + 1}`,loading:'lazy'}),el('span',`素材 ${index + 1}`));
            const remove = el('button','删除未使用素材',{type:'button'});
            remove.addEventListener('click',async () => {
                if (dirty) { say('请先保存草稿，再删除未使用的素材。',true); return; }
                try { const result = await request(`${root.dataset.action.replace('action/','')}assets/${asset.id}/delete/`,{}); assets=result.assets; renderAssets(); say('未使用素材已删除。'); } catch(error) {handleError(error);}
            }); item.append(remove); host.append(item);
        });
    }
    function fitFrame() {
        const width = target === 'card' ? (device === 'mobile' ? 360 : 400) : (device === 'mobile' ? 375 : 1000);
        const scale = Math.min(1,container.clientWidth / width);
        frame.style.width = `${width}px`;
        frame.style.transform = `scale(${scale})`;
        frame.style.left = `${Math.max(0,(container.clientWidth-width*scale)/2)}px`;
        try {
            frame.style.height = '1px';
            const height = frame.contentDocument.body.scrollHeight;
            if (height) { frame.style.height = `${height}px`; container.style.height = `${Math.ceil(height*scale)}px`; }
        } catch (_) { /* The frame is replaced atomically after each preview. */ }
    }
    frame.addEventListener('load',() => { frame.style.height='1px'; fitFrame(); frame.contentDocument?.fonts.ready.then(fitFrame); });
    new ResizeObserver(fitFrame).observe(container);
    async function preview() {
        clearTimeout(timer);
        previewController?.abort(); previewController = new AbortController();
        const sequence = ++previewSequence;
        const result = await request(root.dataset.action,{action:'preview',revision,design,target},previewController.signal);
        if (sequence !== previewSequence) return null;
        frame.srcdoc = result.document;
        say(dirty ? '预览已更新，修改尚未保存。' : '预览已更新，只有本人可见。');
        return result.ticket;
    }
    for (const key of ['nickname','cohort','direction','direction_detail']) {
        const node = form.elements[key]; node.value = design[key];
        node.addEventListener('input',() => {design[key]=node.value; changed();});
    }
    for (const key of ['intro','about','skills','tags','avatar','cover']) {
        const node = form.elements[key]; node.value = key === 'tags' ? design.content.tags.join('，') : design.content[key];
        node.addEventListener('input',() => { design.content[key] = key === 'tags' ? node.value.split(/[,，]/).map(v=>v.trim()).filter(Boolean) : node.value; changed(); });
    }
    function switchTarget(value) {
        target=value;
        document.querySelectorAll('[data-target]').forEach(button => { const selected=button.dataset.target===value; button.setAttribute('aria-selected',String(selected)); button.tabIndex=selected ? 0 : -1; });
        document.getElementById('design-card').hidden = value !== 'card'; document.getElementById('design-page').hidden = value !== 'page';
        document.getElementById('preview-label').textContent = value === 'card' ? '成员卡片预览' : '个人页面预览';
        preview().catch(handleError);
    }
    document.querySelectorAll('[data-target]').forEach(button => {
        button.addEventListener('click',() => switchTarget(button.dataset.target));
        button.addEventListener('keydown',event => { if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) { event.preventDefault(); const next=target==='card'?'page':'card'; document.querySelector(`[data-target=${next}]`).focus(); switchTarget(next); } });
    });
    document.querySelectorAll('[data-device]').forEach(button => button.addEventListener('click',() => { device=button.dataset.device; document.querySelectorAll('[data-device]').forEach(b=>b.setAttribute('aria-pressed',String(b===button))); fitFrame(); }));
    document.querySelectorAll('[data-add]').forEach(button => button.addEventListener('click',() => {
        const kind=button.dataset.add; if (design.content[kind].length>=6) return;
        design.content[kind].push(kind==='works'?{title:'',description:'',image:'',url:'',project:''}:kind==='gallery'?{image:'',caption:''}:{label:'',url:''});
        renderItems(kind); changed();
    }));
    async function upload(copy=false) {
        const data = new FormData();
        if (copy) data.set('copy_avatar','1');
        else { const file=document.getElementById('image-upload').files[0]; if (!file) return; data.set('image',file); }
        try { say('正在检查和处理图片。'); const result=await request(root.dataset.upload,data); assets=result.assets; renderAssets(); document.getElementById('image-upload').value=''; say('素材已加入私有素材库，请在选择框中使用。'); } catch(error) { handleError(error); }
    }
    document.getElementById('image-upload').addEventListener('change',()=>upload());
    document.getElementById('copy-avatar').addEventListener('click',()=>upload(true));
    document.getElementById('refresh-preview').addEventListener('click',()=>preview().catch(handleError));
    document.querySelectorAll('button[data-action]').forEach(button=>button.addEventListener('click',async()=>{
        if (busy) return;
        const operation=button.dataset.action;
        const consent=document.getElementById('publish-consent').checked;
        if (operation==='publish' && !consent) {say('请先阅读并勾选互联网公开说明。',true);return;}
        busy=true;
        const controls=[...form.querySelectorAll('input,select,textarea,button')];
        const disabled=controls.map(c=>c.disabled); controls.forEach(c=>{c.disabled=true;});
        try {
            clearTimeout(timer);
            const ticket=operation==='publish' ? await preview() : '';
            if (operation==='publish' && !ticket) throw new Error('预览仍在更新，请稍后重试。');
            const result=await request(root.dataset.action,{action:operation,revision,design,consent,ticket});
            revision=result.revision;
            if (operation!=='withdraw') dirty=false;
            document.getElementById('showcase-state').textContent=result.published?'已有公开版本':'私有草稿 · 尚未公开';
            document.getElementById('public-link').hidden=!result.published;
            document.getElementById('publish-consent').checked=false;
            say(result.message);
        } catch(error) {handleError(error);} finally {controls.forEach((c,i)=>{c.disabled=disabled[i];});busy=false;}
    }));
    form.addEventListener('submit',e=>e.preventDefault());
    window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
    renderDesign('card'); renderDesign('page'); renderAssets(); renderItems('links');
    preview().catch(handleError);
})();
