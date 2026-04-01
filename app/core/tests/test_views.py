import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Course, Player, Score, Session, SessionPlayer


class AuthTest(TestCase):
    def test_login_required(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_health_check(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")


class DashboardTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

    def test_dashboard_loads(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "#TeamMinigolf")


class PlayerViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

    def test_player_list(self):
        Player.objects.create(name="Alice")
        response = self.client.get(reverse("player_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice")

    def test_player_create(self):
        response = self.client.post(reverse("player_create"), {"name": "Bob", "active": True})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Player.objects.filter(name="Bob").exists())


class ScoringTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")
        self.player = Player.objects.create(name="Scorer")
        self.course = Course.objects.create(name="TestCourse", holes_count=3)
        self.session = Session.objects.create(course=self.course, played_at="2026-01-01", season=2026)
        SessionPlayer.objects.create(session=self.session, player=self.player)

    def test_scoring_page_loads(self):
        response = self.client.get(reverse("scoring", args=[self.session.pk]))
        self.assertEqual(response.status_code, 200)

    def test_score_save(self):
        hole = self.course.holes.first()
        response = self.client.post(
            reverse("score_save", args=[self.session.pk]),
            data=json.dumps(
                {
                    "player_id": self.player.pk,
                    "hole_id": hole.pk,
                    "strokes": 3,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "saved")

    def test_score_save_invalid_player(self):
        hole = self.course.holes.first()
        other_player = Player.objects.create(name="Other")
        response = self.client.post(
            reverse("score_save", args=[self.session.pk]),
            data=json.dumps(
                {
                    "player_id": other_player.pk,
                    "hole_id": hole.pk,
                    "strokes": 3,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class AIScoreImportTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

        self.course = Course.objects.create(name="Sonnenpark", holes_count=18)
        self.player_1 = Player.objects.create(name="Alice")
        self.player_2 = Player.objects.create(name="Bob")

    def test_page_loads(self):
        response = self.client.get(reverse("ai_import"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Score Import")

    def test_import_creates_completed_session_and_scores(self):
        payload = {
            "course": "Sonnenpark",
            "date": "2026-03-10",
            "players": [
                {"name": "Alice", "scores": [2] * 18},
                {"name": "Bob", "scores": [3] * 18},
            ],
        }

        response = self.client.post(
            reverse("ai_import"),
            {"chatgpt_output": json.dumps(payload)},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        session = Session.objects.get(course=self.course, played_at="2026-03-10")
        self.assertEqual(session.status, Session.Status.COMPLETED)
        self.assertEqual(session.players.count(), 2)
        self.assertEqual(Score.objects.filter(session=session).count(), 36)

    def test_import_rejects_unknown_player(self):
        payload = {
            "course": "Sonnenpark",
            "date": "2026-03-10",
            "players": [
                {"name": "Alice", "scores": [2] * 18},
                {"name": "NotExisting", "scores": [3] * 18},
            ],
        }

        response = self.client.post(
            reverse("ai_import"),
            {"chatgpt_output": json.dumps(payload)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Players do not exist")
        self.assertEqual(Session.objects.count(), 0)
