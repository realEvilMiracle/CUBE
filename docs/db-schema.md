# DB схема (логическая)

## `core.User`
- `email` (unique)
- `password` (hash)
- `role` (`admin` / `user`)

## `core.Category`
- `id` (UUID)
- `name` (unique)
- `slug` (unique)

## `core.Tag`
- `id` (UUID)
- `name` (unique)

## `core.Photo`
- `id` (UUID)
- `original_name`
- `mime_type`
- `file_size`
- `uploaded_at`
- `category` (nullable FK)
- `tags` (M2M через таблицу связи)
- `file_path` (relative path от `MEDIA_ROOT`)
- `source` (`web` / `bot`)
- `owner_user` (nullable FK на `core.User`)
- `owner_telegram_id` (nullable string)

## `core.AuditLog` (планируется для audit событий)
- `action`
- `actor_user` / `actor_telegram_id`
- `metadata` (JSON)

## Индексация (для скорости поиска)
- `Photo(uploaded_at, mime_type)`
- `Category(slug)`
- `Tag(name)`

