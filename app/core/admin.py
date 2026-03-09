from django.contrib import admin

from .models import AuditLog, Course, Hole, Player, Score, Session, SessionPlayer


class HoleInline(admin.TabularInline):
    model = Hole
    extra = 0


class SessionPlayerInline(admin.TabularInline):
    model = SessionPlayer
    extra = 0


class ScoreInline(admin.TabularInline):
    model = Score
    extra = 0


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("name",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "holes_count", "created_at")
    inlines = [HoleInline]


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("course", "played_at", "season", "status", "created_by")
    list_filter = ("status", "season", "course")
    inlines = [SessionPlayerInline, ScoreInline]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "model_name", "object_id", "user", "created_at")
    list_filter = ("action", "model_name")
    readonly_fields = ("user", "action", "model_name", "object_id", "details", "created_at")
