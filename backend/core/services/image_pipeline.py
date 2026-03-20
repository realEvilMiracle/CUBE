from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass
from typing import Tuple

from PIL import Image


@dataclass(frozen=True)
class OptimizedImage:
    bytes: bytes
    mime_type: str


def _read_all(uploaded_file) -> bytes:
    # DRF UploadedFile may be lazy; for optimization we need bytes.
    uploaded_file.seek(0)
    return uploaded_file.read()


def optimize_image_lossless(uploaded_file, mime_type: str) -> OptimizedImage:
    """
    "Lossless" в смысле: не выполняем перезапаковку JPEG (она обычно приводит к потере),
    а для PNG применяем опции оптимизации PNG без изменения пикселей.
    """

    data = _read_all(uploaded_file)

    # Валидируем, что это вообще корректная картинка.
    with Image.open(io.BytesIO(data)) as im:
        detected_format = (im.format or "").upper()

        format_to_mime = {
            "PNG": "image/png",
            "JPEG": "image/jpeg",
            "WEBP": "image/webp",
        }
        detected_mime = format_to_mime.get(detected_format)

        # Простейшая валидация: если Pillow определил формат, он должен совпадать с ожидаемым по mime.
        # (На практике content_type иногда бывает не идеален.)
        if detected_mime and detected_mime not in (mime_type or ""):
            # Допускаем мягко: image/jpg -> image/jpeg
            if not (mime_type.startswith("image/jpg") and detected_mime == "image/jpeg"):
                raise ValueError(f"Mime mismatch: expected {mime_type}, detected {detected_mime}")

        if detected_format == "PNG":
            original_size = im.size
            original_mode = im.mode
            out = io.BytesIO()
            # optimize=True / compress_level — без потери пикселей.
            im.save(out, format="PNG", optimize=True, compress_level=9)

            # Контроль качества: размер/режим после оптимизации не меняется.
            out_bytes = out.getvalue()
            with Image.open(io.BytesIO(out_bytes)) as im2:
                if im2.size != original_size:
                    raise ValueError("PNG optimization changed dimensions")
                if im2.mode != original_mode and original_mode not in ("P", "RGBA"):
                    # Иногда Pillow может менять mode, но это не гарантирует потери.
                    # Для строгого контроля можно расширить правила.
                    raise ValueError("PNG optimization changed mode")

            return OptimizedImage(bytes=out_bytes, mime_type="image/png")

        # Для JPEG/WEBP сохраняем исходные байты, но проверяем декодирование Pillow.
        return OptimizedImage(bytes=data, mime_type=mime_type)


def write_photo_file(
    *, optimized_bytes: bytes, media_root: str, file_path_relative: str
) -> Tuple[str, int]:
    abs_dir = os.path.join(media_root, os.path.dirname(file_path_relative))
    os.makedirs(abs_dir, exist_ok=True)
    abs_path = os.path.join(media_root, file_path_relative)
    with open(abs_path, "wb") as f:
        f.write(optimized_bytes)
    return abs_path, len(optimized_bytes)

