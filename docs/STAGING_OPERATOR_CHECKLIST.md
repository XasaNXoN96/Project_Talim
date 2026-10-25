# Чек-лист оператора: настоящий staging (День 17)

**Статус документа.** Инструкция для человека, который будет разворачивать staging. **Staging не существует и не запускался**; ни один шаг ниже не выполнялся на настоящем сервере. Команды взяты из файлов репозитория (`backend/deploy/…`, `docs/SCHEDULER.md`, `docs/BACKUP_AND_RESTORE.md`, `docs/CLAMAV.md`); где команда ещё не проверялась, это помечено **[не проверено]**. Значения в `<…>` подставляет оператор; секретов в репозитории нет и быть не должно. Только вымышленные или обезличенные данные.

Связанные документы: [STAGING_RUNBOOK.md](STAGING_RUNBOOK.md) (карта шагов и откат), [DEPLOYMENT_READINESS.md](DEPLOYMENT_READINESS.md) (матрица, §4 — детали), [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) (черновик).

---

## 0. План оператора в 14 шагов и критерии остановки (День 23)
Каждый шаг — «выполнено» только после записи (дата, кто, результат) вне Git. **Если критерий остановки сработал — дальше не идти, сообщить ответственному.** Все команды и пути ниже существуют в репозитории; что из них проверено только в песочнице, помечено в `STAGING_BLOCKERS.md`.

| № | Шаг | Где подробно | Остановить, если |
|---|---|---|---|
| 1 | Доступность сервера и права: SSH, sudo, письменные разрешения (§3) | §2–3 | нет разрешения владельца или нет доступа |
| 2 | Подготовка отдельной staging-ВМ: пакеты, пользователь `talim`, каталоги | §1, §5.1 | это не отдельная машина / там есть реальные данные |
| 3 | Домен, DNS, доверенный сертификат (получает владелец) | §2, §5.9 | сертификат не проходит проверку (`smoke_remote.py` без `--insecure-self-signed`, браузер) |
| 4 | PostgreSQL и **три** роли: владелец, runtime, резервное копирование (`create_roles.sql`, `create_backup_role.sql`, `apply_grants.sql`) | §5.2, §5.5 | `preflight.py`: роль приложения суперпользователь, создаёт БД/объекты или меняет `audit_auditlog`; роль копий без `CREATEDB` или совпадает с runtime |
| 5 | Gunicorn и Nginx (`talim-gunicorn.service`, шаблон nginx) | §5.7, §5.9 | `nginx -t` не проходит; статика не читается nginx; 80 не перенаправляет на 443 |
| 6 | Секреты и права файлов: `talim.env`, `backup.env`, файлы паролей | §4, §5.3 | `preflight.py` FAIL по правам/заглушкам/`DEBUG`/report-only CSP; **секрет виден в журнале, выводе команды или конфигурации** |
| 7 | Миграции (роль-владелец), `apply_grants.sql`, **`seed_roles --dry-run`**, затем `seed_roles` | §5.5 | миграция завершилась ошибкой (**не повторять вслепую**, §10); `seed_roles` показал неожиданное нестандартное право |
| 8 | SMTP и **реальное** письмо сброса пароля | §7 | письмо не доходит или ссылка ведёт не на staging-хост; токен виден в журнале |
| 9 | ClamAV с официальной базой: `freshclam`, **`check_scanner --eicar`**, загрузка тестовой EICAR отклонена | §8 | `check_scanner --eicar` не прошёл (нет пригодной базы), сканер недоступен, загрузка EICAR принята |
| 10 | systemd: службы и таймеры, `job_status` | §5.10, §9 | `job_status` показывает сбой после ручного запуска |
| 11 | Резервная копия и **восстановление в отдельном окружении** (не на этой же БД) | §9 | копия не создаётся/не проходит проверку; восстановление не удалось проверить |
| 12 | Мониторинг, журналы, оповещения об ошибках (внешний опрос `/healthz/`, замена `ExecStart` в `talim-job-failed@.service`, ротация журналов) | §6.15, §11 | нет дежурного/канала оповещений |
| 13 | Приёмочные сценарии с вымышленными данными | §6–8 | любая проверка §6 не пройдена |
| 14 | Решение о допуске к ограниченному внутреннему пилоту | §11 | не выполнен хотя бы один пункт §11 |
Дополнительно останавливаться при любом пункте §12.

**Порядок эскалации при остановке (День 27).** Контакты вписывает **заказчик/владелец** в `OWNER_HANDOFF.md` §7 вне Git; без них пункт 12 шага не пройден. Порядок: (1) оператор останавливает развёртывание, **ничего не «чинит» в обход защиты** и записывает шаг, команду и текст ошибки без секретов; (2) сообщает ответственному за сервер; (3) если затронуты секреты, ключи, данные или доступ — также ответственному за инциденты (`INCIDENT_RESPONSE.md`, черновик до утверждения); (4) если причина в ресурсе владельца (DNS, сертификат, SMTP, сигнатуры ClamAV, файрвол, хранилище) — владельцу инфраструктуры с указанием блокера из `STAGING_BLOCKERS.md`. Возобновлять — только после записи решения.

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
**`/etc/talim/backup.env`** (`root:talim`, `0640`, имена и пути): `BACKUP_DIR`, `BACKUP_PASSPHRASE_FILE`, `PGPASSFILE`; при необходимости `PGHOST PGPORT PGUSER PGDATABASE PRIVATE_MEDIA_ROOT BACKUP_KEEP`; необязательный `BACKUP_OFFSITE_COMMAND` (абсолютный путь исполняемого файла, который выбрал владелец; получает только имя каталога копии и переменные `OFFSITE_*` — см. `BACKUP_AND_RESTORE.md` §12.5).
**Отдельные секреты-файлы (`0600`, вне Git):** пароль владельца БД, пароль роли приложения, `backup.pass` (≥ 20 символов, вне `BACKUP_DIR`), `backup.pgpass`, приватный ключ TLS. **Копии секретов** (`OTP_ENCRYPTION_KEYS`, `backup.pass`, `talim.env`, ключ TLS) хранить **отдельно от резервных копий данных** (см. DEPLOYMENT_READINESS §6): без `OTP_ENCRYPTION_KEYS` пользователи не войдут после восстановления; без пароля копий копии нечитаемы. Значения не копировать в чаты, тикеты, журналы, Git.
Роль копий (`PGUSER` в `backup.env`) — **отдельная** третья роль (`create_backup_role.sql`): `CREATEDB` + `pg_read_all_data`, не суперпользователь, не владелец, не runtime-роль. Проверка восстановления запускает прикладные шаги **от этой роли** (скрипт сам подставляет её в `DB_USER`), потому что runtime-роль не имеет прав ни на временную БД, ни на DDL. Топология из трёх ролей отрепетирована в песочнице (`deploy/backup/verify_backup_roles.sh`); **на сервере не проверялась** — `preflight.py --backup-env` проверит роль и права.

## 5. Последовательность развёртывания (все команды из репозитория)
0. **Пакеты и рабочий клон кандидата** (от администратора, `sudo`; список по `DEPLOYMENT_READINESS.md` §3; установка на сервере не проверялась):
   ```bash
   sudo apt-get update && sudo apt-get install -y git python3.12 python3.12-venv postgresql-16 nginx clamav-daemon clamav-freshclam curl openssl logrotate chrony
   git clone <репозиторий> ~/talim-src && git -C ~/talim-src checkout <кодовый коммит>      # коммит из OWNER_HANDOFF.md §1 (сейчас RC-5 d8c02ccd785cc0fcde89348f0cc69bb21eaa40a0)
   ~/talim-src/backend/deploy/staging/release_info.sh                                        # сверить с OWNER_HANDOFF.md §1; расхождение — остановиться
   cd ~/talim-src          # шаги 1–2 и 7–10 ниже выполняются из этого клона (пути `backend/deploy/...` — относительно него)
   ```
Рабочий каталог шагов — клон `~/talim-src`; `<тег>` — произвольное имя каталога релиза (например, дата и короткий хеш коммита); `<репозиторий>` — адрес репозитория, который сообщает владелец/заказчик.

1. **Пользователь и каталоги** (DEPLOYMENT_READINESS §4.1):
   ```bash
   sudo useradd --system --home /srv/talim --shell /usr/sbin/nologin talim
   sudo install -d -o root -g talim -m 0750 /etc/talim
   sudo install -d -o talim -g talim -m 0750 /var/lib/talim /var/lib/talim/private_media
   sudo install -d -o talim -g talim -m 0700 /var/backups/talim
   sudo install -d -o talim -g talim -m 0755 /srv/talim /srv/talim/releases     # домашний каталог и место релизов (useradd его не создаёт); 0755: nginx должен проходить по /srv/talim
   sudo cp backend/deploy/tmpfiles.d/talim.conf /etc/tmpfiles.d/ && sudo systemd-tmpfiles --create
   sudo cp backend/deploy/logrotate/talim /etc/logrotate.d/talim
   ```
2. **PostgreSQL**: роли и права (§4.2), `listen_addresses` только локально, `scram-sha-256`. Имя БД — `talim_staging` (как `DB_NAME` в шаблоне `talim.env`; роли — `talim_owner`, `talim_app`, `talim_backup`). Пароли ролей — случайные, из `secrets.token_urlsafe(30)` (символы `A-Za-z0-9_-`: не ломают `.pgpass` и `\set`), лежат в файлах `0600` на **рабочем месте оператора/в хранилище секретов владельца**, а не в репозитории. Пароли передаются в `psql` **через stdin** (в `ps` не видны; `printf` — встроенная команда оболочки, значения не попадают ни в чей argv); способ проверен в песочнице на PostgreSQL 16 (роли созданы, вход по паролю работает), **на сервере не проверялся**:
   ```bash
   { printf "\\set owner_password '%s'\n" "$(cat <файл с паролем владельца>)"; printf "\\set app_password '%s'\n" "$(cat <файл с паролем приложения>)"; cat backend/deploy/postgres/create_roles.sql; } \
     | sudo -u postgres psql -v ON_ERROR_STOP=1 -v owner=talim_owner -v app=talim_app -v db=talim_staging -f -
   # третья роль — только для резервного копирования и проверки восстановления (CREATEDB + чтение данных; не суперпользователь, не владелец):
   { printf "\\set backup_password '%s'\n" "$(cat <файл с паролем роли копий>)"; cat backend/deploy/postgres/create_backup_role.sql; } \
     | sudo -u postgres psql -v ON_ERROR_STOP=1 -v backup_role=talim_backup -f -
   # право подключаться к рабочей БД роль копий получает из apply_grants.sql (шаг 5) при передаче -v backup_role=talim_backup
   ```
3. **Окружение**: создать `/etc/talim/talim.env` по шаблону (`root:talim`, `0640`; владелец — `root`, не `talim`) и `backup.env` (§4). **Значения секретов не печатаются на экран и не передаются аргументами**: генерируются `secrets`/`os.urandom` (криптографически стойкий источник ОС) и записываются прямо в файлы. **Блок выполняется один раз.** Он защищён от повторного запуска: если `talim.env` уже есть, ничего не делается (повтор иначе создал бы новый `DJANGO_SECRET_KEY` и **новый `OTP_ENCRYPTION_KEYS`** — все секреты 2FA в БД стали бы нечитаемыми, а заполненные хост и почта вернулись бы к заглушкам; проверено на временной копии):
   ```bash
   if sudo test -e /etc/talim/talim.env; then
     echo "STOP: /etc/talim/talim.env уже существует - блок не выполняется (изменение - только sudoedit; ротация ключа OTP - DEPLOYMENT_READINESS.md §6.3)"
   else
     sudo install -m 0640 -o root -g talim backend/deploy/staging/talim.env.staging.example /etc/talim/talim.env
     [ -z "$(sudo tail -c1 /etc/talim/talim.env)" ] || echo | sudo tee -a /etc/talim/talim.env >/dev/null   # файл обязан кончаться переводом строки, иначе значение приклеится к последней строке
     # заменить заглушки секретов (остальные значения - хост, почта, путь админки - заполняются вручную: sudoedit /etc/talim/talim.env):
     sudo sed -i '/^DJANGO_SECRET_KEY=/d;/^OTP_ENCRYPTION_KEYS=/d;/^DB_PASSWORD=/d' /etc/talim/talim.env
     printf 'DJANGO_SECRET_KEY=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(70))')" | sudo tee -a /etc/talim/talim.env >/dev/null
     printf 'OTP_ENCRYPTION_KEYS=%s\n' "$(python3 -c 'import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')" | sudo tee -a /etc/talim/talim.env >/dev/null   # формат Fernet.generate_key(): 32 случайных байта, urlsafe-base64, 44 символа; без зависимостей
     printf 'DB_PASSWORD=%s\n' "$(cat <файл с паролем приложения>)" | sudo tee -a /etc/talim/talim.env >/dev/null
   fi
   # файлы паролей копий (читает только talim, режим 0600; значения не выводятся; те же защиты от повтора - не выполнять, если файл уже есть):
   sudo test -e /etc/talim/backup.pass || { sudo install -m 0600 -o talim -g talim /dev/null /etc/talim/backup.pass && python3 -c 'import secrets;print(secrets.token_urlsafe(40))' | sudo tee /etc/talim/backup.pass >/dev/null; }      # пароль шифрования копий (≥ 20 символов)
   sudo test -e /etc/talim/backup.pgpass || { sudo install -m 0600 -o talim -g talim /dev/null /etc/talim/backup.pgpass && printf '127.0.0.1:5432:*:talim_backup:%s\n' "$(cat <файл с паролем роли копий>)" | sudo tee /etc/talim/backup.pgpass >/dev/null; }   # формат libpq (`.pgpass`) проверен в песочнице
   ```
   **Проверка файла после заполнения** (имена и права, значения не выводятся):
   ```bash
   sudo stat -c '%U:%G %a %n' /etc/talim/talim.env /etc/talim/backup.env /etc/talim/backup.pass /etc/talim/backup.pgpass     # talim.env: root:talim 640; backup.env: root:talim 640; backup.pass/backup.pgpass: talim:talim 600
   sudo awk -F= '/^[A-Za-z_]+=/{c[$1]++} END{for(k in c) if(c[k]>1) print "DUPLICATE:",k}' /etc/talim/talim.env       # ожидается пустой вывод; preflight.py дубликатов не замечает (действует последнее значение)
   sudo grep -c 'CHANGE_ME' /etc/talim/talim.env                                                                     # ожидается 0 (preflight.py тоже отвергнет остаточные заглушки)
   ```
   **Правила значений:** без пробелов и спецсимволов; если значение содержит пробелы, `<` или `>` (например, `DEFAULT_FROM_EMAIL`), оно берётся в двойные кавычки: `DEFAULT_FROM_EMAIL="Talim <noreply@хост>"`. Без кавычек команды шагов 5 и 11 (`. /etc/talim/talim.env`) падают с синтаксической ошибкой (проверено); с кавычками `bash`-загрузка и разбор в `preflight.py` дают верное значение, `EnvironmentFile` systemd кавычки поддерживает (**на сервере не проверялось**). Менять файл дальше - только `sudoedit /etc/talim/talim.env` (владелец и режим сохраняются), после правки повторить проверки выше и `preflight.py`.
   **Ключ `OTP_ENCRYPTION_KEYS`.** Формат: один или несколько ключей Fernet через запятую, **новейший первым** (`OTP_ENCRYPTION_KEYS=<новый>,<старый>`; пробелы вокруг запятых игнорируются); приложение читает его из этой переменной (`config/settings/base.py`) и в production не запускается с пустым значением, а корректность формата проверяет `preflight.py`. **Назначение остальных секретов:** `DJANGO_SECRET_KEY` - подпись сессий и токенов (смена - все сессии и ссылки сброса недействительны, данные целы); `DB_PASSWORD` - пароль runtime-роли `talim_app`; `backup.pass` - пароль шифрования копий (потеря = копии нечитаемы); `backup.pgpass` - пароль роли копий для `pg_dump` и проверки восстановления. **Последствия потери `OTP_ENCRYPTION_KEYS`** (поведение подтверждено автотестами): коды приложения-аутентификатора перестают приниматься (пользователь видит спокойное сообщение, в журнале - ошибка без секретов), вход возможен по резервным кодам; остальным пользователям нужен сброс 2FA администратором и повторная привязка; незавершённая привязка пересоздаётся сама; сами данные не теряются, но вход с 2FA без ключа невозможен. **Сохранение:** сразу после создания переместить копию в хранилище секретов владельца (минимум два независимых экземпляра, **не рядом с копиями данных**; `DEPLOYMENT_READINESS.md` §6.2) командой, которую выберет владелец, не выводя значение на экран, и проверить, что сохранённая копия **читается**: при первой проверке восстановления (шаг 11) `restore_check.sh` расшифровывает секреты 2FA именно этим ключом (`verify_restored_two_factor`) - использовать ключ из хранилища, а не из `talim.env`. Копии ключа в чатах, тикетах, письмах и Git недопустимы. Если генерация идёт в консоли с записью сеанса - отключить запись.
4. **Код и зависимости**: релиз = полный checkout репозитория (нужны `backend/` и `assets/`):
   ```bash
   sudo -u talim git clone <репозиторий> /srv/talim/releases/<тег>
   # если репозиторий приватный: клонируйте под своей учётной записью (токен доступа не сохраняйте на сервере) и передайте каталог: sudo cp -a ~/talim-src /srv/talim/releases/<тег> && sudo chown -R talim:talim /srv/talim/releases/<тег>
   sudo -u talim git -C /srv/talim/releases/<тег> checkout <кодовый коммит>   # ТОЛЬКО коммит, указанный владельцем в OWNER_HANDOFF.md §1 (кодовый коммит кандидата), не «последний в ветке»
   sudo -u talim /srv/talim/releases/<тег>/backend/deploy/staging/release_info.sh   # сверить коммит, хеш requirements.txt и хеш файлов развёртывания с OWNER_HANDOFF.md §1; расхождение — остановиться
   sudo -u talim bash -c 'cd /srv/talim/releases/<тег>/backend && python3.12 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt'
   sudo ln -sfn /srv/talim/releases/<тег>/backend /srv/talim/backend      # первый релиз; дальше — release.sh
   ```
**Пароли и ключи не набирать в командной строке** (остаются в истории оболочки и видны в `ps`): в блоках ниже `<…>` означает значение из файла `0600`. Задавать переменные, например, так: `set +o history; set -a; . /etc/talim/talim.env; set +a` (или `read -rs DB_PASSWORD`), затем команда без значений в тексте.

5. **Миграции и права** — владелец БД только для миграций (§4.4, §4.2). Пароль владельца **вводится с клавиатуры** в запрос `read -s` (не отображается, не попадает ни в argv, ни в историю, ни в файл) и существует только в переменных окружения этого одного сеанса, который заканчивается после `apply_grants.sql`:
   ```bash
   sudo -u talim bash -c '
     cd /srv/talim/backend && set -a && . /etc/talim/talim.env && set +a
     IFS= read -rs -p "Пароль владельца БД (talim_owner): " OWNER_PW; echo
     DB_USER=talim_owner DB_PASSWORD="$OWNER_PW" DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py migrate || exit 1
     PGPASSWORD="$OWNER_PW" psql -h 127.0.0.1 -U talim_owner -d "$DB_NAME" -v ON_ERROR_STOP=1 -v app=talim_app -v db="$DB_NAME" -v backup_role=talim_backup -f deploy/postgres/apply_grants.sql
     unset OWNER_PW
     .venv/bin/python manage.py seed_roles --dry-run          # прочитать план; нестандартные права (=) остаются, удаляет только --prune
     .venv/bin/python manage.py seed_roles && .venv/bin/python manage.py collectstatic --noinput'
   ```
   (Исходный файл с паролем владельца хранится у оператора/в хранилище секретов, **не** на сервере.) Остаточный риск: значение живёт в памяти процессов `bash`/`python`/`psql` пользователя `talim` и в их `environ` (читаемо только для `talim` и `root`) на время сеанса. Временных файлов с секретами этот шаг не создаёт, поэтому надёжное стирание файлов (`shred` на журналируемых и copy-on-write файловых системах и SSD гарантий не даёт) не требуется. Если секрет всё же пришлось записать в файл — держать его только в `/dev/shm` (память, исчезает при перезагрузке), права `0600`, каталог `0700`, и удалить сразу после шага; на `shred` не полагаться.
6. **Предпроверка** (от `talim`; **остановиться, если есть FAIL**):
   ```bash
   sudo -u talim /srv/talim/backend/.venv/bin/python /srv/talim/backend/deploy/staging/preflight.py --env-file /etc/talim/talim.env --backend /srv/talim/backend --backup-env /etc/talim/backup.env
   ```
   Ожидается `PREFLIGHT OK`; SKIP (SMTP, TLS, файрвол) — ручные пункты ниже. С `--backup-env` проверяется и среда копий: файл `backup.env` не открыт всем, заданы `BACKUP_DIR`, `BACKUP_PASSPHRASE_FILE`, `PGUSER`; роль копий **не совпадает** с runtime-ролью и не `postgres`; пароль копий 0600, ≥ 20 символов, вне каталога копий и хранилища документов; каталог копий 0700; `PGPASSFILE` 0600; роль реально имеет `CREATEDB` и не суперпользователь (проверка через `psql`, если он установлен).
7. **Gunicorn**: `sudo cp backend/deploy/systemd/talim-gunicorn.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now talim-gunicorn`.
8. **ClamAV**: по [CLAMAV.md](CLAMAV.md) (`freshclam`, `StreamMaxLength 25M`), `DOCUMENT_SCAN_MODE=clamav`; `sudo -u talim … manage.py check_scanner --eicar` → «clamd OK (… EICAR … DETECTED)» (это доказывает, что загружена пригодная база сигнатур; без `--eicar` проверяется только ответ демона). Регулярный таймер `talim-check_scanner.timer` выполняет обычную проверку.
9. **Nginx и TLS**: из `backend/deploy/nginx/talim-production.conf.template` подставить плейсхолдеры (`{{SERVER_NAME}}`, `{{TLS_CERT}}`, `{{TLS_KEY}}`, `{{BACKEND_PORT}}`=8000, `{{HTTP_LISTEN}}`, `{{HTTPS_LISTEN}}`, `{{HTTPS_PORT_SUFFIX}}` (пусто для 443), `{{ERROR_DIR}}`, `{{STATIC_DIR}}` (= `/srv/talim/backend/staticfiles`: каталог, который создаёт `collectstatic`), `{{ACCESS_LOG}}`) — образец подстановки в `backend/deploy/nginx/verify/run_tls.sh`; `sudo nginx -t && sudo systemctl reload nginx`. Права на статику: файлы `collectstatic` публичны и создаются 0644/0755 (настроено в `STORAGES`, проверяется тестом); процесс nginx (другой пользователь) должен проходить по каталогам `/srv`, `/srv/talim`, `releases/<тег>/backend` (режим `o+x`); секреты лежат в `/etc/talim`, не здесь. Версия nginx < 1.25.1: `listen … ssl http2;` (как в шаблоне); ≥ 1.25.1 — см. комментарий в шаблоне.
10. **Таймеры и службы** (SCHEDULER.md §4):
    ```bash
    sudo cp backend/deploy/systemd/talim-job*.service backend/deploy/systemd/talim-*.timer /etc/systemd/system/
    sudo cp -r backend/deploy/systemd/talim-job@run_backup.service.d backend/deploy/systemd/talim-job@run_restore_check.service.d /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now talim-send_task_reminders.timer talim-purge_employee_imports.timer talim-purge_throttles.timer talim-purge_attendance_locations.timer talim-clear_expired_sessions.timer talim-check_scanner.timer talim-verify_document_files.timer talim-backup_create.timer talim-backup_restore_check.timer
    systemctl list-timers 'talim-*'
    ```
    (Каталоги drop-in и их установку сверить с `SCHEDULER.md` §8 — в проверке файлов `verify_deploy_files.sh` они учтены, на сервере установка **[не проверено]**.)
11. **Последующие релизы**: `backend/deploy/staging/release.sh deploy <тег>` с переменными из STAGING_RUNBOOK §1 (`RELEASES_DIR`, `CURRENT_LINK`, `HEALTH_URL`, `HEALTH_HOST`, `RESTART_CMD`, `PRE_BACKUP_CMD`, `MIGRATE_CMD_PREFIX`, `POST_MIGRATE_SQL_CMD`). Нужен `curl`. Вывод `RELEASE_OK`. `release.sh` **не** запускает `seed_roles`: после релиза, добавившего роли или права (например, роли редакции), выполнить `sudo -u talim … manage.py seed_roles` (идемпотентно; сначала `--dry-run`; ничего не удаляет без `--prune`; нестандартные права выводятся в stderr — прочитать; назначения и личные разрешения не меняет) — **[не проверено на сервере]**.
12. **HSTS не включать** (`DJANGO_HSTS_SECONDS=0`), пока §6 не пройден целиком и вручную не проверен настоящий HTTPS (DEPLOYMENT_READINESS §4.12).

## 6. Проверки после развёртывания
| № | Проверка | Как | Ожидаемо |
|---|---|---|---|
| 1 | Приёмка снаружи | с **другой** машины: `python3 backend/deploy/staging/smoke_remote.py https://<хост> --admin-path <DJANGO_ADMIN_URL>` (**без** `--insecure-self-signed`) | `SMOKE OK: 21/21`; недоверенный сертификат = FAIL |
| 2 | Здоровье | `curl -fsS https://<хост>/healthz/` | `{"status": "ok", "database": "ok", "grants": "ok"}` (`grants: error` = роль приложения не читает какую-то таблицу: выполнить `apply_grants.sql`) |
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
4. `sudo systemctl stop clamav-daemon` → новая загрузка **отклоняется** (fail-closed), существующие непроверенные документы недоступны; затем `sudo systemctl start clamav-daemon` → `check_scanner` OK. (В песочнице: тесты `RealClamdTests` пройдены против настоящего `clamd` с официальной базой, но **не на сервере и не через systemd**; полная процедура C-1…C-8 — `CLAMAV.md`, раздел «Процедура проверки ClamAV на staging»; на сервере не выполнялась.)
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
**Откат приложения.** `release.sh deploy <тег>` перед изменениями делает копию (`PRE_BACKUP_CMD`; при её неудаче релиз не начинается), мигрирует, переключает ссылку, перезапускает, опрашивает `/healthz/`; при провале возвращает прежнюю ссылку и перезапускает (код 1, `RELEASE_FAILED_ROLLED_BACK`; код 3 — прежний релиз тоже не отвечает: срочно). Вручную: `release.sh rollback`, `release.sh status` — **с теми же переменными окружения, что и `deploy`** (`STAGING_RUNBOOK.md` §1; их удобно заранее сохранить в файле `0600` и подключать `. файл`, чтобы не искать в аварии). **Для первого релиза отката нет** (нет предыдущего): при сбое — остановить службы, не менять защиту, разобрать причину по журналам, эскалация (§0). Логика отрепетирована в песочнице (`deploy/staging/verify_release.sh`, 24 проверки, настоящие gunicorn/PostgreSQL, production-настройки); **на сервере под systemd не проверялось**.

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


### Дополнение (День 24): создание, проверка и восстановление копий
Подробные гарантии и процедура — [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md) §12. Для оператора: `run_backup` может завершиться кодом **4** («retention failed»: копия создана, но старые копии не удаляются — исправить права, иначе заполнится диск); успешная проверка восстановления ставит метку `RESTORE_VERIFIED`, и ротация эту копию не удаляет; убитые процессы оставляют `*.partial` (удаляются следующим запуском) — при ручной уборке их можно удалять, готовые копии (`talim-*Z` с манифестом) — нет. Внешняя копия **не реализована**: блокер B-22 открыт.


### Дополнение (День 25): защита адреса Django admin
`DJANGO_ADMIN_URL` обязателен нестандартный (≥ 12 символов): иначе production не запустится, `preflight.py` — FAIL. Дополнительно (по решению заказчика, **не проверено на сервере**) адрес можно закрыть на nginx списком адресов — отдельный `location` с `allow <адрес администратора>; deny all;` перед общим `location /` (адреса подставляет оператор; в шаблон они не вносятся). Суперпользователей держать минимальным числом, с 2FA; список и хранение паролей — решение заказчика. Кандидат на релиз фиксируется `backend/deploy/staging/release_info.sh` (см. [RELEASE_CANDIDATE.md](RELEASE_CANDIDATE.md)).
