/* Native scrolling remains available when JavaScript is disabled. */
(() => {
    'use strict';
    document.querySelectorAll('.dash-table-wrap').forEach((region, index) => {
        const table = region.querySelector('table');
        if (!table) return;
        const id = region.id || `dashboard-table-${index}`;
        region.id = id;
        const controls = document.createElement('div');
        controls.className = 'dash-scroll-controls';
        controls.hidden = true;
        const hint = document.createElement('span');
        hint.id = `${id}-hint`;
        hint.textContent = '左右滑动查看其余列，也可聚焦表格后使用方向键。';
        controls.append(hint);
        const buttons = document.createElement('div');
        buttons.className = 'dash-scroll-buttons';
        const makeButton = (label, text, direction) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn btn-outline btn-sm';
            button.setAttribute('aria-label', label);
            button.setAttribute('aria-controls', id);
            button.textContent = text;
            button.addEventListener('click', () => {
                region.scrollBy({ left: direction * region.clientWidth * 0.7, behavior: 'instant' });
            });
            buttons.append(button);
            return button;
        };
        const previous = makeButton('向左查看表格', '向左', -1);
        const next = makeButton('向右查看表格', '向右', 1);
        controls.append(buttons);
        region.before(controls);

        const update = () => {
            const maximum = region.scrollWidth - region.clientWidth;
            const overflow = maximum > 1;
            controls.hidden = !overflow;
            region.classList.toggle('has-horizontal-scroll', overflow);
            if (overflow) {
                region.setAttribute('tabindex', '0');
                region.setAttribute('role', 'region');
                region.setAttribute('aria-label', `${document.querySelector('.dash-top h1')?.textContent || '管理'}表格 ${index + 1}`);
                region.setAttribute('aria-describedby', hint.id);
            } else {
                ['tabindex', 'role', 'aria-label', 'aria-describedby'].forEach(name => region.removeAttribute(name));
            }
            previous.disabled = region.scrollLeft <= 1;
            next.disabled = region.scrollLeft >= maximum - 1;
        };
        region.addEventListener('scroll', update, { passive: true });
        region.addEventListener('keydown', event => {
            // Never intercept arrows used in a nested input or select.
            if (event.target !== region || !region.classList.contains('has-horizontal-scroll')) return;
            const destinations = {
                ArrowLeft: region.scrollLeft - 120,
                ArrowRight: region.scrollLeft + 120,
                Home: 0,
                End: region.scrollWidth,
            };
            if (!(event.key in destinations)) return;
            event.preventDefault();
            region.scrollTo({ left: destinations[event.key], behavior: 'instant' });
        });
        if ('ResizeObserver' in window) {
            const observer = new ResizeObserver(update);
            observer.observe(region);
            observer.observe(table);
        } else {
            window.addEventListener('resize', update);
        }
        update();
    });
    // Hide the fallback only after controls initialize, including script-blocked browsers.
    document.querySelectorAll('.dash-table-fallback').forEach(note => { note.hidden = true; });
})();
