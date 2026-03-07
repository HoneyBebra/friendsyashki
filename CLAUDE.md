# CLAUDE.md

Этот файл содержит инструкции для Claude Code (claude.ai/code) при работе с кодом в этом репозитории.

## Обзор проекта

Монорепо мессенджера ("friendsyashki") на Python-микросервисах. Два сервиса: **auth** (аутентификация, полностью реализован) и **messenger** (MVP в разработке), плюс минимальный **web**-клиент для тестирования.

## Стек технологий

- Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic
- gRPC для межсервисного взаимодействия (auth предоставляет `GetUserInfoByToken`)
- PostgreSQL 17.4, Redis 7.4.1, Nginx 1.25.5
- Gunicorn + Uvicorn workers

## Команды

### Запуск сервисов
```bash
# Один сервис (из директории сервиса)
docker compose up -d --build

# Весь стек
cd deploy && docker compose up -d --build
```

### Миграции
```bash
docker exec -it <service> /bin/sh
alembic upgrade head
```

### Линтинг и проверка типов
```bash
ruff check .          # линтер (конфиг: ruff.toml, line-length=100)
ruff format .         # форматирование
mypy .                # проверка типов (конфиг: setup.cfg, strict mode)
```

### Тестирование
```bash
# Из директории сервиса (например messenger/)
pytest                # использует TestContainers для PostgreSQL
```

### Pre-commit хуки
```bash
pip install -r requirements-dev.txt
pre-commit install
```

## Архитектура

Каждый сервис следует слоистой архитектуре:
```
API (FastAPI routers) -> Dependencies (auth/JWT) -> Services (бизнес-логика) -> Repositories (доступ к данным) -> Models (SQLAlchemy)
```

- **Паттерн Repository**: абстрактные базовые классы в `repositories/base/`, конкретные реализации рядом
- **Версионирование схем**: Pydantic-схемы в `schemas/v1/`
- **Изоляция сервисов**: у каждого сервиса свои PostgreSQL, Redis, Docker
- **Миграции**: Alembic для каждого сервиса в `migration/versions/`

Ключевые точки входа:
- `auth/src/main.py` — FastAPI-приложение + gRPC-сервер (порт 50051)
- `messenger/src/main.py` — FastAPI + WebSocket + gRPC-клиент
- `deploy/docker-compose.yml` — оркестрация всего стека

## Правила кода

- Никогда не использовать голый `except Exception:` — только конкретные типы исключений или привязка объекта исключения
- Не изменять строки с пометкой `# TODO: Для теста` — это намеренные маркеры для разработки
- Документация API доступна по адресу `http://127.0.0.1/<service>/api/v1/openapi`
- Используй MCP context7 для изучения документации
