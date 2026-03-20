from django.urls import path

from core.views import (
    CategoryViewSet,
    PhotoViewSet,
    ReportViewSet,
    TagViewSet,
    UserViewSet,
    auth_login,
    auth_register,
    bot_upload,
    bot_export,
    bot_search,
    qr_image,
)


urlpatterns = [
    # Auth (site)
    path("auth/register/", auth_register, name="auth_register"),
    path("auth/login/", auth_login, name="auth_login"),
    # Bot entrypoints (bot api key, no user JWT)
    path("bot/upload/", bot_upload, name="bot_upload"),
    path("bot/search/", bot_search, name="bot_search"),
    path("bot/export/", bot_export, name="bot_export"),
    # Users / admin
    path("admin/users/", UserViewSet.as_view({"get": "list"}), name="admin_users_list"),
    # Categories & Tags
    path("categories/", CategoryViewSet.as_view({"get": "list"}), name="categories_list"),
    path("categories/create/", CategoryViewSet.as_view({"post": "create"}), name="categories_create"),
    path("tags/", TagViewSet.as_view({"get": "list"}), name="tags_list"),
    path("tags/create/", TagViewSet.as_view({"post": "create"}), name="tags_create"),
    # Photos
    path("photos/", PhotoViewSet.as_view({"get": "list"}), name="photos_list"),
    path("photos/upload/", PhotoViewSet.as_view({"post": "upload"}), name="photos_upload"),
    path("photos/<uuid:photo_id>/file/", PhotoViewSet.as_view({"get": "file"}), name="photos_file"),
    path(
        "photos/<uuid:photo_id>/",
        PhotoViewSet.as_view({"delete": "destroy"}),
        name="photos_destroy",
    ),
    path("photos/export/", PhotoViewSet.as_view({"get": "export"}), name="photos_export"),
    # QR-код
    path("qr/", qr_image, name="qr_image"),
    # Reports
    path("reports/summary/", ReportViewSet.as_view({"get": "summary"}), name="reports_summary"),
    path("reports/top-tags/", ReportViewSet.as_view({"get": "top_tags"}), name="reports_top_tags"),
]

