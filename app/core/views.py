import json
import random
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, Min, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import Course
from django.db import models 
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm

from .best_player import BEST_PLAYER_NAME, ensure_best_player_in_session, recompute_best_scores_for_session
from .forms import AIScoreImportForm, CourseForm, PlayerForm, SessionCreateForm
from .leaderboard_metrics import build_leaderboard_metrics, build_player_profile_stats
from .models import AuditLog, Course, Hole, Player, Score, Session, SessionPlayer


AI_SCORE_IMPORT_PROMPT = """You are helping to digitize a minigolf scorecard.

I will upload a photo of a minigolf scorecard.

Extract the information and return ONLY valid JSON.

Format:

{
\"course\": \"Course Name\",
\"date\": \"YYYY-MM-DD\",
\"players\": [
{
\"name\": \"Player Name\",
\"scores\": [2,3,1,4,2,3,2,3,4,2,3,2,1,3,2,4,3,2]
}
]
}

Rules:

* detect all players
* take the Date from the scorecard or use today's date if not available
* each player must have 18 scores
* ask for numbers if handwriting is unclear and under 75% confidence and for the specific hole (e.g. "Player X, hole 5")
* do not add explanations
* output JSON only
* try to match course name to existing courses in our system, but if not sure, just return the name as it appears on the scorecard
* existing courses: 
    - Gartengolfanlage Eppelheim
* try to match player names to existing players in our system, but if not sure, just return the name as it appears on the scorecard
* existing Players: """


# ---------------------------------------------------------------------------
# Health check (unauthenticated)
# ---------------------------------------------------------------------------
def health_check(request):
    return HttpResponse("ok")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class BootstrapSignUpForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

def signup(request):
    if request.method == 'POST':
        form = BootstrapSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('session_list') # Leitet zur Übersicht weiter
    else:
        form = BootstrapSignUpForm()
    return render(request, 'core/signup.html', {'form': form})


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
    players = Player.objects.exclude(name__iexact=BEST_PLAYER_NAME).annotate(
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
    if player.name.casefold() == BEST_PLAYER_NAME.casefold():
        messages.error(request, "'Best' wird automatisch verwaltet und kann nicht bearbeitet werden.")
        return redirect("player_list")
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
            selected_players = form.cleaned_data["players"]
            random_players = selected_players.order_by('?') 
            for player in random_players:
                SessionPlayer.objects.create(session=session, player=player)
            ensure_best_player_in_session(session)
            return redirect("scoring", pk=session.pk)
    else:
        form = SessionCreateForm(initial={
            "played_at": date.today(),
            "season": date.today().year,
        })
    return render(request, "core/session_create.html", {"form": form})


@login_required
def ai_import(request):
    if request.method == "POST":
        form = AIScoreImportForm(request.POST)
        if form.is_valid():
            payload = form.cleaned_data["parsed_payload"]
            course_name = payload["course"]
            imported_players = payload["players"]

            course = Course.objects.filter(name__iexact=course_name).first()
            if not course:
                form.add_error(
                    "chatgpt_output",
                    f"Course '{course_name}' does not exist. Please create it first.",
                )
            else:
                holes = list(course.holes.order_by("hole_number")[:18])
                if len(holes) != 18:
                    form.add_error(
                        "chatgpt_output",
                        f"Course '{course.name}' must have exactly 18 holes.",
                    )
                else:
                    resolved_players = []
                    missing_players = []
                    for player_data in imported_players:
                        player = Player.objects.filter(name__iexact=player_data["name"]).first()
                        if player is None:
                            missing_players.append(player_data["name"])
                        else:
                            resolved_players.append((player, player_data["scores"]))

                    if missing_players:
                        form.add_error(
                            "chatgpt_output",
                            "Players do not exist: " + ", ".join(missing_players),
                        )
                    else:
                        with transaction.atomic():
                            session = Session.objects.create(
                                course=course,
                                played_at=payload["date"],
                                season=payload["date"].year,
                                status=Session.Status.COMPLETED,
                                notes="Created via AI Score Import",
                                created_by=request.user,
                            )

                            SessionPlayer.objects.bulk_create(
                                [
                                    SessionPlayer(session=session, player=player)
                                    for player, _ in resolved_players
                                ]
                            )

                            ensure_best_player_in_session(session)

                            score_rows = []
                            for player, scores in resolved_players:
                                for index, strokes in enumerate(scores):
                                    score_rows.append(
                                        Score(
                                            session=session,
                                            player=player,
                                            hole=holes[index],
                                            strokes=strokes,
                                        )
                                    )
                            Score.objects.bulk_create(score_rows)
                            recompute_best_scores_for_session(session)

                        messages.success(
                            request,
                            f"Game imported successfully for {course.name} ({session.played_at}).",
                        )
                        return redirect("session_detail", pk=session.pk)
    else:
        form = AIScoreImportForm()

    existing_players = (
        Player.objects.filter(active=True)
        .exclude(name__iexact=BEST_PLAYER_NAME)
        .order_by("name")
    )

    return render(
        request,
        "core/ai_import.html",
        {
            "form": form,
            "chatgpt_prompt": AI_SCORE_IMPORT_PROMPT,
            "existing_players": existing_players,
        },
    )


@login_required
def session_detail(request, pk):
    session = get_object_or_404(
        Session.objects.select_related("course").prefetch_related("players", "scores__hole", "scores__player"),
        pk=pk,
    )
    recompute_best_scores_for_session(session)
    session = get_object_or_404(
        Session.objects.select_related("course").prefetch_related("players", "scores__hole", "scores__player"),
        pk=pk,
    )
    holes = session.course.holes.order_by("hole_number")
    players = session.players.all()
    totalPar = sum((h.par or 0) for h in holes)

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
        "totalPar": totalPar,
    })

@login_required
def logout(request):
    from django.contrib.auth import logout as auth_logout
    auth_logout(request)
    return redirect("login")

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
    best_player = recompute_best_scores_for_session(session)
    holes = session.course.holes.order_by("hole_number")
    players = session.players.exclude(pk=best_player.pk).all().order_by('sessionplayer__id')
    totalPar = sum((h.par or 0) for h in holes)
    existing_scores = {
        (s.player_id, s.hole_id): s.strokes
        for s in session.scores.all()
    }
    best_scores = [
        {
            "hole_id": h.id,
            "strokes": existing_scores.get((best_player.id, h.id)),
        }
        for h in holes
    ]
    best_total = sum((item["strokes"] or 0) for item in best_scores)
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
        "totalPar": totalPar,
        "best_scores": best_scores,
        "best_total": best_total,
    })


@login_required
@require_POST
def score_save(request, session_pk):
    session = get_object_or_404(Session, pk=session_pk)
    best_player = ensure_best_player_in_session(session)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    player_id = data.get("player_id")
    hole_id = data.get("hole_id")
    strokes = data.get("strokes")

    if not all([player_id, hole_id]):
        return JsonResponse({"error": "Missing player_id or hole_id"}, status=400)

    try:
        player_id = int(player_id)
        hole_id = int(hole_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid player_id or hole_id"}, status=400)

    if player_id == best_player.id:
        return JsonResponse({"error": "Best player is computed automatically"}, status=400)

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
        recompute_best_scores_for_session(session, hole_ids=[hole_id])
        best_hole_strokes = (
            Score.objects.filter(
                session=session,
                player=best_player,
                hole_id=hole_id,
            )
            .values_list("strokes", flat=True)
            .first()
        )
        best_total = session.scores.filter(player=best_player).aggregate(t=Sum("strokes"))["t"] or 0
        return JsonResponse({
            "status": "deleted",
            "best_hole_strokes": best_hole_strokes,
            "best_total": best_total,
        })

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
    recompute_best_scores_for_session(session, hole_ids=[hole_id])
    best_hole_strokes = (
        Score.objects.filter(
            session=session,
            player=best_player,
            hole_id=hole_id,
        )
        .values_list("strokes", flat=True)
        .first()
    )
    best_total = session.scores.filter(player=best_player).aggregate(t=Sum("strokes"))["t"] or 0
    return JsonResponse({
        "status": "saved",
        "total": total,
        "best_hole_strokes": best_hole_strokes,
        "best_total": best_total,
    })


# ---------------------------------------------------------------------------
# Stats & Leaderboard
# ---------------------------------------------------------------------------
@login_required
def stats_overview(request):
    season = request.GET.get("season")
    course_id = request.GET.get("course")

    score_qs = Score.objects.exclude(player__name__iexact=BEST_PLAYER_NAME)
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
    season_raw = request.GET.get("season", str(date.today().year))
    season = int(season_raw) if season_raw and season_raw.isdigit() else None

    leaderboard_metrics = build_leaderboard_metrics(season=season)

    seasons = Session.objects.values_list("season", flat=True).distinct().order_by("-season")

    return render(request, "core/leaderboard.html", {
        "leaderboard_metrics": leaderboard_metrics,
        "seasons": seasons,
        "current_season": season_raw,
    })


@login_required
def player_profile_stats(request, pk):
    season_raw = request.GET.get("season")
    season = int(season_raw) if season_raw and season_raw.isdigit() else None
    player = get_object_or_404(Player, pk=pk)

    if player.name.casefold() == BEST_PLAYER_NAME.casefold():
        return JsonResponse({"error": "Best player is computed automatically"}, status=400)

    payload = build_player_profile_stats(player, season=season)
    return JsonResponse(payload)
