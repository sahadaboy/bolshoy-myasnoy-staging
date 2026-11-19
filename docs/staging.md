# Бесплатное staging-размещение: GitHub + Render + Neon

Подготовлено 18 ноября 2026. **Развёртывание ещё не выполнено.** Нет созданного облачного сервиса, проверенного постоянного URL или подтверждённого Telegram-входа на нём.

Схема: один Render Free Web Service запускает Django/Gunicorn, отдаёт собранный React и Admin через WhiteNoise; Neon Free хранит PostgreSQL и фотографии в S3-совместимом Object Storage. Компьютер владельца для работы сайта не требуется. Локальные настройки и исходные SQLite сохранены.

Render Free засыпает после 15 минут простоя; первое открытие может занимать около минуты. Это постоянный URL с холодным стартом, без гарантии мгновенной доступности 24/7. Локальные файлы Render непостоянны, поэтому SQLite/загрузки там не используются. [Ограничения Render Free](https://render.com/docs/free).

Neon Object Storage доступен на Free, в том числе в AWS Frankfurt: 5 ГБ для файлов на проект; текущий перенос занимает менее 4 МБ. Квоты PostgreSQL, вычислений и исходящего трафика ограничены; при исчерпании бесплатных квот возможна остановка до их восстановления. Не переключать организацию на Launch/Scale. [Neon Free](https://neon.com/docs/introduction/plans), [Object Storage](https://neon.com/docs/storage/overview).

## 1. Аккаунты

Нужны только **GitHub Free**, **Render** с Web Service **Free**, **Neon Free**. Бот `@bmmsev_bot` уже существует. Дополнительный AWS/Supabase/R2 аккаунт не нужен. Платные диски, Render Postgres, workers, cron, домен, Neon Auth и платные преобразования изображений не подключаются.

В интерфейсах проверить итоговую стоимость $0, не включать paid runners/платные тарифы и не повышать лимиты расходов GitHub Actions. Бесплатные минуты CI также имеют квоту. Если панель предлагает обязательный платный тариф, остановиться, а не подтверждать оплату.

## 2. Код в отдельный приватный репозиторий

Создать на GitHub пустой **Private** репозиторий, без README. Для него подготовлена отдельная копия кода `.staging-release`; исходную папку магазина превращать в Git-репозиторий не требуется. Копия содержит только файлы приложения, сборки, CI, разрешённые frontend-ресурсы и эту инструкцию. В ней нет `.env`, SQLite, резервных копий, выгрузки данных, медиа из Admin, Cloudflare и локальных инструментов.

Если после подготовки менялся код, сформировать новую копию командой ниже после перемещения предыдущей копии вручную: скрипт никогда её не перезаписывает.

```powershell
Set-Location -LiteralPath 'C:\Users\Gor Sahakyan\Desktop\bolshoy-myasnoy'
& '.\.venv-staging\Scripts\python.exe' deploy/prepare_release.py
```

Если `.staging-release` уже подготовлена, сразу перейти в неё. При установленном Git:

```powershell
Set-Location -LiteralPath 'C:\Users\Gor Sahakyan\Desktop\bolshoy-myasnoy\.staging-release'
git init -b staging
git add .
git status --short
& '..\.venv-staging\Scripts\python.exe' deploy/check_release.py
git commit -m "Prepare free staging deployment"
git remote add origin https://github.com/ВАШ-LOGIN/ВАШ-PRIVATE-REPO.git
git push -u origin staging
```

Использовать реальный URL созданного приватного репозитория. Код последующих изменений переносить в эту копию, проверять `git diff`, коммитить и отправлять в `staging`. Render следит только за этой веткой. Не добавлять файлы через `git add -f` и не копировать в неё приватный снимок.

## 3. Neon Free

1. Создать отдельный проект `bm-staging` в **AWS Frankfurt** на **Free**, с одной основной веткой. Это отдельная тестовая база, не рабочая база другого проекта.
2. В Connect скопировать **pooled PostgreSQL connection URI** с `sslmode=require`, без оболочки `psql`. Значение хранить в секретах как `DATABASE_URL`.
3. В Object Storage создать bucket **`bm-staging-media`** с доступом **`public_read`**. Здесь будут только фотографии, без JSON-снимков, SQLite, паролей или документов. Получить точный S3 endpoint выбранной ветки, регион и branch-scoped S3 credentials с доступом чтения/записи. В S3 Access Key ID используется `token_id`, в Secret — `s3_secret_access_key`, а не API token. [Создание bucket](https://neon.com/docs/storage/buckets), [S3 credentials](https://neon.com/docs/storage/authentication).
4. Сохранить `AWS_ENDPOINT_URL_S3`, `AWS_REGION=eu-central-1`, `AWS_STORAGE_BUCKET_NAME=bm-staging-media`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`. В коде включены path-style и SigV4; отправки ACL, которые Neon не поддерживает, нет. [Совместимость S3](https://neon.com/docs/storage/s3-compatibility).

Если Object Storage недоступен, проверить регион/проект по документации. Не заменять его временным диском Render и не включать платный тариф.

## 4. Render Free

1. Подключить GitHub, дать доступ только к новому приватному репозиторию.
2. New → Blueprint: выбрать репозиторий и ветку **staging**, файл `render.yaml`.
3. Проверить: один Web Service, Docker, Frankfurt, **plan: free**. Базы/диски/платные сервисы blueprint не создаёт.
4. В секретных переменных указать `DATABASE_URL`, `TELEGRAM_BOT_TOKEN` существующего `@bmmsev_bot` и пять AWS/S3 значений из пункта 3. Username уже задан в blueprint. Сохранить сгенерированный Render `DJANGO_SECRET_KEY`; он должен оставаться постоянным между деплоями. Секреты не отправлять в чат или GitHub.
5. Дождаться зелёных проверок GitHub Actions и первого deploy. При необходимости выполнить первый Manual Deploy. Скопировать фактический постоянный `https://ИМЯ-СЕРВИСА.onrender.com`.

`RENDER_EXTERNAL_HOSTNAME` задаётся платформой автоматически: из него получаются точный allowed host, доверенный CSRF origin и адрес Mini App. Никаких `*`/CORS `allow all` не требуется. Для собственного домена в будущем использовать `STAGING_ALLOWED_HOSTS` с точным списком доменов.

Сборка Docker не требует runtime-секретов. При старте выполняются `migrate` и Gunicorn (1 worker/2 threads). Миграции идемпотентны и не загружают товары повторно. Free не имеет dashboard shell/one-off jobs, поэтому разовый перенос выполняется с компьютера напрямую в Neon. [Render Free](https://render.com/docs/free), [Blueprint auto-deploy](https://render.com/docs/blueprint-spec#autodeploytrigger).

## 5. Разовый перенос данных и фотографий

В исходной папке уже есть отдельное окружение `.venv-staging` и проверенный приватный снимок **`.staging-transfer/20261118-release`**:

- 5358 товаров, 12 категорий, 5479 связей товар–категория;
- существующие витрины, рецепты, «О нас», сотрудники и хеши их паролей;
- все ID, включая промежуточные M2M-строки, и все 18 медиафайлов — 3 466 593 байта;
- исходные SQLite-резервные копии, контрольные суммы и локальная проверка восстановления.

В текущем источнике нет покупателей/заказов, но механизм переносит эти модели и их связи тоже. Активные Django-сессии и служебные admin logs не переносятся. Существующий Admin-пользователь переносится; **не создавать суперпользователя в Neon до импорта**.

`frontend/content.sqlite3` содержит две пустые таблицы старого режима и не подключена к текущему приложению. Она сохранена в приватном backup, но не подключается на staging. Если при новом экспорте в ней появятся записи, экспорт остановится с требованием явного переноса — молча отбрасывать их он не будет.

Если локальные данные уже изменились, получить новый снимок, предварительно остановив локальные записи в базу:

```powershell
Set-Location -LiteralPath 'C:\Users\Gor Sahakyan\Desktop\bolshoy-myasnoy'
& '.\.venv-staging\Scripts\python.exe' deploy/export_snapshot.py --output '.staging-transfer/НОВОЕ-ИМЯ'
& '.\.venv-staging\Scripts\python.exe' deploy/validate_snapshot.py '.staging-transfer/НОВОЕ-ИМЯ'
```

Экспорт открывает исходные SQLite read-only и сериализует только отдельную копию. Снимок содержит персональные данные/хеши паролей: не загружать его в GitHub или публичный bucket, хранить как приватную резервную копию.

Для переноса скопировать `.env.staging.example` в **`.env.staging` в исходной папке**, заполнить там те же секреты Neon/Render и фактический Render URL/`STAGING_ALLOWED_HOSTS`. Исходный `.env` не менять. Затем, после успешного старта Render:

```powershell
Set-Location -LiteralPath 'C:\Users\Gor Sahakyan\Desktop\bolshoy-myasnoy'
$Python = '.\.venv-staging\Scripts\python.exe'
$Snapshot = '.staging-transfer/20261118-release'
& $Python manage.py migrate --settings=config.settings_staging
& $Python manage.py upload_staging_media $Snapshot --dry-run --settings=config.settings_staging
& $Python manage.py upload_staging_media $Snapshot --settings=config.settings_staging
& $Python manage.py restore_staging_snapshot $Snapshot --settings=config.settings_staging
```

Дождаться успеха каждой команды, при ошибке остановиться. Загрузка фото сохраняет ключи/имена, проверяет байты, допускает безопасный повтор и отказывается заменять другое содержимое. Импорт БД работает только со staging PostgreSQL и **только при отсутствии данных/пользователей**, в транзакции. Сравниваются все экспортированные значения и связи, исправляются PostgreSQL sequences. При несовпадении данных импорт откатывается. Повторный deploy не запускает этот импорт.

Уже перенесённую/используемую базу повторно не заполнять: команда намеренно откажется. Перед будущими изменениями сохранять отдельные PostgreSQL backup и фотографии вне Render; исходный SQLite backup не включает последующих изменений в Neon. По желанию сменить пароль только staging-сотрудника через `manage.py changepassword --settings=config.settings_staging`.

## 6. Один раз обновить Telegram

В `.env.staging` указать фактический постоянный `MINIAPP_PUBLIC_URL` и токен существующего бота. Из исходной папки:

```powershell
& '.\.venv-staging\Scripts\python.exe' manage.py check_telegram_store --network --settings=config.settings_staging
& '.\.venv-staging\Scripts\python.exe' manage.py check_telegram_store --set-menu --settings=config.settings_staging
```

**Не добавлять `--url`**: адрес берётся из `.env.staging`, а исходный локальный `.env` остаётся прежним. Для меню не нужны чат заказов и HTTPS Admin. Если используется Main Mini App/кнопка в профиле бота/`?startapp`, один раз изменить Main App URL также в BotFather.

Проверить на настоящем телефоне: открыть из меню бота → профиль → закрыть/открыть снова. Имя/аватар при наличии должны прийти через серверную проверку `initData`; Telegram ID и `customer_id` сохраняются в Neon. В браузере остаётся гостевой режим. Пароль/SMS/телефон при входе не запрашиваются. Затем перезапустить Render и проверить сохранность профиля и новой фотографии, добавленной в Admin.

## 7. Контроль перед завершением

- `/healthz`, `/catalog`, `/about`, `/about/map`, `/ideas/dinner`, `/profile` открываются через HTTPS; статика и изображения загружаются.
- `/api/products/` показывает перенесённые товары/цены; витрины и рецепты связаны с прежними ID. В Admin доступны прежние категории, витрины и фотографии.
- `/api/session/`: из настоящего Telegram `authenticated: true`; в обычном браузере `false`; чужие заказы недоступны. Не публиковать `initData`/Authorization.
- После рестарта/деплоя данные и загруженные фото сохраняются. `.env`, SQLite, backup, `/src/`, `/media/` с локального диска не выдаются веб-сервером.
- Заказы и Telegram-уведомления **принудительно выключены в settings_staging**, даже при ошибочном env=1. Worker и оплата не подключены.

Проверено локально: **107 серверных тестов**, **44 frontend-теста**, TypeScript/build, `collectstatic`, security checks с `DEBUG=False`, байтовая проверка медиа, полный ID-сохраняющий round-trip снимка на изолированной SQLite. Исходные базы не изменены. Полный `check --deploy` по-прежнему сообщает `mail.E001`, потому что email-транспорт намеренно отключён; security-tag проходит без скрытых проверок.

**Ещё не проверено:** Docker/Gunicorn на Linux, запуск GitHub Actions/PostgreSQL-теста, подключение к настоящим Neon/PostgreSQL/S3, Render deploy и настоящий Telegram-вход на постоянном URL. Docker/PostgreSQL локально отсутствуют. CI уже содержит отдельную проверку переноса в настоящий тестовый PostgreSQL, PK/M2M sequences и сборку контейнера — они должны пройти после push перед автоматическим deploy.

## Подготовленные файлы

`Dockerfile`, `render.yaml`, `requirements-staging.txt`, `.dockerignore`, `.gitattributes`, `.github/workflows/staging.yml`; отдельные `config/settings_staging.py`, `settings_build.py`, `urls_staging.py`; `deploy/` для ассетов, защиты, проверки релиза и снимка; команды `upload_staging_media` и `restore_staging_snapshot`; пример `.env.staging.example`. Существующие React-компоненты, Telegram HMAC, модели товаров и локальные settings не переписаны.
