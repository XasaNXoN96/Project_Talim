# Mirzacho‘l tumani Xalq ta’limi bo‘limi — UI/UX dizayn maketi

Statik dizayn maketi (HTML + CSS + JS, build va backend kerak emas). Barcha ma’lumotlar namunaviy.
Demo: https://xasanxon96.github.io/Project_Talim/

## Ommaviy sayt
`index.html` · `news.html` · `news-detail.html?id=` · `ustozlar.html` · `ustoz.html?id=` · `media.html` (rasm + video, `#video`) · `tashkilot.html` · `hujjatlar.html` · `login.html`

## Xodimlar portali (`app/`)
dashboard · yangiliklar · xodimlar · yutuqlar · sertifikatlar · topshiriqlar · hujjatlar · media · tashkilot · kirish-chiqish · geolokatsiya · chat · bildirishnomalar · hisobotlar · admin

## Tuzilma
- `assets/css/styles.css` — dizayn tokenlari va komponentlar
- `assets/js/app.js` — ikonkalar, umumiy shell (ommaviy sarlavha/footer, sidebar/topbar), modal, tab, lightbox, **i18n tayyorgarligi** (`I18N`, `t(key)`, `data-i18n`; hozir faqat uz, ru/en keyin to‘ldiriladi)
- `assets/js/data.js` — namunaviy kontent (yangiliklar, ustozlar, muassasalar, hujjatlar, bildirishnomalar)
- `assets/js/pages.js` — data.js asosida sahifalarni chizish (qidiruv/filtr bilan)

Barcha yo‘llar nisbiy — `/Project_Talim/` ostida ishlaydi. Til almashtirish tugmalari (RU/EN) hozircha faqat vizual.
