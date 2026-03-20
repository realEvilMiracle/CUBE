from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from core.models import AuditLog, Category, Photo, Tag, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("email", "role", "is_staff", "is_active", "last_login")
    ordering = ("email",)
    search_fields = ("email",)

    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Role",
            {"fields": ("role",)},
        ),
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    ordering = ("-created_at",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    ordering = ("-created_at",)


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("original_name", "source", "uploaded_at", "mime_type", "file_size")
    list_filter = ("source", "mime_type", "uploaded_at")
    search_fields = ("original_name",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor_user", "actor_telegram_id", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("actor_telegram_id",)

