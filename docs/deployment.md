# Деплой и запуск

## Требования
- Docker / Docker Compose
- Доступ к домену для SSL (если нужно)

## Запуск через Docker Compose
1. Положить `.env` рядом с `infra/docker-compose.yml` (или скопировать `infra/.env.example`).
2. Запустить:
   - `cd infra`
   - `docker compose up --build`

После старта:
- Backend: `http://localhost:8000`
- Админ: `http://localhost:8000/admin/`
- UI: `http://localhost:8000/`, `http://localhost:8000/admin-panel/`

## Миграции
Перед использованием нужно создать таблицы:
- `docker compose exec backend python manage.py makemigrations`
- `docker compose exec backend python manage.py migrate`

## SSL
Рекомендуемый вариант:
- Nginx / Traefik как reverse-proxy с Let's Encrypt.
- backend оставить без терминатора SSL, проксировать запросы.

## Обновления
- При смене кода backend: перезапустить `docker compose up -d --build backend`.
- MEDIA_ROOT хранится в volume `media_data` (не теряется при пересборке).

