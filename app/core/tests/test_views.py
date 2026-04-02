import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
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


class SessionCreateChoiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

    def test_session_create_page_offers_ai_import(self):
        response = self.client.get(reverse("session_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Standard")
        self.assertContains(response, "KI Import")
        self.assertContains(response, reverse("ai_import"))

    def test_ai_import_page_offers_standard_flow(self):
        response = self.client.get(reverse("ai_import"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Score Import")
        self.assertContains(response, reverse("session_create"))


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
        self.session = Session.objects.create(
            course=self.course, played_at="2026-01-01", season=2026
        )
        SessionPlayer.objects.create(session=self.session, player=self.player)

    def test_scoring_page_loads(self):
        response = self.client.get(reverse("scoring", args=[self.session.pk]))
        self.assertEqual(response.status_code, 200)

    def test_score_save(self):
        hole = self.course.holes.first()
        response = self.client.post(
            reverse("score_save", args=[self.session.pk]),
            data=json.dumps({
                "player_id": self.player.pk,
                "hole_id": hole.pk,
                "strokes": 3,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "saved")
        self.assertIsNotNone(data.get("best_hole_strokes"))
        self.assertTrue(
            Score.objects.filter(
                session=self.session,
                player__name="Best",
                hole=hole,
                strokes=3,
            ).exists()
        )

    def test_score_save_invalid_player(self):
        hole = self.course.holes.first()
        other_player = Player.objects.create(name="Other")
        response = self.client.post(
            reverse("score_save", args=[self.session.pk]),
            data=json.dumps({
                "player_id": other_player.pk,
                "hole_id": hole.pk,
                "strokes": 3,
            }),
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
        self.assertEqual(session.players.count(), 3)
        self.assertEqual(Score.objects.filter(session=session).count(), 54)

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


class LeaderboardMetricsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("metricuser", password="testpass123")
        self.client.login(username="metricuser", password="testpass123")

        self.course = Course.objects.create(name="MetricPark", holes_count=18)
        self.alice = Player.objects.create(name="Alice")
        self.bob = Player.objects.create(name="Bob")

        self.session = Session.objects.create(
            course=self.course,
            played_at="2026-03-01",
            season=2026,
            status=Session.Status.COMPLETED,
        )
        SessionPlayer.objects.create(session=self.session, player=self.alice)
        SessionPlayer.objects.create(session=self.session, player=self.bob)

        holes = list(self.course.holes.order_by("hole_number"))
        for hole in holes:
            Score.objects.create(session=self.session, player=self.alice, hole=hole, strokes=2)
            Score.objects.create(session=self.session, player=self.bob, hole=hole, strokes=3)

    def test_leaderboard_renders_metric_cards(self):
        response = self.client.get(reverse("leaderboard"), {"season": 2026})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Average Score")
        self.assertContains(response, "Win Percentage")
        self.assertContains(response, "Hole-in-One King")
        self.assertContains(response, "All-Time Low")

    def test_player_profile_stats_api(self):
        response = self.client.get(
            reverse("player_profile_stats", args=[self.alice.pk]),
            {"season": 2026},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["player"]["name"], "Alice")
        self.assertIn("score_distribution", data)
        self.assertEqual(len(data["score_distribution"]["labels"]), 7)
