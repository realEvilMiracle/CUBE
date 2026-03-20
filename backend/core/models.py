from __future__ import annotations

import os
import uuid
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)
        # AbstractUser's username является обязательным полем в базе, поэтому заполним его email.
        extra_fields.setdefault("username", email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email=email, password=password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        # Для суперадмина роль тоже делаем admin.
        extra_fields.setdefault("role", "admin")
        return self._create_user(email=email, password=password, **extra_fields)


class User(AbstractUser):
    """
    Роль хранится в явном поле, чтобы быстро ограничивать доступ к админ-эндпоинтам.
    """

    class Role(models.TextChoices):
        admin = "admin", "admin"
        user = "user", "user"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.user)

    # Упростим модель: e-mail используется для логина.
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return f"{self.email} ({self.role})"


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["slug"]),
        ]

    def __str__(self) -> str:
        return self.name


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["name"]),
        ]

    def __str__(self) -> str:
        return self.name


class Photo(models.Model):
    class Source(models.TextChoices):
        web = "web", "web"
        bot = "bot", "bot"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Базовые метаданные
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120, db_index=True)
    file_size = models.BigIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Категория (может быть пустой, если пользователь не выбрал)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="photos"
    )

    # Много-теговая разметка
    tags = models.ManyToManyField(Tag, blank=True, related_name="photos")

    # Где лежит файл на диске (relative path от MEDIA_ROOT)
    # Важно: не используем FileField, чтобы контролировать структуру/путь.
    file_path = models.CharField(max_length=512, unique=True)

    source = models.CharField(max_length=8, choices=Source.choices, db_index=True)
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="photos",
    )
    owner_telegram_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["uploaded_at", "mime_type"]),
        ]

    @property
    def file_url(self) -> str:
        return f"/media/{self.file_path}"

    def storage_abs_path(self) -> str:
        return os.path.join(settings.MEDIA_ROOT, self.file_path)

    def exists(self) -> bool:
        try:
            return os.path.exists(self.storage_abs_path())
        except Exception:
            return False

    def __str__(self) -> str:
        return f"{self.original_name} ({self.id})"


class AuditLog(models.Model):
    class Action(models.TextChoices):
        upload = "upload"
        delete = "delete"
        admin_update = "admin_update"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=32, choices=Action.choices)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    actor_telegram_id = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
        ]

