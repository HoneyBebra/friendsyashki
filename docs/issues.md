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

### 8. Утечка информации через JWTError

- **Файл:** `auth/src/dependencies/jwt.py`, строка 83
- **Категория:** Security (Information Disclosure)

```python
detail=str(e)  # раскрывает внутреннюю ошибку JWT-декодирования клиенту
```

**Импакт:** Помогает атакующему подбирать формат токена.

**Рекомендация:** Заменить на `detail="Invalid credentials"`.

---

### 10. Redis: protected-mode off, bind закомментирован

- **Файл:** `auth/infra/configs/redis/redis.conf`, строки 2-5, 133
- **Категория:** Config (Security Misconfiguration)

```
# bind 127.0.0.1 -::1
protected-mode no
```

Redis слушает на всех интерфейсах без защиты. Пароль `develop-password` закоммичен в git.

**Импакт:** При некорректной конфигурации сети Redis будет доступен извне с известным паролем.

**Рекомендация:** `protected-mode yes`, раскомментировать `bind`, не коммитить пароль.

---

### 11. Nginx gateway не проксирует WebSocket-заголовки

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

---

## Medium

### 12. Cookie без SameSite атрибута

- **Файл:** `auth/src/services/users.py`, строки 116-127
- **Категория:** Security (CSRF)

При установке cookie не указан параметр `samesite`, что может привести к CSRF-атакам.

**Рекомендация:** Добавить `samesite="Lax"` или `"Strict"`.

---

### 13. Утечка ресурсов в gRPC-сессиях (незакрытые DB/Redis сессии)

- **Файл:** `auth/src/gRPC/server.py`, строки 77-83
- **Категория:** Bug/Performance

`get_grpc_session()` получает сессии через `await anext()`, но генераторы никогда не закрываются (`aclose()` не вызывается). DB-сессия при ошибке не откатывается, Redis-соединение не закрывается.

**Импакт:** Утечка соединений, проблемы с транзакциями, нестабильность.

**Рекомендация:** Создавать новые сессии для каждого gRPC-запроса или корректно управлять жизненным циклом генераторов.

---

### 14. `datetime.utcnow` deprecated (Python 3.12+)

- **Файл:** `auth/src/models/base.py`, строки 7-8
- **Файл:** `messenger/src/models/base.py`, строки 7-8
- **Файл:** `messenger/src/models/dialog_participants.py`, строка 32
- **Категория:** Bug

`datetime.utcnow` deprecated. Кроме того, `updated_at` устанавливается только при создании и не обновляется при изменении записи (`onupdate` не задан).

**Рекомендация:** `datetime.now(timezone.utc)` + `onupdate=func.now()` для `updated_at`.

---

### 15. `order_by` принимает произвольную строку

- **Файл:** `auth/src/repositories/users.py`, строка 62
- **Категория:** Security (Potential SQL Injection)

`query.order_by(order_by)` принимает строку напрямую. Сейчас не экспонирован через API, но при развитии может стать вектором SQL injection.

**Рекомендация:** Использовать whitelist или атрибуты модели: `getattr(Users, order_by)`.

---

### 17. Timing attack при сравнении хешей PII

- **Файл:** `auth/src/utils/encryption.py`, строка 41
- **Категория:** Security

`verify_user_data` использует `==` для сравнения хешей вместо constant-time comparison.

**Рекомендация:** Использовать `hmac.compare_digest()`.

---

### 18. Hash PII без HMAC (уязвимость length extension attack)

- **Файл:** `auth/src/utils/encryption.py`, строки 34-37
- **Категория:** Security

`hash_user_data` использует `sha256(data + secret)` -- уязвимо к length extension attack.

**Рекомендация:** `hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()`.

---

### 19. Голый `except Exception` в обработчике сообщений

- **Файл:** `messenger/src/api/v1/messages.py`, строки 141-147
- **Категория:** Bug

Нарушает правило из CLAUDE.md: "Никогда не использовать голый `except Exception:`". Ошибка проглатывается, скрывая серьезные проблемы.

**Рекомендация:** Ловить конкретные исключения (`SQLAlchemyError` и т.п.).

---

### 20. Race condition в `set_delivered_if_sent`

- **Файл:** `messenger/src/repositories/messages.py`, строки 104-129
- **Категория:** Bug

Между проверкой `get_status` и вставкой/обновлением нет блокировки. При параллельных запросах возможны дубликаты в `message_statuses`.

**Рекомендация:** Использовать `INSERT ... ON CONFLICT` или `SELECT ... FOR UPDATE`.

---

### 21. Только HTTP, нет HTTPS на gateway

- **Файл:** `deploy/docker-compose.infra.yml`, строка 12
- **Файл:** `deploy/infra/configs/nginx_gateway/site.conf`, строка 2
- **Категория:** Security (Sensitive Data Exposure)

Gateway слушает только на порту 80. Cookies с access/refresh токенами передаются в открытом виде.

**Рекомендация:** Настроить TLS-терминацию на nginx для production.

---

### 22. Нет CORS-конфигурации в обоих сервисах

- **Файл:** `auth/src/main.py`
- **Файл:** `messenger/src/main.py`
- **Категория:** Security (Security Misconfiguration)

CORS middleware не настроен ни в auth, ни в messenger.

**Рекомендация:** Добавить `CORSMiddleware` с whitelist разрешённых origins.

---

## Low

### 23. `POSTGRES_ECHO=1` по умолчанию

- **Файл:** `auth/.env.example`, строка 8
- **Категория:** Config

SQL echo включён -- в production все SQL-запросы будут в логах, включая чувствительные данные.

**Рекомендация:** `POSTGRES_ECHO=0` по умолчанию.

---

### 24. `log_level="debug"` при прямом запуске

- **Файл:** `auth/src/main.py`, строка 49
- **Категория:** Config

Debug-уровень логирования может раскрывать чувствительную информацию.

**Рекомендация:** Использовать переменную окружения для уровня логирования.

---

### 25. Нет `max_length` на поле `password` в модели/схеме

- **Файл:** `auth/src/models/users.py`, строка 19
- **Категория:** Security (DoS)

Нет ограничения длины пароля -- очень длинный пароль вызовет долгое хеширование.

**Рекомендация:** Ограничить max_length пароля (например, 128 символов) в Pydantic-схеме.

---

### 26. gRPC `GetUserByLogin`/`GetUserById` без аутентификации

- **Файл:** `auth/src/gRPC/server.py`, строки 39-52
- **Категория:** Security

Любой сервис в сети может запрашивать информацию о пользователях без аутентификации.

**Рекомендация:** Добавить interceptor или mTLS для межсервисной авторизации.

---

### 27. Нет ограничения количества WebSocket-соединений на пользователя

- **Файл:** `messenger/src/ws/manager.py`, строки 17-25
- **Категория:** Security (DoS)

Один пользователь может открыть неограниченное число WS-соединений.

**Рекомендация:** Лимит (например, 5 соединений на пользователя).

---

### 28. Отсутствует `gunicorn.conf.py` для messenger

- **Файл:** `messenger/gunicorn.conf.py` -- не найден
- **Категория:** Config

В Dockerfile указан gunicorn, но конфигурация отсутствует. Используются дефолты (1 worker).

**Рекомендация:** Создать `gunicorn.conf.py` с настройками `workers`, `timeout`, `graceful_timeout`.

---

## Приоритетные действия

1. **Немедленно:** удалить `**/infra/volumes/` из git, добавить в `.gitignore`, очистить историю
2. **Немедленно:** убрать `COPY .env` из Dockerfile
3. **Немедленно:** ротировать все секреты (JWT, Redis, Postgres, encryption key)
4. **Высокий приоритет:** добавить rate limiting на `/login` и `/signup`
5. **Высокий приоритет:** исправить WebSocket accept до аутентификации
6. **Высокий приоритет:** добавить WebSocket-заголовки в nginx gateway
7. **Высокий приоритет:** перенести токен из URL в WS-сообщение
8. ~~**Средний приоритет:** настроить TLS для gRPC~~ ✅ и HTTPS для nginx
9. **Средний приоритет:** исправить утечки ресурсов в gRPC-сессиях
10. **Средний приоритет:** заменить `datetime.utcnow` на `datetime.now(timezone.utc)`
