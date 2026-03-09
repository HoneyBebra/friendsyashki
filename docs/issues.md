# Security Audit & Code Review: найденные проблемы

Дата аудита: 2026-03-07

---

## Critical

### 3. ~~`.env` копируется в Docker-образ~~ ✅ ИСПРАВЛЕНО (2026-03-07)

- **Файл:** `auth/Dockerfile`, строка 20 (`COPY .env src/.env`)
- **Категория:** Security (Sensitive Data Exposure)

Файл `.env` с секретами копируется прямо в слой Docker-образа. Секреты видны через `docker history` или `docker save`.

**Импакт:** Полная компрометация секретов через Docker registry или экспорт образа.

**Рекомендация:** Убрать `COPY .env`. Передавать секреты через `env_file` в `docker-compose.yml` (уже настроено) или через Docker secrets.

**Исправление:** Удалена строка `COPY .env src/.env` из `auth/Dockerfile`. Добавлены `.dockerignore` для `auth/` и `messenger/` с исключением `.env`, `.env.*`, `infra/volumes/`, `__pycache__`, `.git`.

---

## High

### 4. ~~gRPC без TLS (insecure port/channel)~~ ✅ ИСПРАВЛЕНО (2026-03-08)

- **Файл:** `auth/src/main.py`, строка 23 -- `server.add_insecure_port()`
- **Файл:** `messenger/src/gRPC/client.py`, строка 18 -- `grpc.aio.insecure_channel()`
- **Категория:** Security (Sensitive Data Exposure)

Межсервисное gRPC-соединение не зашифровано. Access-токены пользователей передаются в открытом виде между messenger и auth.

**Импакт:** Man-in-the-middle атака, перехват JWT-токенов.

**Рекомендация:** Использовать `secure_channel()` / `add_secure_port()` с TLS или mTLS. Как минимум убедиться, что gRPC-трафик не выходит за пределы внутренней Docker-сети.

**Исправление:** Реализовано TLS-шифрование для gRPC:
- Auth сервер: `add_insecure_port()` → `add_secure_port()` с `ssl_server_credentials` (server.pem + server.key + ca.pem)
- Messenger клиент: `insecure_channel()` → `secure_channel()` с `ssl_channel_credentials` (ca.pem)
- Скрипт генерации самоподписанных сертификатов: `deploy/certs/grpc/generate_certs.sh` (RSA 4096, SAN: DNS:auth, DNS:localhost, IP:127.0.0.1)
- Сертификаты монтируются в контейнеры через docker-compose volumes (read-only)
- Приватные ключи и сертификаты исключены из git через `.gitignore`
- Пути к сертификатам настраиваются через переменные окружения (`GRPC_TLS_CERT`, `GRPC_TLS_KEY`, `GRPC_TLS_CA`, `AUTH_GRPC_TLS_CA`)

---

### 5. ~~Access-токен передается в URL при WebSocket-подключении~~ ✅ ИСПРАВЛЕНО (2026-03-08)

- **Файл:** `web/index.html`, строка 256
- **Файл:** `messenger/src/ws/router.py`, строки 19-23
- **Категория:** Security (Sensitive Data Exposure)

```javascript
const url = proto + '//' + location.host + '/messenger/ws?access_token=' + encodeURIComponent(token);
```

Токен попадает в access-логи nginx, историю браузера, referer-заголовки.

**Импакт:** Утечка токенов через логи.

**Рекомендация:** Передавать токен через первое WebSocket-сообщение после подключения, а не через URL.

**Исправление:** Токен убран из URL. Теперь клиент подключается без параметров, а после установки WebSocket-соединения отправляет первое сообщение `{"token": "..."}`. Сервер ожидает это сообщение с таймаутом 5 секунд. Если токен не получен или невалиден — соединение закрывается.

---

### 6. ~~WebSocket accept() до аутентификации~~ ✅ ИСПРАВЛЕНО (2026-03-08)

- **Файл:** `messenger/src/ws/router.py`, строки 37-38
- **Категория:** Security (Broken Authentication)

```python
await websocket.accept()  # сначала accept
token = _get_token_from_scope(websocket.scope)  # потом проверка
```

Соединение принимается до проверки токена, позволяя неаутентифицированные WS-соединения.

**Импакт:** DoS через массовое открытие неаутентифицированных WS-соединений.

**Рекомендация:** Аутентифицировать до `accept()`. При невалидном токене возвращать HTTP 403.

**Исправление:** Аутентификация перенесена до `accept()`. Токен читается из cookie `access_token` через `websocket.cookies` (доступен в ASGI scope до принятия соединения). Если cookie отсутствует или токен невалиден — соединение закрывается без `accept()`. Веб-клиент обновлён: убрана отправка токена первым сообщением (cookie отправляется автоматически с WebSocket upgrade request).

---

### 7. ~~Отсутствие rate limiting на login/signup~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `auth/src/api/v1/users.py`, строки 34, 73
- **Категория:** Security (Broken Authentication)

Эндпоинты `/signup` и `/login` не имеют ограничений по частоте запросов. Нет rate limiting ни на FastAPI, ни на nginx.

**Импакт:** Brute-force атака на пароли, credential stuffing, массовое создание аккаунтов.

**Рекомендация:** Добавить rate limiting (`limit_req_zone` в nginx).

**Исправление:** Добавлен rate limiting через `limit_req_zone` в nginx на двух уровнях:
- **Gateway nginx** (`deploy/infra/configs/nginx_gateway/`): зоны `login_limit` (5 req/min, burst 3) и `signup_limit` (3 req/min, burst 2) по `$binary_remote_addr`. Отдельные `location =` для `/auth/api/v1/users/login` и `/auth/api/v1/users/signup` с `limit_req` и статусом 429.
- **Auth nginx** (`auth/infra/configs/nginx_auth/`): зоны `auth_login_limit` и `auth_signup_limit` по `$http_x_forwarded_for` (реальный IP клиента за прокси). Аналогичные `location =` блоки с `limit_req` и статусом 429.
- Режим `nodelay` — превышающие лимит запросы сразу получают 429 без задержки в очереди.

---

### 8. ~~Утечка информации через JWTError~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `auth/src/dependencies/jwt.py`, строка 83
- **Категория:** Security (Information Disclosure)

```python
detail=str(e)  # раскрывает внутреннюю ошибку JWT-декодирования клиенту
```

**Импакт:** Помогает атакующему подбирать формат токена.

**Рекомендация:** Заменить на `detail="Invalid credentials"`.

**Исправление:** Заменено `detail=str(e)` на `detail="Invalid credentials"` в обработчике `JWTError` в функции `__get_payload()`. Теперь при любой ошибке JWT-декодирования клиент получает общее сообщение без деталей внутренней ошибки.

---

### 10. ~~Redis: protected-mode off, bind закомментирован~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `auth/infra/configs/redis/redis.conf`, строки 2-5, 133
- **Категория:** Config (Security Misconfiguration)

```
# bind 127.0.0.1 -::1
protected-mode no
```

Redis слушает на всех интерфейсах без защиты. Пароль `develop-password` закоммичен в git.

**Импакт:** При некорректной конфигурации сети Redis будет доступен извне с известным паролем.

**Рекомендация:** `protected-mode yes`, раскомментировать `bind`, не коммитить пароль.

**Исправление:** Установлен `protected-mode yes`, раскомментирован `bind 0.0.0.0` (в Docker-сети Redis должен быть доступен другим контейнерам). Пароль Redis удалён из `redis.conf` и теперь передаётся через переменную окружения `REDIS_PASSWORD` из `.env` файла в `docker-compose.yml` через аргумент командной строки `--requirepass`.

---

### 11. ~~Nginx gateway не проксирует WebSocket-заголовки~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `deploy/infra/configs/nginx_gateway/site.conf`, строки 11-13
- **Категория:** Bug/Config

```nginx
location /messenger/ {
    proxy_pass http://nginx_messenger;
}
```

Нет заголовков `Upgrade` и `Connection` -- WebSocket через gateway не работает.

**Импакт:** WebSocket-функционал полностью неработоспособен через gateway.

**Рекомендация:** Добавить отдельный location:
```nginx
location /messenger/ws {
    proxy_pass http://nginx_messenger;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

**Исправление:** Добавлен отдельный `location /messenger/ws` перед общим `location /messenger/` в конфиге nginx gateway. Новый location включает `proxy_http_version 1.1`, заголовки `Upgrade` и `Connection "upgrade"` для корректного проксирования WebSocket-соединений.

---

## Medium

### 12. ~~Cookie без SameSite атрибута~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `auth/src/services/users.py`, строки 116-127
- **Категория:** Security (CSRF)

При установке cookie не указан параметр `samesite`, что может привести к CSRF-атакам.

**Рекомендация:** Добавить `samesite="Lax"` или `"Strict"`.

**Исправление:** Добавлен параметр `samesite="lax"` к обоим вызовам `response.set_cookie()` (access_token и refresh_token) в методе `add_tokens_to_response`. Это предотвращает отправку cookies при cross-site запросах, защищая от CSRF-атак.

---

### 13. ~~Утечка ресурсов в gRPC-сессиях (незакрытые DB/Redis сессии)~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `auth/src/gRPC/server.py`, строки 77-83
- **Категория:** Bug/Performance

`get_grpc_session()` получает сессии через `await anext()`, но генераторы никогда не закрываются (`aclose()` не вызывается). DB-сессия при ошибке не откатывается, Redis-соединение не закрывается.

**Импакт:** Утечка соединений, проблемы с транзакциями, нестабильность.

**Рекомендация:** Создавать новые сессии для каждого gRPC-запроса или корректно управлять жизненным циклом генераторов.

**Исправление:** Полностью переработано управление сессиями в gRPC-сервере:
- Создан async context manager `_create_user_service()`, который открывает DB и Redis сессии через генераторы и гарантирует их корректное закрытие через `aclose()` в блоке `finally`.
- Каждый gRPC-метод (`GetUserInfoByToken`, `GetUserByLogin`, `GetUserById`) теперь создаёт собственные сессии через `async with _create_user_service()`, которые автоматически закрываются после обработки запроса.
- При ошибке DB-сессия корректно откатывается (через логику `get_session()` генератора), Redis-соединение закрывается.
- `GrpcServer` больше не хранит `user_service` в конструкторе — устранена проблема использования одной долгоживущей сессии для всех запросов.
- Функция `get_grpc_session()` заменена на `create_grpc_server()` — простая синхронная функция без управления сессиями.

---

### 14. ~~`datetime.utcnow` deprecated (Python 3.12+)~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `auth/src/models/base.py`, строки 7-8
- **Файл:** `messenger/src/models/base.py`, строки 7-8
- **Файл:** `messenger/src/models/dialog_participants.py`, строка 32
- **Категория:** Bug

`datetime.utcnow` deprecated. Кроме того, `updated_at` устанавливается только при создании и не обновляется при изменении записи (`onupdate` не задан).

**Рекомендация:** `datetime.now(timezone.utc)` + `onupdate=func.now()` для `updated_at`.

**Исправление:** Заменено `datetime.utcnow` на `lambda: datetime.now(timezone.utc)` во всех моделях (`auth/src/models/base.py`, `messenger/src/models/base.py`, `messenger/src/models/dialog_participants.py`). Добавлен `onupdate=func.now()` для поля `updated_at` в базовых моделях обоих сервисов, чтобы значение обновлялось автоматически при изменении записи.

---

### 15. ~~`order_by` принимает произвольную строку~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `auth/src/repositories/users.py`, строка 62
- **Категория:** Security (Potential SQL Injection)

`query.order_by(order_by)` принимает строку напрямую. Сейчас не экспонирован через API, но при развитии может стать вектором SQL injection.

**Рекомендация:** Использовать whitelist или атрибуты модели: `getattr(Users, order_by)`.

**Исправление:** Добавлена валидация параметра `order_by` через `hasattr(Users, order_by)`. Если переданное имя поля не существует в модели `Users`, выбрасывается `ValueError` с перечислением допустимых полей. Вместо передачи строки напрямую в `query.order_by()` теперь используется `getattr(Users, order_by)`, что возвращает атрибут модели SQLAlchemy и исключает возможность SQL injection.

---

### 17. ~~Timing attack при сравнении хешей PII~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `auth/src/utils/encryption.py`, строка 41
- **Категория:** Security

`verify_user_data` использует `==` для сравнения хешей вместо constant-time comparison.

**Рекомендация:** Использовать `hmac.compare_digest()`.

**Исправление:** Заменено сравнение `==` на `hmac.compare_digest()` в функции `verify_user_data`. Добавлен `import hmac`. Это предотвращает timing attack, при котором атакующий может по времени ответа определить количество совпадающих символов хеша.

---

### 18. ~~Hash PII без HMAC (уязвимость length extension attack)~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `auth/src/utils/encryption.py`, строки 34-37
- **Категория:** Security

`hash_user_data` использует `sha256(data + secret)` -- уязвимо к length extension attack.

**Рекомендация:** `hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()`.

**Исправление:** Заменено `hashlib.sha256(data + secret)` на `hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()`. HMAC использует внутреннюю конструкцию с двойным хешированием (HMAC-SHA256), которая не подвержена length extension attack. Функция `verify_user_data` (исправленная в задаче #17) вызывает `hash_user_data`, поэтому автоматически использует новый формат хешей.

---

### 19. ~~Голый `except Exception` в обработчике сообщений~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `messenger/src/api/v1/messages.py`, строки 141-147
- **Категория:** Bug

Нарушает правило из CLAUDE.md: "Никогда не использовать голый `except Exception:`". Ошибка проглатывается, скрывая серьезные проблемы.

**Рекомендация:** Ловить конкретные исключения (`SQLAlchemyError` и т.п.).

**Исправление:** Заменён голый `except Exception` на конкретные исключения `(OSError, SQLAlchemyError)` с привязкой объекта исключения (`as e`). Ошибки логируются через `logger.warning` с указанием `message_id` и `user_id` для диагностики. `OSError` покрывает сетевые ошибки при работе с БД, `SQLAlchemyError` — все ошибки SQLAlchemy.

---

### 20. ~~Race condition в `set_delivered_if_sent`~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `messenger/src/repositories/messages.py`, строки 104-129
- **Категория:** Bug

Между проверкой `get_status` и вставкой/обновлением нет блокировки. При параллельных запросах возможны дубликаты в `message_statuses`.

**Рекомендация:** Использовать `INSERT ... ON CONFLICT` или `SELECT ... FOR UPDATE`.

**Исправление:** Добавлен `UniqueConstraint("message_id", "user_id")` на таблицу `message_statuses` (миграция 002). Метод `set_delivered_if_sent` переписан с использованием атомарного `INSERT ... ON CONFLICT DO UPDATE`: при отсутствии записи вставляется статус `DELIVERED`, при конфликте обновляется только если текущий статус `SENT`. Это полностью устраняет race condition и исключает дубликаты.

---

### 21. ~~Только HTTP, нет HTTPS на gateway~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `deploy/docker-compose.infra.yml`, строка 12
- **Файл:** `deploy/infra/configs/nginx_gateway/site.conf`, строка 2
- **Категория:** Security (Sensitive Data Exposure)

Gateway слушает только на порту 80. Cookies с access/refresh токенами передаются в открытом виде.

**Рекомендация:** Настроить TLS-терминацию на nginx для production.

**Исправление:** Настроена TLS-терминация на nginx gateway:
- Добавлен HTTPS server block на порту 443 с SSL (TLSv1.2/TLSv1.3, HIGH ciphers, session cache)
- HTTP (порт 80) теперь выполняет 301 redirect на HTTPS
- Скрипт генерации самоподписанных сертификатов: `deploy/certs/gateway/generate_certs.sh` (RSA 4096, SAN: DNS:nginx_gateway, DNS:localhost, IP:127.0.0.1)
- Сертификаты монтируются в контейнер через docker-compose volumes (read-only)
- Приватные ключи и сертификаты исключены из git через `.gitignore`
- В `docker-compose.infra.yml` добавлен порт 443 и volumes для сертификатов

---

### 22. ~~Нет CORS-конфигурации в обоих сервисах~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `auth/src/main.py`
- **Файл:** `messenger/src/main.py`
- **Категория:** Security (Security Misconfiguration)

CORS middleware не настроен ни в auth, ни в messenger.

**Рекомендация:** Добавить `CORSMiddleware` с whitelist разрешённых origins.

**Исправление:** Добавлен `CORSMiddleware` из FastAPI в оба сервиса (auth и messenger):
- `allow_origins` настраивается через переменную окружения `CORS_ORIGINS` (тип `list[str]`, по умолчанию пустой список — ни один origin не разрешён)
- `allow_credentials=True` для поддержки cookies (access/refresh токены)
- `allow_methods` ограничены стандартными HTTP-методами (GET, POST, PUT, PATCH, DELETE, OPTIONS)
- `allow_headers` ограничены `Content-Type` и `Authorization`
- Настройка `cors_origins` добавлена в `Settings` обоих сервисов и в `.env.example`

---

## Low

### 23. ~~`POSTGRES_ECHO=1` по умолчанию~~ (Исправлено)

- **Файл:** `auth/.env.example`, строка 8; `auth/src/core/config.py`, строка 30
- **Категория:** Config

~~SQL echo включён -- в production все SQL-запросы будут в логах, включая чувствительные данные.~~

**Решение:** `POSTGRES_ECHO=0` по умолчанию в `.env.example`, `postgres_echo: bool = False` в конфиге auth-сервиса.

---

### 24. ~~`log_level="debug"` при прямом запуске~~ ✅ ИСПРАВЛЕНО (2026-03-09)

- **Файл:** `auth/src/main.py`, строка 49
- **Файл:** `messenger/src/main.py`, строка 31
- **Категория:** Config

Debug-уровень логирования может раскрывать чувствительную информацию.

**Рекомендация:** Использовать переменную окружения для уровня логирования.

**Исправление:** Хардкоженный `log_level="debug"` заменён на `settings.log_level` в обоих сервисах (auth и messenger). Добавлена настройка `log_level: str = "info"` в `Settings` обоих сервисов с дефолтным значением `"info"`. Переменная окружения `LOG_LEVEL` добавлена в `.env.example` обоих сервисов.

---

### 25. ~~Нет `max_length` на поле `password` в модели/схеме~~ (Исправлено)

- **Файл:** `auth/src/models/users.py`, строка 19
- **Категория:** Security (DoS)

Нет ограничения длины пароля -- очень длинный пароль вызовет долгое хеширование.

**Рекомендация:** Ограничить max_length пароля (например, 128 символов) в Pydantic-схеме.

**Исправление:** Добавлены ограничения `min_length=8, max_length=128` на поля `password` и `confirm_password` в Pydantic-схемах `UserEntersDataBaseSchema` и `UserRegisterSchema` (`auth/src/schemas/v1/users.py`). Это предотвращает DoS-атаку через отправку сверхдлинных паролей, которые блокируют CPU при bcrypt-хешировании.

---

### 26. ~~gRPC `GetUserByLogin`/`GetUserById` без аутентификации~~ (Исправлено)

- **Файл:** `auth/src/gRPC/server.py`, строки 39-52
- **Категория:** Security

Любой сервис в сети может запрашивать информацию о пользователях без аутентификации.

**Рекомендация:** Добавить interceptor или mTLS для межсервисной авторизации.

**Исправление:** Включена взаимная аутентификация (mTLS) — сервер auth требует клиентский сертификат (`require_client_auth=True`), клиент messenger предоставляет свой сертификат при подключении. Скрипт генерации сертификатов обновлён для создания клиентского сертификата.

---

### 27. ~~Нет ограничения количества WebSocket-соединений на пользователя~~ (Исправлено)

- **Файл:** `messenger/src/ws/manager.py`, строки 17-25
- **Категория:** Security (DoS)

Один пользователь может открыть неограниченное число WS-соединений.

**Рекомендация:** Лимит (например, 5 соединений на пользователя).

**Исправление:** Добавлен лимит одновременных WebSocket-соединений на пользователя (по умолчанию 5, настраивается через `max_ws_connections_per_user` в конфигурации). При превышении лимита самые старые соединения закрываются с кодом 4008.

---

### 28. Отсутствует `gunicorn.conf.py` для messenger

- **Файл:** `messenger/gunicorn.conf.py` -- не найден
- **Категория:** Config

В Dockerfile указан gunicorn, но конфигурация отсутствует. Используются дефолты (1 worker).

**Рекомендация:** Создать `gunicorn.conf.py` с настройками `workers`, `timeout`, `graceful_timeout`.

**Исправление:** Создан `messenger/gunicorn.conf.py` с настройками `workers` (cpu_count * 2 + 1), `worker_class` (UvicornWorker), `timeout` (120s), `graceful_timeout` (30s), `keepalive` (5s) и логирования. Dockerfile обновлён для копирования конфига и использования его через `-c gunicorn.conf.py`.

---

## Приоритетные действия

1. **Немедленно:** удалить `**/infra/volumes/` из git, добавить в `.gitignore`, очистить историю
2. **Немедленно:** убрать `COPY .env` из Dockerfile
3. **Немедленно:** ротировать все секреты (JWT, Redis, Postgres, encryption key)
4. **Высокий приоритет:** добавить rate limiting на `/login` и `/signup`
5. **Высокий приоритет:** исправить WebSocket accept до аутентификации
6. ~~**Высокий приоритет:** добавить WebSocket-заголовки в nginx gateway~~ ✅
7. **Высокий приоритет:** перенести токен из URL в WS-сообщение
8. ~~**Средний приоритет:** настроить TLS для gRPC~~ ✅ ~~и HTTPS для nginx~~ ✅
9. ~~**Средний приоритет:** исправить утечки ресурсов в gRPC-сессиях~~ ✅
10. ~~**Средний приоритет:** заменить `datetime.utcnow` на `datetime.now(timezone.utc)`~~ ✅
