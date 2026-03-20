from __future__ import annotations

from datetime import timedelta

import mimetypes
import os
import re
import uuid
from typing import Any, Iterable
from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404, HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.models import AuditLog, Category, Photo, Tag
from core.serializers import (
    LoginSerializer,
    PhotoSerializer,
    PhotoUploadSerializer,
    RegisterSerializer,
    make_tokens_for_user,
)
from core.services.export_service import build_zip_archive, cleanup_temp_dir_for_zip
from core.services.image_pipeline import optimize_image_lossless, write_photo_file

import qrcode
from PIL import Image


User = get_user_model()


def _user_is_admin(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "role", None) == "admin")


def _bot_token_expected() -> str | None:
    return getattr(settings, "BOT_API_KEY", None) or os.environ.get("BOT_API_KEY")


def _is_bot_request(request) -> bool:
    token = request.headers.get("X-Bot-Token")
    return bool(token and _bot_token_expected() and token == _bot_token_expected())


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _resolve_category(value: str) -> Category | None:
    value = (value or "").strip()
    if not value:
        return None

    # 1) UUID
    try:
        u = uuid.UUID(value)
        return Category.objects.filter(id=u).first()
    except Exception:
        pass

    # 2) slug
    return Category.objects.filter(Q(slug=value) | Q(name=value)).first()


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name)
    # Убираем потенциально опасные символы (оставляем расширение).
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    return name[:180]


class UserViewSet(viewsets.ViewSet):
    def list(self, request):
        if not _user_is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        users = User.objects.all().order_by("-date_joined")[:200]
        return Response(
            [
                {"id": u.id, "email": u.email, "role": u.role, "is_active": u.is_active}
                for u in users
            ]
        )


class CategoryViewSet(viewsets.ViewSet):
    def list(self, request):
        qs = Category.objects.all().order_by("name")
        page = PageNumberPagination()
        page.page_size = min(100, max(1, int(request.query_params.get("page_size", 24))))
        result = page.paginate_queryset(qs, request)
        data = [{"id": c.id, "name": c.name, "slug": c.slug} for c in result]
        return page.get_paginated_response(data)

    def create(self, request):
        if not _user_is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        name = str(request.data.get("name", "")).strip()
        if not name:
            return Response({"detail": "name is required"}, status=status.HTTP_400_BAD_REQUEST)

        slug = str(request.data.get("slug") or name).strip().lower().replace(" ", "-")
        cat, _ = Category.objects.get_or_create(name=name, defaults={"slug": slug})
        if cat.slug != slug:
            cat.slug = slug
            cat.save(update_fields=["slug"])
        AuditLog.objects.create(
            action=AuditLog.Action.admin_update,
            actor_user=request.user,
            metadata={"entity": "category", "id": str(cat.id), "name": cat.name},
        )
        return Response({"id": cat.id, "name": cat.name, "slug": cat.slug}, status=status.HTTP_201_CREATED)


class TagViewSet(viewsets.ViewSet):
    def list(self, request):
        qs = Tag.objects.all().order_by("name")
        page = PageNumberPagination()
        page.page_size = min(200, max(1, int(request.query_params.get("page_size", 24))))
        result = page.paginate_queryset(qs, request)
        data = [{"id": t.id, "name": t.name} for t in result]
        return page.get_paginated_response(data)

    def create(self, request):
        if not _user_is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        name = str(request.data.get("name", "")).strip()
        if not name:
            return Response({"detail": "name is required"}, status=status.HTTP_400_BAD_REQUEST)

        tag, _ = Tag.objects.get_or_create(name=name)
        AuditLog.objects.create(
            action=AuditLog.Action.admin_update,
            actor_user=request.user,
            metadata={"entity": "tag", "id": str(tag.id), "name": tag.name},
        )
        return Response({"id": tag.id, "name": tag.name}, status=status.HTTP_201_CREATED)


class PhotoViewSet(viewsets.ViewSet):
    def list(self, request):
        qs = (
            Photo.objects.select_related("category")
            .prefetch_related("tags")
            .all()
        )

        # filters
        q = str(request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(original_name__icontains=q)
                | Q(category__name__icontains=q)
                | Q(tags__name__icontains=q)
            ).distinct()

        category = str(request.query_params.get("category") or "").strip()
        if category:
            cat = _resolve_category(category)
            if cat:
                qs = qs.filter(category=cat)
            else:
                qs = qs.none()

        tags = _parse_csv(request.query_params.get("tags"))
        if tags:
            qs = qs.filter(tags__name__in=tags).distinct()

        file_type = str(request.query_params.get("file_type") or "").strip().lower()
        if file_type:
            # ожидаем "jpeg" / "png"
            qs = qs.filter(mime_type__icontains=file_type)

        from_date = str(request.query_params.get("from") or "").strip()
        to_date = str(request.query_params.get("to") or "").strip()
        # Допущение по формату: YYYY-MM-DD
        if from_date:
            qs = qs.filter(uploaded_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(uploaded_at__date__lte=to_date)

        sort = str(request.query_params.get("sort") or "uploaded_at_desc").strip()
        if sort == "uploaded_at_asc":
            qs = qs.order_by("uploaded_at")
        elif sort == "file_size_desc":
            qs = qs.order_by("-file_size")
        elif sort == "file_size_asc":
            qs = qs.order_by("file_size")
        else:
            qs = qs.order_by("-uploaded_at")

        paginator = PageNumberPagination()
        paginator.page_size = min(100, max(1, int(request.query_params.get("page_size", settings.REST_FRAMEWORK.get("PAGE_SIZE", 24)))))
        page = paginator.paginate_queryset(qs, request)
        data = PhotoSerializer(page, many=True).data
        return paginator.get_paginated_response(data)

    def upload(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = PhotoUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data["file"]
        mime_type = uploaded_file.content_type or mimetypes.guess_type(uploaded_file.name)[0] or "application/octet-stream"

        if getattr(uploaded_file, "size", 0) > settings.PHOTO_MAX_UPLOAD_BYTES:
            return Response(
                {"detail": "File too large"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if mime_type not in settings.PHOTO_ALLOWED_MIME_TYPES and mime_type.replace("image/jpg", "image/jpeg") not in settings.PHOTO_ALLOWED_MIME_TYPES:
            return Response(
                {"detail": f"Unsupported mime_type: {mime_type}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # На "lossless" этапе фактически: для PNG Pillow-оптимизация, для JPEG — без перезапаковки.
        try:
            optimized = optimize_image_lossless(uploaded_file, mime_type)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        category_value = str(request.data.get("category") or "").strip()
        cat = _resolve_category(category_value) if category_value else None

        if category_value and not cat:
            return Response({"detail": "Unknown category"}, status=status.HTTP_400_BAD_REQUEST)

        tags_raw = str(request.data.get("tags") or "")
        tag_names = serializer.parse_tags(tags_raw)
        if len(tag_names) > 50:
            return Response({"detail": "Too many tags (max 50)"}, status=status.HTTP_400_BAD_REQUEST)
        tags_qs: list[Tag] = []
        for name in tag_names:
            if not name:
                continue
            tag, _ = Tag.objects.get_or_create(name=name)
            tags_qs.append(tag)

        original_name = _sanitize_filename(uploaded_file.name)
        photo_id = uuid.uuid4()
        rel_dir = f"photos/{photo_id}"
        file_ext = os.path.splitext(original_name)[1].lower() or ".img"
        file_rel_path = f"{rel_dir}/{photo_id}{file_ext}"

        photo = Photo.objects.create(
            id=photo_id,
            original_name=original_name,
            mime_type=optimized.mime_type,
            file_size=len(optimized.bytes),
            category=cat,
            file_path=file_rel_path,
            source=Photo.Source.web,
            owner_user=request.user,
        )
        if tags_qs:
            photo.tags.set(tags_qs)

        abs_path, _ = write_photo_file(
            optimized_bytes=optimized.bytes,
            media_root=settings.MEDIA_ROOT,
            file_path_relative=file_rel_path,
        )
        if not os.path.exists(abs_path):
            photo.delete()
            return Response({"detail": "Failed to store file"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        AuditLog.objects.create(
            action=AuditLog.Action.upload,
            actor_user=request.user,
            metadata={
                "photo_id": str(photo.id),
                "source": photo.source,
                "category": cat.slug if cat else None,
                "tags": [t.name for t in tags_qs],
                "file_size": photo.file_size,
            },
        )
        return Response(PhotoSerializer(photo).data, status=status.HTTP_201_CREATED)

    def file(self, request, photo_id: uuid.UUID):
        try:
            photo = Photo.objects.get(id=photo_id)
        except Photo.DoesNotExist:
            raise Http404("Photo not found")

        abs_path = photo.storage_abs_path()
        if not os.path.exists(abs_path):
            raise Http404("File not found")

        resp = FileResponse(open(abs_path, "rb"), content_type=photo.mime_type)
        resp["Content-Disposition"] = f'inline; filename="{photo.original_name}"'
        return resp

    def destroy(self, request, photo_id: uuid.UUID):
        if not _user_is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            photo = Photo.objects.get(id=photo_id)
        except Photo.DoesNotExist:
            raise Http404("Photo not found")

        abs_path = photo.storage_abs_path()
        AuditLog.objects.create(
            action=AuditLog.Action.delete,
            actor_user=request.user,
            metadata={"photo_id": str(photo.id), "file_path": photo.file_path},
        )
        photo.delete()
        try:
            if os.path.exists(abs_path):
                os.remove(abs_path)
        except Exception:
            pass

        return Response(status=status.HTTP_204_NO_CONTENT)

    def export(self, request):
        # Разрешаем: либо сайт-аутентифицированному пользователю, либо бот-запросу по токену.
        if not (request.user and request.user.is_authenticated) and not _is_bot_request(request):
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        # Reuse filters from list endpoint.
        filters = request.query_params
        qs = Photo.objects.select_related("category").prefetch_related("tags").all()

        q = str(filters.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(original_name__icontains=q)
                | Q(category__name__icontains=q)
                | Q(tags__name__icontains=q)
            ).distinct()

        category = str(filters.get("category") or "").strip()
        if category:
            cat = _resolve_category(category)
            qs = qs.filter(category=cat) if cat else qs.none()

        tags = _parse_csv(filters.get("tags"))
        if tags:
            qs = qs.filter(tags__name__in=tags).distinct()

        sort = str(filters.get("sort") or "uploaded_at_desc").strip()
        if sort == "uploaded_at_asc":
            qs = qs.order_by("uploaded_at")
        else:
            qs = qs.order_by("-uploaded_at")

        file_type = str(filters.get("file_type") or "").strip().lower()
        if file_type:
            qs = qs.filter(mime_type__icontains=file_type)

        # Ограничим объем экспорта.
        limit = min(5000, max(1, int(filters.get("limit") or 2000)))
        photos = list(qs[:limit])

        file_paths_abs: list[str] = []
        for p in photos:
            abs_path = p.storage_abs_path()
            if os.path.exists(abs_path):
                file_paths_abs.append(abs_path)

        zip_path = build_zip_archive(
            file_paths_abs=file_paths_abs,
            output_filename="photos_export.zip",
        )
        # Для упрощения не гарантируем удаление файла после скачивания (можно улучшить Celery/background tasks).
        resp = FileResponse(open(zip_path, "rb"), content_type="application/zip")
        resp["Content-Disposition"] = 'attachment; filename="photos_export.zip"'
        resp["X-Export-Count"] = str(len(file_paths_abs))
        # В продакшене лучше удалять через фоновые задачи.
        # cleanup_temp_dir_for_zip(zip_path)
        return resp


class ReportViewSet(viewsets.ViewSet):
    def summary(self, request):
        total_photos = Photo.objects.count()
        total_users = User.objects.count()
        total_categories = Category.objects.count()
        total_tags = Tag.objects.count()

        by_source = (
            Photo.objects.values("source")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
        )

        by_category = (
            Photo.objects.values("category__name")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")[:25]
        )

        # Последние 30 дней (грубая агрегация для админ-статистики)
        # Допущение: хранение/отображение в UTC.
        cutoff = timezone.now() - timedelta(days=30)
        by_day = (
            Photo.objects.filter(uploaded_at__gte=cutoff)
            .annotate(day=TruncDate("uploaded_at"))
            .values("day")
            .annotate(cnt=Count("id"))
            .order_by("day")
        )

        return Response(
            {
                "total_photos": total_photos,
                "total_users": total_users,
                "total_categories": total_categories,
                "total_tags": total_tags,
                "by_source": [{"source": x["source"], "count": x["cnt"]} for x in by_source],
                "by_category": [
                    {"category": x["category__name"] or "uncategorized", "count": x["cnt"]}
                    for x in by_category
                ],
                "by_day": [{"day": str(x["day"]), "count": x["cnt"]} for x in by_day],
            }
        )

    def top_tags(self, request):
        top_n = min(50, max(1, int(request.query_params.get("limit") or 20)))
        qs = (
            Tag.objects.annotate(cnt=Count("photos"))
            .order_by("-cnt", "name")
            .filter(cnt__gt=0)[:top_n]
        )
        return Response({"items": [{"name": t.name, "count": t.cnt} for t in qs]})


@api_view(["POST"])
def auth_register(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data["email"].lower()
    password = serializer.validated_data["password"]

    if User.objects.filter(email=email).exists():
        return Response({"detail": "User already exists"}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.create_user(email=email, password=password, role=User.Role.user)
    return Response({"id": user.id, "email": user.email, "role": user.role}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def auth_login(request):
    serializer = LoginSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.validated_data["user"]
    tokens = make_tokens_for_user(user)
    return Response(
        {
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "user": {"id": user.id, "email": user.email, "role": user.role},
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def bot_upload(request):
    if not _is_bot_request(request):
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    serializer = PhotoUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    telegram_user_id = str(request.data.get("telegram_user_id") or "").strip()
    if not telegram_user_id:
        return Response({"detail": "telegram_user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    # Используем тот же пайплайн оптимизации/хранения.
    uploaded_file = serializer.validated_data["file"]
    mime_type = uploaded_file.content_type or mimetypes.guess_type(uploaded_file.name)[0] or "application/octet-stream"

    if getattr(uploaded_file, "size", 0) > settings.PHOTO_MAX_UPLOAD_BYTES:
        return Response({"detail": "File too large"}, status=status.HTTP_400_BAD_REQUEST)

    if mime_type not in settings.PHOTO_ALLOWED_MIME_TYPES and mime_type.replace("image/jpg", "image/jpeg") not in settings.PHOTO_ALLOWED_MIME_TYPES:
        return Response({"detail": f"Unsupported mime_type: {mime_type}"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        optimized = optimize_image_lossless(uploaded_file, mime_type)
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    category_value = str(request.data.get("category") or "").strip()
    cat = _resolve_category(category_value) if category_value else None
    if category_value and not cat:
        return Response({"detail": "Unknown category"}, status=status.HTTP_400_BAD_REQUEST)

    tags_raw = str(request.data.get("tags") or "")
    tag_names = serializer.parse_tags(tags_raw)
    if len(tag_names) > 50:
        return Response({"detail": "Too many tags (max 50)"}, status=status.HTTP_400_BAD_REQUEST)
    tags_qs: list[Tag] = []
    for name in tag_names:
        if not name:
            continue
        tag, _ = Tag.objects.get_or_create(name=name)
        tags_qs.append(tag)

    original_name = _sanitize_filename(uploaded_file.name)
    photo_id = uuid.uuid4()
    rel_dir = f"photos/{photo_id}"
    file_ext = os.path.splitext(original_name)[1].lower() or ".img"
    file_rel_path = f"{rel_dir}/{photo_id}{file_ext}"

    photo = Photo.objects.create(
        id=photo_id,
        original_name=original_name,
        mime_type=optimized.mime_type,
        file_size=len(optimized.bytes),
        category=cat,
        file_path=file_rel_path,
        source=Photo.Source.bot,
        owner_user=None,
        owner_telegram_id=telegram_user_id,
    )
    if tags_qs:
        photo.tags.set(tags_qs)

    write_photo_file(
        optimized_bytes=optimized.bytes,
        media_root=settings.MEDIA_ROOT,
        file_path_relative=file_rel_path,
    )

    AuditLog.objects.create(
        action=AuditLog.Action.upload,
        actor_user=None,
        actor_telegram_id=telegram_user_id,
        metadata={
            "photo_id": str(photo.id),
            "source": photo.source,
            "category": cat.slug if cat else None,
            "tags": [t.name for t in tags_qs],
            "file_size": photo.file_size,
        },
    )
    return Response(PhotoSerializer(photo).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def bot_search(request):
    if not _is_bot_request(request):
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    # Делаем почти то же что list в PhotoViewSet.
    qs = Photo.objects.select_related("category").prefetch_related("tags").all()
    q = str(request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(original_name__icontains=q)
            | Q(category__name__icontains=q)
            | Q(tags__name__icontains=q)
        ).distinct()

    category = str(request.query_params.get("category") or "").strip()
    if category:
        cat = _resolve_category(category)
        qs = qs.filter(category=cat) if cat else qs.none()

    tags = _parse_csv(request.query_params.get("tags"))
    if tags:
        qs = qs.filter(tags__name__in=tags).distinct()

    sort = str(request.query_params.get("sort") or "uploaded_at_desc").strip()
    if sort == "uploaded_at_asc":
        qs = qs.order_by("uploaded_at")
    else:
        qs = qs.order_by("-uploaded_at")

    paginator = PageNumberPagination()
    paginator.page_size = min(100, max(1, int(request.query_params.get("page_size", 24))))
    page = paginator.paginate_queryset(qs, request)
    data = PhotoSerializer(page, many=True).data
    return paginator.get_paginated_response(data)


@api_view(["GET"])
def bot_export(request):
    if not _is_bot_request(request):
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    # Ровно тот же фильтр, что у PhotoViewSet.export (но без user JWT).
    # Повторяем код частично, чтобы не тащить зависимости от ViewSet.
    filters = request.query_params
    qs = Photo.objects.select_related("category").prefetch_related("tags").all()

    q = str(filters.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(original_name__icontains=q)
            | Q(category__name__icontains=q)
            | Q(tags__name__icontains=q)
        ).distinct()

    category = str(filters.get("category") or "").strip()
    if category:
        cat = _resolve_category(category)
        qs = qs.filter(category=cat) if cat else qs.none()

    tags = _parse_csv(filters.get("tags"))
    if tags:
        qs = qs.filter(tags__name__in=tags).distinct()

    file_type = str(filters.get("file_type") or "").strip().lower()
    if file_type:
        qs = qs.filter(mime_type__icontains=file_type)

    limit = min(5000, max(1, int(filters.get("limit") or 2000)))
    sort = str(filters.get("sort") or "uploaded_at_desc").strip()
    qs = qs.order_by("uploaded_at" if sort == "uploaded_at_asc" else "-uploaded_at")
    photos = list(qs[:limit])

    file_paths_abs: list[str] = []
    for p in photos:
        abs_path = p.storage_abs_path()
        if os.path.exists(abs_path):
            file_paths_abs.append(abs_path)

    zip_path = build_zip_archive(
        file_paths_abs=file_paths_abs,
        output_filename="photos_export.zip",
    )
    resp = FileResponse(open(zip_path, "rb"), content_type="application/zip")
    resp["Content-Disposition"] = 'attachment; filename="photos_export.zip"'
    resp["X-Export-Count"] = str(len(file_paths_abs))
    return resp


@api_view(["GET"])
def qr_image(request):
    """
    Генерирует QR-код (PNG) с сезонной палитрой.

    Параметры:
    - data: строка для QR (например URL) (обязательно)
    - season: auto|winter|spring|summer|autumn (опционально, по умолчанию auto)
    """

    data = str(request.query_params.get("data") or "").strip()
    if not data:
        return Response({"detail": "data is required"}, status=status.HTTP_400_BAD_REQUEST)

    if len(data) > 1500:
        return Response({"detail": "data too long"}, status=status.HTTP_400_BAD_REQUEST)

    season = str(request.query_params.get("season") or "auto").strip().lower()
    if season == "auto":
        # Метеосезоны (упрощенно): зима/весна/лето/осень.
        import datetime as _dt

        month = _dt.datetime.utcnow().month
        if month in (12, 1, 2):
            season = "winter"
        elif month in (3, 4, 5):
            season = "spring"
        elif month in (6, 7, 8):
            season = "summer"
        else:
            season = "autumn"

    palettes = {
        "winter": {"fg": "#D9F3FF", "bg": "#0B3557"},
        "spring": {"fg": "#DFF7D9", "bg": "#1B5E20"},
        "summer": {"fg": "#FFE7C2", "bg": "#6D4C41"},
        "autumn": {"fg": "#FFD4E0", "bg": "#4E1E5E"},
    }
    palette = palettes.get(season) or palettes["winter"]

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color=palette["fg"], back_color=palette["bg"]).convert("RGB")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")

