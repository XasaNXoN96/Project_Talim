/* Public site behaviour: header picture slider, counting numbers, reveal on scroll, accessibility switches (text size, contrast).
   No inline scripts anywhere (strict CSP). Everything degrades to the plain page when this file does not run. */
(function () {
  'use strict';
  var d = document, root = d.documentElement;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var store = {
    get: function (k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* private window: the switch just does not persist */ } }
  };

  /* ---- accessibility: text size and contrast, remembered in this browser ---- */
  function applyA11y() {
    root.classList.toggle('a11y-lg', store.get('a11y-lg') === '1');
    root.classList.toggle('a11y-xl', store.get('a11y-lg') === '2');
    root.classList.toggle('a11y-hc', store.get('a11y-hc') === '1');
    Array.prototype.forEach.call(d.querySelectorAll('[data-a11y="contrast"]'), function (b) { b.setAttribute('aria-pressed', store.get('a11y-hc') === '1' ? 'true' : 'false'); });
  }
  applyA11y();
  Array.prototype.forEach.call(d.querySelectorAll('[data-a11y]'), function (btn) {
    btn.addEventListener('click', function () {
      var kind = btn.getAttribute('data-a11y');
      if (kind === 'contrast') { store.set('a11y-hc', store.get('a11y-hc') === '1' ? '0' : '1'); }
      else if (kind === 'bigger') { var v = store.get('a11y-lg'); store.set('a11y-lg', v === '1' ? '2' : '1'); }
      else if (kind === 'reset') { store.set('a11y-lg', '0'); store.set('a11y-hc', '0'); }
      applyA11y();
    });
  });

  /* ---- header picture slider ---- */
  var slider = d.querySelector('[data-slider]');
  if (slider) {
    var slides = Array.prototype.slice.call(slider.querySelectorAll('.hero-photo'));
    var dots = d.querySelector('.hero-dots');
    var idx = 0, timer = null;
    var show = function (n) {
      idx = (n + slides.length) % slides.length;
      slides.forEach(function (s, i) { s.classList.toggle('is-active', i === idx); });
      if (dots) Array.prototype.forEach.call(dots.children, function (b, i) { b.setAttribute('aria-current', i === idx ? 'true' : 'false'); });
    };
    if (slides.length > 1 && dots) {
      slides.forEach(function (_s, i) {
        var b = d.createElement('button');
        b.type = 'button'; b.setAttribute('aria-label', String(i + 1) + ' / ' + String(slides.length));
        b.addEventListener('click', function () { show(i); restart(); });
        dots.appendChild(b);
      });
      show(0);
      var restart = function () { if (timer) window.clearInterval(timer); if (!reduce) timer = window.setInterval(function () { show(idx + 1); }, 6500); };
      slider.addEventListener('mouseenter', function () { if (timer) window.clearInterval(timer); });
      slider.addEventListener('mouseleave', restart);
      restart();
    }
  }

  /* ---- numbers that count up when they come into view ---- */
  var counters = Array.prototype.slice.call(d.querySelectorAll('[data-count]'));
  var fmt = function (n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); };
  var run = function (el) {
    var end = parseInt(el.getAttribute('data-count'), 10) || 0, suffix = el.getAttribute('data-suffix') || '';
    if (reduce || end < 2) { el.textContent = fmt(end) + suffix; return; }
    var t0 = null, dur = 1400;
    var step = function (t) {
      if (t0 === null) t0 = t;
      var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(Math.round(end * e)) + suffix;
      if (p < 1) window.requestAnimationFrame(step);
    };
    window.requestAnimationFrame(step);
  };

  /* ---- gentle reveal of blocks while scrolling ---- */
  var targets = Array.prototype.slice.call(d.querySelectorAll('.stats .stat, .sec, .news-card, .teacher, .links .lk, .inst-card, .person-card, .gallery .g, .list-rows .li'));
  if ('IntersectionObserver' in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        en.target.classList.add('in'); io.unobserve(en.target);
        if (en.target.hasAttribute && en.target.hasAttribute('data-count')) run(en.target);
        Array.prototype.forEach.call(en.target.querySelectorAll ? en.target.querySelectorAll('[data-count]') : [], run);
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -30px 0px' });
    targets.forEach(function (el, i) { el.classList.add('reveal'); el.style.transitionDelay = String((i % 5) * 60) + 'ms'; io.observe(el); });
    counters.forEach(function (el) { el.textContent = '0' + (el.getAttribute('data-suffix') || ''); });
  } else { counters.forEach(run); }
})();
