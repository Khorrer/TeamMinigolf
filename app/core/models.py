from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Player(models.Model):
    name = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Course(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200, blank=True, default="")
    holes_count = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(36)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            # Auto-create holes when a new course is saved
            Hole.objects.bulk_create(
                [Hole(course=self, hole_number=i) for i in range(1, self.holes_count + 1)]
            )


class Hole(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="holes")
    hole_number = models.PositiveSmallIntegerField()
    par = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(7)]
    )

    class Meta:
        unique_together = ("course", "hole_number")
        ordering = ["course", "hole_number"]

    def __str__(self):
        return f"{self.course.name} – Bahn {self.hole_number}"


class Session(models.Model):
    class Status(models.TextChoices):
        LIVE = "live", "Live"
        COMPLETED = "completed", "Abgeschlossen"

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="sessions")
    played_at = models.DateField()
    season = models.PositiveSmallIntegerField(help_text="Jahr der Saison")
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.LIVE)
    players = models.ManyToManyField(Player, through="SessionPlayer", related_name="sessions")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-played_at", "-created_at"]

    def __str__(self):
        return f"{self.course.name} – {self.played_at}"

    def total_strokes(self, player):
        return (
            self.scores.filter(player=player).aggregate(total=models.Sum("strokes"))["total"] or 0
        )


class SessionPlayer(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="session_players")
    player = models.ForeignKey(Player, on_delete=models.PROTECT)

    class Meta:
        unique_together = ("session", "player")

    def __str__(self):
        return f"{self.session} – {self.player}"


class Score(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="scores")
    player = models.ForeignKey(Player, on_delete=models.PROTECT, related_name="scores")
    hole = models.ForeignKey(Hole, on_delete=models.PROTECT, related_name="scores")
    strokes = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("session", "player", "hole")
        indexes = [
            models.Index(fields=["session", "player"]),
            models.Index(fields=["hole"]),
        ]

    def __str__(self):
        return f"{self.player} – {self.hole}: {self.strokes}"


class AuditLog(models.Model):
    """Tracks changes to scores for accountability."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    action = models.CharField(max_length=20)  # create, update, delete
    model_name = models.CharField(max_length=50)
    object_id = models.PositiveIntegerField()
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["model_name", "object_id"]),
        ]

    def __str__(self):
        return f"{self.action} {self.model_name}#{self.object_id}"
