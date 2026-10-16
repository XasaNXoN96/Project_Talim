/* Page renderers for the static mockup (reads window.DATA). Runs before app.js. */
(function () {
  const D = window.DATA, $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const qs = new URLSearchParams(location.search);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ic = n => `<span data-i="${n}" data-c="sm"></span>`;
  const img = (s, cls = 'ratio-16-9') => s ? `<div class="${cls}" data-ph="${s}"></div>` : `<div class="${cls} ph-none">Rasm yo‘q</div>`;
  const empty = (t, x) => `<div class="card empty" style="grid-column:1/-1"><div class="ic-chip c-blue" data-i="search"></div><h3>${t}</h3><p>${x}</p></div>`;
  const prefix = document.body.dataset.shell === 'app' ? '../' : '';
  const badgeCls = { 'E’lonlar': 'b-warn', 'Tadbirlar': 'b-info', 'Muvaffaqiyatlar': 'b-violet', 'Ommaviy axborot': 'b-teal' };

  const newsCard = (n, admin) => `<article class="card news-card">${img(n.img)}<div class="body"><div class="row wrap"><span class="badge plain ${badgeCls[n.c]}">${n.c}</span>${admin ? `<span class="badge ${n.st === 'Qoralama' ? 'b-warn' : 'b-ok'}">${n.st}</span>` : ''}</div><h3 class="clamp3">${esc(n.t)}</h3><span class="xs muted">${n.d}</span>${n.ex ? `<p class="clamp3">${esc(n.ex)}</p>` : ''}<a class="go" href="${prefix}news-detail.html?id=${n.id}">Batafsil ${ic('arrow')}</a></div></article>`;
  const teacherCard = t => `<a class="card teacher t-link" href="${prefix}ustoz.html?id=${t.id}"><span class="award" data-i="trophy" data-c="sm"></span><div class="av" data-name="${t.n}"></div><b>${t.n}</b><span class="xs muted">${t.r}</span><span class="badge plain b-info" style="margin-top:8px">${t.s}</span></a>`;
  const fileKind = k => ({ PDF: 'f-pdf', DOC: 'f-doc', XLS: 'f-xls' }[k] || 'f-other');

  /* filter helper: tabs/pills + search + select drive a list */
  function wire(host, items, draw, opts = {}) {
    const state = { q: '', c: 'Barchasi', s: '' };
    const out = $(opts.out || '[data-out]', host);
    const run = () => {
      const list = items.filter(i => (state.c === 'Barchasi' || opts.cat(i) === state.c) && (!state.s || opts.sel(i) === state.s) && (!state.q || opts.text(i).toLowerCase().includes(state.q)));
      out.innerHTML = list.length ? list.map(draw).join('') : (opts.empty ? opts.empty() : empty('Hech narsa topilmadi', 'Qidiruv yoki filtr shartlarini o‘zgartirib ko‘ring.'));
      const c = $('[data-count]', host); if (c) c.textContent = list.length;
      window.TALIM && window.TALIM.refresh && window.TALIM.refresh();
    };
    const si = $('[data-q]', host); si && si.addEventListener('input', () => { state.q = si.value.trim().toLowerCase(); run(); });
    const se = $('[data-sel]', host); se && se.addEventListener('change', () => { state.s = se.value; run(); });
    $$('[data-cat]', host).forEach(b => b.addEventListener('click', () => { state.c = b.dataset.cat; run(); }));
    run();
  }
  const R = {
    'news-list': el => wire(el, D.news.filter(n => el.dataset.admin || n.st !== 'Qoralama'), n => newsCard(n, !!el.dataset.admin), { cat: n => n.c, text: n => n.t + ' ' + (n.ex || ''), sel: n => n.st }),
    'news-detail': el => {
      const n = D.news.find(x => x.id == qs.get('id')) || D.news[0]; document.title = n.t.slice(0, 70) + ' — Mirzacho‘l tumani Xalq ta’limi bo‘limi';
      const rel = D.news.filter(x => x.id !== n.id && x.st !== 'Qoralama').slice(0, 3);
      el.innerHTML = `<div class="split"><article class="card article"><div class="row wrap"><span class="badge plain ${badgeCls[n.c]}">${n.c}</span><span class="small muted">${n.d}</span></div><h1>${esc(n.t)}</h1>${img(n.img, 'ratio-16-9 r')}${D.body.map(p => `<p>${p}</p>`).join('')}<div class="row wrap" style="margin-top:20px"><a class="btn btn-secondary" href="news.html">${ic('left')}Barcha yangiliklar</a><button class="btn btn-ghost" data-toast="Maket: ulashish ishlamaydi">${ic('globe')}Ulashish</button></div></article>
      <aside class="stack"><h2 style="font-size:17px">Boshqa yangiliklar</h2>${rel.map(r => `<a class="card row rel" href="news-detail.html?id=${r.id}">${r.img ? `<div class="ph" data-ph="${r.img}" style="width:84px;aspect-ratio:1;flex:none;border-radius:10px"></div>` : `<div class="ph-none" style="width:84px;aspect-ratio:1;flex:none;border-radius:10px">—</div>`}<div class="grow"><b class="small clamp3">${esc(r.t)}</b><span class="xs muted">${r.d}</span></div></a>`).join('')}</aside></div>`;
    },
    'teachers': el => { const subj = [...new Set(D.teachers.map(t => t.s))]; $('[data-sel]', el).insertAdjacentHTML('beforeend', subj.map(s => `<option>${s}</option>`).join('')); wire(el, D.teachers, teacherCard, { cat: () => 'Barchasi', text: t => t.n + ' ' + t.r + ' ' + t.sc, sel: t => t.s }); },
    'teacher-profile': el => {
      const t = D.teachers.find(x => x.id == qs.get('id')) || D.teachers[0]; document.title = t.n + ' — Mirzacho‘l tumani Xalq ta’limi bo‘limi';
      el.innerHTML = `<div class="split" style="grid-template-columns:minmax(0,1fr) minmax(0,2fr)"><aside class="card profile-card"><div class="av xl" data-name="${t.n}"></div><h1 style="font-size:20px">${t.n}</h1><p class="muted small">${t.r}</p><div class="kv"><div>${ic('building')}${t.sc}</div><div>${ic('book')}Fan: ${t.s}</div><div>${ic('trophy')}${t.a} — ${t.y}</div></div><p class="xs muted" style="margin-top:12px">Aloqa ma’lumotlari ommaviy ko‘rsatilmaydi.</p></aside>
      <div class="stack"><section class="card card-pad"><h2 style="font-size:17px;margin-bottom:8px">Qisqacha ma’lumot</h2><p class="muted">Namunaviy tavsif: pedagogning faoliyati, tajribasi va yo‘nalishlari haqida qisqa ma’lumot shu yerda joylashtiriladi.</p></section>
      <section class="card card-pad"><h2 style="font-size:17px;margin-bottom:8px">Yutuqlar</h2><div class="list-rows"><div class="li"><span class="ic-chip c-orange" data-i="trophy"></span><div class="grow t1">${t.a}<div class="date">${t.y}</div></div></div><div class="li"><span class="ic-chip c-violet" data-i="award"></span><div class="grow t1">Malaka oshirish sertifikati<div class="date">namuna sana</div></div></div></div></section>
      <a class="btn btn-secondary" style="justify-self:start" href="ustozlar.html">${ic('left')}Barcha ustozlar</a></div></div>`;
    },
    'media': el => {
      el.innerHTML = `<div class="tabs" data-tabs="md"><button class="tab active" data-panel="mPh">Fotorasmlar</button><button class="tab" data-panel="mVi" data-hash="video">Video</button></div>
      <div id="mPh" data-panel-group="md" style="margin-top:16px"><div class="photo-grid">${D.photos.map(([s, c], i) => `<figure class="photo"><button class="g" data-lb aria-label="${c} — kattalashtirish"><div class="ph" data-ph="${s}" style="aspect-ratio:4/3"></div></button><figcaption class="small">${c}</figcaption></figure>`).join('')}</div></div>
      <div id="mVi" data-panel-group="md" hidden style="margin-top:16px"><div class="auto-grid">${D.videos.map(v => `<article class="card"><div class="video"><div class="ratio-16-9" data-ph="${v.s}"></div><button class="play" data-toast="Maket: video ijro etilmaydi" aria-label="Videoni ijro etish"><span data-i="play"></span></button><span class="duration">${v.l}</span></div><div style="padding:12px 14px"><b class="small">${v.t}</b><div class="xs muted">${v.d}</div></div></article>`).join('')}</div></div>`;
    },
    'org': el => {
      const types = [...new Set(D.schools.map(s => s.t))];
      el.innerHTML = `<section class="sec" style="margin-top:0"><h2 style="font-size:22px;margin-bottom:16px">Bo‘lim tuzilmasi</h2><div class="org"><div class="org-top card"><span class="ic-chip c-blue" data-i="building"></span><div><b>Xalq ta’limi bo‘limi</b><div class="xs muted">Rahbariyat</div></div></div><div class="org-line"></div><div class="org-kids">${D.depts.slice(1).map(d => `<div class="card org-node"><span class="ic-chip ${d.c}" data-i="${d.i}"></span><b class="small">${d.n}</b></div>`).join('')}</div></div></section>
      <section class="sec"><h2 style="font-size:22px;margin-bottom:16px">Bo‘limlar</h2><div class="auto-grid">${D.depts.map(d => `<article class="card card-pad row" style="align-items:flex-start"><span class="ic-chip ${d.c}" data-i="${d.i}"></span><div><b>${d.n}</b><p class="small muted" style="margin-top:4px">${d.d}</p></div></article>`).join('')}</div></section>
      <section class="sec" id="muassasalar" data-schools><div class="sec-head"><h2 style="font-size:22px">Ta’lim muassasalari <span class="badge plain" data-count></span></h2></div><div class="toolbar" style="margin-bottom:16px"><div class="search"><span data-i="search" data-c="sm"></span><input data-q placeholder="Muassasa qidirish" aria-label="Muassasa qidirish"></div><select class="select" data-sel aria-label="Turi"><option value="">Turi: Barchasi</option>${types.map(t => `<option>${t}</option>`).join('')}</select></div><div class="auto-grid" data-out></div></section>`;
      wire($('[data-schools]', el), D.schools, s => `<article class="card card-pad"><div class="row"><span class="ic-chip c-teal" data-i="school"></span><div class="grow"><b class="clamp2">${s.n}</b><div class="xs muted">${s.t}</div></div><span class="badge ${s.s === 'Yangi' ? 'b-info' : 'b-ok'}">${s.s}</span></div><div class="small muted" style="margin-top:10px">Rahbar: ${s.h}</div></article>`, { cat: () => 'Barchasi', text: s => s.n, sel: s => s.t });
    },
    'docs': el => wire(el, D.docs, d => `<tr><td><span class="file-ico ${fileKind(d.k)}">${d.k}</span></td><td><b>${d.t}</b></td><td>${d.d}</td><td>${d.a}</td><td><button class="btn btn-secondary btn-sm" data-toast="Maket: yuklab olish ishlamaydi">${ic('download')}Yuklab olish</button></td></tr>`, { out: 'tbody', cat: d => d.k, text: d => d.t, sel: () => '', empty: () => '<tr><td colspan="5"><div class="empty"><div class="ic-chip c-blue" data-i="search"></div><h3>Hujjat topilmadi</h3><p>Qidiruv yoki filtrni o‘zgartirib ko‘ring.</p></div></td></tr>' }),
    'notifs': el => {
      const draw = n => `<a class="notif ${n.u ? 'unread-row' : ''}" href="${n.h}"><span class="ic-chip ${n.c}" data-i="${n.i}"></span><div class="grow"><b class="small">${n.t}</b><div class="small muted">${n.x}</div></div><span class="xs muted nw">${n.w}</span><i class="udot" aria-label="${n.u ? 'O‘qilmagan' : ''}"></i></a>`;
      wire(el, D.notifs, draw, { cat: n => n.k, text: n => n.t + ' ' + n.x, sel: () => '' });
      const mk = $('[data-readall]'); mk && mk.addEventListener('click', () => { $$('.unread-row', el).forEach(r => r.classList.remove('unread-row')); window.TALIM.toast && window.TALIM.toast('Barchasi o‘qilgan deb belgilandi'); });
    },
    'achv': el => { el.innerHTML = [...D.teachers].sort((a, b) => b.y - a.y).map(t => `<a class="card admin-tile t-link" href="${prefix}ustoz.html?id=${t.id}"><span class="ic-chip c-orange" data-i="trophy"></span><div><b>${t.a}</b><small>${t.n} · ${t.y}</small></div></a>`).join(''); },
    'certs': el => { el.innerHTML = D.teachers.slice(0, 6).map(t => `<article class="cert"><div class="cert-thumb"><div><b>Sertifikat</b><small>Namuna nomi</small></div></div><div style="padding:12px"><b class="small">Malaka oshirish</b><div class="xs muted">Egasi: ${t.n} · Berilgan: namuna sana · Amal qilish: namuna</div><button class="btn btn-secondary btn-sm" style="margin-top:8px" data-modal="mCert">Ko‘rish</button></div></article>`).join(''); }
  };
  $$('[data-render]').forEach(el => R[el.dataset.render] && R[el.dataset.render](el));
  /* index.html static sections reuse data: nothing to render */
})();
