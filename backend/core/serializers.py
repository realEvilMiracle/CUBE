from __future__ import annotations

from typing import Any

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Category, Photo, Tag


User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"],
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError("Неверный логин или пароль.")
        attrs["user"] = user
        return attrs


class UserTokenSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


def make_tokens_for_user(user: User) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "created_at")


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name", "created_at")


class PhotoSerializer(serializers.ModelSerializer):
    category = CategorySerializer(allow_null=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Photo
        fields = (
            "id",
            "original_name",
            "mime_type",
            "file_size",
            "uploaded_at",
            "category",
            "tags",
            "source",
        )


class PhotoUploadSerializer(serializers.Serializer):
    """
    Ожидается multipart/form-data:
    - file: файл изображения
    - category: строка (id UUID или slug/name) или пусто
    - tags: JSON-массив или строка через запятую
    """

    file = serializers.FileField()
    category = serializers.CharField(required=False, allow_blank=True)
    tags = serializers.CharField(required=False, allow_blank=True)

    def parse_tags(self, value: str) -> list[str]:
        value = value.strip()
        if not value:
            return []

        # Разрешим и JSON-массив, и строку с запятыми.
        if value.startswith("["):
            try:
                import json

                arr = json.loads(value)
                if isinstance(arr, list):
                    return [str(x).strip() for x in arr if str(x).strip()]
            except Exception:
                pass

        return [t.strip() for t in value.split(",") if t.strip()]

