/* Portal helpers: forms marked data-confirm ask before they are sent (no inline scripts, strict CSP). */
(function () {
  'use strict';
  Array.prototype.forEach.call(document.querySelectorAll('form[data-confirm]'), function (f) {
    f.addEventListener('submit', function (e) { if (!window.confirm(f.getAttribute('data-confirm'))) e.preventDefault(); });
  });
})();
