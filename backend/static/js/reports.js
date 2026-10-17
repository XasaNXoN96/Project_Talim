/* Report page: shows a "preparing" state on the export buttons (the download itself is a normal GET). */
(function () {
  document.querySelectorAll('[data-export]').forEach(function (a) {
    a.addEventListener('click', function () {
      if (a.getAttribute('aria-busy') === 'true') { return; }
      var label = a.textContent;
      a.setAttribute('aria-busy', 'true');
      a.textContent = a.getAttribute('data-busy') || '…';
      setTimeout(function () { a.removeAttribute('aria-busy'); a.textContent = label; }, 4000);
    });
  });
})();
