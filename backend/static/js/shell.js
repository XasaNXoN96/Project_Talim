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
