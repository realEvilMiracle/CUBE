# Security hardening и backup

## Секреты (ключи, токены)
- Не коммитить `.env` / секреты в репозиторий.
- В продакшене передавать переменные окружения через Docker secrets/CI variables.
- Использовать отдельные значения для:
  - `DJANGO_SECRET_KEY`
  - `BOT_API_KEY`
  - `TELEGRAM_BOT_TOKEN`
  - `POSTGRES_PASSWORD`

## Ограничение доступа
- Запись фото: только для сайта-аутентифицированных пользователей (JWT).
- Бот-загрузки/поиск/экспорт: только при заголовке `X-Bot-Token` равном `BOT_API_KEY`.
- Админ-эндпоинты (категории/теги/удаление фото): только роль `admin`.

## Ограничения и валидация загрузок
- Лимит размера файла: `PHOTO_MAX_UPLOAD_BYTES` (по умолчанию 20MB).
- Разрешенные MIME: `PHOTO_ALLOWED_MIME_TYPES` (по умолчанию JPEG/PNG/WEBP).
- PNG-оптимизация выполняется без потери пикселей (Pillow optimize + контроль размера/режима).

## Rate limiting
- Включены DRF throttling для анонимных и авторизованных запросов (см. `DEFAULT_THROTTLE_RATES` в settings).

## Audit логирование
- Создается `AuditLog` для действий:
  - загрузка фото (`upload`)
  - удаление (`delete`)
  - изменение справочников (`admin_update`)

## Backup/restore
### Что бэкапить
- PostgreSQL (таблицы и metadata).
- Директорию `MEDIA_ROOT` (файлы фото на SSD).

### Вариант ручного бэкапа (пример)
1. База:
   - `pg_dump` с сохранением в storage:
     - `pg_dump -Fc -h <host> -U <user> <db> > backup.dump`
2. Файлы:
   - `rsync -a --delete /path/to/MEDIA_ROOT/ <backup_dir>/media/`

### Restore (в общих чертах)
1. Восстановить DB из dump.
2. Развернуть `MEDIA_ROOT` и убедиться, что paths в таблице `Photo.file_path` соответствуют.

## Восстановление после потери файлов
- При загрузке в backend проверяется существование файла; для “битых” записей можно делать аудит через admin panel / SQL.

