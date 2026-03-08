# Codebase Documentation — Friendsyashki

Монорепозиторий мессенджера (аналог Telegram). MVP: текстовые 1:1 диалоги в реальном времени.

---

## Содержание

1. [Обзор архитектуры](#1-обзор-архитектуры)
2. [Быстрый старт](#2-быстрый-старт)
3. [Структура репозитория](#3-структура-репозитория)
4. [Сервис `auth`](#4-сервис-auth)
   - [Переменные окружения](#41-переменные-окружения)
   - [Точка входа](#42-точка-входа)
   - [API](#43-api)
   - [Слои приложения](#44-слои-приложения)
   - [gRPC](#45-grpc)
   - [База данных](#46-база-данных)
   - [Миграции](#47-миграции)
   - [Безопасность](#48-безопасность)
5. [Сервис `messenger`](#5-сервис-messenger-запланирован)
6. [Инфраструктура](#6-инфраструктура)
7. [Паттерны и конвенции](#7-паттерны-и-конвенции)
8. [Разработка и тестирование](#8-разработка-и-тестирование)
9. [Добавление нового функционала](#9-добавление-нового-функционала)
10. [Бэклог и тикеты](#10-бэклог-и-тикеты)

---

## 1. Обзор архитектуры

```
                      ┌─────────────────────────────────┐
                      │         Nginx Gateway            │
                      │  /auth/*   →  auth:8000          │
                      │  /messenger/* → messenger:8000   │
                      └────────────┬────────────────────┘
                                   │
               ┌───────────────────┴───────────────────┐
               │                                       │
        ┌──────▼──────┐                       ┌────────▼────────┐
        │  auth svc   │  gRPC :50051          │ messenger svc   │
        │  FastAPI    │◄──────────────────────│  FastAPI + WS   │
        │  REST + gRPC│                       │  Kafka consumer │
        └──────┬──────┘                       └────────┬────────┘
               │                                       │
        ┌──────▼──────┐                       ┌────────▼────────┐
        │  PostgreSQL │                       │  PostgreSQL     │
        │  Redis      │                       │  Redis          │
        └─────────────┘                       │  Kafka          │
                                              └─────────────────┘
```

**Текущее состояние:**
- `auth` — полностью реализован
- `messenger` — БД + модели + репозитории + auth dependency + dialogs + messages endpoints (TASK-001 ✅, TASK-002 ✅, TASK-003 ✅, TASK-004 ✅, TASK-005 ✅, TASK-006 ✅, TASK-007 ✅), в разработке (TASK-008..011)
- `web` — минимальный веб-клиент для ручного тестирования (TASK-UI-001 ✅)

---

## 2. Быстрый старт

### Запуск только `auth` (для разработки)

```bash
cd auth
cp .env.example .env  # заполнить переменные
docker compose up -d
```

Сервис будет доступен на `http://localhost/auth/api/v1/openapi`.

### Запуск всего стека

```bash
cd deploy
docker compose up -d
```

### Установка dev-зависимостей

```bash
pip install -r requirements-dev.txt
pre-commit install
```

---

## 3. Структура репозитория

```
friendsyashki/
├── PRD.md                        # Продуктовые требования
├── tickets.md                    # Задачи MVP
├── codebase-documentation.md     # Этот файл
├── ruff.toml                     # Единый линтер (line-length=100)
├── setup.cfg                     # mypy (python 3.12, strict)
├── requirements-dev.txt          # Dev-зависимости
│
├── auth/                         # Сервис аутентификации ✅ реализован
├── messenger/                    # Сервис мессенджера (v0.1.6) ✅
├── web/                          # Минимальный веб-клиент ✅ (TASK-UI-001)
└── deploy/                       # Единый docker-compose для всего стека
```

Каждый сервис самодостаточен: имеет свой `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `alembic.ini`, `migration/`.

---

## 4. Сервис `auth`

### 4.1 Переменные окружения

Файл: `auth/.env` (читается через `pydantic-settings`)

| Переменная | Описание |
|---|---|
| `POSTGRES_USER` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |
| `POSTGRES_DB` | Имя базы данных |
| `POSTGRES_HOST` | Хост PostgreSQL |
| `POSTGRES_PORT` | Порт PostgreSQL |
| `POSTGRES_ECHO` | Логировать SQL-запросы (bool) |
| `APP_NAME` | Название приложения (для OpenAPI) |
| `APP_DESCRIPTION` | Описание приложения |
| `APP_VERSION` | Версия приложения |
| `JWT_SECRET_KEY` | Секрет для подписи JWT |
| `JWT_ALGORITHM` | Алгоритм JWT (например, `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | TTL access-токена (мин., default: 30) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | TTL refresh-токена (дни, default: 7) |
| `REDIS_HOST` | Хост Redis |
| `REDIS_PORT` | Порт Redis |
| `REDIS_DB` | Номер БД Redis |
| `REDIS_PASSWORD` | Пароль Redis |
| `ENCRYPTION_USER_DATA_SECRET_KEY` | Ключ Fernet для шифрования PII |
| `GRPC_PORT` | Порт gRPC сервера (default: 50051) |
| `GRPC_TLS_CERT` | Путь к TLS-сертификату gRPC сервера |
| `GRPC_TLS_KEY` | Путь к приватному ключу gRPC сервера |
| `GRPC_TLS_CA` | Путь к CA-сертификату для gRPC |
| `BACKOFF_RETRIES_COUNT` | Кол-во попыток reconnect (default: 10) |
| `COOKIE_SECURE` | Флаг Secure для cookie (bool, default: `true`) |

### 4.2 Точка входа

`auth/src/main.py` — создаёт FastAPI-приложение и запускает gRPC-сервер в `lifespan`.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    server = grpc.aio.server()
    user_pb2_grpc.add_UserServicer_to_server(await get_grpc_session(), server)
    credentials = _load_grpc_server_credentials()  # TLS: server.pem + server.key + ca.pem
    server.add_secure_port(f"[::]:{settings.grpc_port}", credentials)
    await server.start()
    yield
    await server.stop()
```

- FastAPI и gRPC-сервер запускаются **одновременно** в одном процессе
- gRPC-сервер использует TLS (самоподписанные сертификаты, генерируются `deploy/certs/grpc/generate_certs.sh`)
- Документация OpenAPI: `GET /auth/api/v1/openapi`
- Default response class: `ORJSONResponse` (быстрее стандартного JSON)

### 4.3 API

Префикс: `/auth/api/v1`

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/users/signup` | Регистрация нового пользователя |
| `POST` | `/users/login` | Аутентификация, выдача токенов |
| `GET` | `/users/me` | Данные текущего пользователя (требует access-токен) |
| `POST` | `/users/refresh` | Обновление access-токена (требует refresh-токен) |
| `POST` | `/users/logout` | Выход (токены добавляются в blacklist) |

**Важно:** Все токены передаются исключительно через **`HttpOnly`-куки** (не в заголовках). Это защищает от XSS-атак.

Имена кук:
- `access_token` — короткоживущий токен (30 мин.)
- `refresh_token` — долгоживущий токен (7 дней)

### 4.4 Слои приложения

Зависимость между слоями строго однонаправлена: `api → dependencies → services → repositories → models/db`.

#### `api/v1/users.py`
FastAPI-роутер. Принимает HTTP-запросы, вызывает сервис, устанавливает/удаляет куки.

#### `services/users.py`
Бизнес-логика. Методы:
- `create(schema)` — хеширует пароль, шифрует PII, сохраняет пользователя
- `authenticate(schema)` — верифицирует пароль, возвращает пользователя или выбрасывает `InvalidCredentials`
- `add_tokens_to_response(response, user_id, login=None)` — генерирует пару токенов (с полем `login` в payload при наличии) и записывает в куки
- `add_token_to_blacklist(token_data, raw_token)` — помещает токен в Redis blacklist

#### `repositories/users.py`
SQLAlchemy async CRUD. Все методы обёрнуты `@retry` (tenacity) для устойчивости к сбоям БД.

```python
# Чтение по фильтрам
async def read(self, session, login=None, phone_number_hash=None, email_hash=None) -> User | None
```

#### `repositories/jwt_token.py`
Redis-репозиторий для blacklist токенов.

```python
async def set_token_to_blacklist(session, token, expire_seconds) -> None  # SETEX
async def is_token_in_blacklist(session, token) -> bool                   # EXISTS
```

#### `repositories/base/`
Абстрактные базовые классы (ABC) с абстрактными методами. Конкретные реализации рядом в `repositories/`.

#### `schemas/v1/`
Pydantic v2 схемы:

| Схема | Описание |
|---|---|
| `UserRegisterSchema` | Регистрация: `login`, `password`, `confirm_password`, `phone_number`, `email` |
| `UserLoginSchema` | Вход: `login`, `password` |
| `ResponseUserData` | Ответ: `id`, `login` |
| `UserJwtSchema` | Payload JWT: `sub`, `iat`, `exp`, `type` |

Валидация пароля (`schemas/v1/base.py`): минимум 8 символов, заглавная буква, строчная буква, цифра, спецсимвол.

#### `models/users.py`
SQLAlchemy-модель таблицы `users`:

| Колонка | Тип | Описание |
|---|---|---|
| `id` | UUID | Primary key |
| `login` | str | Уникальный логин, индексирован |
| `password` | str | Хеш пароля (pbkdf2_sha256) |
| `encrypted_phone_number` | str | Зашифрованный номер телефона (Fernet) |
| `phone_number_hash` | str | SHA-256 хеш номера (для поиска) |
| `encrypted_email` | str | Зашифрованный email (Fernet) |
| `email_hash` | str | SHA-256 хеш email (для поиска) |

#### `dependencies/jwt.py`
FastAPI Depends-зависимости для защищённых эндпоинтов:
- `get_access_token_data` — читает `access_token` из куки, проверяет blacklist, декодирует JWT
- `get_refresh_token_data` — аналогично для `refresh_token`

Оба возвращают `tuple[UserJwtSchema, str]` — (данные токена, сырой токен).

### 4.5 gRPC

**Сервер** в `auth/src/gRPC/server.py`. Используется другими сервисами для валидации токенов без прямого доступа к auth-БД.

Proto-контракт (`auth/src/gRPC/protos/user.proto`):

```protobuf
service User {
  rpc GetUserInfoByToken (GetUserInfoByTokenRequest) returns (GetUserInfoByTokenResponse);
  rpc GetUserByLogin (GetUserByLoginRequest) returns (GetUserByLoginResponse);
  rpc GetUserById (GetUserByIdRequest) returns (GetUserByIdResponse);
}

message GetUserInfoByTokenRequest  { string access_token = 1; }
message GetUserInfoByTokenResponse { string id = 1; string login = 2; }
message GetUserByLoginRequest      { string login = 1; }
message GetUserByLoginResponse     { string id = 1; string login = 2; }
message GetUserByIdRequest         { string id = 1; }
message GetUserByIdResponse        { string id = 1; string login = 2; }
```

Методы:
- `GetUserInfoByToken` — валидация access token, возвращает `id` и `login`. Используется в auth dependency.
- `GetUserByLogin` — поиск пользователя по логину, возвращает `id` и `login`. Используется при создании диалога (TASK-004). Возвращает `NOT_FOUND` если пользователь не найден.
- `GetUserById` — поиск пользователя по `id`, возвращает `id` и `login`. Используется в messenger для отображения логинов в участниках диалогов и в сообщениях вместо UUID.

### 4.6 База данных

#### PostgreSQL (`db/postgres.py`)

```python
engine = create_async_engine(
    settings.postgres_dsn,
    echo=settings.postgres_echo,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={"keepalives": 1, ...}
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

Dependency `get_session()` — async generator с автоматическим rollback при ошибке.

#### Redis (`db/redis.py`)

Dependency `get_redis_session()` — async generator, `Redis` как context manager.

Настроен `ExponentialBackoff` для retry при `ConnectionError` / `TimeoutError`.

### 4.7 Миграции

Файлы в `auth/migration/versions/`. История:

| Ревизия | Описание |
|---|---|
| `initial_revision` | Первичная структура |
| `added_users` | Добавлена таблица users |
| `deleted_tg_fields` | Удалены поля Telegram |
| `added_hashed_fields` | Добавлены хеш-поля email/phone |
| `added_unique_mark` | Уникальные ограничения |
| `added_login_index` | Индекс на `login` |

Команды:

```bash
# Применить миграции
docker compose exec auth alembic upgrade head

# Создать новую миграцию
docker compose exec auth alembic revision --autogenerate -m "description"

# Откатить последнюю
docker compose exec auth alembic downgrade -1
```

### 4.8 Безопасность

#### Хранение паролей
`utils/encryption.py` использует `passlib` (pbkdf2_sha256):

```python
hash_password(password: str) -> str
verify_password(plain: str, hashed: str) -> bool
```

#### Шифрование PII (номер телефона, email)
Двойной подход:
- **Хеш** (SHA-256 + соль) — для поиска по полю без расшифровки
- **Зашифрованное значение** (Fernet, симметричное) — для отображения пользователю

```python
hash_user_data(data: str) -> str      # SHA-256 + секретный ключ
encrypt_data(data: str) -> str        # Fernet encrypt
decrypt_data(data: str) -> str        # Fernet decrypt
```

#### JWT
`utils/jwt.py`: создание токенов через `python-jose`. Payload содержит `sub` (user_id), `iat`, `exp`, `type` (`"access"` или `"refresh"`).

#### Token Blacklist
При logout оба токена помещаются в Redis с TTL = оставшееся время жизни токена. `get_access_token_data` проверяет blacklist при каждом запросе.

---

## 5. Сервис `messenger` (v0.1.6)

### 5.0 Текущее состояние (v0.1.6)

- FastAPI-приложение с health endpoint (`GET /messenger/api/v1/health` → `200 {"status": "ok"}`)
- Конфигурация через `pydantic-settings` из `.env` (включая postgres_*, auth_grpc_*)
- Docker-интеграция: `Dockerfile` + `docker-compose.yml` (messenger + postgres_messenger + nginx_messenger)
- Интегрирован в `deploy/docker-compose.yml` и nginx gateway
- PostgreSQL: async engine (`asyncpg`), session factory, `get_session` dependency
- Alembic: миграции в `migration/versions/`, async env.py
- 4 таблицы: `dialogs`, `dialog_participants`, `messages`, `message_statuses`
- Репозитории: `DialogsRepository`, `MessagesRepository` (абстрактные + конкретные)
- gRPC-клиент к auth (`GetUserInfoByToken`, `GetUserByLogin`, `GetUserById`) + FastAPI dependency `get_current_user_id`; резолв логина по user_id через `get_login_by_user_id`
- `POST /dialogs/direct` — создание/получение 1:1 диалога (слои: schemas → service → repository)
- `GET /dialogs` — список диалогов текущего пользователя, отсортированных по `updated_at` DESC
- `POST /dialogs/{dialog_id}/messages` — отправка текстового сообщения с идемпотентностью по `client_message_id` и проверкой участия в диалоге; после сохранения рассылается событие `new_message` по WebSocket участникам диалога; для участников с активным WS проставляется статус `delivered` (TASK-009, v0.1.8)
- `GET /dialogs/{dialog_id}/messages` — история сообщений с пагинацией (limit 1-100, offset 0-10000), доступ только участникам диалога, порядок по `created_at ASC`
- WebSocket: endpoint `GET /messenger/ws` (v0.1.7), аутентификация по query `access_token` или cookie `access_token`, хранение соединений по `user_id` в `ConnectionManager`; при новом сообщении рассылка `{"event": "new_message", "payload": MessageResponse}` всем подключённым участникам диалога; статус `delivered` проставляется только участникам диалога с активным WS
- Тесты: `pytest` + `httpx` + `testcontainers` (health, миграции, CRUD, auth dependency, dialogs, messages, message history, WebSocket: new_message, reconnect, delivered при активном WS, статусы не для неучастников)

### 5.1 Переменные окружения

Файл: `messenger/.env` (читается через `pydantic-settings`)

| Переменная | Описание |
|---|---|
| `APP_NAME` | Название приложения |
| `APP_DESCRIPTION` | Описание приложения |
| `APP_VERSION` | Версия приложения |
| `API_V1_PREFIX` | Префикс API (default: `/messenger/api/v1`) |
| `POSTGRES_USER` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |
| `POSTGRES_DB` | Имя базы данных |
| `POSTGRES_HOST` | Хост PostgreSQL |
| `POSTGRES_PORT` | Порт PostgreSQL |
| `POSTGRES_ECHO` | Логировать SQL-запросы (bool, default: false) |
| `AUTH_GRPC_HOST` | Хост gRPC-сервера auth (default: `auth`) |
| `AUTH_GRPC_PORT` | Порт gRPC-сервера auth (default: `50051`) |
| `AUTH_GRPC_TLS_CA` | Путь к CA-сертификату для TLS-подключения к auth gRPC |

### 5.2 Идентификация пользователя (gRPC-клиент к auth)

Messenger валидирует access token пользователя через gRPC-вызов к auth-сервису.

**gRPC-клиент** (`src/gRPC/client.py`):
- TLS-канал открывается в lifespan приложения (`open_auth_grpc_channel`, `secure_channel` с CA cert) и закрывается при shutdown
- `get_user_id_by_token(access_token) -> UUID` — вызывает `UserStub.GetUserInfoByToken`
- `get_user_id_by_login(login) -> UUID` — вызывает `UserStub.GetUserByLogin` (TASK-004)
- `get_login_by_user_id(user_id) -> str` — вызывает `UserStub.GetUserById`, возвращает логин для отображения в API (диалоги, сообщения)

**FastAPI dependency** (`src/dependencies/auth.py`):
- `get_current_user_id(access_token: Cookie) -> UUID`
- Читает `access_token` из cookie, вызывает gRPC, возвращает UUID пользователя
- `PERMISSION_DENIED` → HTTP 403, `UNAVAILABLE/DEADLINE_EXCEEDED/INTERNAL` → HTTP 503

Использование в endpoint:

```python
from src.dependencies.auth import get_current_user_id

@router.get("/protected")
async def protected(user_id: UUID = Depends(get_current_user_id)):
    ...
```

### 5.3 База данных

#### PostgreSQL (`db/postgres.py`)

Аналогично auth: `create_async_engine` с `pool_pre_ping`, `pool_recycle=3600`, TCP keepalive.
Dependency `get_session()` — async generator с rollback при ошибке.
Engine dispose в lifespan при shutdown.

#### Модели

| Таблица | Модель | Описание |
|---|---|---|
| `dialogs` | `Dialog` | `id` (UUID PK), `type` (enum: direct/group), `title`, `created_at`, `updated_at` |
| `dialog_participants` | `DialogParticipant` | `id` (UUID PK), `dialog_id` (FK), `user_id`, `joined_at`, `created_at`, `updated_at` |
| `messages` | `Message` | `id` (UUID PK), `dialog_id` (FK), `sender_id`, `text`, `client_message_id` (unique), `created_at`, `updated_at` |
| `message_statuses` | `MessageStatus` | `id` (UUID PK), `message_id` (FK), `user_id`, `status` (enum: sent/delivered/read), `created_at`, `updated_at` |

Enum-ы: `DialogType` (direct, group), `MessageStatusEnum` (sent, delivered, read) — хранятся как VARCHAR (`native_enum=False`).

Relationship-ы: `Dialog ↔ DialogParticipant` (selectin), `Dialog ↔ Message` (noload), `Message ↔ MessageStatus` (noload).

#### Миграции

| Ревизия | Описание |
|---|---|
| `001` | Начальная: 4 таблицы, индексы, FK с CASCADE |

Команды:
```bash
cd messenger
alembic upgrade head
alembic downgrade -1
```

#### Репозитории

| Репозиторий | Методы |
|---|---|
| `DialogsRepository` | `create`, `create_with_participants`, `get_by_id`, `get_user_dialogs`, `add_participant`, `get_direct_dialog` |
| `MessagesRepository` | `create`, `get_by_client_message_id`, `get_by_id`, `get_by_dialog` (с пагинацией), `get_status`, `set_status`, `set_delivered_if_sent` |

Абстрактные базы в `repositories/base/`, конкретные реализации в `repositories/`.

### 5.4 Тесты

| Файл | Тесты |
|---|---|
| `test_health.py` | health endpoint → 200 |
| `test_migrations.py` | upgrade на чистой БД, idempotent re-run |
| `test_repositories.py` | CRUD: dialogs (create, get_by_id, not_found, participants), messages (create, get_by_id, get_by_dialog, pagination, set_status) |
| `test_auth_dependency.py` | Auth dependency: valid token → 200, invalid/expired/blacklisted → 403, missing → 422, unavailable → 503 |
| `test_dialogs.py` | POST /dialogs/direct: create, idempotent get, self-dialog → 400, not found → 404; GET /dialogs: user isolation, sorted by activity |
| `test_messages.py` | POST /dialogs/{id}/messages: send → 201, idempotent, foreign → 403; GET /dialogs/{id}/messages: limit/offset, deterministic order, participants only, 404 not found |
| `test_00_websocket.py` | WebSocket: два клиента получают new_message; reconnect; при активном WS у получателя статус delivered (TASK-009); статусы не проставляются неучастникам диалога |

Инфра: `testcontainers` (PostgreSQL 17.4), alembic via subprocess, async sessions. `db_client` fixture overrides `get_session` for integration tests.

### API

| Метод | Путь | Описание | Статус |
|---|---|---|---|
| `POST` | `/messenger/api/v1/dialogs/direct` | Создать/получить 1:1 диалог | ✅ реализован |
| `GET` | `/messenger/api/v1/dialogs` | Список диалогов | ✅ реализован |
| `GET` | `/messenger/api/v1/dialogs/{id}/messages` | История сообщений | ✅ реализован |
| `POST` | `/messenger/api/v1/dialogs/{id}/messages` | Отправить сообщение | ✅ реализован |
| `POST` | `/messenger/api/v1/messages/{id}/read` | Отметить как прочитанное | планируется |
| `WS` | `/messenger/ws` | WebSocket для realtime (new_message) | ✅ реализован |

### 5.5 POST /dialogs/direct (TASK-004)

Создание или получение существующего 1:1 диалога.

**Слои:**

| Слой | Файл | Описание |
|---|---|---|
| Schema | `schemas/v1/dialogs.py` | `CreateDirectDialogRequest` (target_login), `DialogResponse`, `ParticipantResponse` (login, joined_at) |
| API | `api/v1/dialogs.py` | `POST /direct`, обработка ошибок (400/404/503) |
| Service | `services/dialogs.py` | `DialogsService.create_or_get_direct`: resolve login → check self → find existing → create |
| Repository | `repositories/dialogs.py` | `get_direct_dialog` (aliased join на DialogParticipant) |
| Exceptions | `exceptions/dialogs.py` | `SelfDialogError`, `UserNotFoundError`, `AuthServiceUnavailableError` |
| gRPC | `gRPC/client.py` | `get_user_id_by_login` → auth `GetUserByLogin` |

**Поток:**
1. Получаем `current_user_id` из cookie (auth dependency)
2. Резолвим `target_login` → `target_user_id` через gRPC `GetUserByLogin`
3. Проверяем `current_user_id != target_user_id` (иначе 400)
4. Ищем существующий direct-диалог между парой
5. Если найден — возвращаем, если нет — создаём + добавляем обоих участников

### 5.6 GET /dialogs (TASK-005)

Список диалогов текущего пользователя, отсортированных по последней активности (`updated_at DESC`).

**Слои:**

| Слой | Файл | Описание |
|---|---|---|
| Schema | `schemas/v1/dialogs.py` | `DialogsListResponse` (список `DialogResponse`) |
| API | `api/v1/dialogs.py` | `GET ""`, маппинг через `_dialog_to_response` |
| Service | `services/dialogs.py` | `DialogsService.get_user_dialogs` |
| Repository | `repositories/dialogs.py` | `get_user_dialogs` (JOIN DialogParticipant, ORDER BY updated_at DESC) |

**Поток:**
1. Получаем `current_user_id` из cookie (auth dependency)
2. Запрашиваем диалоги через `get_user_dialogs(user_id)` — JOIN по `dialog_participants`
3. Результат отсортирован по `updated_at DESC` (недавно обновлённые — первыми)
4. Возвращаем `DialogsListResponse` со списком `DialogResponse`

### 5.7 POST /dialogs/{dialog_id}/messages (TASK-006)

Отправка текстового сообщения в диалог с идемпотентностью по `client_message_id`.

**Слои:**

| Слой | Файл | Описание |
|---|---|---|
| Schema | `schemas/v1/messages.py` | `SendMessageRequest` (text, client_message_id), `MessageResponse` (id, dialog_id, sender_login, text, …) |
| API | `api/v1/messages.py` | `POST /{dialog_id}/messages`, обработка ошибок (403/404/409) |
| Service | `services/messages.py` | `MessagesService.send_message`: проверка диалога → проверка участия → идемпотентность → создание |
| Repository | `repositories/messages.py` | `get_by_client_message_id` (поиск существующего сообщения) |
| Exceptions | `exceptions/messages.py` | `NotDialogParticipantError`, `DialogNotFoundError`, `ClientMessageIdConflictError` |

**Поток:**
1. Получаем `current_user_id` из cookie (auth dependency)
2. Проверяем существование диалога по `dialog_id`
3. Проверяем, что `current_user_id` является участником диалога
4. Ищем существующее сообщение по `client_message_id` (идемпотентность)
5. Если найдено с тем же `dialog_id` и `sender_id` — возвращаем (без дубликата)
6. Если найдено с другим контекстом — 409 Conflict
7. Если не найдено — создаём и возвращаем 201

### 5.8 GET /dialogs/{dialog_id}/messages (TASK-007)

История сообщений диалога с пагинацией (limit/offset), доступ только участникам.

**Слои:**

| Слой | Файл | Описание |
|---|---|---|
| Schema | `schemas/v1/messages.py` | `MessagesListResponse` (список `MessageResponse`) |
| API | `api/v1/messages.py` | `GET /{dialog_id}/messages`, query params: `limit` (1-100, default 50), `offset` (0-10000, default 0) |
| Service | `services/messages.py` | `MessagesService.get_messages`: проверка диалога → проверка участия → выборка с пагинацией |
| Repository | `repositories/messages.py` | `get_by_dialog(dialog_id, limit, offset)` — ORDER BY `created_at ASC` |

**Поток:**
1. Получаем `current_user_id` из cookie (auth dependency)
2. Проверяем существование диалога по `dialog_id` (404 если не найден)
3. Проверяем, что `current_user_id` является участником диалога (403 если нет)
4. Запрашиваем сообщения с пагинацией, отсортированные хронологически (`created_at ASC`)
5. Возвращаем `MessagesListResponse` со списком `MessageResponse`

### WebSocket события (планируется)

```json
// Сервер → клиент
{ "type": "new_message", "payload": { "dialog_id": "...", "message": {...} } }
{ "type": "status_update", "payload": { "message_id": "...", "status": "read" } }
```

### Идентификация пользователя
`messenger` использует gRPC-клиент к `auth` (`GetUserInfoByToken`) — см. секцию 5.2.

---

## 5.9 Веб-клиент (TASK-UI-001)

Минимальный single-page клиент для ручного тестирования мессенджера.

**Файл:** `web/index.html` — единый HTML-файл с встроенными CSS и JS.

**Функционал:**
- Регистрация (signup) и вход (login) через auth API
- Автоматическая проверка сессии при загрузке (`GET /auth/api/v1/users/me`)
- Автоматический refresh токена при 403
- Список диалогов с обновлением
- Создание 1:1 диалога по логину собеседника
- Отправка и просмотр сообщений
- Responsive layout (mobile-friendly)

**Раздача через nginx:** `http://localhost/web/` (корень `/` редиректит на `/web/`)

**Конфигурация:**
- `deploy/infra/configs/nginx_gateway/site.conf` — location `/web/` с alias `/data/web/`
- `deploy/docker-compose.infra.yml` — volume `../web:/data/web:ro`

**Безопасность:**
- XSS-защита через DOM-based escaping (`textContent` → `innerHTML`)
- Cookie-based auth с `credentials: 'include'`
- `cookie_secure` в auth настраивается через env (`COOKIE_SECURE`, default: `true`)

---

## 6. Инфраструктура

### `auth/docker-compose.yml`
Локальный стек для разработки: `auth`, `postgres`, `redis`, `nginx_auth`.

### `deploy/docker-compose.yml`
Включает `auth/docker-compose.yml` + `messenger/docker-compose.yml` + `deploy/docker-compose.infra.yml`.

### `deploy/docker-compose.infra.yml`
Только Nginx gateway (`nginx:1.25.5`) на порту `80`.

### Nginx
- `auth/infra/configs/nginx_auth/` — reverse proxy для auth-сервиса
- `deploy/infra/configs/nginx_gateway/` — главный gateway: роутит `/auth/*` и `/messenger/*`

### Технологический стек

| Компонент | Технология |
|---|---|
| API | FastAPI (REST + WebSocket) |
| ORM / миграции | SQLAlchemy async + Alembic |
| Валидация | Pydantic v2 |
| БД | PostgreSQL |
| Кэш / pub-sub | Redis |
| Брокер событий | Kafka |
| Межсервисный RPC | gRPC |
| Proxy | Nginx |
| Метрики | Prometheus + Grafana |
| Хранилище файлов | S3-compatible (MinIO local) |
| Тесты | pytest + pytest-asyncio + httpx |
| Линтер | ruff + mypy |
| Pre-commit | ruff, ruff-format, yaml/eof/whitespace |

---

## 7. Паттерны и конвенции

### Слоистая архитектура

Каждый сервис строго следует слоям:

```
api/v1/          ← HTTP/WS handlers, зависимости через Depends()
dependencies/    ← FastAPI Depends: извлечение user из токена, проверки
services/        ← бизнес-логика, оркестрация репозиториев
repositories/    ← доступ к данным (PostgreSQL, Redis)
  base/          ← ABC с абстрактными методами
models/          ← SQLAlchemy ORM модели
schemas/v1/      ← Pydantic v2 схемы входа/выхода
utils/           ← утилиты (JWT, шифрование)
db/              ← соединения с хранилищами
exceptions/      ← кастомные исключения
gRPC/            ← gRPC сервер или клиент
```

### Репозитории

Всегда есть абстрактный базовый класс в `repositories/base/` и конкретная реализация рядом. Это позволяет легко заменить хранилище.

```python
# base/users.py
class AbstractUserRepository(ABC):
    @abstractmethod
    async def create(self, session, schema) -> User: ...
    @abstractmethod
    async def read(self, session, **filters) -> User | None: ...

# users.py
class UserRepository(AbstractUserRepository):
    async def create(self, session, schema) -> User:
        ...
```

### Retry через tenacity

Все методы репозиториев обёрнуты `@retry` с экспоненциальным backoff:

```python
@retry(
    retry=retry_if_exception_type((DisconnectionError, OperationalError)),
    stop=stop_after_attempt(settings.backoff_retries_count),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def read(self, ...): ...
```

### Версионирование API и схем

- Префикс `/api/v1` в роутерах
- Схемы в `schemas/v1/` — версионирование с первого дня
- При breaking changes — добавить `schemas/v2/` и `api/v2/`

### Конфигурация

Только через `pydantic-settings` из `.env`. Никаких хардкоженных значений в коде.

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

### Логирование

`core/logger.py` — единый `LOGGING` dict для `uvicorn.run(log_config=LOGGING)`. Форматтеры: `verbose` (с timestamp), `default`, `access`.

### Именование файлов

- Файлы — `snake_case.py`
- Классы — `PascalCase`
- Функции, переменные — `snake_case`
- Константы — `UPPER_SNAKE_CASE`

---

## 8. Разработка и тестирование

### Линтер и форматтер

```bash
# Проверка
ruff check .

# Форматирование
ruff format .

# Типы
mypy auth/src/
```

`ruff.toml` в корне — единая конфигурация для всех сервисов (line-length=100).

`setup.cfg` — mypy в strict-режиме для python 3.12.

### Pre-commit

```bash
pre-commit install  # при клонировании репозитория
pre-commit run --all-files  # запустить вручную
```

Хуки: `ruff`, `ruff-format`, `check-yaml`, `end-of-file-fixer`, `trailing-whitespace`.

### Тесты

```bash
# Запуск всех тестов
pytest auth/ -v

# С покрытием
pytest auth/ --cov=auth/src --cov-report=html
```

Стек: `pytest`, `pytest-asyncio`, `httpx` (async HTTP клиент для тестов).

---

## 9. Добавление нового функционала

### Новый REST-эндпоинт в `auth`

1. Добавить схемы в `auth/src/schemas/v1/`
2. Добавить метод в репозиторий (`repositories/`) + его абстракцию (`repositories/base/`)
3. Добавить бизнес-логику в `services/users.py`
4. Добавить роут в `api/v1/users.py`
5. Если нужны новые поля в БД — создать миграцию Alembic

### Новая таблица

1. Создать модель в `models/`
2. Создать репозиторий с базовым классом
3. Создать миграцию: `alembic revision --autogenerate -m "add_table_name"`
4. Применить: `alembic upgrade head`

### Новый сервис (например, `messenger`)

```
messenger/
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── requirements.txt
├── migration/
│   └── versions/
└── src/
    ├── main.py
    ├── api/v1/
    ├── core/config.py
    ├── db/postgres.py + redis.py
    ├── dependencies/
    ├── exceptions/
    ├── gRPC/       ← клиент к auth
    ├── models/
    ├── repositories/base/
    ├── schemas/v1/
    ├── services/
    └── utils/
```

Скопировать структуру из `auth/`, настроить свой `.env`, добавить в `deploy/docker-compose.yml`.

---

## 10. Бэклог и тикеты

Подробности в `tickets.md`.
