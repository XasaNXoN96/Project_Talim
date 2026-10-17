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

Всего строк в каталогах: 831.


## A. E-mail texts (sent to real people; tone and formality matter) — 47

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
| 15 | Topshiriq eslatmalarini yuborish | Отправка напоминаний по заданиям | Sending task reminders |
| 16 | Muddati o‘tgan sessiyalarni tozalash | Очистка просроченных сессий | Cleaning expired sessions |
| 17 | Zaxira nusxadan tiklash tekshirildi | Восстановление из резервной копии проверено | Restore from a backup verified |
| 18 | Topshiriq muddati yaqin | Срок задания близко | A task is due soon |
| 19 | Topshiriq muddati o‘tdi | Срок задания истёк | A task is overdue |
| 20 | %(kind)s: %(title)s ⏎  ⏎ Batafsil ma’lumot uchun xodimlar portaliga kiring. | %(kind)s: %(title)s ⏎  ⏎ Подробности — на портале сотрудников. | %(kind)s: %(title)s ⏎  ⏎ See the staff portal for details. |
| 21 | Bu import allaqachon bajarilgan, bekor qilingan yoki muddati o‘tgan. | Этот импорт уже выполнен, отменён или просрочен. | This import has already been completed, cancelled or has expired. |
| 22 | Muddati o‘tdi | Срок истёк | Expired |
| 23 | Muddati o‘tgan (ochiq) | Просрочено (открытые) | Overdue (open) |
| 24 | Havola yaroqsiz | Ссылка недействительна | The link is not valid |
| 25 | Havola muddati tugagan, allaqachon ishlatilgan yoki noto‘g‘ri. Yangi havola so‘rang. | Срок действия ссылки истёк, она уже использована или неверна. Запросите новую ссылку. | The link has expired, was already used, or is incorrect. Request a new link. |
| 26 | Yangi havola so‘rash | Запросить новую ссылку | Request a new link |
| 27 | Havola yuborildi | Ссылка отправлена | Link sent |
| 28 | Agar kiritilgan e-pochta tizimda mavjud bo‘lsa, parolni tiklash havolasi yuborildi. Havola 30 daqiqa amal qiladi va faqat bir marta ishlaydi. | Если указанный адрес есть в системе, на него отправлена ссылка для восстановления пароля. Ссылка действует 30 минут и работает только один раз. | If the address you entered exists in the system, a password-reset link was sent to it. The link is valid for 30 minutes and works only once. |
| 29 | %(site_name)s xodimlar portalida parolni tiklash so‘raldi. | На портале сотрудников «%(site_name)s» запрошено восстановление пароля. | A password reset was requested on the “%(site_name)s” staff portal. |
| 30 | Yangi parol o‘rnatish uchun havolaga o‘ting (havola 30 daqiqa amal qiladi va faqat bir marta ishlaydi): | Чтобы задать новый пароль, перейдите по ссылке (действует 30 минут и работает только один раз): | To set a new password, open this link (valid for 30 minutes and works only once): |
| 31 | Parolni tiklash | Восстановление пароля | Password reset |
| 32 | Hisobingizga biriktirilgan e-pochta manzilini kiriting. Agar u tizimda bo‘lsa, parolni tiklash havolasi yuboriladi. | Введите адрес электронной почты вашей учётной записи. Если он есть в системе, мы отправим ссылку для восстановления пароля. | Enter the e-mail address of your account. If it exists in the system, we will send a password-reset link. |
| 33 | Havola yuborish | Отправить ссылку | Send link |
| 34 | %(site_name)s: parolni tiklash | %(site_name)s: восстановление пароля | %(site_name)s: password reset |
| 35 | Amal qilish muddati | Действует до | Valid until |
| 36 | Oxirgi faollik taxminan 5 daqiqa aniqlikda ko‘rsatiladi. Brauzer yopilgan bo‘lsa ham, sessiya muddati tugamaguncha server uchun amalda bo‘lib turadi. Joylashuv va qurilma modeli aniqlanmaydi. | Последняя активность показана с точностью около 5 минут. Даже если браузер закрыт, сессия остаётся действующей для сервера до истечения срока. Местоположение и модель устройства не определяются. | Last activity is shown to within about 5 minutes. Even if the browser was closed, the session stays valid for the server until it expires. Location and device model are not determined. |
| 37 | Xodimlar portali | Портал сотрудников | Staff portal |
| 38 | Foydali havolalar | Полезные ссылки | Useful links |
| 39 | Bu sahifani ko‘rish uchun huquqingiz yetarli emas. | У вас недостаточно прав для просмотра этой страницы. | You do not have permission to view this page. |
| 40 | Ko‘rib chiqish muddati o‘tdi, yuklangan qatorlar o‘chirildi. Faylni qayta yuklang. | Срок проверки истёк, загруженные строки удалены. Загрузите файл заново. | The review period has expired and the uploaded rows were deleted. Upload the file again. |
| 41 | Sanalar: YYYY-MM-DD yoki DD.MM.YYYY. Formulalar, makroslar va havolalar qabul qilinmaydi. | Даты: YYYY-MM-DD или DD.MM.YYYY. Формулы, макросы и ссылки не принимаются. | Dates: YYYY-MM-DD or DD.MM.YYYY. Formulas, macros and links are not accepted. |
| 42 | Zaxira nusxa: “yaratildi” — arxiv yozildi va o‘qib chiqildi; “tiklash tekshirildi” — eng yangi nusxa alohida baza va katalogga haqiqatan tiklab ko‘rildi. Ikkalasi ham nusxa SHU serverdan tashqarida saqlanayotganini tasdiqlamaydi: bir serverdagi nusxa serverning yo‘qolishidan himoya qilmaydi. | Резервные копии: «создана» — архив записан и прочитан обратно; «восстановление проверено» — самая новая копия действительно восстановлена в отдельную базу и каталог. Ни то, ни другое не подтверждает, что копия хранится вне ЭТОГО сервера: копия на том же сервере не защищает от его потери. | Backups: “created” — the archive was written and read back; “restore verified” — the newest backup was really restored into a separate database and directory. Neither confirms that the copy is stored away from THIS server: a copy on the same server does not protect against losing it. |
| 43 | muddati o‘tgan | просрочено | overdue |
| 44 | Muddati o‘tgan | Просрочено | Overdue |
| 45 | Taklifnoma yuborish | Отправить приглашение | Send an invitation |
| 46 | Parol kiritilmaydi: foydalanuvchi o‘z parolini taklifnoma havolasi orqali o‘rnatadi. | Пароль не вводится: пользователь задаёт пароль сам по ссылке из приглашения. | No password is entered: the user sets their own password using the link in the invitation. |
| 47 | Xodimlar portaliga kirish uchun ma’lumotlaringizni kiriting. | Введите свои данные для входа на портал сотрудников. | Enter your details to sign in to the staff portal. |

## B. Security, login and 2FA messages (must be unambiguous) — 102

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
| 31 | Joriy sessiyani yakunlash uchun tizimdan chiqing. | Чтобы завершить текущую сессию, выйдите из системы. | To end the current session, sign out. |
| 32 | Bu sessiya allaqachon yakunlangan. | Эта сессия уже завершена. | This session has already ended. |
| 33 | Sessiya yakunlandi. | Сессия завершена. | Session ended. |
| 34 | Boshqa sessiyalar yakunlandi. | Остальные сессии завершены. | The other sessions were ended. |
| 35 | Yakunlash uchun boshqa sessiya yo‘q. | Других сессий для завершения нет. | There are no other sessions to end. |
| 36 | Tizimga kirish | Вход в систему | Sign in |
| 37 | Muvaffaqiyatsiz kirish | Неудачная попытка входа | Failed sign-in attempt |
| 38 | Kirish vaqtincha bloklandi | Вход временно заблокирован | Sign-in temporarily locked |
| 39 | Bloklangan paytda kirishga urinish | Попытка входа во время блокировки | Sign-in attempt while locked |
| 40 | Parol almashtirildi | Пароль изменён | Password changed |
| 41 | Parol tiklandi | Пароль восстановлен | Password reset completed |
| 42 | 2FA yoqildi | 2FA включена | 2FA enabled |
| 43 | 2FA o‘chirildi | 2FA отключена | 2FA disabled |
| 44 | 2FA kodi noto‘g‘ri | Неверный код 2FA | Incorrect 2FA code |
| 45 | 2FA tekshiruvi vaqtincha bloklandi | Проверка 2FA временно заблокирована | 2FA verification temporarily locked |
| 46 | Bloklangan paytda 2FA urinishi | Попытка 2FA во время блокировки | 2FA attempt while locked |
| 47 | Zaxira kod ishlatildi | Использован резервный код | Backup code used |
| 48 | 2FA talab qilingani uchun sessiya yopildi | Сеанс закрыт: требуется 2FA | Session closed: 2FA required |
| 49 | Parolni almashtirish majburiy qilindi | Потребована смена пароля | Password change required |
| 50 | Sessiya yakunlandi | Сессия завершена | Session ended |
| 51 | Boshqa sessiyalar yakunlandi | Остальные сессии завершены | Other sessions ended |
| 52 | Urinishlar hisoblagichini tozalash | Очистка счётчиков попыток входа | Cleaning attempt counters |
| 53 | Zaxira nusxa yaratildi (arxiv o‘qiladi) | Резервная копия создана (архив читается) | Backup created (the archive can be read) |
| 54 | kirish darajasi | уровень доступа | access level |
| 55 | Parolni almashtirish | Смена пароля | Change password |
| 56 | Almashtirgandan so‘ng boshqa qurilmalardagi sessiyalar yopiladi. | После смены пароля сеансы на других устройствах будут завершены. | After the change, sessions on other devices will be closed. |
| 57 | Parolingiz yangilandi. Boshqa qurilmalardagi sessiyalar yopildi. | Пароль обновлён. Сеансы на других устройствах завершены. | Your password was updated. Sessions on other devices were closed. |
| 58 | Xavfsizlik sahifasiga qaytish | Вернуться к безопасности | Back to security |
| 59 | Yangi parol o‘rnatildi. Barcha eski sessiyalar yopildi. Endi kirishingiz mumkin. | Новый пароль установлен. Все прежние сеансы завершены. Теперь вы можете войти. | Your new password has been set. All previous sessions were closed. You can now sign in. |
| 60 | Kirish | Войти | Sign in |
| 61 | Yangi parol | Новый пароль | New password |
| 62 | Yangi parol o‘rnatish | Установка нового пароля | Set a new password |
| 63 | Parolni saqlash | Сохранить пароль | Save password |
| 64 | Kirish sahifasi | Страница входа | Sign-in page |
| 65 | Agar siz buni so‘ramagan bo‘lsangiz, bu xatga e’tibor bermang — parolingiz o‘zgarmaydi. | Если вы этого не запрашивали, проигнорируйте это письмо — ваш пароль не изменится. | If you did not request this, ignore this e-mail — your password will not change. |
| 66 | Xavfsizlik | Безопасность | Security |
| 67 | Parol va ikki bosqichli himoya | Пароль и двухэтапная защита | Password and two-step protection |
| 68 | Parolni almashtirsangiz, boshqa qurilmalardagi sessiyalar yopiladi. | После смены пароля сеансы на других устройствах будут завершены. | After you change your password, sessions on other devices will be closed. |
| 69 | Faol sessiyalar | Активные сессии | Active sessions |
| 70 | Qaysi qurilmalardan kirilganini ko‘ring va keraksiz sessiyalarni yakunlang. | Посмотрите, с каких устройств выполнен вход, и завершите ненужные сессии. | See which devices are signed in and end the sessions you do not need. |
| 71 | Sessiyalarni ko‘rish | Посмотреть сессии | View sessions |
| 72 | Ikki bosqichli himoya (2FA) | Двухэтапная защита (2FA) | Two-step protection (2FA) |
| 73 | Qolgan zaxira kodlar: %(n)s | Осталось резервных кодов: %(n)s | Backup codes left: %(n)s |
| 74 | Sizning rolingiz uchun 2FA majburiy. | Для вашей роли 2FA обязательна. | 2FA is mandatory for your role. |
| 75 | 2FA ni yoqish | Включить 2FA | Turn on 2FA |
| 76 | Sessiyani yakunlash | Завершить сессию | End session |
| 77 | Bu sessiya yakunlansa, o‘sha qurilmada qayta kirish kerak bo‘ladi. | После завершения этой сессии на том устройстве нужно будет войти заново. | If this session is ended, you will have to sign in again on that device. |
| 78 | Hisobingizga kirilgan va server hali qabul qilayotgan sessiyalar. Tanimagan sessiya bo‘lsa, uni yakunlang va parolni almashtiring. | Сессии, в которых выполнен вход в вашу учётную запись и которые сервер ещё принимает. Если видите незнакомую сессию — завершите её и смените пароль. | Sessions signed in to your account that the server still accepts. If you see one you do not recognise, end it and change your password. |
| 79 | Boshqa barcha sessiyalarni yakunlash | Завершить все остальные сессии | End all other sessions |
| 80 | Joriy sessiya | Текущая сессия | Current session |
| 81 | Faol sessiyalar topilmadi | Активных сессий не найдено | No active sessions found |
| 82 | Boshqa sessiyalarni yakunlash | Завершить остальные сессии | End other sessions |
| 83 | Joriy sessiyadan tashqari barcha sessiyalar yakunlanadi (%(count)s ta ko‘rinadigan). Siz bu qurilmada tizimda qolasiz; boshqa qurilmalarda qayta kirish kerak bo‘ladi. | Все сессии, кроме текущей, будут завершены (видимых: %(count)s). На этом устройстве вы останетесь в системе; на других нужно будет войти заново. | All sessions except the current one will be ended (%(count)s visible). You stay signed in on this device; on the others you will have to sign in again. |
| 84 | Zaxira kodlar | Резервные коды | Backup codes |
| 85 | Bu kodlar faqat bir marta ko‘rsatiladi. Har biri bir marta ishlaydi va telefoningiz yo‘qolganda kirishga yordam beradi. Xavfsiz joyda saqlang. | Эти коды показываются только один раз. Каждый работает один раз и поможет войти, если вы потеряете телефон. Храните их в надёжном месте. | These codes are shown only once. Each works one time and helps you sign in if you lose your phone. Keep them somewhere safe. |
| 86 | 2FA ni sozlash | Настройка 2FA | Set up 2FA |
| 87 | Telefoningizda autentifikator ilovasini oching (masalan, Google Authenticator, Microsoft Authenticator, Aegis). | Откройте на телефоне приложение-аутентификатор (например, Google Authenticator, Microsoft Authenticator, Aegis). | Open an authenticator app on your phone (for example Google Authenticator, Microsoft Authenticator, Aegis). |
| 88 | QR-kodni skanerlang yoki maxfiy kalitni qo‘lda kiriting. | Отсканируйте QR-код или введите секретный ключ вручную. | Scan the QR code or enter the secret key manually. |
| 89 | Ilovada ko‘rinadigan 6 xonali kodni pastga kiriting. | Введите ниже 6-значный код из приложения. | Enter the 6-digit code shown in the app below. |
| 90 | Autentifikator ilovasidagi 6 xonali kodni kiriting. Qurilmangiz yo‘q bo‘lsa, zaxira kodlardan birini kiriting. | Введите 6-значный код из приложения-аутентификатора. Если устройства нет под рукой, введите один из резервных кодов. | Enter the 6-digit code from your authenticator app. If you do not have your device, enter one of your backup codes. |
| 91 | Xavfsizlik tekshiruvi muvaffaqiyatsiz tugadi. Sahifani yangilab, qayta urinib ko‘ring. | Проверка безопасности не пройдена. Обновите страницу и повторите попытку. | The security check failed. Refresh the page and try again. |
| 92 | Kirish, chiqish va rollar o‘zgarishi yozuvlari. Yozuvlarni o‘zgartirib yoki o‘chirib bo‘lmaydi. | Записи о входах, выходах и изменении ролей. Записи нельзя изменять или удалять. | Records of sign-ins, sign-outs and role changes. Records cannot be changed or deleted. |
| 93 | Bu portalning asosiy skeleti: kirish, rollar va audit ishlaydi. Xodimlar, topshiriqlar, hujjatlar va boshqa bo‘limlar keyingi bosqichlarda qo‘shiladi. | Это основа портала: работают вход, роли и аудит. Сотрудники, задания, документы и другие разделы будут добавлены на следующих этапах. | This is the portal’s foundation: sign-in, roles and audit work. Employees, tasks, documents and other sections will be added in later stages. |
| 94 | Xavfsizlik uchun faqat PDF, rasm va oddiy matn ko‘rsatiladi. Faylni yuklab olib oching. | В целях безопасности в портале показываются только PDF, изображения и простой текст. Скачайте файл и откройте его на своём устройстве. | For security, the portal shows only PDF, images and plain text. Download the file and open it on your device. |
| 95 | Vaqtincha bloklangan | Временно заблокирована | Temporarily locked |
| 96 | Parolni almashtirishi shart | Обязана сменить пароль | Must change password |
| 97 | 2FA majburiy, hali yoqilmagan | 2FA обязательна, ещё не включена | 2FA is mandatory, not yet enabled |
| 98 | 2FA yoqilmagan | 2FA не включена | 2FA is not enabled |
| 99 | Parolni almashtirishni talab qilish | Потребовать смену пароля | Require a password change |
| 100 | Hisoblar va rollar. Parollar bu yerda ko‘rinmaydi. | Учётные записи и роли. Пароли здесь не отображаются. | Accounts and roles. Passwords are never shown here. |
| 101 | Parolni ko‘rsatish | Показать пароль | Show password |
| 102 | Parolni unutdingizmi? | Забыли пароль? | Forgot your password? |

## C. Personal-data, privacy and access wording (legal weight) — 51

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
| 11 | Bu amal uchun ruxsatingiz yo‘q. | У вас нет прав на это действие. | You do not have permission for this action. |
| 12 | Maxfiy (muallif va kadrlar/administrator) | Конфиденциально (автор, кадры и администратор) | Confidential (author, HR and administrator) |
| 13 | Barcha (maxfiy bo‘lmagan) hujjatlarni, jumladan bo‘limlarnikini ko‘rish | Просмотр всех неконфиденциальных документов, включая документы подразделений | View all non-confidential documents, including department documents |
| 14 | Maxfiy hujjatlarni ko‘rish | Просмотр конфиденциальных документов | View confidential documents |
| 15 | Bu fayl turi ruxsat etilmagan. Ruxsat etilgan: %(types)s. | Этот тип файла не разрешён. Разрешены: %(types)s. | This file type is not allowed. Allowed: %(types)s. |
| 16 | Bu topshiriqni ko‘rishga ruxsatingiz yo‘q yoki u o‘chirilgan. | У вас нет доступа к этому заданию, либо оно удалено. | You do not have access to this task, or it was deleted. |
| 17 | Import bekor qilindi. Yuklangan ma’lumotlar o‘chirildi. | Импорт отменён. Загруженные данные удалены. | Import cancelled. The uploaded data was deleted. |
| 18 | Qiymatda ruxsat etilmagan belgilar bor. | В значении есть недопустимые символы. | The value contains characters that are not allowed. |
| 19 | Noma’lum holat: “%(value)s”. Ruxsat etilgan: %(allowed)s. | Неизвестный статус: «%(value)s». Допустимо: %(allowed)s. | Unknown status: “%(value)s”. Allowed: %(allowed)s. |
| 20 | Telefon raqami noto‘g‘ri formatda. | Неверный формат телефона. | The phone number has an invalid format. |
| 21 | Sana ruxsat etilgan oraliqdan tashqarida. | Дата вне допустимого диапазона. | The date is outside the allowed range. |
| 22 | Faylda ma’lumotli varaq yo‘q. | В файле нет листа с данными. | The file has no sheet with data. |
| 23 | ish telefoni | рабочий телефон | work phone |
| 24 | shaxsiy telefon | личный телефон | personal phone |
| 25 | tug‘ilgan sana | дата рождения | date of birth |
| 26 | Xodimlarning aloqa ma’lumotlarini ko‘rish | Просмотр контактных данных сотрудников | View employees’ contact details |
| 27 | Xodimlarning shaxsiy ma’lumotlarini ko‘rish | Просмотр личных данных сотрудников | View employees’ personal data |
| 28 | Ma’lumot yo‘q. | Нет данных. | No data. |
| 29 | Hisobotda ijrochilar kesimini ko‘rish (shaxsiy natijalar) | Просмотр отчёта в разрезе исполнителей (личные результаты) | View the report broken down by assignee (personal results) |
| 30 | Shaxsiy natijalar: faqat ruxsati bor foydalanuvchilarga ko‘rinadi. | Личные результаты: видны только пользователям с соответствующим правом. | Personal results: visible only to users with the corresponding permission. |
| 31 | Faqat siz ko‘rishga ruxsat etilgan, faol hujjatlar hisoblanadi. | Учитываются только активные документы, которые вам разрешено просматривать. | Only active documents you are allowed to view are counted. |
| 32 | Manzil: tasdiqlangan ma’lumot kiritiladi | Адрес: будут указаны подтверждённые данные | Address: verified information will be added |
| 33 | Telefon: tasdiqlangan ma’lumot kiritiladi | Телефон: будут указаны подтверждённые данные | Phone: verified information will be added |
| 34 | E-pochta: tasdiqlangan ma’lumot kiritiladi | Эл. почта: будут указаны подтверждённые данные | E-mail: verified information will be added |
| 35 | Ruxsat yo‘q | Доступ запрещён | Access denied |
| 36 | Ruxsat etilgan: PDF, DOCX, XLSX, PPTX, ODT, ODS, PNG, JPG, TXT. Makroli va faol tarkibli fayllar qabul qilinmaydi. Yuklangan fayl antivirus bilan tekshiriladi; tekshiruv bajarilmasa, fayl qabul qilinmaydi. | Разрешены: PDF, DOCX, XLSX, PPTX, ODT, ODS, PNG, JPG, TXT. Файлы с макросами и активным содержимым не принимаются. Загружаемый файл проверяется антивирусом; если проверку выполнить не удалось, файл не принимается. | Allowed: PDF, DOCX, XLSX, PPTX, ODT, ODS, PNG, JPG, TXT. Files with macros or active content are not accepted. Uploaded files are scanned by an antivirus; if the scan cannot be completed, the file is not accepted. |
| 37 | Fayllar xavfsiz saqlanadi va faqat huquqingiz bo‘lsa yuklab olinadi. | Файлы хранятся в защищённом хранилище и скачиваются только при наличии прав. | Files are stored securely and can be downloaded only if you have permission. |
| 38 | Ish telefoni | Рабочий телефон | Work phone |
| 39 | Shaxsiy ma’lumotlar | Личные данные | Personal data |
| 40 | Bu ma’lumotlarni ko‘rish jurnalga yoziladi. | Просмотр этих данных фиксируется в журнале. | Viewing this data is recorded in the log. |
| 41 | Tug‘ilgan sana | Дата рождения | Date of birth |
| 42 | Shaxsiy telefon | Личный телефон | Personal phone |
| 43 | Haqiqiy shaxsiy ma’lumotlarni kiritishdan oldin huquqiy tekshiruv yakunlangan bo‘lishi kerak. | Перед внесением реальных личных данных должна быть завершена юридическая проверка. | A legal review must be completed before real personal data is entered. |
| 44 | Bekor qilish va ma’lumotlarni o‘chirish | Отменить и удалить данные | Cancel and delete the data |
| 45 | Yuklangan fayl va qatorlar saqlanmagan. Bu hisobotda shaxsiy ma’lumotlar yo‘q — faqat qator raqamlari. | Загруженный файл и строки не сохранены. В этом отчёте нет персональных данных — только номера строк. | The uploaded file and rows are not stored. This report contains no personal data — only row numbers. |
| 46 | Ism, bo‘lim, lavozim va holat. Aloqa ma’lumotlari xodim kartasida, ruxsat bo‘lsa ko‘rinadi. | Имя, подразделение, должность и статус. Контактные данные — на карточке сотрудника, если у вас есть право. | Name, department, position and status. Contact details are on the employee card, if you have permission. |
| 47 | Obyekt mavjud emas yoki ruxsat yo‘q | Объект не существует или нет доступа | The item does not exist or you have no access |
| 48 | Tanlangan davr va filtrlar bo‘yicha ma’lumot yo‘q. | Нет данных за выбранный период и по выбранным фильтрам. | No data for the selected period and filters. |
| 49 | Ma’lumotlar bazasidagi joriy ma’lumotlar. Siz faqat o‘z doirangizdagi ma’lumotlarni ko‘rasiz. | Актуальные данные из базы данных. Вы видите только данные в пределах своей области. | Current data from the database. You only see data within your own scope. |
| 50 | Xodimlar, bo‘limlar, topshiriqlar, hujjatlar va yangiliklar nomlari bo‘yicha qidiradi. Faqat sizga ochiq ma’lumotlar ko‘rsatiladi. Bu to‘liq matnli qidiruv emas: faqat nom va tavsif maydonlaridagi so‘zlar. | Ищет по названиям сотрудников, подразделений, заданий, документов и новостей. Показываются только доступные вам данные. Это не полнотекстовый поиск: учитываются только слова в полях названия и описания. | Searches the names of employees, departments, tasks, documents and news. Only data you may access is shown. This is not full-text search: only words in name and description fields are matched. |
| 51 | Sizga berilgan, siz bergan va ko‘rishga ruxsat etilgan topshiriqlar. | Задания, назначенные вам, поручённые вами и те, которые вам разрешено просматривать. | Tasks assigned to you, assigned by you, and those you are allowed to view. |

## D. Statuses, roles and organisational terms (official terminology) — 112

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
| 32 | Xodimlar importi: ko‘rib chiqish | Импорт сотрудников: предварительный просмотр | Employee import: preview |
| 33 | Xodimlar importi: fayl rad etildi | Импорт сотрудников: файл отклонён | Employee import: file rejected |
| 34 | Xodimlar importi bajarildi | Импорт сотрудников выполнен | Employee import completed |
| 35 | Xodimlar importi bekor qilindi | Импорт сотрудников отменён | Employee import cancelled |
| 36 | Xodimlar importi xatolik bilan to‘xtadi | Импорт сотрудников остановлен из-за ошибки | Employee import stopped by an error |
| 37 | Kontent | Контент | Content |
| 38 | Tekshiruvda | На проверке | In review |
| 39 | Yangilikni ma’qullaysizmi? Shundan keyin vakolatli xodim uni nashr eta oladi. | Одобрить новость? После этого уполномоченный сотрудник сможет её опубликовать. | Approve this news item? An authorised employee can then publish it. |
| 40 | Mirzacho‘l tumani Xalq ta’limi bo‘limi | Отдел народного образования Мирзачульского района | Mirzachul District Public Education Department |
| 41 | Xalq ta’limi bo‘limi | Отдел народного образования | Public Education Department |
| 42 | Faqat «Faqat bo‘lim» darajasi uchun. | Только для уровня «Только подразделение». | Only for the “Department only” level. |
| 43 | Bo‘lim darajasi uchun bo‘lim tanlang. | Для уровня «Подразделение» выберите подразделение. | Choose a department for the “Department” level. |
| 44 | faol | активно | active |
| 45 | Faol | Активен | Active |
| 46 | Arxivda | В архиве | Archived |
| 47 | Barcha xodimlar | Все сотрудники | All employees |
| 48 | Faqat bo‘lim | Только подразделение | Department only |
| 49 | bo‘lim | подразделение | department |
| 50 | Bu hisob boshqa xodimga biriktirilgan. | Эта учётная запись уже привязана к другому сотруднику. | This account is already linked to another employee. |
| 51 | Bu nomdagi bo‘lim shu joyda allaqachon bor. | Подразделение с таким названием здесь уже есть. | A department with this name already exists here. |
| 52 | Faol xodimlari yoki faol quyi bo‘limlari bor bo‘limni o‘chirib bo‘lmaydi. | Нельзя отключить подразделение, в котором есть активные сотрудники или активные дочерние подразделения. | A department with active employees or active sub-departments cannot be deactivated. |
| 53 | Bunday faol bo‘lim topilmadi: “%(value)s”. Import yangi bo‘lim yaratmaydi. | Активное подразделение не найдено: «%(value)s». Импорт не создаёт новые подразделения. | No active department found: “%(value)s”. The import does not create new departments. |
| 54 | Bo‘lim nomi bir necha joyda uchraydi: “%(value)s”. To‘liq yo‘lni yozing (masalan, “Yuqori bo‘lim / Quyi bo‘lim”). | Название подразделения встречается в нескольких местах: «%(value)s». Укажите полный путь (например, «Верхнее / Нижнее»). | The department name appears in several places: “%(value)s”. Write the full path (for example “Parent / Child”). |
| 55 | Bunday lavozim topilmadi: “%(value)s”. Import yangi lavozim yaratmaydi. | Должность не найдена: «%(value)s». Импорт не создаёт новые должности. | Position not found: “%(value)s”. The import does not create new positions. |
| 56 | Bunday F.I.Sh. bilan xodim allaqachon mavjud (mumkin bo‘lgan dublikat). Mavjud xodim o‘zgartirilmaydi. | Сотрудник с таким ФИО уже есть (возможный дубликат). Существующий сотрудник не изменяется. | An employee with this full name already exists (possible duplicate). The existing employee is not changed. |
| 57 | Bu ish e-pochtasi boshqa xodimda bor (mumkin bo‘lgan dublikat). | Эта рабочая почта уже есть у другого сотрудника (возможный дубликат). | This work e-mail already belongs to another employee (possible duplicate). |
| 58 | bo‘limlar | подразделения | departments |
| 59 | lavozim | должность | position |
| 60 | lavozimlar | должности | positions |
| 61 | Yangi | Новое | New |
| 62 | xodim | сотрудник | employee |
| 63 | xodimlar | сотрудники | employees |
| 64 | Xodimlar ro‘yxatini ko‘rish (ism, lavozim, bo‘lim, holat) | Просмотр списка сотрудников (имя, должность, подразделение, статус) | View the employee list (name, position, department, status) |
| 65 | Bajarildi | Выполнено | Done |
| 66 | Bekor qilindi | Отменено | Cancelled |
| 67 | Sizning hisobingizga xodim kartasi biriktirilmagan. | К вашей учётной записи не привязана карточка сотрудника. | No employee card is linked to your account. |
| 68 | Xodim qo‘shildi. | Сотрудник добавлен. | The employee was added. |
| 69 | Xodim arxivdan qaytarildi. | Сотрудник восстановлен из архива. | The employee was restored from the archive. |
| 70 | Xodim arxivlandi. | Сотрудник архивирован. | The employee was archived. |
| 71 | Lavozim | Должность | Position |
| 72 | Xodimlar | Сотрудники | Employees |
| 73 | Bo‘limlar | Разделы | Sections |
| 74 | Faol xodimlar | Активные сотрудники | Active employees |
| 75 | Xodimlar (arxivdan tashqari) | Сотрудники (без архива) | Employees (excluding archived) |
| 76 | Bo‘lim filtri: %(v)s | Фильтр по подразделению: %(v)s | Department filter: %(v)s |
| 77 | Hisobotlar sahifasini ko‘rish (doira rol bo‘yicha) | Просмотр страницы отчётов (область определяется ролью) | View the reports page (scope depends on the role) |
| 78 | Barcha bo‘limlar | Все подразделения | All departments |
| 79 | Bo‘lim: %(name)s | Подразделение: %(name)s | Department: %(name)s |
| 80 | Xodimlar: bo‘limlar bo‘yicha | Сотрудники: по подразделениям | Employees: by department |
| 81 | — (lavozim ko‘rsatilmagan) | — (должность не указана) | — (no position set) |
| 82 | Xodimlar: lavozimlar bo‘yicha | Сотрудники: по должностям | Employees: by position |
| 83 | — (bo‘limsiz) | — (без подразделения) | — (no department) |
| 84 | Bajarilish: bo‘limlar bo‘yicha | Выполнение: по подразделениям | Completion: by department |
| 85 | Bir nechta ijrochili topshiriq har bir ijrochining bo‘limida hisoblanadi. | Задание с несколькими исполнителями учитывается в подразделении каждого исполнителя. | A task with several assignees is counted in each assignee’s department. |
| 86 | Jarayonda | В работе | In progress |
| 87 | Bo‘lim (yoki butun tashkilot) topshiriqlarini ko‘rish | Просмотр заданий подразделения (или всей организации) | View tasks of a department (or the whole organization) |
| 88 | Sizning rolingiz uchun bu majburiy. Sozlashni tugatmaguncha tizimga kira olmaysiz. | Для вашей роли это обязательно. Пока вы не завершите настройку, войти в систему нельзя. | This is mandatory for your role. You cannot use the system until the setup is finished. |
| 89 | Tuzilma | Структура | Structure |
| 90 | Ishlab chiqish bosqichi: qolgan bo‘limlar keyingi bosqichlarda qo‘shiladi | Этап разработки: остальные разделы будут добавлены позже | Development stage: the remaining sections will be added later |
| 91 | Rollar | Роли | Roles |
| 92 | rol biriktirilmagan | роль не назначена | no role assigned |
| 93 | Xodim qo‘shish | Добавить сотрудника | Add an employee |
| 94 | %(ok)s ta yangi xodim qo‘shiladi. Xatoli qatorlar (%(skipped)s) o‘tkazib yuboriladi. Mavjud xodimlar o‘zgartirilmaydi. | Будет добавлено новых сотрудников: %(ok)s. Строки с ошибками (%(skipped)s) будут пропущены. Существующие сотрудники не изменяются. | New employees to be added: %(ok)s. Rows with errors (%(skipped)s) will be skipped. Existing employees are not changed. |
| 95 | Xodimlar ro‘yxati | Список сотрудников | Employee list |
| 96 | Xodimlarni import qilish | Импорт сотрудников | Import employees |
| 97 | Xodimlarni Excel’dan import qilish | Импорт сотрудников из Excel | Import employees from Excel |
| 98 | Import faqat yangi xodimlar qo‘shadi. Mavjud xodimlar o‘zgartirilmaydi va birlashtirilmaydi. Avval ko‘rib chiqasiz, so‘ng tasdiqlaysiz. | Импорт только добавляет новых сотрудников. Существующие не изменяются и не объединяются. Сначала вы просматриваете результат, затем подтверждаете. | The import only adds new employees. Existing ones are neither changed nor merged. You review first, then confirm. |
| 99 | department — bo‘lim nomi; nom takrorlansa to‘liq yo‘l: “Yuqori / Quyi”. Bo‘lim va lavozim oldindan yaratilgan bo‘lishi kerak. | department — название подразделения; если названия повторяются — полный путь: «Верхнее / Нижнее». Подразделения и должности должны быть созданы заранее. | department — the department name; if names repeat, the full path: “Parent / Child”. Departments and positions must be created beforehand. |
| 100 | F.I.Sh. yoki ish e-pochtasi mavjud xodim bilan mos kelsa — qator “mumkin bo‘lgan dublikat” deb belgilanadi va sukut bo‘yicha o‘tkazib yuboriladi. | Если ФИО или рабочая почта совпадают с существующим сотрудником, строка помечается как «возможный дубликат» и по умолчанию пропускается. | If the full name or work e-mail matches an existing employee, the row is flagged as a “possible duplicate” and skipped by default. |
| 101 | Qidirish: ism, lavozim | Поиск: имя, должность | Search: name, position |
| 102 | Xatolik yuz berdi. Keyinroq qayta urinib ko‘ring; muammo davom etsa, administratorga murojaat qiling. | Произошла ошибка. Повторите попытку позже; если проблема сохраняется, обратитесь к администратору. | An error occurred. Try again later; if the problem persists, contact an administrator. |
| 103 | Tashkiliy tuzilma | Организационная структура | Organization structure |
| 104 | Bo‘limlar daraxti va lavozimlar. Bo‘limlar o‘chirilmaydi, faqat faol emas qilinadi. | Дерево подразделений и должности. Подразделения не удаляются, а только отключаются. | Department tree and positions. Departments are never deleted, only deactivated. |
| 105 | Bo‘lim qo‘shish | Добавить подразделение | Add a department |
| 106 | Lavozim qo‘shish | Добавить должность | Add a position |
| 107 | Bo‘limlar hali kiritilmagan. | Подразделения ещё не внесены. | No departments have been entered yet. |
| 108 | Lavozimlar | Должности | Positions |
| 109 | Lavozimlar hali kiritilmagan. | Должности ещё не внесены. | No positions have been entered yet. |
| 110 | Rol biriktirilmagan: foydalanuvchi hech narsaga kira olmaydi. | Роль не назначена: пользователь ни к чему не имеет доступа. | No role assigned: the user cannot access anything. |
| 111 | Rol biriktirish | Назначить роль | Assign a role |
| 112 | Barcha rollar | Все роли | All roles |

## E. Task and document workflow wording — 71

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
| 12 | Hujjat fayllari yaxlitligini tekshirish | Проверка целостности файлов документов | Document file integrity check |
| 13 | Hujjatlarni antivirus bilan qayta tekshirish | Повторная проверка документов антивирусом | Re-scanning documents with the antivirus |
| 14 | Hujjatlar | Документы | Documents |
| 15 | Hisobotlar | Отчёты | Reports |
| 16 | hujjat turkumi | категория документов | document category |
| 17 | hujjat turkumlari | категории документов | document categories |
| 18 | hujjat raqami | номер документа | document number |
| 19 | turkum | категория | category |
| 20 | hujjat sanasi | дата документа | document date |
| 21 | hujjat | документ | document |
| 22 | hujjatlar | документы | documents |
| 23 | Hujjat yuklandi. | Документ загружен. | The document was uploaded. |
| 24 | Yangi versiya (v%(n)d) yuklandi. | Загружена новая версия (v%(n)d). | A new version (v%(n)d) was uploaded. |
| 25 | Hujjat arxivdan qaytarildi. | Документ восстановлен из архива. | The document was restored from the archive. |
| 26 | Hujjat arxivlandi. | Документ архивирован. | The document was archived. |
| 27 | Bildirishnomalar | Уведомления | Notifications |
| 28 | Topshiriq berildi | Вам назначено задание | A task was assigned to you |
| 29 | Topshiriq tekshiruvga topshirildi | Задание сдано на проверку | A task was submitted for review |
| 30 | Topshiriq qabul qilindi | Задание принято | A task was accepted |
| 31 | Topshiriq qaytarildi | Задание возвращено на доработку | A task was returned for rework |
| 32 | Topshiriq bekor qilindi | Задание отменено | A task was cancelled |
| 33 | Topshiriqlar | Задания | Tasks |
| 34 | Davrda yaratilgan topshiriqlar | Заданий создано за период | Tasks created in the period |
| 35 | Davrda yakunlangan topshiriqlar | Заданий завершено за период | Tasks completed in the period |
| 36 | Davrda yuklangan hujjatlar | Документов загружено за период | Documents uploaded in the period |
| 37 | Topshiriq holati: %(v)s | Статус задания: %(v)s | Task status: %(v)s |
| 38 | Hujjat turkumi: %(v)s | Категория документов: %(v)s | Document category: %(v)s |
| 39 | Hisobot | Отчёт | Report |
| 40 | Topshiriqlar dinamikasi | Динамика заданий | Task trend |
| 41 | Hisobotlarni Excel/PDF ga yuklab olish | Скачивание отчётов в Excel/PDF | Download reports as Excel/PDF |
| 42 | Topshiriq holati | Статус задания | Task status |
| 43 | Hujjat turkumi | Категория документов | Document category |
| 44 | Barcha turkumlar | Все категории | All categories |
| 45 | Topshiriqlar: holatlar bo‘yicha | Задания: по статусам | Tasks: by status |
| 46 | Bajarilish: ijrochilar bo‘yicha | Выполнение: по исполнителям | Completion: by assignee |
| 47 | Ijrochi | Исполнитель | Assignee |
| 48 | Hujjatlar: turkumlar bo‘yicha | Документы: по категориям | Documents: by category |
| 49 | Turkum | Категория | Category |
| 50 | Hujjatlar: davrlar bo‘yicha | Документы: по периодам | Documents: by period |
| 51 | Faqat hujjat yuklangan davrlar ko‘rsatiladi. | Показаны только периоды, в которые загружались документы. | Only periods in which documents were uploaded are shown. |
| 52 | Ijrochilar | Исполнители | Assignees |
| 53 | Bir nechta ijrochini Ctrl (⌘) bosib tanlang. | Для выбора нескольких исполнителей удерживайте Ctrl (⌘). | Hold Ctrl (⌘) to select several assignees. |
| 54 | Kamida bitta ijrochi tanlang. | Выберите хотя бы одного исполнителя. | Select at least one assignee. |
| 55 | topshiriq | задание | task |
| 56 | topshiriqlar | задания | tasks |
| 57 | Faylni topshiriqdan olib tashlash (faylning o‘zi o‘chirilmaydi) | Открепление файла от задания (сам файл не удаляется) | Remove a file from a task (the file itself is not deleted) |
| 58 | Topshiriq yaratildi. | Задание создано. | The task was created. |
| 59 | Bitta topshiriqqa %(n)d tadan ortiq fayl biriktirib bo‘lmaydi. | К одному заданию нельзя прикрепить более %(n)d файлов. | No more than %(n)d files can be attached to one task. |
| 60 | Fayl topshiriqdan olib tashlandi. | Файл откреплён от задания. | The file was removed from the task. |
| 61 | Versiyalar | Версии | Versions |
| 62 | Yangi versiya yuklash | Загрузить новую версию | Upload a new version |
| 63 | Hujjat yuklash | Загрузка документа | Upload a document |
| 64 | Hujjatlar topilmadi | Документы не найдены | No documents found |
| 65 | Hujjat sahifasi | Страница документа | Document page |
| 66 | Hujjat arxivda. | Документ находится в архиве. | The document is archived. |
| 67 | Topshiriqlar va yangiliklarni tekshirish bo‘yicha xabarlar. | Сообщения о заданиях и проверке новостей. | Messages about tasks and news review. |
| 68 | Bildirishnomalar yo‘q | Уведомлений нет | No notifications |
| 69 | Hisobotni tayyorlab bo‘lmadi | Не удалось подготовить отчёт | The report could not be prepared |
| 70 | Yangi topshiriq | Новое задание | New task |
| 71 | Topshiriqlar yo‘q | Заданий нет | No tasks |

## F. Остальные строки — 448

Интерфейсные подписи общего назначения (кнопки, заголовки, подсказки). Проверяются выборочно при общей вычитке; полный список — в файлах `.po`.

