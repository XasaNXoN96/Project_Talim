# Список строк для проверки специалистом (RU/EN) / Translation review list

**Статус.** Переводы RU и EN подготовлены разработчиком с помощью ИИ-ассистента. **Профессиональной проверки носителем языка или переводчиком не проводилось.** Узбекский язык — язык-источник; отдельной редакторской вычитки узбекских текстов тоже не было. Этот список не заявляет качества перевода — он указывает, что нужно проверить человеку в первую очередь.

Файл сформирован автоматически из `backend/locale/{ru,en}/LC_MESSAGES/django.po`. Формат: исходная строка (UZ) → RU → EN. Каждая строка попадает только в первую подходящую категорию (категории пересекаются по смыслу). Если строку правят — править в `.po`, затем `compilemessages`, затем `manage.py test apps.core.tests_i18n`.

## Что именно просим проверить
1. Тон и уровень официальности писем и сообщений (обращение на «вы», канцелярский стиль).
2. Терминология: «Xodim» = «Сотрудник»/Employee, «Topshiriq» = «Задание»/Task, «Bo‘lim/Tuzilma» = «Подразделение»/Department — подтвердить, что это термины, принятые у заказчика (возможны «поручение», «отдел», «управление»).
3. Правовые и кадровые формулировки (категория C) — вместе с юристом заказчика.
4. Падежи и множественное число в RU после подстановки значений (`%(name)s`, числа).
5. Узбекская латиница: апострофы `‘ ’` и термины источника.
6. Длинные подписи в RU на узких экранах (проверено визуально на 390 px: горизонтальной прокрутки нет, но читаемость оценивает дизайнер).

Всего строк в каталогах: 650.


## A. E-mail texts (sent to real people; tone and formality matter) — 37

| # | UZ (источник) | RU | EN |
|---|---|---|---|
| 1 | Foydalanuvchi yaratildi. Endi unga taklifnoma yuboring. | Пользователь создан. Теперь отправьте ему приглашение. | The user was created. Now send them an invitation. |
| 2 | Taklifnoma yuborildi. | Приглашение отправлено. | The invitation was sent. |
| 3 | Parolni tiklash havolasi orqali hisobingizga yangi parol o‘rnatildi. Barcha sessiyalar yopildi. | По ссылке для восстановления для вашей учётной записи установлен новый пароль. Все сеансы завершены. | A new password was set for your account using a password-reset link. All sessions were closed. |
| 4 | Xodimlar portaliga taklif | Приглашение на портал сотрудников | Invitation to the staff portal |
| 5 | Siz uchun xodimlar portalida hisob yaratildi. | Для вас создана учётная запись на портале сотрудников. | An account was created for you on the staff portal. |
| 6 | Faol bo‘lmagan hisobga taklif yuborib bo‘lmaydi. | Нельзя отправить приглашение неактивной учётной записи. | An invitation cannot be sent to an inactive account. |
| 7 | Taklifnomalar juda ko‘p yuborildi. Keyinroq urinib ko‘ring. | Отправлено слишком много приглашений. Повторите позже. | Too many invitations were sent. Try again later. |
| 8 | Assalomu alaykum, %(name)s! ⏎  ⏎ Siz uchun %(site)s xodimlar portalida hisob yaratildi. ⏎ Login: %(login)s ⏎  ⏎ Parolni o‘rnatish uchun havolaga o‘ting (30 daqiqa amal qiladi, faqat bir marta ishlaydi): ⏎  ⏎ %(link)s ⏎  ⏎ Havola muddati tugasa, kirish sahifasidagi «Parolni unutdingizmi?» orqali yangisini so‘rang. ⏎  | Здравствуйте, %(name)s! ⏎  ⏎ Для вас создана учётная запись на портале сотрудников «%(site)s». ⏎ Логин: %(login)s ⏎  ⏎ Чтобы задать пароль, перейдите по ссылке (действует 30 минут, работает один раз): ⏎  ⏎ %(link)s ⏎  ⏎ Если срок действия ссылки истёк, запросите новую через «Забыли пароль?» на странице входа. ⏎  | Hello, %(name)s! ⏎  ⏎ An account was created for you on the “%(site)s” staff portal. ⏎ Username: %(login)s ⏎  ⏎ To set your password, open this link (valid for 30 minutes, works only once): ⏎  ⏎ %(link)s ⏎  ⏎ If the link has expired, request a new one with “Forgot your password?” on the sign-in page. ⏎  |
| 9 | %(site)s: portalga taklif | %(site)s: приглашение на портал | %(site)s: portal invitation |
| 10 | Kirish muddati tugadi. Qaytadan kiring. | Время входа истекло. Войдите заново. | The sign-in session expired. Please sign in again. |
| 11 | Parolni tiklash so‘raldi | Запрошено восстановление пароля | Password reset requested |
| 12 | Parolni tiklash so‘rovlari cheklandi | Запросы на восстановление пароля ограничены | Password reset requests throttled |
| 13 | Taklifnoma yuborildi | Приглашение отправлено | Invitation sent |
| 14 | Oddiy matn. Bo‘sh qator — yangi abzats. HTML va havolalar matn sifatida ko‘rinadi. | Простой текст. Пустая строка — новый абзац. HTML и ссылки отображаются как обычный текст. | Plain text. A blank line starts a new paragraph. HTML and links are shown as plain text. |
| 15 | Topshiriq muddati yaqin | Срок задания близко | A task is due soon |
| 16 | Topshiriq muddati o‘tdi | Срок задания истёк | A task is overdue |
| 17 | %(kind)s: %(title)s ⏎  ⏎ Batafsil ma’lumot uchun xodimlar portaliga kiring. | %(kind)s: %(title)s ⏎  ⏎ Подробности — на портале сотрудников. | %(kind)s: %(title)s ⏎  ⏎ See the staff portal for details. |
| 18 | Muddati o‘tgan (ochiq) | Просрочено (открытые) | Overdue (open) |
| 19 | Havola yaroqsiz | Ссылка недействительна | The link is not valid |
| 20 | Havola muddati tugagan, allaqachon ishlatilgan yoki noto‘g‘ri. Yangi havola so‘rang. | Срок действия ссылки истёк, она уже использована или неверна. Запросите новую ссылку. | The link has expired, was already used, or is incorrect. Request a new link. |
| 21 | Yangi havola so‘rash | Запросить новую ссылку | Request a new link |
| 22 | Havola yuborildi | Ссылка отправлена | Link sent |
| 23 | Agar kiritilgan e-pochta tizimda mavjud bo‘lsa, parolni tiklash havolasi yuborildi. Havola 30 daqiqa amal qiladi va faqat bir marta ishlaydi. | Если указанный адрес есть в системе, на него отправлена ссылка для восстановления пароля. Ссылка действует 30 минут и работает только один раз. | If the address you entered exists in the system, a password-reset link was sent to it. The link is valid for 30 minutes and works only once. |
| 24 | %(site_name)s xodimlar portalida parolni tiklash so‘raldi. | На портале сотрудников «%(site_name)s» запрошено восстановление пароля. | A password reset was requested on the “%(site_name)s” staff portal. |
| 25 | Yangi parol o‘rnatish uchun havolaga o‘ting (havola 30 daqiqa amal qiladi va faqat bir marta ishlaydi): | Чтобы задать новый пароль, перейдите по ссылке (действует 30 минут и работает только один раз): | To set a new password, open this link (valid for 30 minutes and works only once): |
| 26 | Parolni tiklash | Восстановление пароля | Password reset |
| 27 | Hisobingizga biriktirilgan e-pochta manzilini kiriting. Agar u tizimda bo‘lsa, parolni tiklash havolasi yuboriladi. | Введите адрес электронной почты вашей учётной записи. Если он есть в системе, мы отправим ссылку для восстановления пароля. | Enter the e-mail address of your account. If it exists in the system, we will send a password-reset link. |
| 28 | Havola yuborish | Отправить ссылку | Send link |
| 29 | %(site_name)s: parolni tiklash | %(site_name)s: восстановление пароля | %(site_name)s: password reset |
| 30 | Xodimlar portali | Портал сотрудников | Staff portal |
| 31 | Foydali havolalar | Полезные ссылки | Useful links |
| 32 | Bu sahifani ko‘rish uchun huquqingiz yetarli emas. | У вас недостаточно прав для просмотра этой страницы. | You do not have permission to view this page. |
| 33 | muddati o‘tgan | просрочено | overdue |
| 34 | Muddati o‘tgan | Просрочено | Overdue |
| 35 | Taklifnoma yuborish | Отправить приглашение | Send an invitation |
| 36 | Parol kiritilmaydi: foydalanuvchi o‘z parolini taklifnoma havolasi orqali o‘rnatadi. | Пароль не вводится: пользователь задаёт пароль сам по ссылке из приглашения. | No password is entered: the user sets their own password using the link in the invitation. |
| 37 | Xodimlar portaliga kirish uchun ma’lumotlaringizni kiriting. | Введите свои данные для входа на портал сотрудников. | Enter your details to sign in to the staff portal. |

## B. Security, login and 2FA messages (must be unambiguous) — 82

| # | UZ (источник) | RU | EN |
|---|---|---|---|
| 1 | Login yoki parol noto‘g‘ri yoki urinishlar soni chegaradan oshgan. 15 daqiqadan so‘ng qayta urinib ko‘ring. | Неверный логин или пароль, либо превышено число попыток. Повторите через 15 минут. | The login or password is incorrect, or the number of attempts was exceeded. Try again in 15 minutes. |
| 2 | Kod noto‘g‘ri yoki urinishlar soni chegaradan oshgan. 15 daqiqadan so‘ng qayta urinib ko‘ring. | Неверный код, либо превышено число попыток. Повторите через 15 минут. | The code is incorrect, or the number of attempts was exceeded. Try again in 15 minutes. |
| 3 | Joriy parol noto‘g‘ri yoki urinishlar soni chegaradan oshgan. 15 daqiqadan so‘ng qayta urinib ko‘ring. | Неверный текущий пароль, либо превышено число попыток. Повторите через 15 минут. | The current password is incorrect, or the number of attempts was exceeded. Try again in 15 minutes. |
| 4 | Parol | Пароль | Password |
| 5 | Yangi parol joriy paroldan farq qilishi kerak. | Новый пароль должен отличаться от текущего. | The new password must be different from the current one. |
| 6 | Tasdiqlash kodi yoki zaxira kod | Код подтверждения или резервный код | Verification code or backup code |
| 7 | Ilovadagi 6 xonali kod | 6-значный код из приложения | 6-digit code from the app |
| 8 | Joriy parol | Текущий пароль | Current password |
| 9 | Keyingi kirishda parolni almashtirish talab qilinadi. | При следующем входе потребуется сменить пароль. | A password change will be required at the next sign-in. |
| 10 | Xavfsizlik uchun qayta kiring: ikki bosqichli tasdiqlash talab qilinadi. | В целях безопасности войдите заново: требуется двухэтапное подтверждение. | For your security, please sign in again: two-step verification is required. |
| 11 | Davom etishdan oldin parolingizni almashtiring. | Прежде чем продолжить, смените пароль. | Please change your password before continuing. |
| 12 | parolni almashtirish shart | обязательная смена пароля | password change required |
| 13 | Parolingiz almashtirildi | Ваш пароль изменён | Your password was changed |
| 14 | Hisobingiz paroli almashtirildi. Boshqa qurilmalardagi sessiyalar yopildi. | Пароль вашей учётной записи изменён. Сеансы на других устройствах завершены. | Your account password was changed. Sessions on other devices were closed. |
| 15 | Parolingiz tiklandi | Ваш пароль сброшен | Your password was reset |
| 16 | Hisobingizda ikki bosqichli himoya (2FA) yoqildi. | Для вашей учётной записи включена двухэтапная защита (2FA). | Two-step protection (2FA) was turned on for your account. |
| 17 | Hisobingizda ikki bosqichli himoya (2FA) o‘chirildi. Endi hisob faqat parol bilan himoyalangan. | Для вашей учётной записи отключена двухэтапная защита (2FA). Теперь учётная запись защищена только паролем. | Two-step protection (2FA) was turned off for your account. It is now protected by a password only. |
| 18 | Zaxira kodlar yangilandi | Резервные коды обновлены | Backup codes regenerated |
| 19 | Hisobingizning zaxira kodlari yangilandi; eskilari bekor qilindi. | Резервные коды вашей учётной записи обновлены; прежние аннулированы. | The backup codes of your account were regenerated; the old ones are no longer valid. |
| 20 | 2FA administrator tomonidan tiklandi | 2FA сброшена администратором | 2FA reset by an administrator |
| 21 | Hisobingizning ikki bosqichli himoyasi administrator tomonidan olib tashlandi. Keyingi kirishda uni qayta sozlaysiz. | Двухэтапная защита вашей учётной записи снята администратором. При следующем входе вы настроите её заново. | The two-step protection of your account was removed by an administrator. You will set it up again at your next sign-in. |
| 22 | Agar buni siz qilmagan bo‘lsangiz, zudlik bilan administratorga murojaat qiling va parolingizni almashtiring. | Если это были не вы, немедленно обратитесь к администратору и смените пароль. | If this was not you, contact an administrator immediately and change your password. |
| 23 | Zaxira kodlaringiz kam qoldi. Yangilarini yarating. | Резервных кодов осталось мало. Создайте новые. | You are running low on backup codes. Generate new ones. |
| 24 | Zaxira kodlarni yangilash | Обновление резервных кодов | Regenerate backup codes |
| 25 | Yangi kodlar yaratish | Создать новые коды | Generate new codes |
| 26 | Eski zaxira kodlar bekor qilinadi. | Прежние резервные коды будут аннулированы. | The old backup codes will be invalidated. |
| 27 | Sizning rolingiz uchun 2FA majburiy: uni o‘chirib bo‘lmaydi. | Для вашей роли 2FA обязательна: её нельзя отключить. | 2FA is mandatory for your role: it cannot be turned off. |
| 28 | 2FA ni o‘chirish | Отключение 2FA | Turn off 2FA |
| 29 | Hisob faqat parol bilan himoyalanadi. | Учётная запись будет защищена только паролем. | The account will be protected by a password only. |
| 30 | 2FA o‘chirildi. | 2FA отключена. | 2FA was turned off. |
| 31 | Tizimga kirish | Вход в систему | Sign in |
| 32 | Muvaffaqiyatsiz kirish | Неудачная попытка входа | Failed sign-in attempt |
| 33 | Kirish vaqtincha bloklandi | Вход временно заблокирован | Sign-in temporarily locked |
| 34 | Bloklangan paytda kirishga urinish | Попытка входа во время блокировки | Sign-in attempt while locked |
| 35 | Parol almashtirildi | Пароль изменён | Password changed |
| 36 | Parol tiklandi | Пароль восстановлен | Password reset completed |
| 37 | 2FA yoqildi | 2FA включена | 2FA enabled |
| 38 | 2FA o‘chirildi | 2FA отключена | 2FA disabled |
| 39 | 2FA kodi noto‘g‘ri | Неверный код 2FA | Incorrect 2FA code |
| 40 | 2FA tekshiruvi vaqtincha bloklandi | Проверка 2FA временно заблокирована | 2FA verification temporarily locked |
| 41 | Bloklangan paytda 2FA urinishi | Попытка 2FA во время блокировки | 2FA attempt while locked |
| 42 | Zaxira kod ishlatildi | Использован резервный код | Backup code used |
| 43 | 2FA talab qilingani uchun sessiya yopildi | Сеанс закрыт: требуется 2FA | Session closed: 2FA required |
| 44 | Parolni almashtirish majburiy qilindi | Потребована смена пароля | Password change required |
| 45 | kirish darajasi | уровень доступа | access level |
| 46 | Parolni almashtirish | Смена пароля | Change password |
| 47 | Almashtirgandan so‘ng boshqa qurilmalardagi sessiyalar yopiladi. | После смены пароля сеансы на других устройствах будут завершены. | After the change, sessions on other devices will be closed. |
| 48 | Parolingiz yangilandi. Boshqa qurilmalardagi sessiyalar yopildi. | Пароль обновлён. Сеансы на других устройствах завершены. | Your password was updated. Sessions on other devices were closed. |
| 49 | Xavfsizlik sahifasiga qaytish | Вернуться к безопасности | Back to security |
| 50 | Yangi parol o‘rnatildi. Barcha eski sessiyalar yopildi. Endi kirishingiz mumkin. | Новый пароль установлен. Все прежние сеансы завершены. Теперь вы можете войти. | Your new password has been set. All previous sessions were closed. You can now sign in. |
| 51 | Kirish | Войти | Sign in |
| 52 | Yangi parol | Новый пароль | New password |
| 53 | Yangi parol o‘rnatish | Установка нового пароля | Set a new password |
| 54 | Parolni saqlash | Сохранить пароль | Save password |
| 55 | Kirish sahifasi | Страница входа | Sign-in page |
| 56 | Agar siz buni so‘ramagan bo‘lsangiz, bu xatga e’tibor bermang — parolingiz o‘zgarmaydi. | Если вы этого не запрашивали, проигнорируйте это письмо — ваш пароль не изменится. | If you did not request this, ignore this e-mail — your password will not change. |
| 57 | Xavfsizlik | Безопасность | Security |
| 58 | Parol va ikki bosqichli himoya | Пароль и двухэтапная защита | Password and two-step protection |
| 59 | Parolni almashtirsangiz, boshqa qurilmalardagi sessiyalar yopiladi. | После смены пароля сеансы на других устройствах будут завершены. | After you change your password, sessions on other devices will be closed. |
| 60 | Ikki bosqichli himoya (2FA) | Двухэтапная защита (2FA) | Two-step protection (2FA) |
| 61 | Qolgan zaxira kodlar: %(n)s | Осталось резервных кодов: %(n)s | Backup codes left: %(n)s |
| 62 | Sizning rolingiz uchun 2FA majburiy. | Для вашей роли 2FA обязательна. | 2FA is mandatory for your role. |
| 63 | 2FA ni yoqish | Включить 2FA | Turn on 2FA |
| 64 | Zaxira kodlar | Резервные коды | Backup codes |
| 65 | Bu kodlar faqat bir marta ko‘rsatiladi. Har biri bir marta ishlaydi va telefoningiz yo‘qolganda kirishga yordam beradi. Xavfsiz joyda saqlang. | Эти коды показываются только один раз. Каждый работает один раз и поможет войти, если вы потеряете телефон. Храните их в надёжном месте. | These codes are shown only once. Each works one time and helps you sign in if you lose your phone. Keep them somewhere safe. |
| 66 | 2FA ni sozlash | Настройка 2FA | Set up 2FA |
| 67 | Telefoningizda autentifikator ilovasini oching (masalan, Google Authenticator, Microsoft Authenticator, Aegis). | Откройте на телефоне приложение-аутентификатор (например, Google Authenticator, Microsoft Authenticator, Aegis). | Open an authenticator app on your phone (for example Google Authenticator, Microsoft Authenticator, Aegis). |
| 68 | QR-kodni skanerlang yoki maxfiy kalitni qo‘lda kiriting. | Отсканируйте QR-код или введите секретный ключ вручную. | Scan the QR code or enter the secret key manually. |
| 69 | Ilovada ko‘rinadigan 6 xonali kodni pastga kiriting. | Введите ниже 6-значный код из приложения. | Enter the 6-digit code shown in the app below. |
| 70 | Autentifikator ilovasidagi 6 xonali kodni kiriting. Qurilmangiz yo‘q bo‘lsa, zaxira kodlardan birini kiriting. | Введите 6-значный код из приложения-аутентификатора. Если устройства нет под рукой, введите один из резервных кодов. | Enter the 6-digit code from your authenticator app. If you do not have your device, enter one of your backup codes. |
| 71 | Xavfsizlik tekshiruvi muvaffaqiyatsiz tugadi. Sahifani yangilab, qayta urinib ko‘ring. | Проверка безопасности не пройдена. Обновите страницу и повторите попытку. | The security check failed. Refresh the page and try again. |
| 72 | Kirish, chiqish va rollar o‘zgarishi yozuvlari. Yozuvlarni o‘zgartirib yoki o‘chirib bo‘lmaydi. | Записи о входах, выходах и изменении ролей. Записи нельзя изменять или удалять. | Records of sign-ins, sign-outs and role changes. Records cannot be changed or deleted. |
| 73 | Bu portalning asosiy skeleti: kirish, rollar va audit ishlaydi. Xodimlar, topshiriqlar, hujjatlar va boshqa bo‘limlar keyingi bosqichlarda qo‘shiladi. | Это основа портала: работают вход, роли и аудит. Сотрудники, задания, документы и другие разделы будут добавлены на следующих этапах. | This is the portal’s foundation: sign-in, roles and audit work. Employees, tasks, documents and other sections will be added in later stages. |
| 74 | Xavfsizlik uchun faqat PDF, rasm va oddiy matn ko‘rsatiladi. Faylni yuklab olib oching. | В целях безопасности в портале показываются только PDF, изображения и простой текст. Скачайте файл и откройте его на своём устройстве. | For security, the portal shows only PDF, images and plain text. Download the file and open it on your device. |
| 75 | Vaqtincha bloklangan | Временно заблокирована | Temporarily locked |
| 76 | Parolni almashtirishi shart | Обязана сменить пароль | Must change password |
| 77 | 2FA majburiy, hali yoqilmagan | 2FA обязательна, ещё не включена | 2FA is mandatory, not yet enabled |
| 78 | 2FA yoqilmagan | 2FA не включена | 2FA is not enabled |
| 79 | Parolni almashtirishni talab qilish | Потребовать смену пароля | Require a password change |
| 80 | Hisoblar va rollar. Parollar bu yerda ko‘rinmaydi. | Учётные записи и роли. Пароли здесь не отображаются. | Accounts and roles. Passwords are never shown here. |
| 81 | Parolni ko‘rsatish | Показать пароль | Show password |
| 82 | Parolni unutdingizmi? | Забыли пароль? | Forgot your password? |

## C. Personal-data, privacy and access wording (legal weight) — 41

| # | UZ (источник) | RU | EN |
|---|---|---|---|
| 1 | Rollar va huquqlar | Роли и права | Roles and permissions |
| 2 | Kadrlar bo‘limi | Отдел кадров | HR department |
| 3 | Ma’lumotlar saqlandi. | Данные сохранены. | Changes saved. |
| 4 | Audit jurnali | Журнал аудита | Audit log |
| 5 | Xodim kartasi ko‘rildi (shaxsiy ma’lumotlar) | Просмотрена карточка сотрудника (личные данные) | Employee card viewed (personal data) |
| 6 | Maxfiy hujjat ko‘rildi | Просмотрен конфиденциальный документ | Confidential document viewed |
| 7 | Hujjat ma’lumotlari o‘zgartirildi | Данные документа изменены | Document details changed |
| 8 | audit yozuvi | запись аудита | audit entry |
| 9 | audit yozuvlari | записи аудита | audit entries |
| 10 | Formada xatolar bor. Kiritilgan ma’lumotlar saqlanib turibdi. | В форме есть ошибки. Введённые данные сохранены в полях. | The form has errors. What you entered is still in the fields. |
| 11 | Maxfiy (muallif va kadrlar/administrator) | Конфиденциально (автор, кадры и администратор) | Confidential (author, HR and administrator) |
| 12 | Barcha (maxfiy bo‘lmagan) hujjatlarni, jumladan bo‘limlarnikini ko‘rish | Просмотр всех неконфиденциальных документов, включая документы подразделений | View all non-confidential documents, including department documents |
| 13 | Maxfiy hujjatlarni ko‘rish | Просмотр конфиденциальных документов | View confidential documents |
| 14 | Bu fayl turi ruxsat etilmagan. Ruxsat etilgan: %(types)s. | Этот тип файла не разрешён. Разрешены: %(types)s. | This file type is not allowed. Allowed: %(types)s. |
| 15 | Bu topshiriqni ko‘rishga ruxsatingiz yo‘q yoki u o‘chirilgan. | У вас нет доступа к этому заданию, либо оно удалено. | You do not have access to this task, or it was deleted. |
| 16 | ish telefoni | рабочий телефон | work phone |
| 17 | shaxsiy telefon | личный телефон | personal phone |
| 18 | tug‘ilgan sana | дата рождения | date of birth |
| 19 | Xodimlarning aloqa ma’lumotlarini ko‘rish | Просмотр контактных данных сотрудников | View employees’ contact details |
| 20 | Xodimlarning shaxsiy ma’lumotlarini ko‘rish | Просмотр личных данных сотрудников | View employees’ personal data |
| 21 | Ma’lumot yo‘q. | Нет данных. | No data. |
| 22 | Hisobotda ijrochilar kesimini ko‘rish (shaxsiy natijalar) | Просмотр отчёта в разрезе исполнителей (личные результаты) | View the report broken down by assignee (personal results) |
| 23 | Shaxsiy natijalar: faqat ruxsati bor foydalanuvchilarga ko‘rinadi. | Личные результаты: видны только пользователям с соответствующим правом. | Personal results: visible only to users with the corresponding permission. |
| 24 | Faqat siz ko‘rishga ruxsat etilgan, faol hujjatlar hisoblanadi. | Учитываются только активные документы, которые вам разрешено просматривать. | Only active documents you are allowed to view are counted. |
| 25 | Manzil: tasdiqlangan ma’lumot kiritiladi | Адрес: будут указаны подтверждённые данные | Address: verified information will be added |
| 26 | Telefon: tasdiqlangan ma’lumot kiritiladi | Телефон: будут указаны подтверждённые данные | Phone: verified information will be added |
| 27 | E-pochta: tasdiqlangan ma’lumot kiritiladi | Эл. почта: будут указаны подтверждённые данные | E-mail: verified information will be added |
| 28 | Ruxsat yo‘q | Доступ запрещён | Access denied |
| 29 | Ruxsat etilgan: PDF, DOCX, XLSX, PPTX, ODT, ODS, PNG, JPG, TXT. Makroli va faol tarkibli fayllar qabul qilinmaydi. Yuklangan fayl antivirus bilan tekshiriladi; tekshiruv bajarilmasa, fayl qabul qilinmaydi. | Разрешены: PDF, DOCX, XLSX, PPTX, ODT, ODS, PNG, JPG, TXT. Файлы с макросами и активным содержимым не принимаются. Загружаемый файл проверяется антивирусом; если проверку выполнить не удалось, файл не принимается. | Allowed: PDF, DOCX, XLSX, PPTX, ODT, ODS, PNG, JPG, TXT. Files with macros or active content are not accepted. Uploaded files are scanned by an antivirus; if the scan cannot be completed, the file is not accepted. |
| 30 | Fayllar xavfsiz saqlanadi va faqat huquqingiz bo‘lsa yuklab olinadi. | Файлы хранятся в защищённом хранилище и скачиваются только при наличии прав. | Files are stored securely and can be downloaded only if you have permission. |
| 31 | Ish telefoni | Рабочий телефон | Work phone |
| 32 | Shaxsiy ma’lumotlar | Личные данные | Personal data |
| 33 | Bu ma’lumotlarni ko‘rish jurnalga yoziladi. | Просмотр этих данных фиксируется в журнале. | Viewing this data is recorded in the log. |
| 34 | Tug‘ilgan sana | Дата рождения | Date of birth |
| 35 | Shaxsiy telefon | Личный телефон | Personal phone |
| 36 | Haqiqiy shaxsiy ma’lumotlarni kiritishdan oldin huquqiy tekshiruv yakunlangan bo‘lishi kerak. | Перед внесением реальных личных данных должна быть завершена юридическая проверка. | A legal review must be completed before real personal data is entered. |
| 37 | Ism, bo‘lim, lavozim va holat. Aloqa ma’lumotlari xodim kartasida, ruxsat bo‘lsa ko‘rinadi. | Имя, подразделение, должность и статус. Контактные данные — на карточке сотрудника, если у вас есть право. | Name, department, position and status. Contact details are on the employee card, if you have permission. |
| 38 | Topshiriq mavjud emas yoki ruxsat yo‘q | Задание не существует или нет доступа | The task does not exist or you have no access |
| 39 | Tanlangan davr va filtrlar bo‘yicha ma’lumot yo‘q. | Нет данных за выбранный период и по выбранным фильтрам. | No data for the selected period and filters. |
| 40 | Ma’lumotlar bazasidagi joriy ma’lumotlar. Siz faqat o‘z doirangizdagi ma’lumotlarni ko‘rasiz. | Актуальные данные из базы данных. Вы видите только данные в пределах своей области. | Current data from the database. You only see data within your own scope. |
| 41 | Sizga berilgan, siz bergan va ko‘rishga ruxsat etilgan topshiriqlar. | Задания, назначенные вам, поручённые вами и те, которые вам разрешено просматривать. | Tasks assigned to you, assigned by you, and those you are allowed to view. |

## D. Statuses, roles and organisational terms (official terminology) — 94

| # | UZ (источник) | RU | EN |
|---|---|---|---|
| 1 | Bo‘lim | Подразделение | Department |
| 2 | rol biriktirish | назначение роли | role assignment |
| 3 | rol biriktirishlar | назначения ролей | role assignments |
| 4 | Bo‘lim doirasi uchun bo‘lim ko‘rsatilishi shart. | Для области «Подразделение» необходимо указать подразделение. | A department is required for the “Department” scope. |
| 5 | Bo‘lim faqat «Bo‘lim» doirasi uchun ko‘rsatiladi. | Подразделение указывается только для области «Подразделение». | A department can only be set for the “Department” scope. |
| 6 | Xodim | Сотрудник | Employee |
| 7 | Bo‘lim boshlig‘i | Руководитель подразделения | Department head |
| 8 | Kontent-menejer | Контент-менеджер | Content manager |
| 9 | Administrator | Администратор | Administrator |
| 10 | Tizim administratori | Системный администратор | System administrator |
| 11 | Rol | Роль | Role |
| 12 | Bo‘lim (faqat bo‘lim boshlig‘i uchun) | Подразделение (только для руководителя подразделения) | Department (only for a department head) |
| 13 | Rol yoki bo‘lim noto‘g‘ri tanlangan. | Роль или подразделение выбраны неверно. | The role or department selection is invalid. |
| 14 | Rol biriktirildi. | Роль назначена. | The role was assigned. |
| 15 | Rol olib tashlandi. | Роль снята. | The role was removed. |
| 16 | Rollarni biriktirish va olib tashlash | Назначение и снятие ролей | Assign and remove roles |
| 17 | Bu rolni faqat administrator bera oladi. | Эту роль может назначить только администратор. | Only an administrator can assign this role. |
| 18 | Noma’lum rol. | Неизвестная роль. | Unknown role. |
| 19 | Bo‘lim boshlig‘i roli uchun bo‘lim ko‘rsatilishi shart. | Для роли руководителя подразделения необходимо указать подразделение. | A department is required for the department head role. |
| 20 | Bu rol allaqachon biriktirilgan. | Эта роль уже назначена. | This role is already assigned. |
| 21 | Bu rolni faqat administrator olib tashlay oladi. | Эту роль может снять только администратор. | Only an administrator can remove this role. |
| 22 | O‘zingizning administrator rolingizni olib tashlab bo‘lmaydi. | Нельзя снять собственную роль администратора. | You cannot remove your own administrator role. |
| 23 | Oxirgi administratorning rolini olib tashlab bo‘lmaydi. | Нельзя снять роль у последнего администратора. | The last administrator’s role cannot be removed. |
| 24 | Oxirgi administratorni o‘chirib bo‘lmaydi. | Нельзя отключить последнего администратора. | The last administrator cannot be deactivated. |
| 25 | Rol biriktirildi | Роль назначена | Role assigned |
| 26 | Rol olib tashlandi | Роль снята | Role removed |
| 27 | Xodim qo‘shildi | Сотрудник добавлен | Employee added |
| 28 | Xodim o‘zgartirildi | Сотрудник изменён | Employee changed |
| 29 | Xodim arxivlandi | Сотрудник архивирован | Employee archived |
| 30 | Xodim arxivdan qaytarildi | Сотрудник восстановлен из архива | Employee restored from the archive |
| 31 | Tashkiliy tuzilma o‘zgartirildi | Организационная структура изменена | Organization structure changed |
| 32 | Kontent | Контент | Content |
| 33 | Tekshiruvda | На проверке | In review |
| 34 | Mirzacho‘l tumani Xalq ta’limi bo‘limi | Отдел народного образования Мирзачульского района | Mirzachul District Public Education Department |
| 35 | Xalq ta’limi bo‘limi | Отдел народного образования | Public Education Department |
| 36 | Faqat «Faqat bo‘lim» darajasi uchun. | Только для уровня «Только подразделение». | Only for the “Department only” level. |
| 37 | Bo‘lim darajasi uchun bo‘lim tanlang. | Для уровня «Подразделение» выберите подразделение. | Choose a department for the “Department” level. |
| 38 | faol | активно | active |
| 39 | Faol | Активен | Active |
| 40 | Arxivda | В архиве | Archived |
| 41 | Barcha xodimlar | Все сотрудники | All employees |
| 42 | Faqat bo‘lim | Только подразделение | Department only |
| 43 | bo‘lim | подразделение | department |
| 44 | Bu hisob boshqa xodimga biriktirilgan. | Эта учётная запись уже привязана к другому сотруднику. | This account is already linked to another employee. |
| 45 | Bu nomdagi bo‘lim shu joyda allaqachon bor. | Подразделение с таким названием здесь уже есть. | A department with this name already exists here. |
| 46 | Faol xodimlari yoki faol quyi bo‘limlari bor bo‘limni o‘chirib bo‘lmaydi. | Нельзя отключить подразделение, в котором есть активные сотрудники или активные дочерние подразделения. | A department with active employees or active sub-departments cannot be deactivated. |
| 47 | bo‘limlar | подразделения | departments |
| 48 | lavozim | должность | position |
| 49 | lavozimlar | должности | positions |
| 50 | Yangi | Новое | New |
| 51 | xodim | сотрудник | employee |
| 52 | xodimlar | сотрудники | employees |
| 53 | Xodimlar ro‘yxatini ko‘rish (ism, lavozim, bo‘lim, holat) | Просмотр списка сотрудников (имя, должность, подразделение, статус) | View the employee list (name, position, department, status) |
| 54 | Sizning hisobingizga xodim kartasi biriktirilmagan. | К вашей учётной записи не привязана карточка сотрудника. | No employee card is linked to your account. |
| 55 | Xodim qo‘shildi. | Сотрудник добавлен. | The employee was added. |
| 56 | Xodim arxivdan qaytarildi. | Сотрудник восстановлен из архива. | The employee was restored from the archive. |
| 57 | Xodim arxivlandi. | Сотрудник архивирован. | The employee was archived. |
| 58 | Lavozim | Должность | Position |
| 59 | Faol xodimlar | Активные сотрудники | Active employees |
| 60 | Xodimlar (arxivdan tashqari) | Сотрудники (без архива) | Employees (excluding archived) |
| 61 | Bo‘lim filtri: %(v)s | Фильтр по подразделению: %(v)s | Department filter: %(v)s |
| 62 | Hisobotlar sahifasini ko‘rish (doira rol bo‘yicha) | Просмотр страницы отчётов (область определяется ролью) | View the reports page (scope depends on the role) |
| 63 | Barcha bo‘limlar | Все подразделения | All departments |
| 64 | Bo‘lim: %(name)s | Подразделение: %(name)s | Department: %(name)s |
| 65 | Xodimlar: bo‘limlar bo‘yicha | Сотрудники: по подразделениям | Employees: by department |
| 66 | Xodimlar | Сотрудники | Employees |
| 67 | — (lavozim ko‘rsatilmagan) | — (должность не указана) | — (no position set) |
| 68 | Xodimlar: lavozimlar bo‘yicha | Сотрудники: по должностям | Employees: by position |
| 69 | — (bo‘limsiz) | — (без подразделения) | — (no department) |
| 70 | Bajarilish: bo‘limlar bo‘yicha | Выполнение: по подразделениям | Completion: by department |
| 71 | Bir nechta ijrochili topshiriq har bir ijrochining bo‘limida hisoblanadi. | Задание с несколькими исполнителями учитывается в подразделении каждого исполнителя. | A task with several assignees is counted in each assignee’s department. |
| 72 | Jarayonda | В работе | In progress |
| 73 | Bajarildi | Выполнено | Done |
| 74 | Bekor qilindi | Отменено | Cancelled |
| 75 | Bo‘lim (yoki butun tashkilot) topshiriqlarini ko‘rish | Просмотр заданий подразделения (или всей организации) | View tasks of a department (or the whole organization) |
| 76 | Sizning rolingiz uchun bu majburiy. Sozlashni tugatmaguncha tizimga kira olmaysiz. | Для вашей роли это обязательно. Пока вы не завершите настройку, войти в систему нельзя. | This is mandatory for your role. You cannot use the system until the setup is finished. |
| 77 | Bo‘limlar | Разделы | Sections |
| 78 | Tuzilma | Структура | Structure |
| 79 | Ishlab chiqish bosqichi: qolgan bo‘limlar keyingi bosqichlarda qo‘shiladi | Этап разработки: остальные разделы будут добавлены позже | Development stage: the remaining sections will be added later |
| 80 | Rollar | Роли | Roles |
| 81 | rol biriktirilmagan | роль не назначена | no role assigned |
| 82 | Xodim qo‘shish | Добавить сотрудника | Add an employee |
| 83 | Qidirish: ism, lavozim | Поиск: имя, должность | Search: name, position |
| 84 | Xatolik yuz berdi. Keyinroq qayta urinib ko‘ring; muammo davom etsa, administratorga murojaat qiling. | Произошла ошибка. Повторите попытку позже; если проблема сохраняется, обратитесь к администратору. | An error occurred. Try again later; if the problem persists, contact an administrator. |
| 85 | Tashkiliy tuzilma | Организационная структура | Organization structure |
| 86 | Bo‘limlar daraxti va lavozimlar. Bo‘limlar o‘chirilmaydi, faqat faol emas qilinadi. | Дерево подразделений и должности. Подразделения не удаляются, а только отключаются. | Department tree and positions. Departments are never deleted, only deactivated. |
| 87 | Bo‘lim qo‘shish | Добавить подразделение | Add a department |
| 88 | Lavozim qo‘shish | Добавить должность | Add a position |
| 89 | Bo‘limlar hali kiritilmagan. | Подразделения ещё не внесены. | No departments have been entered yet. |
| 90 | Lavozimlar | Должности | Positions |
| 91 | Lavozimlar hali kiritilmagan. | Должности ещё не внесены. | No positions have been entered yet. |
| 92 | Rol biriktirilmagan: foydalanuvchi hech narsaga kira olmaydi. | Роль не назначена: пользователь ни к чему не имеет доступа. | No role assigned: the user cannot access anything. |
| 93 | Rol biriktirish | Назначить роль | Assign a role |
| 94 | Barcha rollar | Все роли | All roles |

## E. Task and document workflow wording — 69

| # | UZ (источник) | RU | EN |
|---|---|---|---|
| 1 | Hujjat yuklandi | Документ загружен | Document uploaded |
| 2 | Hujjatning yangi versiyasi yuklandi | Загружена новая версия документа | New document version uploaded |
| 3 | Hujjat yuklab olindi | Документ скачан | Document downloaded |
| 4 | Hujjat arxivlandi | Документ архивирован | Document archived |
| 5 | Hujjat arxivdan qaytarildi | Документ восстановлен из архива | Document restored from the archive |
| 6 | Hujjat yuklash rad etildi | Загрузка документа отклонена | Document upload rejected |
| 7 | Hisobot yuklab olindi | Отчёт скачан | Report downloaded |
| 8 | Hisobotda ijrochilar kesimi ko‘rildi | Просмотрен разрез отчёта по исполнителям | Report breakdown by assignee viewed |
| 9 | Topshiriqqa fayl biriktirildi | К заданию прикреплён файл | File attached to a task |
| 10 | Topshiriq fayli yuklab olindi | Файл задания скачан | Task file downloaded |
| 11 | Topshiriq fayli olib tashlandi | Файл задания откреплён | Task file removed |
| 12 | Hujjatlar | Документы | Documents |
| 13 | Hisobotlar | Отчёты | Reports |
| 14 | hujjat turkumi | категория документов | document category |
| 15 | hujjat turkumlari | категории документов | document categories |
| 16 | hujjat raqami | номер документа | document number |
| 17 | turkum | категория | category |
| 18 | hujjat sanasi | дата документа | document date |
| 19 | hujjat | документ | document |
| 20 | hujjatlar | документы | documents |
| 21 | Hujjat yuklandi. | Документ загружен. | The document was uploaded. |
| 22 | Yangi versiya (v%(n)d) yuklandi. | Загружена новая версия (v%(n)d). | A new version (v%(n)d) was uploaded. |
| 23 | Hujjat arxivdan qaytarildi. | Документ восстановлен из архива. | The document was restored from the archive. |
| 24 | Hujjat arxivlandi. | Документ архивирован. | The document was archived. |
| 25 | Bildirishnomalar | Уведомления | Notifications |
| 26 | Topshiriq berildi | Вам назначено задание | A task was assigned to you |
| 27 | Topshiriq tekshiruvga topshirildi | Задание сдано на проверку | A task was submitted for review |
| 28 | Topshiriq qabul qilindi | Задание принято | A task was accepted |
| 29 | Topshiriq qaytarildi | Задание возвращено на доработку | A task was returned for rework |
| 30 | Topshiriq bekor qilindi | Задание отменено | A task was cancelled |
| 31 | Davrda yaratilgan topshiriqlar | Заданий создано за период | Tasks created in the period |
| 32 | Davrda yakunlangan topshiriqlar | Заданий завершено за период | Tasks completed in the period |
| 33 | Davrda yuklangan hujjatlar | Документов загружено за период | Documents uploaded in the period |
| 34 | Topshiriq holati: %(v)s | Статус задания: %(v)s | Task status: %(v)s |
| 35 | Hujjat turkumi: %(v)s | Категория документов: %(v)s | Document category: %(v)s |
| 36 | Hisobot | Отчёт | Report |
| 37 | Topshiriqlar dinamikasi | Динамика заданий | Task trend |
| 38 | Hisobotlarni Excel/PDF ga yuklab olish | Скачивание отчётов в Excel/PDF | Download reports as Excel/PDF |
| 39 | Topshiriq holati | Статус задания | Task status |
| 40 | Hujjat turkumi | Категория документов | Document category |
| 41 | Barcha turkumlar | Все категории | All categories |
| 42 | Topshiriqlar: holatlar bo‘yicha | Задания: по статусам | Tasks: by status |
| 43 | Bajarilish: ijrochilar bo‘yicha | Выполнение: по исполнителям | Completion: by assignee |
| 44 | Ijrochi | Исполнитель | Assignee |
| 45 | Hujjatlar: turkumlar bo‘yicha | Документы: по категориям | Documents: by category |
| 46 | Turkum | Категория | Category |
| 47 | Hujjatlar: davrlar bo‘yicha | Документы: по периодам | Documents: by period |
| 48 | Faqat hujjat yuklangan davrlar ko‘rsatiladi. | Показаны только периоды, в которые загружались документы. | Only periods in which documents were uploaded are shown. |
| 49 | Topshiriqlar | Задания | Tasks |
| 50 | Ijrochilar | Исполнители | Assignees |
| 51 | Bir nechta ijrochini Ctrl (⌘) bosib tanlang. | Для выбора нескольких исполнителей удерживайте Ctrl (⌘). | Hold Ctrl (⌘) to select several assignees. |
| 52 | Kamida bitta ijrochi tanlang. | Выберите хотя бы одного исполнителя. | Select at least one assignee. |
| 53 | topshiriq | задание | task |
| 54 | topshiriqlar | задания | tasks |
| 55 | Faylni topshiriqdan olib tashlash (faylning o‘zi o‘chirilmaydi) | Открепление файла от задания (сам файл не удаляется) | Remove a file from a task (the file itself is not deleted) |
| 56 | Topshiriq yaratildi. | Задание создано. | The task was created. |
| 57 | Bitta topshiriqqa %(n)d tadan ortiq fayl biriktirib bo‘lmaydi. | К одному заданию нельзя прикрепить более %(n)d файлов. | No more than %(n)d files can be attached to one task. |
| 58 | Fayl topshiriqdan olib tashlandi. | Файл откреплён от задания. | The file was removed from the task. |
| 59 | Versiyalar | Версии | Versions |
| 60 | Yangi versiya yuklash | Загрузить новую версию | Upload a new version |
| 61 | Hujjat yuklash | Загрузка документа | Upload a document |
| 62 | Hujjatlar topilmadi | Документы не найдены | No documents found |
| 63 | Hujjat sahifasi | Страница документа | Document page |
| 64 | Hujjat arxivda. | Документ находится в архиве. | The document is archived. |
| 65 | Topshiriqlar bo‘yicha yangiliklar. | Новости по заданиям. | News about tasks. |
| 66 | Bildirishnomalar yo‘q | Уведомлений нет | No notifications |
| 67 | Hisobotni tayyorlab bo‘lmadi | Не удалось подготовить отчёт | The report could not be prepared |
| 68 | Yangi topshiriq | Новое задание | New task |
| 69 | Topshiriqlar yo‘q | Заданий нет | No tasks |

## F. Остальные строки — 327

Интерфейсные подписи общего назначения (кнопки, заголовки, подсказки). Проверяются выборочно при общей вычитке; полный список — в файлах `.po`.

