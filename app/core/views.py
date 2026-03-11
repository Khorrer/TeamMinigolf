import json
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Min, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import Course
from django.db import models 

from .forms import CourseForm, PlayerForm, SessionCreateForm
from .models import AuditLog, Course, Hole, Player, Score, Session, SessionPlayer


# ---------------------------------------------------------------------------
# Health check (unauthenticated)
# ---------------------------------------------------------------------------
def health_check(request):
    return HttpResponse("ok")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@login_required
def dashboard(request):
    live_sessions = Session.objects.filter(status=Session.Status.LIVE).select_related("course")[:5]
    recent_sessions = (
        Session.objects.filter(status=Session.Status.COMPLETED)
        .select_related("course")[:5]
    )
    player_count = Player.objects.filter(active=True).count()
    course_count = Course.objects.count()
    return render(request, "core/dashboard.html", {
        "live_sessions": live_sessions,
        "recent_sessions": recent_sessions,
        "player_count": player_count,
        "course_count": course_count,
    })


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------
@login_required
def player_list(request):
    players = Player.objects.annotate(
        session_count=Count("sessions"),
        avg_strokes=Avg("scores__strokes"),
    )
    return render(request, "core/player_list.html", {"players": players})


@login_required
def player_create(request):
    form = PlayerForm(request.POST or None)
    if form.is_valid():
        form.save()
        return redirect("player_list")
    return render(request, "core/player_form.html", {"form": form, "title": "Spieler anlegen"})


@login_required
def player_edit(request, pk):
    player = get_object_or_404(Player, pk=pk)
    form = PlayerForm(request.POST or None, instance=player)
    if form.is_valid():
        form.save()
        return redirect("player_list")
    return render(request, "core/player_form.html", {"form": form, "title": "Spieler bearbeiten"})


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------
@login_required
def course_list(request):
    courses = Course.objects.annotate(session_count=Count("sessions"))
    return render(request, "core/course_list.html", {"courses": courses})

@login_required
def course_create(request):
    form = CourseForm(request.POST or None)
    if form.is_valid():
        form.save()
        return redirect("course_list")
    return render(request, "core/course_form.html", {"form": form, "title": "Anlage erstellen"})


@login_required
def course_detail(request, pk):
    course = get_object_or_404(Course.objects.prefetch_related("holes"), pk=pk)
    holes = course.holes.annotate(avg_strokes=Avg("scores__strokes"))
    return render(request, "core/course_detail.html", {"course": course, "holes": holes})


@login_required
def course_edit(request, pk):
    course = get_object_or_404(Course.objects.prefetch_related("holes"), pk=pk)
    # Hole alle existierenden Bahnen oder erstelle sie, falls nötig
    holes = course.holes.annotate(avg_strokes=Avg("scores__strokes"))
    
    if request.method == "POST":
        for hole in holes:
            par_value = request.POST.get(f'par_{hole.hole_number}')
            if par_value:
                hole.par = par_value
                hole.save()
        return redirect('course_list')

    return render(request, 'core/course_pars.html', {
        'course': course,
        'holes': holes
    })

# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
@login_required
def session_list(request):
    sessions = Session.objects.select_related("course").prefetch_related("players")
    status_filter = request.GET.get("status")
    if status_filter in ("live", "completed"):
        sessions = sessions.filter(status=status_filter)
    season_filter = request.GET.get("season")
    if season_filter and season_filter.isdigit():
        sessions = sessions.filter(season=int(season_filter))
    seasons = Session.objects.values_list("season", flat=True).distinct().order_by("-season")
    return render(request, "core/session_list.html", {
        "sessions": sessions,
        "seasons": seasons,
        "current_status": status_filter,
        "current_season": season_filter,
    })


@login_required
def session_create(request):
    if request.method == "POST":
        form = SessionCreateForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            session.created_by = request.user
            session.save()
            for player in form.cleaned_data["players"]:
                SessionPlayer.objects.create(session=session, player=player)
            return redirect("scoring", pk=session.pk)
    else:
        form = SessionCreateForm(initial={
            "played_at": date.today(),
            "season": date.today().year,
        })
    return render(request, "core/session_create.html", {"form": form})


@login_required
def session_detail(request, pk):
    session = get_object_or_404(
        Session.objects.select_related("course").prefetch_related("players", "scores__hole", "scores__player"),
        pk=pk,
    )
    holes = session.course.holes.order_by("hole_number")
    players = session.players.all()

    # Build score grid: {player_id: {hole_id: strokes}}
    score_map = {}
    for score in session.scores.all():
        score_map.setdefault(score.player_id, {})[score.hole_id] = score.strokes

    player_data = []
    for player in players:
        scores_for_player = []
        total = 0
        for hole in holes:
            s = score_map.get(player.id, {}).get(hole.id)
            scores_for_player.append(s)
            if s:
                total += s
        player_data.append({
            "player": player,
            "scores": scores_for_player,
            "total": total,
        })

    return render(request, "core/session_detail.html", {
        "session": session,
        "holes": holes,
        "player_data": player_data,
    })


@login_required
@require_POST
def session_complete(request, pk):
    session = get_object_or_404(Session, pk=pk)
    session.status = Session.Status.COMPLETED
    session.save()
    return redirect("session_detail", pk=pk)


# ---------------------------------------------------------------------------
# Scoring (Live)
# ---------------------------------------------------------------------------
@login_required
def scoring(request, pk):
    session = get_object_or_404(
        Session.objects.select_related("course").prefetch_related("players"),
        pk=pk,
    )
    holes = session.course.holes.order_by("hole_number")
    players = session.players.all()
    existing_scores = {
        (s.player_id, s.hole_id): s.strokes
        for s in session.scores.all()
    }
    # JSON-serializable version for JavaScript: {"playerId_holeId": strokes}
    scores_json = json.dumps({
        f"{pid}_{hid}": strokes for (pid, hid), strokes in existing_scores.items()
    })
    return render(request, "core/scoring.html", {
        "session": session,
        "holes": holes,
        "players": players,
        "existing_scores": existing_scores,
        "existing_scores_json": scores_json,
    })


@login_required
@require_POST
def score_save(request, session_pk):
    session = get_object_or_404(Session, pk=session_pk)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    player_id = data.get("player_id")
    hole_id = data.get("hole_id")
    strokes = data.get("strokes")

    if not all([player_id, hole_id]):
        return JsonResponse({"error": "Missing player_id or hole_id"}, status=400)

    # Validate player is part of session
    if not session.session_players.filter(player_id=player_id).exists():
        return JsonResponse({"error": "Player not in session"}, status=400)

    # Validate hole belongs to session's course
    hole = Hole.objects.filter(pk=hole_id, course=session.course).first()
    if not hole:
        return JsonResponse({"error": "Invalid hole"}, status=400)

    if strokes is None or strokes == "":
        # Delete score if exists
        deleted, _ = Score.objects.filter(
            session=session, player_id=player_id, hole_id=hole_id
        ).delete()
        if deleted:
            AuditLog.objects.create(
                user=request.user,
                action="delete",
                model_name="Score",
                object_id=0,
                details={"session": session.pk, "player": player_id, "hole": hole_id},
            )
        return JsonResponse({"status": "deleted"})

    strokes = int(strokes)
    if strokes < 1 or strokes > 10:
        return JsonResponse({"error": "Strokes must be 1-10"}, status=400)

    score, created = Score.objects.update_or_create(
        session=session,
        player_id=player_id,
        hole_id=hole_id,
        defaults={"strokes": strokes},
    )
    AuditLog.objects.create(
        user=request.user,
        action="create" if created else "update",
        model_name="Score",
        object_id=score.pk,
        details={"session": session.pk, "player": player_id, "hole": hole_id, "strokes": strokes},
    )

    # Return updated total for player
    total = session.scores.filter(player_id=player_id).aggregate(t=Sum("strokes"))["t"] or 0
    return JsonResponse({"status": "saved", "total": total})


# ---------------------------------------------------------------------------
# Stats & Leaderboard
# ---------------------------------------------------------------------------
@login_required
def stats_overview(request):
    season = request.GET.get("season")
    course_id = request.GET.get("course")

    score_qs = Score.objects.all()
    if season and season.isdigit():
        score_qs = score_qs.filter(session__season=int(season))
    if course_id and course_id.isdigit():
        score_qs = score_qs.filter(hole__course_id=int(course_id))

    # Per-player stats
    player_stats = (
        score_qs.values("player__id", "player__name")
        .annotate(
            avg_strokes=Avg("strokes"),
            total_strokes=Sum("strokes"),
            best_hole=Min("strokes"),
            rounds=Count("session", distinct=True),
        )
        .order_by("avg_strokes")
    )

    # Per-hole stats (if course selected)
    hole_stats = []
    if course_id and course_id.isdigit():
        hole_stats = (
            score_qs.filter(hole__course_id=int(course_id))
            .values("hole__hole_number", "hole__par")
            .annotate(avg_strokes=Avg("strokes"), count=Count("id"))
            .order_by("hole__hole_number")
        )

    seasons = Session.objects.values_list("season", flat=True).distinct().order_by("-season")
    courses = Course.objects.all()

    return render(request, "core/stats.html", {
        "player_stats": player_stats,
        "hole_stats": hole_stats,
        "seasons": seasons,
        "courses": courses,
        "current_season": season,
        "current_course": course_id,
    })


@login_required
def leaderboard(request):
    season = request.GET.get("season", str(date.today().year))

    score_qs = Score.objects.all()
    if season and season.isdigit():
        score_qs = score_qs.filter(session__season=int(season))

    leaderboard_data = (
        score_qs.values("player__id", "player__name")
        .annotate(
            avg_strokes=Avg("strokes"),
            total_rounds=Count("session", distinct=True),
            total_strokes=Sum("strokes"),
        )
        .order_by("avg_strokes")
    )

    seasons = Session.objects.values_list("season", flat=True).distinct().order_by("-season")

    return render(request, "core/leaderboard.html", {
        "leaderboard": leaderboard_data,
        "seasons": seasons,
        "current_season": season,
    })
