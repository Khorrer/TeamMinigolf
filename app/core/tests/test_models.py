from django.db.utils import IntegrityError
from django.test import TestCase

from core.models import Course, Hole, Player, Score, Session, SessionPlayer


class PlayerModelTest(TestCase):
    def test_create_player(self):
        p = Player.objects.create(name="TestSpieler")
        self.assertEqual(str(p), "TestSpieler")
        self.assertTrue(p.active)

    def test_unique_name(self):
        Player.objects.create(name="Unique")
        with self.assertRaises(IntegrityError):
            Player.objects.create(name="Unique")


class CourseModelTest(TestCase):
    def test_auto_creates_holes(self):
        course = Course.objects.create(name="Testanlage", holes_count=12)
        self.assertEqual(course.holes.count(), 12)
        self.assertEqual(
            list(course.holes.values_list("hole_number", flat=True)),
            list(range(1, 13)),
        )

    def test_str(self):
        course = Course.objects.create(name="Golfpark", holes_count=18)
        self.assertEqual(str(course), "Golfpark")


class HoleModelTest(TestCase):
    def test_unique_together(self):
        course = Course.objects.create(name="Test", holes_count=1)
        # Hole 1 already created by Course.save()
        with self.assertRaises(IntegrityError):
            Hole.objects.create(course=course, hole_number=1)


class ScoreModelTest(TestCase):
    def setUp(self):
        self.player = Player.objects.create(name="Scorer")
        self.course = Course.objects.create(name="ScoreCourse", holes_count=3)
        self.session = Session.objects.create(course=self.course, played_at="2026-01-01", season=2026)
        SessionPlayer.objects.create(session=self.session, player=self.player)

    def test_create_score(self):
        hole = self.course.holes.first()
        score = Score.objects.create(session=self.session, player=self.player, hole=hole, strokes=3)
        self.assertEqual(score.strokes, 3)

    def test_unique_constraint(self):
        hole = self.course.holes.first()
        Score.objects.create(session=self.session, player=self.player, hole=hole, strokes=2)
        with self.assertRaises(IntegrityError):
            Score.objects.create(session=self.session, player=self.player, hole=hole, strokes=4)

    def test_total_strokes(self):
        for hole in self.course.holes.all():
            Score.objects.create(session=self.session, player=self.player, hole=hole, strokes=3)
        self.assertEqual(self.session.total_strokes(self.player), 9)
