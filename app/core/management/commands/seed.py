import random
from datetime import date

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from core.models import Course, Player, Score, Session, SessionPlayer


class Command(BaseCommand):
    help = "Seed the database with example data."

    def handle(self, *args, **options):
        # Superuser
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin")
            self.stdout.write(self.style.SUCCESS("Created superuser: admin / admin"))

        # Players
        player_names = ["Jonathan", "Max", "Anna", "Lukas", "Sophie"]
        players = []
        for name in player_names:
            p, created = Player.objects.get_or_create(name=name)
            players.append(p)
            if created:
                self.stdout.write(f"  Created player: {name}")

        # Course
        course, created = Course.objects.get_or_create(
            name="Minigolf am See",
            defaults={"location": "Musterstadt", "holes_count": 18},
        )
        if created:
            self.stdout.write(f"  Created course: {course.name}")
            pars = [2, 3, 2, 3, 4, 2, 3, 2, 3, 4, 2, 3, 2, 3, 4, 2, 3, 3]
            for hole in course.holes.order_by("hole_number"):
                hole.par = pars[hole.hole_number - 1] if hole.hole_number <= len(pars) else 3
                hole.save()

        # Example session
        if not Session.objects.exists():
            session = Session.objects.create(
                course=course,
                played_at=date.today(),
                season=date.today().year,
                status=Session.Status.COMPLETED,
                notes="Beispiel-Spieltag",
            )
            for player in players[:4]:
                SessionPlayer.objects.create(session=session, player=player)
                for hole in course.holes.all():
                    Score.objects.create(
                        session=session,
                        player=player,
                        hole=hole,
                        strokes=random.randint(1, 6),
                    )
            self.stdout.write(self.style.SUCCESS(f"  Created session with {session.scores.count()} scores"))

        self.stdout.write(self.style.SUCCESS("Seeding complete!"))
