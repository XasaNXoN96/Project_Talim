# Антивирусная проверка загрузок (ClamAV)

**Статус:** реализовано в коде; проверено с настоящим `clamd` в тестовой среде, но **на сигнатурах, созданных локально** (см. «Что именно проверено»). На боевом сервере не развёрнуто.

## Как это работает
Каждый загружаемый файл (документы, новые версии, вложения заданий) проходит **один и тот же** путь — `backend/apps/documents/files.py`:
проверка размера/расширения/типа/структуры → **сканирование ClamAV** → только затем запись в приватное хранилище и появление записи в БД.
Пока проверка не закончилась успешно, файл никому не доступен: его ещё нет ни на диске, ни в базе.

| Исход | Что происходит |
|---|---|
| Чисто | файл сохраняется, у версии `scan_status=clean`, фиксируется время и движок |
| Найдена угроза | файл **не** сохраняется; пользователю — «зарарли дастур аниқланди»; в аудит: `file_threat_detected` (только **имя сигнатуры**) и `document_upload_rejected` (причина `malware`); имя файла и содержимое не пишутся |
| clamd не отвечает / отказ в соединении | **fail-closed**: файл отклоняется, причина `scan_unavailable`; в журнале приложения — только тип ошибки |
| Тайм-аут (`CLAMAV_TIMEOUT`, по умолчанию 20 с на всё: соединение + передача + ответ) | отклоняется, `scan_timeout` |
| Любой иной ответ (ERROR, превышен лимит потока демона, мусор, обрыв) | отклоняется, `scan_error` |

Карантинной очереди **нет**: при сбое сканера загрузка просто отклоняется и пользователь повторяет её позже. Это сознательный выбор (проще и безопаснее).
Файл передаётся только тому `clamd`, который указан в настройках (unix-сокет или `127.0.0.1`); внешним сервисам ничего не отправляется.

## Настройки (переменные окружения)
| Переменная | По умолчанию | Смысл |
|---|---|---|
| `DOCUMENT_SCAN_MODE` | `clamav` | `clamav` или `disabled`. **`disabled` — только для разработки**; production-настройки **не запускаются** с `disabled` |
| `CLAMAV_SOCKET` | пусто | путь к unix-сокету clamd (рекомендуется), например `/run/clamav/clamd.ctl` |
| `CLAMAV_HOST`, `CLAMAV_PORT` | `127.0.0.1`, `3310` | используются, если сокет не задан. TCP-порт clamd **нельзя** открывать наружу |
| `CLAMAV_TIMEOUT` | `20` | секунд на одну проверку |

## Установка (Ubuntu/Debian, пример)
```bash
sudo apt-get install clamav clamav-daemon clamav-freshclam
sudo systemctl enable --now clamav-freshclam        # обновление сигнатур (по умолчанию несколько раз в сутки)
sudo systemctl stop clamav-freshclam; sudo freshclam; sudo systemctl start clamav-freshclam   # первое скачивание вручную
```
Минимальные правки `/etc/clamav/clamd.conf`:
```
LocalSocket /run/clamav/clamd.ctl
LocalSocketGroup talim            # группа пользователя приложения (или добавьте пользователя в группу clamav)
LocalSocketMode 660
StreamMaxLength 25M               # больше DOCUMENT_MAX_BYTES (10 МБ); иначе крупные файлы будут отклоняться
MaxFileSize 25M
# TCPSocket / TCPAddr — не включать, если используется сокет
```
Затем `sudo systemctl enable --now clamav-daemon`. Демон загружает всю базу в память (порядка 1–2 ГБ ОЗУ — учтите при выборе сервера) и стартует десятки секунд.

## Проверка и мониторинг
```bash
python manage.py check_scanner      # PING + тестовая проверка; код выхода 1, если сканер недоступен
```
Запускайте её из мониторинга (например, каждые 5 минут). Пока она падает, **загрузки отклоняются** (чтение и скачивание работают).

## Обновление сигнатур
Выполняет `clamav-freshclam`. Контролируйте: `journalctl -u clamav-freshclam`, дата базы в `clamdscan --version`. Устаревшая база — пониженная защита без каких-либо ошибок в приложении.
После заметного обновления (или если сканер был отключён) пересканируйте уже сохранённое:
```bash
python manage.py scan_documents            # только «не проверенные» версии и вложения
python manage.py scan_documents --all      # всё заново
```
Найденное помечается `infected`, **перестаёт отдаваться** и пишется в аудит (`file_threat_detected`, `source=rescan`). Если сканер недоступен, команда останавливается с ошибкой и ничего не меняет.

## Если сканер недоступен: что делать
1. `python manage.py check_scanner` и `systemctl status clamav-daemon`; `journalctl -u clamav-daemon`.
2. Частые причины: не хватило памяти, обновление базы ещё не закончилось (демон перезагружает её), неверная группа сокета, `StreamMaxLength` меньше загружаемого файла.
3. Пользователям: «загрузка временно недоступна». **Не** переключайте `DOCUMENT_SCAN_MODE=disabled` на production (оно и не запустится).
4. После восстановления — `scan_documents`, если что-то могло быть сохранено без проверки (в production такого быть не должно).

## Что именно проверено
- **Тесты с заглушкой** (`apps/documents/tests_scanner.py`, выполняются всегда): протокол, чистый файл, угроза, ERROR/лимит/мусор, обрыв, тайм-аут, недоступность, unix-сокет, fail-closed во всех путях загрузки, аудит без содержимого, пересканирование, карантин.
- **Тесты с настоящим clamd** (`apps/documents/tests_real_clamd.py`, пропускаются без `CLAMAV_REAL_TEST=1` и работающего демона): чистый файл, обнаружение тестовой строки EICAR, превышение лимита потока, полный цикл загрузки. Запуск: `CLAMAV_REAL_TEST=1 python manage.py test apps.documents.tests_real_clamd`.
- **Ограничение этой проверки:** в среде разработки ClamAV 1.5.4 был установлен и запущен по-настоящему, но **официальные сигнатуры скачать не удалось** (сетевой прокси блокирует `database.clamav.net`). Обнаружение EICAR выполнено **локальной сигнатурой на хэш** (`Local.Eicar-Test-Signature`). Значит, проверено: настоящий движок, протокол, поведение приложения. **Не проверено:** то, что официальная база реально ловит вредоносные файлы на вашем сервере, и производительность/память с полной базой.
- Антивирус ловит известные угрозы; он не гарантирует отсутствие вредоносного содержимого (нулевые дни, целевые файлы). Остальные меры (белый список типов, скачивание только как вложение) сохраняются.

## Тесты с настоящим clamd: как запустить и что они доказывают (День 30)
**Почему «пропущено 4».** `apps.documents.tests_real_clamd.RealClamdTests` (4 теста) пропускаются **намеренно**, если не задан `CLAMAV_REAL_TEST=1` («set CLAMAV_REAL_TEST=1 to run the real-clamd checks») либо демон не отвечает на PING («CLAMAV_REAL_TEST=1 but clamd does not answer PING»). Это не скрытая ошибка: при остановленном демоне и заданной переменной пропуск воспроизведён. Моков и заглушек в этих тестах нет, число пропусков не «обнуляется» кодом.

**Команда (из `backend/`, на машине с работающим `clamd` и загруженной базой):**
```bash
CLAMAV_REAL_TEST=1 CLAMAV_HOST=127.0.0.1 CLAMAV_PORT=3310 \
  python manage.py test apps.documents.tests_real_clamd --settings=config.settings.test --noinput -v 2
# вместо TCP можно: CLAMAV_SOCKET=/run/clamav/clamd.ctl (CLAMAV_HOST/CLAMAV_PORT тогда не нужны)
```
Ожидается `Ran 4 tests … OK` **без** `skipped`. Условия: (1) `clamd` запущен и отвечает на `PING`; (2) загружена официальная база (`freshclam` выполнен; она содержит EICAR); (3) `StreamMaxLength` в `clamd.conf` соответствует `CLAMAV_*`/`DOCUMENT_MAX_BYTES` (тест «данные сверх лимита потока → сбой, а не «чисто»» опирается на лимит демона, см. выше); (4) для тестов нужна доступная PostgreSQL (тестовая БД создаётся и удаляется). Тесты работают с `config.settings.test` и **не** касаются рабочих данных.

**Единственный прогон (песочница, День 30):** `freshclam` скачал официальные базы (`main`, `daily` версия 28157, `bytecode`) во временный каталог вне репозитория; `clamd` 1.5.4 запущен отдельным процессом с временной конфигурацией (TCP 127.0.0.1:3310, `StreamMaxLength 25M`, 3 628 169 сигнатур) без изменения системных файлов. Результат: **4 теста — OK, 0 пропусков**; затем демон остановлен, временные файлы вне репозитория. Ранее (docstring теста, Дни 6–9) в песочнице официальная база скачана не была и использовалась локальная сигнатура; теперь сеть позволила официальную. **Это не проверка staging:** другая машина, демон не под systemd и не с рабочей конфигурацией владельца, база не обновляется по расписанию. Блокер B-06 остаётся открытым до выполнения на staging: `freshclam` по расписанию, `clamd` как служба, `check_scanner --eicar`, загрузка EICAR отклонена и отклонение при остановленном `clamd` (`STAGING_OPERATOR_CHECKLIST.md` шаги 8–9), затем эта же команда на сервере. Полный набор тестов этим прогоном не повторялся: код не менялся.

## Что проверено, что нужно проверить на staging и что не проводилось (День 31)
| Категория | Содержание |
|---|---|
| **1. Проверено в песочнице** (не staging) | 4 теста `RealClamdTests` против настоящего `clamd` 1.5.4 с официальной базой (скачана `freshclam`) — OK; `check_scanner --eicar` и загрузка EICAR на **локальной** сигнатуре (Дни 6–9); fail-closed (`ScanFailed` → отказ загрузки) — тестами `documents/tests_scanner` на **тестовом сервере-заглушке протокола clamd** (это не настоящий демон) и тестом превышения лимита потока на настоящем демоне; остановка настоящей службы `clamav-daemon` не проверялась. |
| **2. Обязательно выполнить на staging** | процедура ниже (шаги C-1…C-8). До этого **B-06 открыт**. |
| **3. Не проводилось вообще** | `clamd` и `freshclam` как системные службы на сервере с рабочей конфигурацией; обновление базы по расписанию и контроль её даты; нагрузка на сканер; поведение при нехватке памяти на ВМ; отказ загрузки через настоящий HTTPS-путь с `nginx`; оповещение дежурного о падении `clamd`; запуск `RealClamdTests` на сервере. |

## Процедура проверки ClamAV на staging (C-1…C-8)
Выполняет оператор на staging-ВМ (не на песочнице), от пользователя `talim` там, где указано; результат каждого шага записывается вне Git (дата, кто, вывод **без** секретов). Имена служб и команды взяты из этого репозитория и `CLAMAV.md`; **все шаги ниже на сервере ещё не выполнялись.** Если шаг не пройден — остановиться (`STAGING_OPERATOR_CHECKLIST.md` §12).

**C-1. Официальные сигнатуры и обновление.**
```bash
sudo systemctl stop clamav-freshclam; sudo freshclam; sudo systemctl start clamav-freshclam
systemctl is-active clamav-freshclam            # ожидается: active
journalctl -u clamav-freshclam -n 30 --no-pager  # нет ошибок загрузки, указана свежая версия базы
clamdscan --version                              # в выводе — версия ClamAV, номер и дата базы (свежие)
```
Критерий: базы `main`, `daily`, `bytecode` скачаны с официальных серверов; дата базы не старше нескольких суток; служба обновления включена (`systemctl is-enabled clamav-freshclam`).

**C-2. `clamd` как системная служба и PING.**
```bash
sudo systemctl enable --now clamav-daemon; systemctl is-active clamav-daemon   # ожидается: active (старт — десятки секунд)
sudo -u talim /srv/talim/backend/.venv/bin/python /srv/talim/backend/manage.py check_scanner    # код 0
```
`check_scanner` выполняет PING и проверку чистой строки; в `talim.env` заданы `DOCUMENT_SCAN_MODE=clamav` и (рекомендуется) `CLAMAV_SOCKET=/run/clamav/clamd.ctl`. Критерий: служба активна после перезагрузки сервера (`systemctl is-enabled clamav-daemon`), пользователь `talim` имеет доступ к сокету (группа/режим из `clamd.conf`), TCP-порт 3310 снаружи закрыт (проверка с другой машины).

**C-3. Согласованность лимитов.**
```bash
grep -E '^(StreamMaxLength|MaxFileSize)' /etc/clamav/clamd.conf     # ожидается 25M и 25M
grep -E '^DOCUMENT_MAX_BYTES' /etc/talim/talim.env || echo "по умолчанию 10 МБ (10485760)"
```
Критерий: `StreamMaxLength` **больше** `DOCUMENT_MAX_BYTES` (по умолчанию 25M > 10 МБ); иначе крупные допустимые файлы будут отклоняться. Проверка «данные сверх лимита потока → сбой, а не «чисто»» входит в C-4.

**C-4. Четыре теста `RealClamdTests` (`CLAMAV_REAL_TEST=1`) — отдельная тестовая роль.**
*Что нужно Django.* `manage.py test` подключается к служебной БД `postgres`, выполняет `CREATE DATABASE test_<DB_NAME>`, применяет все миграции в ней и в конце `DROP DATABASE`. Нужны: `LOGIN`, `CREATEDB` и право `CONNECT` на БД `postgres`; права на рабочую БД, `pg_read_all_data`, суперпользователь и `CREATEROLE` **не нужны**. Роль приложения (`DB_USER` из `talim.env`) `CREATEDB` не имеет и **не получает**: при запуске от неё прогон останавливается с «permission denied to create database». Роль копий (`create_backup_role.sql`) формально подходит (есть `CREATEDB`), но **не рекомендуется**: у неё `pg_read_all_data`, и после `apply_grants.sql -v backup_role=…` она может читать рабочую БД — тест не должен работать с учётными данными, способными читать рабочие данные. Минимальный вариант — **отдельная одноразовая роль**:
```bash
# 1. На staging, от суперпользователя PostgreSQL (пароль — из нового файла 0600, создать на сервере, не в Git и не в командной строке):
umask 077; python3 -c 'import secrets;print(secrets.token_urlsafe(30))' > /root/clamtest.pw
sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -v tr=talim_clamtest -v tp="$(cat /root/clamtest.pw)" \
  -c "CREATE ROLE :\"tr\" LOGIN PASSWORD :'tp' NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
# (на хосте, где у PUBLIC отозван CONNECT на БД postgres, дополнительно: GRANT CONNECT ON DATABASE postgres TO talim_clamtest)
# 2. Прогон — в отдельном checkout того же кандидата (release_info.sh: те же хеши), НЕ с talim.env и НЕ с рабочей БД:
cd <checkout>/backend && DB_NAME=talim_clamtest_scratch DB_USER=talim_clamtest DB_PASSWORD="$(cat /root/clamtest.pw)" DB_HOST=127.0.0.1 \
  CLAMAV_REAL_TEST=1 CLAMAV_SOCKET=/run/clamav/clamd.ctl \
  .venv/bin/python manage.py test apps.documents.tests_real_clamd --settings=config.settings.test --noinput -v 2
# 3. Сразу после прогона — удалить роль и пароль:
sudo -u postgres psql -d postgres -c "DROP ROLE talim_clamtest"   # (если GRANT CONNECT выдавался: сначала REVOKE ALL ON DATABASE postgres FROM talim_clamtest)
shred -u /root/clamtest.pw; rm -rf /tmp/talim-test-private-*
```
`DB_NAME` может не существовать (подключение идёт к `postgres`); любое имя, кроме имени рабочей БД. Чтение `CLAMAV_SOCKET=/run/clamav/clamd.ctl` требует, чтобы пользователь прогона входил в группу сокета (`LocalSocketGroup`, `clamd.conf`); иначе используйте TCP на `127.0.0.1:3310` только если он включён локально (наружу не открывать). Ожидается `Ran 4 tests … OK` без `skipped`; временная БД `test_<DB_NAME>` удалена (`sudo -u postgres psql -Atc "select datname from pg_database"`). Каталоги `/tmp/talim-test-private-*` тестовые настройки создают на каждый прогон и не удаляют — убрать вручную (команда выше).
*Статус.* Поведение ролей **проверено в песочнице** (PostgreSQL 16.15, роли созданы скриптами репозитория `create_roles.sql`, `create_backup_role.sql` и приведённым выше `CREATE ROLE`, затем удалены): runtime-роль — отказ «permission denied to create database»; отдельная роль с `CREATEDB` и без доступа к рабочей БД — 4 теста OK, временная БД удалена; роль копий — 4 теста OK (не рекомендуется по причине выше); при отозванном `CONNECT` на `postgres` от `PUBLIC` — отказ, после точечного `GRANT CONNECT` — OK. **На staging не выполнялось**; настройки `pg_hba.conf` и политики сервера владельца могут отличаться (например, запрет `CREATEDB` вообще — тогда тест запускается на другой машине с собственной временной PostgreSQL, а не на сервере).

**C-5. `check_scanner --eicar` в боевых настройках.**
```bash
sudo -u talim /srv/talim/backend/.venv/bin/python /srv/talim/backend/manage.py check_scanner --eicar   # код 0, EICAR обнаружен
```
Выполняется под `config.settings.production` (в `config.settings.test` команда отказывается: сканирование там отключено). Критерий: код 0; в выводе — «EICAR … DETECTED».

**C-6. Отклонение EICAR через путь загрузки приложения.** Создать вручную файл с тестовой строкой EICAR (безвредна); в браузере войти вымышленным пользователем с правом загрузки, `/portal/documents/new/` — загрузить; затем загрузить вымышленный чистый PDF.
Критерий: EICAR **отклонён** (сообщение об обнаруженной угрозе, версия не сохранена как «чистая»), в журнале аудита есть запись `file_threat_detected`; чистый PDF принят, статус «проверен», скачивается побайтно совпадающим (`/portal/documents/<id>/download/`); `manage.py verify_document_files` — без расхождений.

**C-7. Fail-closed при остановленном/недоступном `clamd`.**
```bash
sudo systemctl stop clamav-daemon
sudo -u talim /srv/talim/backend/.venv/bin/python /srv/talim/backend/manage.py check_scanner; echo $?    # ненулевой код
# попытаться загрузить вымышленный чистый PDF через /portal/documents/new/ -> загрузка ОТКЛОНЕНА, документ не сохранён
sudo systemctl start clamav-daemon; sudo -u talim ... manage.py check_scanner                              # снова 0
```
Также (если разрешено) неверная группа/режим сокета или значение `CLAMAV_SOCKET` — загрузка отклоняется. Критерий: пока демон недоступен, **ни одна новая версия не принята как чистая**; после запуска — работа восстановлена; оповещение дежурному о падении `talim-job@check_scanner.service` (таймер `talim-check_scanner.timer`, каждые 5 мин) пришло — если мониторинг настроен (B-11).

**C-8. Журналы.**
```bash
journalctl -u talim-gunicorn --since "-30min" --no-pager | grep -E "Virus scan"
```
В журнале приложения при сбое — только строки вида `Virus scanner unreachable (<класс>)`, `Virus scan timed out after <N>s`, `Virus scanner returned an unexpected verdict (<N> chars)`; нет ни содержимого файлов, ни их имён, ни токенов. Проверить, что на время остановки `clamd` (C-7) в таблице версий документов нет записи со статусом «чистый» (`manage.py scan_documents` без `--all` ничего не должна менять, сообщив о недоступном сканере). Критерий: каждый отказ виден в журнале, а принятых как чистые при сбое файлов нет.

**B-06 закрывается** только когда шаги C-1…C-8 выполнены на staging и результат записан (дата, кто). Песочничные тесты и любые моделирования его не закрывают.
