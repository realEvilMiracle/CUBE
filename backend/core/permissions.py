from __future__ import annotations

import os

from django.conf import settings
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminRole(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and getattr(user, "role", None) == "admin")


class IsBotAuthorized(BasePermission):
    """
    Бот не использует пользовательский JWT. Вместо этого передается заголовок:
    - X-Bot-Token: BOT_API_KEY
    """

    def has_permission(self, request, view) -> bool:
        token = request.headers.get("X-Bot-Token")
        expected = getattr(settings, "BOT_API_KEY", None) or os.environ.get("BOT_API_KEY")
        return bool(token and expected and token == expected)


class ReadOnlyForAuthenticated(BasePermission):
    """
    Подходит для режимов: чтение публично, запись - только аутентифицированным.
    (На практике наш проект обычно требует логин даже для загрузки.)
    """

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

