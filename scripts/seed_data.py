#!/usr/bin/env python
"""Seed example data for development."""

import os
import sys
from datetime import date

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
django.setup()

from django.contrib.auth.models import User  # noqa: E402

from core.models import Course, Hole, Player, Score, Session, SessionPlayer  # noqa: E402

print("Seeding data...")

# Create superuser if not exists
if not User.objects.filter(username="admin").exists():
    User.objects.create_superuser("admin", "admin@example.com", "admin")
    print("  Created superuser: admin / admin")

# Players
player_names = ["Jonathan", "Max", "Anna", "Lukas", "Sophie"]
players = []
for name in player_names:
    p, created = Player.objects.get_or_create(name=name)
    players.append(p)
    if created:
        print(f"  Created player: {name}")

# Course
course, created = Course.objects.get_or_create(
    name="Minigolf am See",
    defaults={"location": "Musterstadt", "holes_count": 18},
)
if created:
    print(f"  Created course: {course.name} ({course.holes_count} holes)")
    # Set par values
    pars = [2, 3, 2, 3, 4, 2, 3, 2, 3, 4, 2, 3, 2, 3, 4, 2, 3, 3]
    for hole in course.holes.order_by("hole_number"):
        hole.par = pars[hole.hole_number - 1] if hole.hole_number <= len(pars) else 3
        hole.save()

# Example session
if not Session.objects.exists():
    import random

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
    print(f"  Created example session with {session.scores.count()} scores")

print("Seeding complete!")
