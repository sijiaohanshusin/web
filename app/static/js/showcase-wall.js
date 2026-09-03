(() => {
    'use strict';
    const wall = document.getElementById('member-wall');
    if (!wall) return;
    const form = wall.querySelector('form');
    const feedback = document.getElementById('filter-feedback');
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const motion = window.ESTA?.motion;
    const animated = new Set();
    const observers = new Map();
    function reveal(root) {
        window.ESTA?.hydrateImageFades?.(root);
        if (!motion?.gsap || reduced.matches) return;
        root.querySelectorAll('.sc-card').forEach((card, index) => {
            const observer = motion.once(card, () => {
                observers.get(card)?.disconnect(); observers.delete(card);
                if (reduced.matches || !card.isConnected) return;
                animated.add(card);
                motion.gsap.fromTo(card, {opacity:0, y:14}, {opacity:1, y:0, duration:.6,
                    delay:(index % 3) * .065, ease:motion.EASE.rise, clearProps:'opacity,transform',
                    onComplete:() => animated.delete(card)});
            });
            if (observer) observers.set(card,observer);
        });
    }
    function stopMotion() {
        if (!reduced.matches || !motion?.gsap) return;
        animated.forEach(node => { motion.gsap.killTweensOf(node); motion.gsap.set(node, {clearProps:'opacity,transform'}); });
        animated.clear();
        observers.forEach(observer => observer.disconnect()); observers.clear();
    }
    reduced.addEventListener('change', stopMotion);
    if (motion?.scene) motion.scene('member-wall', () => {
        if (!reduced.matches && motion.gsap) {
            const heading = wall.querySelector('.sc-wall-heading');
            animated.add(heading);
            motion.gsap.fromTo(heading, {opacity:0, y:10}, {opacity:1, y:0, duration:.6, ease:motion.EASE.rise,
                clearProps:'opacity,transform', onComplete:() => animated.delete(heading)});
        }
        reveal(wall);
    }); else reveal(wall);

    let sequence = 0;
    let controller;
    let timer;
    let composing = false;
    function queryUrl() {
        const url = new URL(form.action, location.href);
        const params = new URLSearchParams(new FormData(form));
        for (const [key,value] of [...params]) if (!value || (key === 'sort' && value === 'cohort_desc')) params.delete(key);
        url.search = params.toString();
        return url;
    }
    function fillFilters(url) {
        for (const key of ['q','cohort','direction','position','sort']) {
            form.elements[key].value = url.searchParams.get(key) || (key === 'sort' ? 'cohort_desc' : '');
        }
    }
    async function update(url, historyMode = 'push', focus = false) {
        clearTimeout(timer);
        controller?.abort(); controller = new AbortController();
        const current = ++sequence;
        const old = document.getElementById('member-results');
        old.setAttribute('aria-busy','true');
        feedback.textContent = '正在查找伙伴…';
        try {
            const response = await fetch(url, {headers:{'X-Showcase-Partial':'1'}, credentials:'same-origin',
                cache:'no-store', signal:controller.signal});
            if (!response.ok) throw new Error();
            const doc = new DOMParser().parseFromString(await response.text(),'text/html');
            if (current !== sequence) return;
            const results = doc.getElementById('member-results');
            if (!results || !/^\d+$/.test(results.dataset.count)) throw new Error();
            old.querySelectorAll('.sc-card').forEach(node => { motion?.gsap?.killTweensOf(node); animated.delete(node); observers.get(node)?.disconnect(); observers.delete(node); });
            old.replaceWith(results);
            document.getElementById('member-count').textContent = results.dataset.count;
            if (historyMode === 'push' && url.href !== location.href) history.pushState(null,'',url);
            fillFilters(url);
            feedback.textContent = `找到 ${results.dataset.count} 位公开成员`;
            reveal(results);
            if (focus) results.focus({preventScroll:true});
        } catch (error) {
            if (error.name === 'AbortError' || current !== sequence) return;
            feedback.replaceChildren(document.createTextNode('暂时无法更新，原结果仍然保留。'));
            const retry = document.createElement('a'); retry.href = url.href; retry.textContent = '重新加载';
            feedback.append(' ',retry);
        } finally {
            if (current === sequence) document.getElementById('member-results').removeAttribute('aria-busy');
        }
    }
    form.addEventListener('submit', event => { event.preventDefault(); update(queryUrl()); });
    form.addEventListener('change', event => { if (event.target.tagName === 'SELECT') update(queryUrl()); });
    form.elements.q.addEventListener('compositionstart', () => { composing = true; clearTimeout(timer); controller?.abort(); sequence++; });
    form.elements.q.addEventListener('compositionend', () => { composing = false; schedule(); });
    function schedule() {
        clearTimeout(timer);
        // Invalidate immediately, not after the debounce: an older result must not win while typing.
        controller?.abort(); sequence++;
        if (!composing) timer = setTimeout(() => update(queryUrl()),300);
    }
    form.elements.q.addEventListener('input',schedule);
    wall.addEventListener('click', event => {
        const link = event.target.closest('a[data-wall-link]');
        if (!link || event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault(); update(new URL(link.href),'push',true);
    });
    window.addEventListener('popstate', () => { const url = new URL(location.href); fillFilters(url); update(url,'none'); });
})();
