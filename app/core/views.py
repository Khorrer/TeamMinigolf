import json
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

from .forms import AIScoreImportForm, CourseForm, PlayerForm, SessionCreateForm
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

                        messages.success(
                            request,
                            f"Game imported successfully for {course.name} ({session.played_at}).",
                        )
                        return redirect("session_detail", pk=session.pk)
    else:
        form = AIScoreImportForm()

    existing_players = Player.objects.filter(active=True).order_by("name")

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
    holes = session.course.holes.order_by("hole_number")
    players = session.players.all()
    totalPar = sum(h.par for h in holes)

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
    holes = session.course.holes.order_by("hole_number")
    players = session.players.all()
    totalPar = sum(h.par for h in holes)
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
        "totalPar": totalPar,
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
