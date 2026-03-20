from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from typing import Iterable


def build_zip_archive(*, file_paths_abs: Iterable[str], output_filename: str) -> str:
    """
    Возвращает путь к ZIP-файлу на диске.
    """

    tmp_dir = tempfile.mkdtemp(prefix="photozip_")
    zip_path = os.path.join(tmp_dir, output_filename)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for abs_path in file_paths_abs:
            if not abs_path or not os.path.exists(abs_path):
                continue
            arcname = os.path.basename(abs_path)
            zf.write(abs_path, arcname=arcname)

    return zip_path


def cleanup_temp_dir_for_zip(zip_path: str) -> None:
    try:
        tmp_dir = os.path.dirname(zip_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        # Нельзя гарантировать наличие права на удаление; не валим ответ пользователю.
        pass

