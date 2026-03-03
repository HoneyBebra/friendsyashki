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
- `messenger` — каркас реализован (TASK-001 ✅), в разработке (TASK-002..011)

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
├── messenger/                    # Сервис мессенджера 🚧 каркас готов (v0.1.0)
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
| `BACKOFF_RETRIES_COUNT` | Кол-во попыток reconnect (default: 10) |

### 4.2 Точка входа

`auth/src/main.py` — создаёт FastAPI-приложение и запускает gRPC-сервер в `lifespan`.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    server = grpc.aio.server()
    user_pb2_grpc.add_UserServicer_to_server(await get_grpc_session(), server)
    server.add_insecure_port(f"[::]:{settings.grpc_port}")
    await server.start()
    yield
    await server.stop()
```

- FastAPI и gRPC-сервер запускаются **одновременно** в одном процессе
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
- `add_tokens_to_response(response, user_id)` — генерирует пару токенов и записывает в куки
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
}

message GetUserInfoByTokenRequest  { string access_token = 1; }
message GetUserInfoByTokenResponse { string id = 1; }
```

Использование из `messenger` (планируется):

```python
# В messenger: gRPC-клиент для идентификации пользователя
channel = grpc.aio.insecure_channel("auth:50051")
stub = UserStub(channel)
response = await stub.GetUserInfoByToken(
    GetUserInfoByTokenRequest(access_token=token)
)
user_id = response.id
```

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

## 5. Сервис `messenger` (v0.1.0 — каркас)

Каркас сервиса реализован (TASK-001). Текущий функционал: health endpoint.

### 5.0 Текущее состояние (v0.1.0)

- FastAPI-приложение с health endpoint (`GET /messenger/api/v1/health` → `200 {"status": "ok"}`)
- Конфигурация через `pydantic-settings` из `.env`
- Docker-интеграция: `Dockerfile` + `docker-compose.yml` (messenger + nginx_messenger)
- Интегрирован в `deploy/docker-compose.yml` и nginx gateway
- Структура директорий подготовлена для дальнейшей разработки (db, models, repositories, services, ws, gRPC)
- Тесты: `pytest` + `httpx` (async ASGI transport)

### Планируемые таблицы

| Таблица | Описание |
|---|---|
| `dialogs` | Диалоги |
| `dialog_participants` | Участники диалога |
| `messages` | Сообщения |
| `message_statuses` | Статусы: `sent`, `delivered`, `read` |

### Планируемый API

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/messenger/api/v1/dialogs/direct` | Создать 1:1 диалог |
| `GET` | `/messenger/api/v1/dialogs` | Список диалогов |
| `GET` | `/messenger/api/v1/dialogs/{id}/messages` | История сообщений |
| `POST` | `/messenger/api/v1/dialogs/{id}/messages` | Отправить сообщение |
| `POST` | `/messenger/api/v1/messages/{id}/read` | Отметить как прочитанное |
| `WS` | `/messenger/api/v1/ws` | WebSocket для realtime |

### WebSocket события (планируется)

```json
// Сервер → клиент
{ "type": "new_message", "payload": { "dialog_id": "...", "message": {...} } }
{ "type": "status_update", "payload": { "message_id": "...", "status": "read" } }
```

### Идентификация пользователя
`messenger` будет использовать gRPC-клиент к `auth` (`GetUserInfoByToken`) — см. TASK-003.

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
