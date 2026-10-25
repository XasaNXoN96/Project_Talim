/* "Kirish-chiqish": a live clock and the position read ONLY when a button is pressed (never in the background). No inline script (strict CSP). */
(function () {
  var clock = document.getElementById('live-clock');
  if (clock) {
    // the time shown is the SERVER's, in the site's time zone: the device clock may be wrong (only the offset to it is used)
    var offset = (parseInt(clock.dataset.now, 10) || Date.now()) - Date.now();
    var fmt;
    try { fmt = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: clock.dataset.tz || undefined }); } catch (e) { fmt = null; }
    var tick = function () { if (fmt) clock.textContent = fmt.format(new Date(Date.now() + offset)); };
    tick();
    setInterval(tick, 1000);
  }
  var form = document.getElementById('clock-form');
  if (!form) return;
  var msg = document.getElementById('geo-msg');
  var say = function (text) { if (msg) { msg.textContent = text; msg.hidden = false; } };
  form.addEventListener('submit', function (e) {
    if (form.dataset.geo !== '1' || form.dataset.located === '1') return;   // no zone for this person, or the position is already filled in
    var kind = e.submitter && e.submitter.value;
    if (!kind) return;
    e.preventDefault();
    var hidden = document.createElement('input');
    hidden.type = 'hidden'; hidden.name = 'kind'; hidden.value = kind; form.appendChild(hidden);
    var buttons = form.querySelectorAll('button[type=submit]');
    buttons.forEach(function (b) { b.disabled = true; });
    var go = function () { form.dataset.located = '1'; form.submit(); };
    if (!('geolocation' in navigator)) { go(); return; }
    say(form.dataset.waiting || '…');
    navigator.geolocation.getCurrentPosition(function (pos) {
      document.getElementById('f-lat').value = pos.coords.latitude.toFixed(6);
      document.getElementById('f-lon').value = pos.coords.longitude.toFixed(6);
      document.getElementById('f-acc').value = Math.round(pos.coords.accuracy || 0);
      go();
    }, function () { go(); }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  });
})();
