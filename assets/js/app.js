/* Mirzacho‘l tumani Xalq ta’limi bo‘limi — UI shell & interactions (design mock, no backend) */
(function () {
  const ORG = 'Mirzacho‘l tumani Xalq ta’limi bo‘limi';
  const ICONS = {
    home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    news: '<path d="M4 4h14a2 2 0 012 2v14H6a2 2 0 01-2-2z"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 3-6 6.5-6s6.5 2.4 6.5 6"/><path d="M16 4.5a3.5 3.5 0 010 7M18 14.4c2.2.7 3.5 2.6 3.5 5.6"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
    trophy: '<path d="M8 4h8v6a4 4 0 01-8 0z"/><path d="M8 6H4v1a4 4 0 004 4M16 6h4v1a4 4 0 01-4 4"/><path d="M12 14v4M8 21h8M9 18h6"/>',
    award: '<circle cx="12" cy="9" r="6"/><path d="M8.5 14L7 22l5-3 5 3-1.5-8"/>',
    clipboard: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4h6v3H9zM9 12h6M9 16h4"/>',
    file: '<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    folder: '<path d="M3 6a2 2 0 012-2h4l2 2h8a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-8 9"/>',
    building: '<path d="M4 21V8l8-5 8 5v13"/><path d="M9 21v-6h6v6M8 11h.01M12 11h.01M16 11h.01"/>',
    school: '<path d="M2 10l10-6 10 6-10 6z"/><path d="M6 12.5V17c0 1.5 3 3 6 3s6-1.5 6-3v-4.5M22 10v6"/>',
    book: '<path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2z"/><path d="M4 19V5M8 7h7"/>',
    login: '<path d="M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3"/><path d="M10 17l5-5-5-5M15 12H3"/>',
    logout: '<path d="M9 4H6a2 2 0 00-2 2v12a2 2 0 002 2h3"/><path d="M16 17l5-5-5-5M21 12H9"/>',
    pin: '<path d="M12 21s7-6.2 7-11a7 7 0 00-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    chat: '<path d="M21 12a8 8 0 01-11.6 7.1L3 21l1.9-5.4A8 8 0 1121 12z"/>',
    chart: '<path d="M4 20V4M4 20h16"/><path d="M8 16v-5M12 16V8M16 16v-8"/>',
    shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    bell: '<path d="M6 16V11a6 6 0 1112 0v5l2 2H4z"/><path d="M10 21h4"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    right: '<path d="M9 6l6 6-6 6"/>', left: '<path d="M15 6l-6 6 6 6"/>', down: '<path d="M6 9l6 6 6-6"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>', plus: '<path d="M12 5v14M5 12h14"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    eyeoff: '<path d="M3 3l18 18M10.6 6.1A9.8 9.8 0 0112 6c6.5 0 10 6 10 6a17 17 0 01-3.2 3.9M6.6 7.6A17 17 0 002 12s3.5 7 10 7a9.6 9.6 0 004.4-1"/>',
    phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2z"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    play: '<path d="M7 4l13 8-13 8z"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    download: '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>', upload: '<path d="M12 16V5M7 9l5-5 5 5M5 20h14"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.9l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.9-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.9.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.9 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.9l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.9.3h0a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.9-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.9v0a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>',
    check: '<path d="M5 12l5 5 9-10"/>', alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    filter: '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>', send: '<path d="M21 3L10 14M21 3l-7 18-4-7-7-4z"/>', clip: '<path d="M20 11l-8.5 8.5a5 5 0 01-7-7L13 4a3.5 3.5 0 015 5l-8.5 8.5a2 2 0 01-3-3L14 7"/>',
    more: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>', quote: '<path d="M10 7H6a2 2 0 00-2 2v4a2 2 0 002 2h2l-1 3M20 7h-4a2 2 0 00-2 2v4a2 2 0 002 2h2l-1 3"/>',
    grid: '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>',
    list: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
    star: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>', trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    tag: '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1"/>', globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18"/>',
    tg: '<path d="M21 4L3 11l6 2 2 6 3-4 5 4z"/>', fb: '<path d="M14 8h3V4h-3a4 4 0 00-4 4v3H7v4h3v5h4v-5h3l1-4h-4V8z"/>', ig: '<rect x="4" y="4" width="16" height="16" rx="5"/><circle cx="12" cy="12" r="3.5"/>', yt: '<rect x="3" y="6" width="18" height="12" rx="4"/><path d="M10 9.5v5l4.5-2.5z"/>',
    msg: '<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 21l3-4"/>', lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>', layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>', history: '<path d="M3 12a9 9 0 109-9 9 9 0 00-7 3.3L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>'
  };
  const icon = (n, c = '') => `<svg class="ico ${c}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ''}</svg>`;
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const body = document.body;
  window.TALIM = { icon, ORG };

  /* ---- logo (temporary brand mark: open book + spark) ---- */
  const LOGO = `<svg viewBox="0 0 48 48" aria-hidden="true"><rect width="48" height="48" rx="12" fill="#1f6bff"/><path d="M8 17c5-2 11-1 16 3v18c-5-4-11-5-16-3z" fill="#fff"/><path d="M40 17c-5-2-11-1-16 3v18c5-4 11-5 16-3z" fill="#cfe0ff"/><circle cx="24" cy="12" r="4" fill="#ffc83d"/><path d="M24 5v2M17 8l1.4 1.4M31 8l-1.4 1.4" stroke="#ffc83d" stroke-width="1.6" stroke-linecap="round"/></svg>`;
  window.TALIM.LOGO = LOGO;

  /* ---- placeholder scenes (no real photos — clearly illustrative) ---- */
  const scenes = {
    building: (a, b) => `<svg viewBox="0 0 400 225" preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="sk${a}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5c9bf0"/><stop offset="1" stop-color="#cfe3fb"/></linearGradient></defs><rect width="400" height="225" fill="url(#sk${a})"/><circle cx="60" cy="40" r="18" fill="#fff" opacity=".5"/><rect x="90" y="70" width="230" height="120" fill="#e9dcc3"/><rect x="70" y="95" width="40" height="95" fill="#dccdb0"/><rect x="300" y="95" width="40" height="95" fill="#dccdb0"/><path d="M85 70h250l-12-14H97z" fill="#c9b894"/>${Array.from({length:7},(_,i)=>`<rect x="${105+i*30}" y="90" width="16" height="26" fill="#6c8fb8"/><rect x="${105+i*30}" y="130" width="16" height="26" fill="#6c8fb8"/>`).join('')}<rect x="190" y="160" width="40" height="30" fill="#8a6f4d"/><rect y="190" width="400" height="35" fill="#6fa86a"/><rect y="205" width="400" height="20" fill="#9aa3ad"/><circle cx="30" cy="150" r="34" fill="#3f8a4e"/><rect x="26" y="160" width="8" height="35" fill="#6b4a2f"/><circle cx="375" cy="145" r="38" fill="#3f8a4e"/><rect x="371" y="160" width="8" height="35" fill="#6b4a2f"/></svg>`,
    class: () => `<svg viewBox="0 0 400 225" preserveAspectRatio="xMidYMid slice"><rect width="400" height="225" fill="#e8efe3"/><rect x="40" y="26" width="320" height="70" rx="4" fill="#2f6b52"/><rect x="40" y="26" width="320" height="70" rx="4" fill="none" stroke="#b58b4c" stroke-width="5"/>${[0,1,2].map(r=>[0,1,2,3].map(c=>`<rect x="${50+c*88}" y="${125+r*28}" width="64" height="12" rx="3" fill="#b58b4c"/><circle cx="${82+c*88}" cy="${118+r*28}" r="8" fill="#${['f1c27d','d9a066','c68642','e8b98a'][(r+c)%4]}"/>`).join('')).join('')}</svg>`,
    ceremony: () => `<svg viewBox="0 0 400 225" preserveAspectRatio="xMidYMid slice"><rect width="400" height="225" fill="#2a4f8f"/><rect x="0" y="0" width="400" height="60" fill="#3f6fc4"/><rect y="30" width="400" height="12" fill="#fff" opacity=".85"/><rect y="42" width="400" height="12" fill="#2da35f" opacity=".9"/>${Array.from({length:14},(_,i)=>`<circle cx="${20+i*28}" cy="118" r="11" fill="#${['f1c27d','d9a066','c68642','e8b98a'][i%4]}"/><rect x="${9+i*28}" y="130" width="22" height="60" rx="8" fill="#${['1c2b4a','2b3a5e','0f1b33','3a4a70'][i%4]}"/>`).join('')}<rect y="195" width="400" height="30" fill="#1b3466"/></svg>`,
    sport: () => `<svg viewBox="0 0 400 225" preserveAspectRatio="xMidYMid slice"><rect width="400" height="225" fill="#4fae5b"/><rect x="20" y="20" width="360" height="185" fill="none" stroke="#fff" stroke-width="3"/><path d="M200 20v185" stroke="#fff" stroke-width="3"/><circle cx="200" cy="112" r="30" fill="none" stroke="#fff" stroke-width="3"/><circle cx="150" cy="90" r="9" fill="#1f6bff"/><circle cx="240" cy="130" r="9" fill="#e5484d"/></svg>`,
    hall: () => `<svg viewBox="0 0 400 225" preserveAspectRatio="xMidYMid slice"><rect width="400" height="225" fill="#f1d9a0"/><rect y="150" width="400" height="75" fill="#c9a064"/>${Array.from({length:10},(_,i)=>`<circle cx="${28+i*38}" cy="${100+(i%2)*26}" r="10" fill="#${['f1c27d','d9a066','c68642'][i%3]}"/><rect x="${16+i*38}" y="${112+(i%2)*26}" width="24" height="38" rx="8" fill="#${['2b6cf0','12a05c','e07b0a','7a4fe0'][i%4]}"/>`).join('')}</svg>`,
    people: () => `<svg viewBox="0 0 400 225" preserveAspectRatio="xMidYMid slice"><rect width="400" height="225" fill="#dfe8f6"/><rect y="140" width="400" height="85" fill="#b9c8e3"/>${Array.from({length:5},(_,i)=>`<circle cx="${60+i*70}" cy="85" r="18" fill="#${['f1c27d','d9a066','c68642','e8b98a','f1c27d'][i]}"/><rect x="${38+i*70}" y="105" width="44" height="80" rx="16" fill="#${['10244d','1f6bff','183166','0f1b33','2b3a5e'][i]}"/>`).join('')}</svg>`,
    school: (a) => scenes.building(a + 'b')
  };
  let uid = 0;
  const initVisuals = () => {
  $$('[data-ph]:not([data-phd])').forEach(el => {
    el.dataset.phd = 1; const k = el.dataset.ph; el.classList.add('ph');
    el.innerHTML = (scenes[k] || scenes.building)(++uid);
    el.setAttribute('role', 'img'); el.setAttribute('aria-label', 'Namuna tasvir (dizayn maketi)');
  });
  /* avatars */
  const pal = ['#1f6bff', '#12a05c', '#e07b0a', '#7a4fe0', '#0e9aa7', '#d9363e', '#183166'];
  $$('.av[data-name]:not([data-done])').forEach(el => {
    el.dataset.done = 1;
    const n = el.dataset.name; const ini = n.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
    let h = 0; for (const c of n) h = (h * 31 + c.charCodeAt(0)) >>> 0;
    el.textContent = ini; el.style.background = pal[h % pal.length]; el.setAttribute('aria-label', n);
  });
  };

  /* ---- i18n groundwork: shell texts go through t(key). Add ru/en dictionaries later; fallback is uz. ---- */
  const I18N = {
    uz: { 'nav.home': 'Bosh sahifa', 'nav.news': 'Yangiliklar', 'nav.staff': 'Xodimlar', 'nav.achievements': 'Yutuqlar', 'nav.certs': 'Sertifikatlar', 'nav.tasks': 'Topshiriqlar', 'nav.docs': 'Hujjatlar', 'nav.media': 'Media', 'nav.org': 'Tashkilot', 'nav.attendance': 'Kirish-chiqish', 'nav.geo': 'Geolokatsiya', 'nav.chat': 'Chat', 'nav.notifs': 'Bildirishnomalar', 'nav.reports': 'Hisobotlar', 'nav.admin': 'Admin panel',
      'pub.home': 'Bosh sahifa', 'pub.news': 'Yangiliklar', 'pub.schools': 'Ta’lim muassasalari', 'pub.teachers': 'Ustozlar', 'pub.achievements': 'Yutuqlar', 'pub.docs': 'Hujjatlar', 'pub.media': 'Media', 'pub.contact': 'Bog‘lanish', 'pub.login': 'Kirish', 'pub.search': 'Qidirish', 'pub.useful': 'Foydali havolalar', 'pub.contactTitle': 'Aloqa', 'pub.location': 'Joylashuv' },
    ru: {}, en: {}
  };
  const LANG = 'uz';
  const t = k => (I18N[LANG] && I18N[LANG][k]) || I18N.uz[k] || k;
  const langSwitch = () => `<div class="lang" role="group" aria-label="Til"><button class="active" aria-pressed="true">UZ</button><button data-toast="Til almashtirish keyinroq qo‘shiladi" aria-pressed="false">RU</button><button data-toast="Til almashtirish keyinroq qo‘shiladi" aria-pressed="false">EN</button></div>`;
  window.TALIM.t = t;


  /* ---- Public shell (header + footer shared by all public pages) ---- */
  if (body.dataset.shell === 'public') {
    const nav = body.dataset.nav || '';
    const items = [['home', 'index.html', 'pub.home'], ['news', 'news.html', 'pub.news'], ['schools', 'tashkilot.html#muassasalar', 'pub.schools'], ['teachers', 'ustozlar.html', 'pub.teachers'], ['achievements', 'ustozlar.html#yutuqlar', 'pub.achievements'], ['docs', 'hujjatlar.html', 'pub.docs'], ['media', 'media.html', 'pub.media'], ['contact', '#boglanish', 'pub.contact']];
    const hdr = document.createElement('header'); hdr.className = 'pub-header';
    hdr.innerHTML = `<div class="container"><a class="brand" href="index.html" aria-label="${t('pub.home')}"><span style="display:block;width:44px;height:44px;flex:none">${LOGO}</span><div><b>Xalq ta’limi bo‘limi</b><span>Mirzacho‘l tumani</span></div></a>
      <nav class="pub-nav" aria-label="Asosiy menyu">${items.map(([id, href, k]) => `<a href="${href}" class="${id === nav ? 'active' : ''}" ${id === nav ? 'aria-current="page"' : ''} data-i18n="${k}">${t(k)}</a>`).join('')}<div class="nav-lang">${langSwitch()}</div></nav>
      <div class="pub-actions">${langSwitch()}<div class="search"><label class="sr-only" for="ps">${t('pub.search')}</label>${icon('search', 'sm')}<input id="ps" placeholder="${t('pub.search')}"></div><a class="btn btn-primary" href="login.html">${icon('lock', 'sm')}<span data-i18n="pub.login">${t('pub.login')}</span></a></div>
      <button class="btn btn-secondary btn-icon burger" aria-label="Menyu" aria-expanded="false">${icon('menu')}</button></div>`;
    const ftr = document.createElement('footer'); ftr.className = 'pub-footer'; ftr.id = 'boglanish';
    ftr.innerHTML = `<div class="container"><div class="foot-grid"><div><a class="brand" href="index.html"><span style="display:block;width:44px;height:44px;flex:none">${LOGO}</span><div><b>Xalq ta’limi bo‘limi</b><span>Mirzacho‘l tumani</span></div></a><p style="margin-top:14px;font-size:14px">Ta’lim — kelajak poydevori. Sifatli ta’lim, barkamol avlod va yuksalish sari birgalikda!</p></div>
      <div><h4>${t('pub.useful')}</h4><a href="news.html">${t('pub.news')}</a><a href="tashkilot.html#muassasalar">${t('pub.schools')}</a><a href="ustozlar.html">${t('pub.teachers')}</a><a href="hujjatlar.html">${t('pub.docs')}</a></div>
      <div><h4>${t('pub.contactTitle')}</h4><div class="foot-row">${icon('pin', 'sm')}<span>Manzil: tasdiqlangan ma’lumot kiritiladi</span></div><div class="foot-row">${icon('phone', 'sm')}<span>Telefon: tasdiqlangan ma’lumot kiritiladi</span></div><div class="foot-row">${icon('mail', 'sm')}<span>E-pochta: tasdiqlangan ma’lumot kiritiladi</span></div></div>
      <div><h4>${t('pub.location')}</h4><div class="map-card"><svg viewBox="0 0 300 150" width="100%" height="100%" preserveAspectRatio="xMidYMid slice"><rect width="300" height="150" fill="#e4ecfa"/><path d="M-10 100L120 60l100 40 100-30M80-10l40 170M200-10l-30 170" stroke="#fff" stroke-width="10" fill="none"/></svg><span class="pin">${icon('pin', 'lg')}</span></div><p class="xs" style="margin-top:6px">Xarita namunasi — manzil tasdiqlangach almashtiriladi.</p></div></div>
      <div class="copy"><span>© 2026 Mirzacho‘l tumani Xalq ta’limi bo‘limi</span><span>Dizayn maketi</span></div></div>`;
    const m = $('main'); m.id = m.id || 'main';
    m.before(hdr); m.after(ftr);
  }

  /* ---- Workspace shell ---- */
  const NAV = [
    ['dashboard', 'nav.home', 'home'], ['yangiliklar', 'nav.news', 'news'], ['xodimlar', 'nav.staff', 'users'],
    ['yutuqlar', 'nav.achievements', 'trophy'], ['sertifikatlar', 'nav.certs', 'award'], ['topshiriqlar', 'nav.tasks', 'clipboard'],
    ['hujjatlar', 'nav.docs', 'file'], ['media', 'nav.media', 'image'], ['tashkilot', 'nav.org', 'building'],
    ['kirish-chiqish', 'nav.attendance', 'login'], ['geolokatsiya', 'nav.geo', 'pin'], ['chat', 'nav.chat', 'chat'],
    ['bildirishnomalar', 'nav.notifs', 'bell'], ['hisobotlar', 'nav.reports', 'chart'], ['admin', 'nav.admin', 'shield']
  ];
  if (body.dataset.shell === 'app') {
    const page = body.dataset.page, title = body.dataset.title || 'Bosh sahifa';
    const content = $('main'); content.classList.add('content'); content.id = 'content';
    const crumb = body.dataset.crumb ? `<div class="crumbs"><a href="dashboard.html">Bosh sahifa</a>${icon('right', 'sm')}<span>${body.dataset.crumb}</span></div>` : '';
    if (crumb) content.insertAdjacentHTML('afterbegin', crumb);
    const sidebar = document.createElement('aside'); sidebar.className = 'sidebar'; sidebar.setAttribute('aria-label', 'Asosiy navigatsiya');
    sidebar.innerHTML = `<a class="sb-brand" href="dashboard.html" title="${ORG}">${LOGO}<div><b>Xalq ta’limi bo‘limi<br>Mirzacho‘l tumani</b><small>Xodimlar portali</small></div></a>
      <nav class="sb-nav" aria-label="Bo‘limlar">${NAV.map(([id, key, ic]) => `<a href="${id}.html" class="${id === page ? 'active' : ''}" ${id === page ? 'aria-current="page"' : ''} title="${t(key)}">${icon(ic)}<span data-i18n="${key}">${t(key)}</span></a>`).join('')}</nav>
      <div class="sb-foot">Dizayn maketi · demo ma’lumotlar</div>`;
    const topbar = document.createElement('header'); topbar.className = 'topbar';
    topbar.innerHTML = `<button class="btn btn-secondary btn-icon" id="sbToggle" aria-label="Menyuni ochish yoki yig‘ish">${icon('menu')}</button>
      <div class="search"><label class="sr-only" for="gs">Qidirish</label>${icon('search', 'sm')}<input id="gs" placeholder="Qidirish…"></div><div class="grow"></div>${langSwitch()}
      <div class="dd"><button class="btn btn-secondary btn-icon bell" data-dd aria-label="Bildirishnomalar">${icon('bell')}<i class="dot"></i></button>
        <div class="dd-menu" style="min-width:300px"><div class="small muted" style="padding:6px 10px">Yangi bildirishnomalar</div>
        <a href="topshiriqlar.html">${icon('clipboard', 'sm')}<span>Hisobot tayyorlash topshirig‘i muddati yaqin</span></a><a href="yangiliklar.html">${icon('news', 'sm')}<span>Yangi e’lon e’lon qilindi</span></a><div class="sep"></div><a href="bildirishnomalar.html">Barchasini ko‘rish</a></div></div>
      <div class="dd"><button class="me" data-dd aria-label="Profil menyusi"><span class="av" data-name="Xasanxon Mirzaxo‘jayev"></span><div><b>Xasanxon</b><small>Administrator</small></div>${icon('down', 'sm')}</button>
        <div class="dd-menu"><a href="xodimlar.html#profil">${icon('user', 'sm')}Mening profilim</a><a href="admin.html">${icon('settings', 'sm')}Sozlamalar</a><div class="sep"></div><a class="danger" href="../login.html">${icon('logout', 'sm')}Tizimdan chiqish</a></div></div>`;
    const wrap = document.createElement('div'); wrap.className = 'app';
    const main = document.createElement('div'); main.className = 'main';
    content.parentNode.insertBefore(wrap, content);
    main.append(topbar, content, Object.assign(document.createElement('div'), { className: 'demo-foot', textContent: `${ORG} · Dizayn maketi — barcha ma’lumotlar namunaviy` }));
    const scrim = Object.assign(document.createElement('div'), { className: 'scrim' });
    wrap.append(sidebar, main); body.append(scrim);
    const mq = () => window.innerWidth;
    try { if (localStorage.getItem('sbc') === '1' && mq() >= 1200) body.classList.add('collapsed'); } catch (e) {}
    $('#sbToggle').onclick = () => {
      if (mq() >= 1200) { body.classList.toggle('collapsed'); try { localStorage.setItem('sbc', body.classList.contains('collapsed') ? '1' : '0'); } catch (e) {} }
      else if (mq() >= 768) body.classList.toggle('sb-wide'); else body.classList.toggle('sb-open');
    };
    scrim.onclick = () => body.classList.remove('sb-open', 'sb-wide');
    $$('.sb-nav a').forEach(a => a.addEventListener('click', () => body.classList.remove('sb-open', 'sb-wide')));
  }

  initVisuals();
  /* ---- icons fill ---- */
  const fillIcons = () => $$('[data-i]:not([data-d])').forEach(el => { el.dataset.d = 1; el.insertAdjacentHTML('afterbegin', icon(el.dataset.i, el.dataset.c || '')); });
  fillIcons();
  window.TALIM.refresh = () => { initVisuals(); fillIcons(); };
  $$('[data-logo]').forEach(el => el.innerHTML = LOGO);

  /* ---- toast ---- */
  const toast = msg => { let c = $('#toasts'); if (!c) { c = document.createElement('div'); c.id = 'toasts'; c.setAttribute('role', 'status'); document.body.append(c); } const t = document.createElement('div'); t.className = 'toast'; t.innerHTML = icon('check') + `<span>${msg}</span>`; c.append(t); setTimeout(() => t.remove(), 3200); };
  window.TALIM.toast = toast;
  $$('[data-toast]').forEach(b => b.addEventListener('click', e => { e.preventDefault(); toast(b.dataset.toast); }));

  /* ---- dropdowns ---- */
  document.addEventListener('click', e => {
    const t = e.target.closest('[data-dd]');
    $$('.dd.open').forEach(d => { if (!t || d !== t.closest('.dd')) d.classList.remove('open'); });
    if (t) t.closest('.dd').classList.toggle('open');
  });

  /* ---- tabs / pills (visual state + optional panels) ---- */
  $$('[data-tabs]').forEach(g => {
    const btns = $$('.tab, .pill', g);
    btns.forEach(b => b.addEventListener('click', () => {
      btns.forEach(x => { x.classList.toggle('active', x === b); x.setAttribute('aria-selected', x === b); });
      if (b.dataset.panel) $$(`[data-panel-group="${g.dataset.tabs}"]`).forEach(p => p.hidden = p.id !== b.dataset.panel);
    }));
  });

  { const h = location.hash.slice(1); if (h) $$('.tab[data-hash]').forEach(b => b.dataset.hash === h && b.click()); }
  /* ---- modals ---- */
  $$('[data-modal]').forEach(b => b.addEventListener('click', () => { const m = $('#' + b.dataset.modal); if (m) { m.classList.add('open'); const f = m.querySelector('input,button,select,textarea'); f && f.focus(); } }));
  $$('.modal-back').forEach(m => m.addEventListener('click', e => { if (e.target === m || e.target.closest('[data-close]')) m.classList.remove('open'); }));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { $$('.modal-back.open').forEach(m => m.classList.remove('open')); closeLb(); $$('.dd.open').forEach(d => d.classList.remove('open')); body.classList.remove('sb-open', 'sb-wide'); } });

  /* ---- public nav burger ---- */
  const bg = $('.burger'); if (bg) bg.onclick = () => { const o = $('.pub-nav').classList.toggle('open'); bg.setAttribute('aria-expanded', o); };

  /* ---- password toggle ---- */
  $$('[data-eye]').forEach(b => b.addEventListener('click', () => { const i = $(b.dataset.eye); const show = i.type === 'password'; i.type = show ? 'text' : 'password'; b.innerHTML = icon(show ? 'eyeoff' : 'eye'); b.setAttribute('aria-label', show ? 'Parolni yashirish' : 'Parolni ko‘rsatish'); }));

  /* ---- grid/list view toggle ---- */
  $$('[data-view]').forEach(s => { const tgt = $(s.dataset.view); $$('button', s).forEach(b => b.addEventListener('click', () => { $$('button', s).forEach(x => x.classList.toggle('active', x === b)); tgt.dataset.mode = b.dataset.mode; })); });

  /* ---- clock ---- */
  const clk = $('[data-clock]'); if (clk) { const tick = () => { const d = new Date(); clk.textContent = d.toLocaleTimeString('en-GB'); const dt = $('[data-date]'); if (dt) dt.textContent = d.toLocaleDateString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric' }); }; tick(); setInterval(tick, 1000); }

  /* ---- lightbox ---- */
  let lbIdx = 0; const lbItems = $$('[data-lb]');
  let lb = null;
  function closeLb() { if (lb) lb.classList.remove('open'); }
  function showLb(i) { lbIdx = (i + lbItems.length) % lbItems.length; const src = lbItems[lbIdx].querySelector('.ph').innerHTML; $('.stage', lb).innerHTML = src; $('.lb-count', lb).textContent = `${lbIdx + 1} / ${lbItems.length}`; }
  if (lbItems.length) {
    lb = document.createElement('div'); lb.className = 'lightbox'; lb.setAttribute('role', 'dialog'); lb.setAttribute('aria-modal', 'true'); lb.setAttribute('aria-label', 'Fotogalereya');
    lb.innerHTML = `<button class="lb-close" aria-label="Yopish">${icon('x')}</button><button class="lb-prev" aria-label="Oldingi">${icon('left')}</button><div class="stage"></div><button class="lb-next" aria-label="Keyingi">${icon('right')}</button><div class="lb-count"></div>`;
    document.body.append(lb);
    lbItems.forEach((el, i) => el.addEventListener('click', () => { lb.classList.add('open'); showLb(i); }));
    $('.lb-close', lb).onclick = closeLb; $('.lb-prev', lb).onclick = () => showLb(lbIdx - 1); $('.lb-next', lb).onclick = () => showLb(lbIdx + 1);
    lb.addEventListener('click', e => { if (e.target === lb) closeLb(); });
    document.addEventListener('keydown', e => { if (!lb.classList.contains('open')) return; if (e.key === 'ArrowRight') showLb(lbIdx + 1); if (e.key === 'ArrowLeft') showLb(lbIdx - 1); });
  }

  /* ---- chat mobile switch ---- */
  const chat = $('.chat'); if (chat) { $$('.conv', chat).forEach(c => c.addEventListener('click', () => { $$('.conv', chat).forEach(x => x.classList.toggle('active', x === c)); chat.classList.add('in-conv'); })); const bk = $('.chat-back'); bk && (bk.onclick = () => chat.classList.remove('in-conv')); const f = $('#chatForm'); f && f.addEventListener('submit', e => { e.preventDefault(); const i = $('input', f); if (!i.value.trim()) return; const m = document.createElement('div'); m.className = 'msg mine'; m.textContent = i.value; $('.chat-msgs').append(m); i.value = ''; m.scrollIntoView(); }); }

  /* ---- login (mock states only) ---- */
  const lf = $('#loginForm'); if (lf) lf.addEventListener('submit', e => {
    e.preventDefault(); const u = $('#lu'), p = $('#lp'), err = $('#loginErr'), btn = $('#loginBtn');
    err.hidden = true; [u, p].forEach(i => i.classList.remove('invalid'));
    if (!u.value.trim() || !p.value) { [u, p].forEach(i => !i.value && i.classList.add('invalid')); err.hidden = false; err.querySelector('span').textContent = 'Login va parolni kiriting.'; return; }
    if (p.value === 'xato') { p.classList.add('invalid'); err.hidden = false; err.querySelector('span').textContent = 'Login yoki parol noto‘g‘ri. Qaytadan urinib ko‘ring.'; return; }
    btn.classList.add('loading'); btn.lastChild.textContent = ' Tekshirilmoqda…'; setTimeout(() => location.href = 'app/dashboard.html', 900);
  });
})();
