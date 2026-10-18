/* Portal shell behaviour for server-rendered pages (sidebar collapse / mobile drawer). No data access. */
(function () {
  var body = document.body;
  var btn = document.getElementById('sbToggle');
  var scrim = document.querySelector('.scrim');
  function width() { return window.innerWidth; }
  try { if (localStorage.getItem('sbc') === '1' && width() >= 1200) body.classList.add('collapsed'); } catch (e) {}
  if (btn) btn.addEventListener('click', function () {
    if (width() >= 1200) {
      body.classList.toggle('collapsed');
      try { localStorage.setItem('sbc', body.classList.contains('collapsed') ? '1' : '0'); } catch (e) {}
    } else if (width() >= 768) { body.classList.toggle('sb-wide'); }
    else { body.classList.toggle('sb-open'); }
  });
  function closeDrawer() { body.classList.remove('sb-open', 'sb-wide'); }
  if (scrim) scrim.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeDrawer(); });
})();

/* ---- Design alignment (no data access, text is always inserted with textContent) ---- */
(function () {
  var T = window.TALIM || {};
  var content = document.getElementById('content');
  if (!content) return;
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; }
  function refresh() { if (T.refresh) T.refresh(); }

  /* breadcrumbs: Home > [active menu item] > page heading */
  var head = content.querySelector('.page-head'), h1 = head && head.querySelector('h1');
  var links = document.querySelectorAll('.sb-nav a'), home = links[0], active = document.querySelector('.sb-nav a.active');
  if (head && h1 && home && !content.querySelector('.crumbs') && active !== home) {
    var nav = el('nav', 'crumbs'); nav.setAttribute('aria-label', 'Breadcrumb');
    function crumb(text, href) { var n = href ? el('a', '', text) : el('span', '', text); if (href) n.setAttribute('href', href); nav.appendChild(n); }
    function sep() { var s = el('span', 'crumb-sep'); if (T.icon) s.innerHTML = T.icon('right', 'sm'); else s.textContent = '\u203a'; nav.appendChild(s); }
    var title = h1.textContent.trim(), mid = active ? active.textContent.trim() : '';
    crumb(home.textContent.trim(), home.getAttribute('href')); sep();
    if (mid && title.indexOf(mid) !== 0 && mid.indexOf(title) !== 0) { crumb(mid, active.getAttribute('href')); sep(); }
    crumb(title);
    head.parentNode.insertBefore(nav, head);
  }

  /* search fields get the magnifier of the design */
  document.querySelectorAll('input[type=search]').forEach(function (input) {
    if (input.closest('.search')) return;
    var wrap = el('span', 'search'); input.parentNode.insertBefore(wrap, input); wrap.appendChild(input);
    if (T.icon) wrap.insertAdjacentHTML('afterbegin', T.icon('search', 'sm'));
    input.classList.remove('input');
  });

  /* tables: remember each column heading so that rows can become cards on narrow screens */
  document.querySelectorAll('table.t').forEach(function (table) {
    var heads = Array.prototype.map.call(table.querySelectorAll('thead th'), function (th) { return th.textContent.trim(); });
    table.classList.add('stack-m');
    table.querySelectorAll('tbody tr').forEach(function (tr) {
      Array.prototype.forEach.call(tr.children, function (td, i) { if (heads[i]) td.setAttribute('data-label', heads[i]); });
    });
  });

  /* grid / list switch (news management) */
  document.querySelectorAll('.view-switch').forEach(function (sw) {
    var target = document.querySelector('.news-views'); if (!target) return;
    function set(mode) {
      target.setAttribute('data-mode', mode);
      sw.querySelectorAll('button').forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-view') === mode); });
      try { localStorage.setItem('newsView', mode); } catch (e) {}
    }
    sw.querySelectorAll('button').forEach(function (b) { b.addEventListener('click', function () { set(b.getAttribute('data-view')); }); });
    try { var saved = localStorage.getItem('newsView'); if (saved === 'grid' || saved === 'list') set(saved); } catch (e) {}
  });
  refresh();
})();
