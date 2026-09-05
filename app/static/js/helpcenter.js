(() => {
  'use strict';
  const article = document.querySelector('[data-help-article]');
  if (!article) return;
  const chapters = document.querySelector('.hc-sidebar details');
  if (chapters) chapters.open = !matchMedia('(max-width: 1023px)').matches;
  const key = 'heuesta-help:' + article.dataset.helpArticle + ':' + article.dataset.helpVersion;
  const boxes = [...article.querySelectorAll('[data-checkpoint]')];
  const status = article.querySelector('.hc-check-status');
  let store;
  try { store = article.dataset.helpArticle.startsWith('admin/') ? sessionStorage : localStorage; } catch {}
  try { const saved = JSON.parse(store.getItem(key) || '[]'); boxes.forEach((box, i) => box.checked = saved.includes(i)); } catch {}
  function update(save = true) {
    const completed = boxes.flatMap((box, i) => box.checked ? [i] : []);
    status.textContent = `已核对 ${completed.length} / ${boxes.length} 项。此记录不会操作网站数据。`;
    if (save) { try { store.setItem(key, JSON.stringify(completed)); } catch {} }
  }
  boxes.forEach(box => box.addEventListener('change', () => update()));
  article.querySelector('[data-reset-checks]')?.addEventListener('click', () => { boxes.forEach(box => box.checked = false); update(); });
  update(false);
  article.querySelectorAll('.hc-prose img').forEach(img => {
    const link = document.createElement('a'); link.href = img.src; link.target = '_blank'; link.rel = 'noopener';
    link.setAttribute('aria-label', '放大截图：' + img.alt); img.replaceWith(link); link.append(img);
  });
})();
