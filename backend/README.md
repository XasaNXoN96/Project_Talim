# Backend — Mirzacho‘l tumani Xalq ta’limi bo‘limi (Django)

**Статус: каркас (День 1). Не production-ready. Не развёрнут нигде.** Статический макет в корне репозитория
(GitHub Pages) не изменялся и остаётся визуальным эталоном; этот каталог живёт рядом с ним.

## Что здесь реально работает
- Публичная главная `/`, список и страница новостей `/yangiliklar/` — данные из PostgreSQL, показываются только опубликованные.
- Вход `/accounts/login/` (логин **или** e-mail, «Meni eslab qolish»), выход (только POST), защита CSRF.
- Защищённый портал `/portal/` (нужен вход) и `/portal/audit/` (нужно право `audit.view_auditlog`; иначе 403).
- Журнал аудита: входы, неудачные входы (без введённого текста), выходы, назначение/снятие ролей. Записи нельзя менять и удалять.
- Роли = группы Django (`employee`, `department_head`, `content_manager`, `hr`, `admin`, `sysadmin`) + область (`own/department/all`).
- Техническая админка Django `/admin/` (по умолчанию; адрес задаётся `DJANGO_ADMIN_URL`).

## Чего ещё НЕТ (сознательно)
Восстановление пароля, 2FA, ограничение попыток входа, CSP, загрузка файлов, редактор новостей в портале,
сотрудники/задания/документы/уведомления/отчёты/чат/геолокация (см. `docs/FEATURE_ROADMAP.md`).
Формы-заглушки не используются: каждая отображаемая форма здесь реально работает.

## Структура
```
backend/
  manage.py
  config/settings/{base,dev,test,production}.py   # production — заготовка, не используется
  apps/{core,accounts,organization,access,content,audit,portal}
  templates/  static/  tests/
  requirements.in / requirements.txt (версии и хэши закреплены)
  .env.example   # шаблон; настоящий .env не коммитится
```
Общий CSS/JS берутся **из корня репозитория** (`/assets`) через `STATICFILES_DIRS` — без копирования.
Шаблоны Django не дублируют HTML макета: они используют те же классы дизайн-системы.

## Локальный запуск
Требуется: Python 3.12, PostgreSQL 16 (Django 5.2 LTS поддерживает Python 3.10–3.13).

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.txt

# PostgreSQL: локальная роль с правом CREATEDB (нужно для тестов) и база
sudo -u postgres psql -c "CREATE ROLE talim_dev LOGIN CREATEDB PASSWORD '<придумайте-пароль>';"
sudo -u postgres createdb -O talim_dev talim_dev

cp .env.example .env      # впишите сгенерированный SECRET_KEY и пароль БД
python -c "import secrets; print(secrets.token_urlsafe(64))"   # для DJANGO_SECRET_KEY

python manage.py migrate
python manage.py seed_roles                  # создаёт группы-роли (идемпотентно)
python manage.py createsuperuser             # только для локальной разработки
python manage.py runserver 127.0.0.1:8000    # http://127.0.0.1:8000/
```
Первому пользователю роль выдаётся в `/admin/` (Пользователи → «Назначения ролей»). Никаких пользователей по умолчанию нет.

## Тесты
```bash
python manage.py test --settings=config.settings.test --noinput
```
Тесты используют PostgreSQL (создаётся и удаляется `test_<DB_NAME>`). Без доступной БД они не запустятся.

## Проверка конфигурации безопасности (без запуска сервера)
```bash
DJANGO_SECRET_KEY=<любой-длинный-ключ> DJANGO_ALLOWED_HOSTS=example.test \
  python manage.py check --deploy --settings=config.settings.production
```
HSTS намеренно выключен по умолчанию (`DJANGO_HSTS_SECONDS=0`): включается только после проверки HTTPS.

## Обновление зависимостей
Правьте `requirements.in`, затем:
`uv pip compile requirements.in --python-version 3.12 --generate-hashes -o requirements.txt`

## Важно про GitHub Pages
Pages публикует корень ветки как есть, поэтому файлы `backend/` тоже доступны по адресу сайта как **статические текстовые файлы**
(шаблоны Django там не обрабатываются, Python не выполняется). В репозитории нет секретов — он публичный; `.env` в Git не попадает
(`.gitignore`, плюс тест `SecretsNotInGitTests`). Настоящие значения паролей и ключей никогда не добавляйте в коммиты.

## Правила
Только вымышленные данные («Namuna …», домен `example.test`). Реальные персональные данные не вносятся, пока не закрыт
`docs/LEGAL_AND_DATA_CHECKLIST.md`.
