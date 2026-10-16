/* Demo content (namunaviy ma’lumotlar). Haqiqiy ma’lumot tizim ulanganda almashtiriladi. */
window.DATA = {
  cats: ['E’lonlar', 'Tadbirlar', 'Muvaffaqiyatlar', 'Ommaviy axborot'],
  news: [
    { id: 1, t: 'Mirzacho‘l tumanida Ustozlar kuni munosabati bilan tadbir o‘tkazildi', d: '02.10.2026', c: 'Tadbirlar', img: 'ceremony', ex: 'Tuman xalq ta’limi tashabbusi bilan Ustozlar kuni munosabati bilan tantanali tadbir bo‘lib o‘tdi.', st: 'Nashr etilgan' },
    { id: 2, t: 'Yangi o‘quv yiliga tayyorgarlik ishlari', d: '28.09.2026', c: 'E’lonlar', img: 'class', ex: 'Maktablarda yangi o‘quv yiliga tayyorgarlik ishlari davom etmoqda.', st: 'Nashr etilgan' },
    { id: 3, t: 'Tuman maktablarida yangi loyihalar ishga tushirildi (juda uzun sarlavha holati namunasi: barcha ta’lim muassasalari ishtirokida)', d: '25.09.2026', c: 'Muvaffaqiyatlar', img: null, ex: null, st: 'Nashr etilgan' },
    { id: 4, t: 'Malaka oshirish kurslari boshlandi', d: '20.09.2026', c: 'E’lonlar', img: 'hall', ex: 'Pedagoglar uchun malaka oshirish kurslarining yangi guruhi o‘z faoliyatini boshladi.', st: 'Nashr etilgan' },
    { id: 5, t: 'Fan olimpiadasining tuman bosqichi yakunlandi', d: '15.09.2026', c: 'Muvaffaqiyatlar', img: 'people', ex: 'Olimpiada g‘oliblari tuman ta’lim bo‘limi tomonidan taqdirlandi.', st: 'Nashr etilgan' },
    { id: 6, t: 'Sport musobaqalari: maktablararo turnir', d: '10.09.2026', c: 'Tadbirlar', img: 'sport', ex: 'Maktablararo sport turniri qiziqarli bahslarga boy bo‘ldi.', st: 'Qoralama' },
    { id: 7, t: 'Matbuotda: tumanda ta’lim sifatini oshirish', d: '05.09.2026', c: 'Ommaviy axborot', img: 'building', ex: 'Ommaviy axborot vositalarida ta’lim sohasidagi islohotlar yoritildi.', st: 'Nashr etilgan' },
    { id: 8, t: 'Metodik tavsiyalar yangilandi', d: '01.09.2026', c: 'E’lonlar', img: 'class', ex: 'Maktablar uchun yangilangan metodik tavsiyalar e’lon qilindi.', st: 'Nashr etilgan' }
  ],
  body: ['Bu maket uchun namunaviy matn. Haqiqiy yangilik matni tizim ulanganda shu yerda ko‘rsatiladi.', 'Ikkinchi xatboshi: voqea tafsilotlari, ishtirokchilar va natijalar haqida ma’lumot joylashtiriladi.', 'Uchinchi xatboshi: xulosa va keyingi rejalar. Matn uzunligi o‘zgarganda maket moslashuvchan qoladi.'],
  teachers: [
    { id: 1, n: 'Namuna Ustoz', r: 'Matematika o‘qituvchisi', s: 'Matematika', sc: 'Namuna maktab №1', a: 'Yilning eng yaxshi ustozi', y: 2026 },
    { id: 2, n: 'Namuna Muallim', r: 'Informatika o‘qituvchisi', s: 'Informatika', sc: 'Namuna maktab №2', a: 'Innovatsion loyihalar sovrindori', y: 2025 },
    { id: 3, n: 'Namuna Metodist', r: 'Metodist', s: 'Metodika', sc: 'Namuna maktab №3', a: 'Metodik ishlanmalar g‘olibi', y: 2025 },
    { id: 4, n: 'Namuna Mutaxassis', r: 'IT yo‘nalishi mutaxassisi', s: 'Informatika', sc: 'Namuna maktab №1', a: 'IT yo‘nalishi bo‘yicha yutuq', y: 2024 },
    { id: 5, n: 'Namuna Tarbiyachi', r: 'Boshlang‘ich sinf o‘qituvchisi', s: 'Boshlang‘ich ta’lim', sc: 'Namuna maktab №4', a: 'Eng yaxshi sinf rahbari', y: 2024 },
    { id: 6, n: 'Namuna Adabiyotchi', r: 'Ona tili va adabiyot o‘qituvchisi', s: 'Ona tili', sc: 'Namuna maktab №2', a: 'Ijodiy tanlov g‘olibi', y: 2023 },
    { id: 7, n: 'Namuna Fizik', r: 'Fizika o‘qituvchisi', s: 'Fizika', sc: 'Namuna maktab №5', a: 'Fan olimpiadasi murabbiyi', y: 2023 },
    { id: 8, n: 'Namuna Tilshunos', r: 'Ingliz tili o‘qituvchisi', s: 'Xorijiy tillar', sc: 'Namuna maktab №3', a: 'Xalqaro sertifikat sohibi', y: 2022 }
  ],
  schools: [
    { id: 1, n: 'Namuna maktab №1', t: 'Umumiy o‘rta ta’lim', h: 'Namuna Direktor', s: 'Faol' },
    { id: 2, n: 'Namuna maktab №2', t: 'Umumiy o‘rta ta’lim', h: 'Namuna Direktor', s: 'Faol' },
    { id: 3, n: 'Namuna maktab №3', t: 'Umumiy o‘rta ta’lim', h: 'Namuna Direktor', s: 'Faol' },
    { id: 4, n: 'Namuna maktab №4', t: 'Umumiy o‘rta ta’lim', h: 'Namuna Direktor', s: 'Faol' },
    { id: 5, n: 'Namuna ixtisoslashtirilgan maktab', t: 'Ixtisoslashtirilgan', h: 'Namuna Direktor', s: 'Faol' },
    { id: 6, n: 'Namuna maktabgacha ta’lim muassasasi №1', t: 'MTT', h: 'Namuna Mudira', s: 'Faol' },
    { id: 7, n: 'Namuna maktabgacha ta’lim muassasasi №2', t: 'MTT', h: 'Namuna Mudira', s: 'Faol' },
    { id: 8, n: 'Namuna ijod maktabi', t: 'Ijod maktabi', h: 'Namuna Rahbar', s: 'Yangi' },
    { id: 9, n: 'Namuna kasb-hunar maktabi', t: 'Kasbiy ta’lim', h: 'Namuna Direktor', s: 'Faol' }
  ],
  depts: [
    { n: 'Rahbariyat', d: 'Bo‘lim faoliyatini boshqaradi va muvofiqlashtiradi.', i: 'building', c: 'c-blue' },
    { n: 'Ta’lim sifati nazorati', d: 'Ta’lim sifatini monitoring qiladi va baholaydi.', i: 'shield', c: 'c-green' },
    { n: 'Metodik bo‘lim', d: 'Pedagoglarga metodik yordam ko‘rsatadi.', i: 'book', c: 'c-violet' },
    { n: 'Axborot texnologiyalari', d: 'Raqamli xizmatlar va axborot tizimlari.', i: 'globe', c: 'c-teal' },
    { n: 'Moliyaviy bo‘lim', d: 'Moliyaviy hisob va hisobotlar.', i: 'chart', c: 'c-orange' },
    { n: 'Kadrlar bo‘limi', d: 'Kadrlar bilan ishlash va hujjatlar.', i: 'users', c: 'c-red' }
  ],
  photos: [
    ['ceremony', 'Ustozlar kuni tadbiri'], ['hall', 'Tantanali yig‘ilish'], ['sport', 'Sport musobaqasi'], ['class', 'Sinf mashg‘uloti'], ['people', 'Pedagoglar uchrashuvi'], ['building', 'Muassasa binosi'],
    ['class', 'Fan olimpiadasi'], ['hall', 'Mukofotlash'], ['ceremony', 'Bitiruv kechasi'], ['sport', 'Sport bayrami'], ['people', 'Seminar'], ['building', 'Yangi bino']
  ],
  videos: [
    { t: 'Ustozlar kuni munosabati bilan tantanali tadbir', d: '01.10.2026', s: 'ceremony', l: '00:00' },
    { t: 'Yangi o‘quv yiliga tayyorgarlik', d: '28.09.2026', s: 'class', l: '00:00' },
    { t: 'Fan olimpiadasi g‘oliblari', d: '15.09.2026', s: 'people', l: '00:00' }
  ],
  docs: [
    { t: 'Normativ-huquqiy hujjat (namuna)', k: 'PDF', d: '01.10.2026', a: 'Administrator', st: 'Faol' },
    { t: 'Metodik tavsiyalar (namuna)', k: 'DOC', d: '27.09.2026', a: 'Metodist', st: 'Faol' },
    { t: 'Muassasalar ro‘yxati (namuna)', k: 'XLS', d: '20.09.2026', a: 'Hisobchi', st: 'Faol' },
    { t: 'O‘quv yili tartib-qoidalari (namuna)', k: 'PDF', d: '15.09.2026', a: 'Administrator', st: 'Faol' },
    { t: 'Attestatsiya jadvali (namuna)', k: 'XLS', d: '10.09.2026', a: 'Kadrlar bo‘limi', st: 'Arxiv' }
  ],
  notifs: [
    { id: 1, k: 'Topshiriqlar', t: 'Yangi topshiriq biriktirildi', x: 'Hisobot tayyorlash', w: '2 soat oldin', u: 1, i: 'clipboard', c: 'c-orange', h: 'topshiriqlar.html' },
    { id: 2, k: 'Yangiliklar', t: 'Yangilik e’lon qilindi', x: 'Ustozlar kuni munosabati bilan tadbir', w: 'Kecha, 16:20', u: 1, i: 'news', c: 'c-blue', h: '../news-detail.html?id=1' },
    { id: 3, k: 'Hujjatlar', t: 'Hujjat yangilandi', x: 'Metodik tavsiyalar', w: '2 kun oldin', u: 0, i: 'file', c: 'c-green', h: 'hujjatlar.html' },
    { id: 4, k: 'Topshiriqlar', t: 'Muddat yaqinlashmoqda', x: 'Maktablarni tekshirish — 10.10.2026', w: '3 kun oldin', u: 0, i: 'alert', c: 'c-red', h: 'topshiriqlar.html' },
    { id: 5, k: 'Yangiliklar', t: 'Yangi izoh qoldirildi', x: 'Yangi o‘quv yiliga tayyorgarlik', w: '4 kun oldin', u: 0, i: 'chat', c: 'c-violet', h: '../news-detail.html?id=2' },
    { id: 6, k: 'Hujjatlar', t: 'Yangi hujjat yuklandi', x: 'Attestatsiya jadvali', w: '1 hafta oldin', u: 0, i: 'upload', c: 'c-teal', h: 'hujjatlar.html' }
  ]
};
