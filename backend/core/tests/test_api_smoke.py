import io
import os
import tempfile
from datetime import datetime

from PIL import Image
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Category, Tag, User, Photo


def make_png_bytes(color=(255, 0, 0), size=(64, 64)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class APISmokeTests(TestCase):
    def setUp(self):
        self.tmp_media = tempfile.TemporaryDirectory(prefix="media_test_")
        settings.MEDIA_ROOT = self.tmp_media.name

        self.client = APIClient()

        self.user = User.objects.create_user(
            email="user@test.local", password="pass12345", role=User.Role.user
        )
        self.admin = User.objects.create_user(
            email="admin@test.local", password="pass12345", role=User.Role.admin
        )

        self.category = Category.objects.create(name="Природа", slug="priroda")
        self.tag1 = Tag.objects.create(name="зима")

    def tearDown(self):
        self.tmp_media.cleanup()

    def _login(self, email: str, password: str) -> str:
        resp = self.client.post(
            "/api/auth/login/",
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()["access"]

    def test_upload_search_export_delete(self):
        access = self._login("user@test.local", "pass12345")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        png = make_png_bytes()
        uploaded = SimpleUploadedFile("test.png", png, content_type="image/png")

        resp = self.client.post(
            "/api/photos/upload/",
            {"file": uploaded, "category": self.category.slug, "tags": "зима,события"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201)
        photo_id = resp.json()["id"]

        resp = self.client.get("/api/photos/", {"q": "зима", "page_size": 10})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertTrue(any(p["id"] == photo_id for p in results))

        resp = self.client.get("/api/photos/export/", {"q": "зима", "limit": 10})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("zip", resp["Content-Type"].lower())

        # delete: только admin
        admin_access = self._login("admin@test.local", "pass12345")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_access}")
        resp = self.client.delete(f"/api/photos/{photo_id}/")
        self.assertIn(resp.status_code, (204, 200))
        self.assertFalse(Photo.objects.filter(id=photo_id).exists())

