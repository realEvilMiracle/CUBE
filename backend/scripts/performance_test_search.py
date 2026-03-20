"""
Performance test (manual) для оценки скорости поиска/фильтрации при 1000+ фото.

Использование:
  1) Подготовить БД и выполнить migrate.
  2) Запустить:
     - DJANGO_SECRET_KEY=... BOT_API_KEY=... python3 backend/scripts/performance_test_search.py

Скрипт:
- создает/переиспользует категорию и теги
- генерирует небольшие PNG-файлы (lossless) в MEDIA_ROOT
- пишет метаданные в Photo
- замеряет время ORM-поиска по тегам и category
"""

from __future__ import annotations

import io
import os
import random
import time
import uuid

import django
from PIL import Image
from django.conf import settings
from django.core.files.storage import default_storage

from core.models import Category, Photo, Tag
from core.services.image_pipeline import optimize_image_lossless, write_photo_file


def setup_django():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "photo_sort.settings")
    django.setup()


def make_png_bytes(color=(0, 128, 255), size=(64, 64)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main():
    setup_django()

    # Тестовые параметры
    target_count = int(os.environ.get("PERF_TARGET_PHOTOS", "1000"))
    batch_size = 200
    media_root = settings.MEDIA_ROOT

    cat, _ = Category.objects.get_or_create(name="PerfCategory", defaults={"slug": "perf-category"})
    tag_names = [f"t{i}" for i in range(20)]
    tags = [Tag.objects.get_or_create(name=n)[0] for n in tag_names]

    png_bytes = make_png_bytes()
    # proxy-мимикрия UploadedFile не нужна: optimize_image_lossless использует Pillow и отдает bytes.
    from django.core.files.uploadedfile import SimpleUploadedFile

    uploaded = SimpleUploadedFile("seed.png", png_bytes, content_type="image/png")
    optimized = optimize_image_lossless(uploaded, "image/png")

    # seed (простая вставка, без очередей)
    existing = Photo.objects.count()
    if existing < target_count:
        to_create = target_count - existing
        created = 0
        while created < to_create:
            chunk = min(batch_size, to_create - created)
            objs = []
            for _ in range(chunk):
                photo_id = uuid.uuid4()
                original_name = f"seed_{photo_id}.png"
                rel_dir = f"photos/{photo_id}"
                file_rel_path = f"{rel_dir}/{photo_id}.png"

                p = Photo(
                    id=photo_id,
                    original_name=original_name,
                    mime_type="image/png",
                    file_size=len(optimized.bytes),
                    category=cat,
                    file_path=file_rel_path,
                    source=Photo.Source.web,
                    owner_user=None,
                )
                objs.append(p)

            Photo.objects.bulk_create(objs)
            # После bulk_create проставляем M2M теги
            for p in objs:
                chosen = random.sample(tags, k=random.randint(1, 5))
                p.tags.set(chosen)
                write_photo_file(
                    optimized_bytes=optimized.bytes,
                    media_root=media_root,
                    file_path_relative=p.file_path,
                )

            created += chunk
            print(f"Seeded {created}/{to_create}")

    # Замер ORM-поиска
    probe_tags = tag_names[:3]
    start = time.perf_counter()
    qs = Photo.objects.filter(category=cat, tags__name__in=probe_tags).distinct()[:200]
    list(qs)
    elapsed = time.perf_counter() - start

    print(f"Query elapsed: {elapsed:.3f}s for {min(200, qs.count() if hasattr(qs, 'count') else 200)} rows")
    print("Target acceptance (from ТЗ): <= 5 сек на сценариях с 1000 фото.")


if __name__ == "__main__":
    main()

