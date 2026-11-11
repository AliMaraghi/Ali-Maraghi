/* Progressive enhancement only. No network writes, analytics or external assets. */
(() => {
  'use strict';
  const root = document.documentElement;
  const panels = Array.from(document.querySelectorAll('.panel'));
  const links = Array.from(document.querySelectorAll('[data-section]'));
  const safeGet = key => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const safeSet = (key, value) => { try { localStorage.setItem(key, value); } catch (_) { /* Private mode: no persistence. */ } };
  const language = value => {
    const selected = value === 'fa' ? 'fa' : 'en';
    root.lang = selected; root.dir = selected === 'fa' ? 'rtl' : 'ltr';
    const search = document.getElementById('timeline-search');
    if (search) { search.placeholder = selected === 'fa' ? 'کامیت، شناسه یا رویداد…' : 'Commit, trace, event…'; search.setAttribute('aria-label', selected === 'fa' ? 'جست‌وجوی رویدادها' : 'Search timeline'); }
    safeSet('apex-language', selected);
  };
  const showPanel = () => {
    const key = location.hash.slice(1) || document.body.dataset.initial || 'overview';
    const selected = panels.find(panel => panel.id === key) || panels[0];
    panels.forEach(panel => panel.classList.toggle('active', panel === selected));
    links.forEach(link => {
      if (link.dataset.section === selected.id) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    document.title = 'APEX · ' + selected.querySelector('h2').textContent.trim();
  };
  language(safeGet('apex-language'));
  const savedTheme = safeGet('apex-theme');
  if (savedTheme === 'light' || savedTheme === 'dark') root.dataset.theme = savedTheme;
  document.getElementById('language')?.addEventListener('click', () => language(root.lang === 'fa' ? 'en' : 'fa'));
  document.getElementById('theme')?.addEventListener('click', () => {
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark'; safeSet('apex-theme', root.dataset.theme);
  });
  document.getElementById('detail-mode')?.addEventListener('click', event => {
    const expanded = event.currentTarget.getAttribute('aria-pressed') !== 'true';
    event.currentTarget.setAttribute('aria-pressed', String(expanded));
    document.querySelectorAll('details.technical').forEach(item => { item.open = expanded; });
  });
  document.getElementById('refresh')?.addEventListener('click', () => location.reload());
  document.getElementById('timeline-search')?.addEventListener('input', event => {
    const query = event.target.value.toLocaleLowerCase().trim(); let visible = 0;
    document.querySelectorAll('.timeline-event').forEach(item => {
      const matched = item.textContent.toLocaleLowerCase().includes(query);
      item.hidden = !matched; if (matched) visible += 1;
    });
    const empty = document.getElementById('timeline-empty'); if (empty) empty.hidden = visible > 0 || !query;
  });
  window.addEventListener('hashchange', showPanel);
  if (panels.length) { showPanel(); root.classList.add('js-ready'); }
})();
