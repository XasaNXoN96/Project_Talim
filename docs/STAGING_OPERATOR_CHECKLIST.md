# Чек-лист оператора: настоящий staging (День 17)

**Статус документа.** Инструкция для человека, который будет разворачивать staging. **Staging не существует и не запускался**; ни один шаг ниже не выполнялся на настоящем сервере. Команды взяты из файлов репозитория (`backend/deploy/…`, `docs/SCHEDULER.md`, `docs/BACKUP_AND_RESTORE.md`, `docs/CLAMAV.md`); где команда ещё не проверялась, это помечено **[не проверено]**. Значения в `<…>` подставляет оператор; секретов в репозитории нет и быть не должно. Только вымышленные или обезличенные данные.

Связанные документы: [STAGING_RUNBOOK.md](STAGING_RUNBOOK.md) (карта шагов и откат), [DEPLOYMENT_READINESS.md](DEPLOYMENT_READINESS.md) (матрица, §4 — детали), [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) (черновик).

---

## 1. Минимальные требования к серверу/ВМ
Отдельная машина, **не production**; Ubuntu 24.04 LTS (на ней сверялись версии); ≥ 2 vCPU, 4 ГБ ОЗУ (ClamAV держит базу 1–2 ГБ), 40 ГБ SSD + место под копии (≥ 3× объёма БД и документов); статический публичный адрес; Python 3.12, PostgreSQL 16, nginx, ClamAV (`clamd`, `freshclam`), `curl`, `openssl`, `systemd`; автоматические обновления безопасности и NTP включены средствами ОС. Для проверки восстановления — **второй** каталог/машина (лучше отдельный сервер).

## 2. Что должен предоставить владелец инфраструктуры
| Ресурс | Требование |
|---|---|
| Домен/имя хоста | DNS-запись на адрес staging (создаёт владелец; DNS оператор не меняет) |
| TLS-сертификат | доверенный центр (например, ACME) для этого имени, с полной цепочкой; продление автоматическое или с напоминанием; приватный ключ — только на сервере, права `0600` |
| SMTP | хост, порт (по умолчанию 587), STARTTLS, учётная запись; тестовый ящик, который оператор может прочитать; адрес отправителя |
| ClamAV | доступ ВМ к серверам сигнатур (`freshclam`) — без официальной базы защита формальна |
| Файрвол | снаружи только 80 и 443 (+ SSH с ограничением по адресам); 8000 и 5432 только локально |
| Резервное место | второй каталог/сервер для проверки восстановления |

## 3. Доступы и письменные разрешения (до начала)
Письменно от владельца: (1) разрешение на развёртывание именно на этой машине; (2) открытие 80/443; (3) выпуск сертификата и запись DNS; (4) правило `sudoers` только для `systemctl restart talim-gunicorn` пользователю `talim` **[не проверено]**; (5) подтверждение, что данные только вымышленные/обезличенные; (6) назначен ответственный за сервер и канал связи при инциденте. Оператору — чтение репозитория; секреты оператор создаёт сам на сервере.

## 4. Переменные окружения и секреты (только названия)
**`/etc/talim/talim.env`** (`root:talim`, `0640`; шаблон — `backend/deploy/staging/talim.env.staging.example`):
`DJANGO_SETTINGS_MODULE`, `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_ADMIN_URL`, `DJANGO_TRUSTED_PROXIES`, `DJANGO_PRIVATE_MEDIA_ROOT`, `DJANGO_HSTS_SECONDS`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `OTP_ENCRYPTION_KEYS`, `DOCUMENT_SCAN_MODE`, `EMAIL_HOST`, `DEFAULT_FROM_EMAIL`.
Необязательные (есть в `config/settings`): `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `CLAMAV_HOST`, `CLAMAV_PORT`, `CLAMAV_SOCKET`, `CLAMAV_TIMEOUT`, `DOCUMENT_MAX_BYTES`, `NOTIFICATION_EMAILS_ENABLED`, `DJANGO_LOG_LEVEL`. **Не задавать** `DJANGO_CSP_REPORT_ONLY` (CSP должен блокировать) и `DJANGO_SECURE_SSL_REDIRECT=0`.
**`/etc/talim/backup.env`** (`root:talim`, `0640`, имена и пути): `BACKUP_DIR`, `BACKUP_PASSPHRASE_FILE`, `PGPASSFILE`; при необходимости `PGHOST PGPORT PGUSER PGDATABASE PRIVATE_MEDIA_ROOT BACKUP_KEEP`.
**Отдельные секреты-файлы (`0600`, вне Git):** пароль владельца БД, пароль роли приложения, `backup.pass` (≥ 20 символов, вне `BACKUP_DIR`), `backup.pgpass`, приватный ключ TLS. **Копии секретов** (`OTP_ENCRYPTION_KEYS`, `backup.pass`, `talim.env`, ключ TLS) хранить **отдельно от резервных копий данных** (см. DEPLOYMENT_READINESS §6): без `OTP_ENCRYPTION_KEYS` пользователи не войдут после восстановления; без пароля копий копии нечитаемы. Значения не копировать в чаты, тикеты, журналы, Git.
⚠ **[не проверено]** Роль `PGUSER` в `backup.env` по умолчанию совпадает с рабочей ролью приложения (`DB_USER`), у которой нет `CREATEDB`; для `run_restore_check` нужна отдельная роль с `CREATEDB` и правом чтения всех таблиц — задать её в `backup.env` (`PGUSER`) и `backup.pgpass`. Эта комбинация на настоящем сервере не проверялась.

## 5. Последовательность развёртывания (все команды из репозитория)
Рабочий каталог — клон репозитория; `<тег>` — каталог релиза.

1. **Пользователь и каталоги** (DEPLOYMENT_READINESS §4.1):
   ```bash
   sudo useradd --system --home /srv/talim --shell /usr/sbin/nologin talim
   sudo install -d -o root -g talim -m 0750 /etc/talim
   sudo install -d -o talim -g talim -m 0750 /var/lib/talim /var/lib/talim/private_media
   sudo install -d -o talim -g talim -m 0700 /var/backups/talim
   sudo cp backend/deploy/tmpfiles.d/talim.conf /etc/tmpfiles.d/ && sudo systemd-tmpfiles --create
   sudo cp backend/deploy/logrotate/talim /etc/logrotate.d/talim
   ```
2. **PostgreSQL**: роли и права (§4.2), `listen_addresses` только локально, `scram-sha-256`:
   ```bash
   sudo -u postgres psql -v owner=talim_owner -v app=talim_app -v db=talim -v owner_password="$(cat <файл>)" -v app_password="$(cat <файл>)" -f backend/deploy/postgres/create_roles.sql
   ```
3. **Окружение**: создать `/etc/talim/talim.env` по шаблону (`root:talim`, `0640`) и `backup.env` (§4). Файл не должен принадлежать пользователю `talim`.
4. **Код и зависимости**: релиз = полный checkout репозитория (нужны `backend/` и `assets/`):
   ```bash
   sudo -u talim git clone <репозиторий> /srv/talim/releases/<тег>
   cd /srv/talim/releases/<тег>/backend && python3.12 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt
   sudo ln -sfn /srv/talim/releases/<тег>/backend /srv/talim/backend      # первый релиз; дальше — release.sh
   ```
5. **Миграции и права** — владелец БД только для миграций (§4.4, §4.2):
   ```bash
   DB_USER=talim_owner DB_PASSWORD=<…> DJANGO_SETTINGS_MODULE=config.settings.production <остальные переменные из talim.env> .venv/bin/python manage.py migrate
   PGPASSWORD=<…> psql -h 127.0.0.1 -U talim_owner -d talim -v app=talim_app -v db=talim -f deploy/postgres/apply_grants.sql
   .venv/bin/python manage.py seed_roles --dry-run    # прочитать план; нестандартные права (=) остаются, удаляет только --prune
   .venv/bin/python manage.py seed_roles && .venv/bin/python manage.py collectstatic --noinput
   ```
6. **Предпроверка** (от `talim`; **остановиться, если есть FAIL**):
   ```bash
   sudo -u talim /srv/talim/backend/.venv/bin/python /srv/talim/backend/deploy/staging/preflight.py --env-file /etc/talim/talim.env --backend /srv/talim/backend
   ```
   Ожидается `PREFLIGHT OK`; SKIP (SMTP, TLS, файрвол) — ручные пункты ниже.
7. **Gunicorn**: `sudo cp backend/deploy/systemd/talim-gunicorn.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now talim-gunicorn`.
8. **ClamAV**: по [CLAMAV.md](CLAMAV.md) (`freshclam`, `StreamMaxLength 25M`), `DOCUMENT_SCAN_MODE=clamav`; `sudo -u talim … manage.py check_scanner` → OK.
9. **Nginx и TLS**: из `backend/deploy/nginx/talim-production.conf.template` подставить плейсхолдеры (`{{SERVER_NAME}}`, `{{TLS_CERT}}`, `{{TLS_KEY}}`, `{{BACKEND_PORT}}`=8000, `{{HTTP_LISTEN}}`, `{{HTTPS_LISTEN}}`, `{{HTTPS_PORT_SUFFIX}}` (пусто для 443), `{{ERROR_DIR}}`, `{{STATIC_DIR}}`, `{{ACCESS_LOG}}`) — образец подстановки в `backend/deploy/nginx/verify/run_tls.sh`; `sudo nginx -t && sudo systemctl reload nginx`. Версия nginx < 1.25.1: `listen … ssl http2;` (как в шаблоне); ≥ 1.25.1 — см. комментарий в шаблоне.
10. **Таймеры и службы** (SCHEDULER.md §4):
    ```bash
    sudo cp backend/deploy/systemd/talim-job*.service backend/deploy/systemd/talim-*.timer /etc/systemd/system/
    sudo cp -r backend/deploy/systemd/talim-job@run_backup.service.d backend/deploy/systemd/talim-job@run_restore_check.service.d /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now talim-send_task_reminders.timer talim-purge_employee_imports.timer talim-purge_throttles.timer talim-clear_expired_sessions.timer talim-check_scanner.timer talim-verify_document_files.timer talim-backup_create.timer talim-backup_restore_check.timer
    systemctl list-timers 'talim-*'
    ```
    (Каталоги drop-in и их установку сверить с `SCHEDULER.md` §8 — в проверке файлов `verify_deploy_files.sh` они учтены, на сервере установка **[не проверено]**.)
11. **Последующие релизы**: `backend/deploy/staging/release.sh deploy <тег>` с переменными из STAGING_RUNBOOK §1 (`RELEASES_DIR`, `CURRENT_LINK`, `HEALTH_URL`, `HEALTH_HOST`, `RESTART_CMD`, `PRE_BACKUP_CMD`, `MIGRATE_CMD_PREFIX`, `POST_MIGRATE_SQL_CMD`). Нужен `curl`. Вывод `RELEASE_OK`. `release.sh` **не** запускает `seed_roles`: после релиза, добавившего роли или права (например, роли редакции), выполнить `sudo -u talim … manage.py seed_roles` (идемпотентно; сначала `--dry-run`; ничего не удаляет без `--prune`; нестандартные права выводятся в stderr — прочитать; назначения и личные разрешения не меняет) — **[не проверено на сервере]**.
12. **HSTS не включать** (`DJANGO_HSTS_SECONDS=0`), пока §6 не пройден целиком и вручную не проверен настоящий HTTPS (DEPLOYMENT_READINESS §4.12).

## 6. Проверки после развёртывания
| № | Проверка | Как | Ожидаемо |
|---|---|---|---|
| 1 | Приёмка снаружи | с **другой** машины: `python3 backend/deploy/staging/smoke_remote.py https://<хост> --admin-path <DJANGO_ADMIN_URL>` (**без** `--insecure-self-signed`) | `SMOKE OK: 21/21`; недоверенный сертификат = FAIL |
| 2 | Здоровье | `curl -fsS https://<хост>/healthz/` | `{"status": "ok", "database": "ok"}` |
| 3 | HTTP→HTTPS | `curl -sI http://<хост>/` | `301` на `https://` |
| 4 | TLS | внешний сканер TLS/браузер | цепочка полная, TLS 1.2/1.3, имя совпадает **[не проверено]** |
| 5 | `check --deploy` | `manage.py check --deploy` (на сервере) | только `security.W004` |
| 6 | Миграции | `manage.py makemigrations --check --dry-run` | без изменений |
| 7 | Права БД | входит в `preflight.py` | роль приложения не суперпользователь, не меняет `audit_auditlog` |
| 8 | Закрытые маршруты | входит в `smoke_remote.py` | `/media`, `/private_media`, `/admin/` → 404; `/portal/…` → редирект на вход |
| 9 | Вход, 2FA | браузер: вход тестовым администратором, `/accounts/2fa/setup/`, повторный вход с кодом | вход проходит; коды восстановления показаны один раз |
| 10 | Роли и страницы | вход под ролями (создать вымышленных пользователей на `/portal/users/`) | каждая роль видит только свои разделы; чужие объекты → 403/404 |
| 11 | Новости, задачи, отчёты | создать/опубликовать вымышленную новость, задачу, выгрузку | работает на всех трёх языках (UZ/RU/EN) |
| 12 | Импорт Excel | `/portal/employees/import/` — шаблон со страницы, вымышленные строки, подтверждение | предпросмотр → подтверждение; загрузка слишком большого/неверного файла отклонена |
| 13 | Поиск | `/portal/search/` | находит вымышленные записи, чужие закрытые не показывает |
| 14 | Сессии | `/accounts/security/sessions/`: вход с двух браузеров, «завершить остальные» | вторая сессия закрыта |
| 15 | Журналы | `journalctl -u talim-gunicorn`, nginx access/error log | нет паролей, токенов сброса, query-строк, ключей |

## 7. Письмо восстановления пароля
1. `sudo -u talim` (с окружением из `talim.env`) `.venv/bin/python manage.py sendtestemail <тестовый адрес>` — письмо дошло, отправитель верный, нет в «спаме» (SPF/DKIM — по настройке владельца) **[не проверено]**.
2. В браузере `/accounts/password-reset/` для вымышленного пользователя с адресом тестового ящика → письмо со ссылкой `https://<хост>/accounts/reset/<uid>/<токен>/` → задать новый пароль → вход.
3. Проверить: в access-журнале nginx ссылка записана **без токена**; повторное использование ссылки отклонено; запрос для несуществующего адреса даёт тот же ответ (без перечисления пользователей); троттлинг запросов срабатывает.
Остановить запуск, если письмо не доходит или токен виден в любом журнале.

## 8. Документы: загрузка, сканирование, скачивание
1. `manage.py check_scanner` → OK; `freshclam` обновил базу (проверить дату базы в журнале).
2. `/portal/documents/new/`: загрузить вымышленный PDF → статус «проверен» → скачать (`/portal/documents/<id>/download/`) → побайтно совпадает.
3. Строка EICAR (тестовая, безвредная; создать файл вручную) → загрузка **отклонена/в карантине**.
4. `sudo systemctl stop clamav-daemon` → новая загрузка **отклоняется** (fail-closed), существующие непроверенные документы недоступны; затем `sudo systemctl start clamav-daemon` → `check_scanner` OK. (Проверено только на песочничной сигнатуре EICAR; **с официальной базой не проверялось**.)
5. Чужая роль по прямой ссылке на закрытый документ → 403/404; в журнале аудита записано скачивание.
6. `manage.py verify_document_files` → без расхождений.

## 9. Фоновые задачи, резервная копия, восстановление
```bash
sudo systemctl start talim-job@job_status.service; echo $?        # 0 — все задачи здоровы (SCHEDULER.md §4)
sudo systemctl start talim-job@send_task_reminders.service && journalctl -u talim-job@send_task_reminders.service -n 20
sudo systemctl start talim-job@run_backup.service                  # копия; затем job_status — «создана»
sudo systemctl start talim-job@run_restore_check.service           # восстановление во временную БД и каталог
```
Ожидается (вывод скрипта в журнале службы и/или статус в `job_status`; что именно попадает в журнал, на сервере **[не проверено]**): `BACKUP_OK name=… db_bytes=… files=…` и `RESTORE_OK name=… two_factor_devices=N`. Затем:
* **Восстановление на втором окружении** (по BACKUP_AND_RESTORE.md §5 «Реальное восстановление»): скопировать копию на другую машину, `backend/deploy/backup/restore_check.sh <каталог копии>` с `BACKUP_PASSPHRASE_FILE`, `BACKEND_DIR`, `PYTHON`, `PGHOST/PGUSER`(роль с `CREATEDB`) и **теми же** `OTP_ENCRYPTION_KEYS`; ожидается `RESTORE_OK`, `two_factor_devices=N` без `failed`. **[не проверено на настоящих машинах]**.
* **Что восстановление означает для данных:** после восстановления состояние возвращается на момент копии; всё, что сделано позже (пользователи, документы, аудит), **теряется** — при суточной копии до суток. Оператор обязан до восстановления: зафиксировать выбранную точку (имя копии), сообщить пользователям окно потери, сохранить текущую БД и каталог документов как есть (не удалять), и только затем восстанавливать **в чистую** БД и каталог. Восстановление «поверх» боевой базы автоматикой не выполняется.
* Внешняя копия: **не реализована** (`ship_offsite.example.sh` — пример, не проверялся). Запись «внешняя копия работает» недопустима.

## 10. Откат
**Откат приложения.** `release.sh deploy <тег>` перед изменениями делает копию (`PRE_BACKUP_CMD`; при её неудаче релиз не начинается), мигрирует, переключает ссылку, перезапускает, опрашивает `/healthz/`; при провале возвращает прежнюю ссылку и перезапускает (код 1, `RELEASE_FAILED_ROLLED_BACK`; код 3 — прежний релиз тоже не отвечает: срочно). Вручную: `release.sh rollback`, `release.sh status`. Логика отрепетирована в песочнице (`deploy/staging/verify_release.sh`, 23 проверки, настоящие gunicorn/PostgreSQL, production-настройки); **на сервере под systemd не проверялось**.

**⚠ Откат приложения НЕ откатывает схему БД.** Миграции не отменяются автоматически; после неудачного релиза прежний код работает с новой схемой. План при проблемах с миграцией:
1. Миграция упала (`release.sh` код 1, «migrate FAILED»): ссылка не переключалась, прежний релиз работает. Прочитать ошибку; частично применённая миграция возможна — **не** запускать повторно вслепую; решить (исправить и выпустить новый релиз, либо восстановить БД).
2. Миграция прошла, релиз не стартует: прежний код вернулся, схема новая. Проверить `/healthz/` и основные сценарии прежнего релиза. Если прежний код работает неверно — решение о восстановлении БД из копии шага 1 релиза принимает ответственный; восстановление по п. 9 (с потерей данных после точки копии).
3. Не делать `migrate <app> <предыдущая>` вручную на единственной БД без копии и без решения ответственного.
4. После любого восстановления: `migrate`, `apply_grants.sql`, `verify_document_files`, `check_scanner`, вход тестовым пользователем.

## 11. Критерии допуска к внутреннему пилоту (вымышленные/обезличенные данные)
Все пункты выполнены **и записаны** (дата, кто, результат):
- [ ] §3 разрешения получены; ответственный за сервер назначен.
- [ ] `preflight.py` — `PREFLIGHT OK`.
- [ ] `smoke_remote.py` без `--insecure-self-signed` — 21/21, сертификат доверенный.
- [ ] Вход, 2FA, сброс пароля **с настоящим письмом**, роли, документы с официальной базой ClamAV, импорт, поиск, сессии — §6–8 пройдены.
- [ ] `run_backup` и `run_restore_check` — успешны, восстановление на втором окружении выполнено.
- [ ] `release.sh deploy` с заведомо неудачным релизом вернулся на прежний (на staging), оператор прочитал §10.
- [ ] Журналы без секретов; ротация журналов настроена.
- [ ] Минимальный мониторинг: внешний опрос `/healthz/`, оповещение о провале задач (замена `ExecStart` в `talim-job-failed@.service`), дежурный назван.
- [ ] Пользователям пилота объявлено: данные вымышленные; перевод UZ/RU/EN — рабочий вариант, проверка носителями языка не завершена (`TRANSLATION_REVIEW_LIST.md`).

## 12. Когда запуск необходимо остановить
Немедленно остановить и сообщить ответственному, если: `preflight.py` или `smoke_remote.py` дали FAIL; сертификат не проходит проверку; в любом журнале найден пароль, токен сброса, ключ или персональные данные; пришло письмо, в котором ссылка сброса ведёт не на staging-хост; `clamd` недоступен, а загрузки принимаются (fail-closed нарушен); CSP в режиме отчётов; `DEBUG` включён; `healthz` отвечает `degraded`; задачи резервного копирования провалены больше одного цикла; `release.sh` вернул код 3; обнаружен доступ к чужим документам; на сервер попали реальные персональные данные (изолировать, зафиксировать, сообщить — [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)); нет разрешения владельца на какое-либо из действий §3.

## 13. Что остаётся непроверенным даже после прохождения этого списка
Нагрузка; независимая проверка безопасности; юридические требования к персональным данным; внешняя копия и RTO/RPO; проверка переводов носителями языка; мониторинг сверх минимума. Production этим списком **не** допускается.


### Дополнение (День 21): если замечено неожиданное изменение разрешений
Вывод `seed_roles` (`= … kept`) или запись аудита `admin_changed` по `Group`/`User` с `permissions_added`/`user_permissions_added`, которую никто не ожидал: (1) не запускать `--prune` сразу; (2) найти автора и время на странице аудита портала; (3) решить, нужно ли право; если нет — снять его (личное — в админке, у группы роли — `seed_roles --dry-run --prune`, затем `--prune`); (4) записать в журнал инцидентов ([INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)); (5) если право выдано неизвестным лицом — считать учётную запись суперпользователя скомпрометированной. Доступ к Django admin — только по закрытому адресу, с 2FA, минимум людей. **Не проверено на сервере.**
