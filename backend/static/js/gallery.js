/* Photo viewer for real pictures of the gallery (the mock's own viewer only knows placeholders). Links marked data-lbx open here; without
   JavaScript they simply open the picture. Text goes in with textContent, never as HTML. */
(function () {
  'use strict';
  var items = Array.prototype.slice.call(document.querySelectorAll('[data-lbx]'));
  if (!items.length) return;
  var L = { uz: ['Yopish', 'Oldingi', 'Keyingi', 'Fotogalereya'], ru: ['Закрыть', 'Предыдущее', 'Следующее', 'Фотогалерея'], en: ['Close', 'Previous', 'Next', 'Photo gallery'] };
  var t = L[(document.documentElement.lang || 'uz').slice(0, 2)] || L.uz;
  var idx = 0, opener = null, box = document.createElement('div');
  box.className = 'lightbox';
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-modal', 'true');
  box.setAttribute('aria-label', t[3]);
  function btn(cls, label, text) {
    var b = document.createElement('button');
    b.type = 'button'; b.className = cls; b.setAttribute('aria-label', label); b.textContent = text;
    return b;
  }
  var close = btn('lb-close', t[0], '×'), prev = btn('lb-prev', t[1], '‹'), next = btn('lb-next', t[2], '›');
  var stage = document.createElement('div'); stage.className = 'stage lbx';
  var img = document.createElement('img'); stage.appendChild(img);
  var cap = document.createElement('div'); cap.className = 'lb-count';
  box.appendChild(close); box.appendChild(prev); box.appendChild(stage); box.appendChild(next); box.appendChild(cap);
  document.body.appendChild(box);
  function show(i) {
    idx = (i + items.length) % items.length;
    var a = items[idx], c = a.getAttribute('data-caption') || '';
    img.src = a.getAttribute('href'); img.alt = c;
    cap.textContent = (idx + 1) + ' / ' + items.length + (c ? ' — ' + c : '');
  }
  function open(i, from) { opener = from; box.classList.add('open'); show(i); close.focus(); }
  function shut() { box.classList.remove('open'); img.removeAttribute('src'); if (opener) opener.focus(); }
  items.forEach(function (a, i) { a.addEventListener('click', function (e) { e.preventDefault(); open(i, a); }); });
  close.addEventListener('click', shut);
  prev.addEventListener('click', function () { show(idx - 1); });
  next.addEventListener('click', function () { show(idx + 1); });
  box.addEventListener('click', function (e) { if (e.target === box) shut(); });
  document.addEventListener('keydown', function (e) {
    if (!box.classList.contains('open')) return;
    if (e.key === 'Escape') shut();
    else if (e.key === 'ArrowRight') show(idx + 1);
    else if (e.key === 'ArrowLeft') show(idx - 1);
  });
})();
