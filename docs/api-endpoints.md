# API эндпоинты (backend)

## Auth (сайт)
- `POST /api/auth/register/`
- `POST /api/auth/login/`
- JWT также доступен через:
  - `POST /api/auth/token/`
  - `POST /api/auth/token/refresh/`

## Загрузка фото
- Сайт:
  - `POST /api/photos/upload/` (multipart)
    - `file` (image)
    - `category` (slug или name или UUID) или пусто
    - `tags` (JSON-массив или CSV строка)
  - `GET /api/photos/<photo_id>/file/` (скачивание файла)
- Telegram-бот:
  - `POST /api/bot/upload/` (multipart)
    - `X-Bot-Token`
    - `telegram_user_id`
    - те же `file/category/tags`

## Поиск/фильтрация
- `GET /api/photos/`
  - `q` (ключевые слова по названию/категории/тегам)
  - `category` (slug/name/uuid)
  - `tags` (comma-separated)
  - `file_type` (`jpeg`/`png`)
  - `from`/`to` (`YYYY-MM-DD`)
  - `sort` (`uploaded_at_desc`, `uploaded_at_asc`, `file_size_desc`, ...)
  - `page`, `page_size`

- Бот:
  - `GET /api/bot/search/` (аналогично, с `X-Bot-Token`)

## Экспорт
- Сайт:
  - `GET /api/photos/export/` (zip)
- Бот:
  - `GET /api/bot/export/` (zip)

## Админка (API)
- Категории:
  - `GET /api/categories/`
  - `POST /api/categories/create/` (admin)
- Теги:
  - `GET /api/tags/`
  - `POST /api/tags/create/` (admin)
- Пользователи:
  - `GET /api/admin/users/` (admin)
- Отчеты:
  - `GET /api/reports/summary/`
  - `GET /api/reports/top-tags/`

