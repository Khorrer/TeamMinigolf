from __future__ import annotations

from collections import defaultdict
from statistics import mean

from django.db.models import Avg, Count, Sum

from .best_player import BEST_PLAYER_NAME
from .models import Player, Score

FULL_ROUND_HOLES = 18
MAX_STROKES_FOR_BOUNCE_BACK = 10


def _base_score_queryset(season: int | None = None):
    qs = Score.objects.exclude(player__name__iexact=BEST_PLAYER_NAME)
    if season is not None:
        qs = qs.filter(session__season=season)
    return qs


def _full_round_totals_queryset(season: int | None = None):
    return (
        _base_score_queryset(season)
        .filter(session__course__holes_count=FULL_ROUND_HOLES)
        .values("session_id", "player_id", "player__name")
        .annotate(
            round_total=Sum("strokes"),
            hole_count=Count("hole_id", distinct=True),
        )
        .filter(hole_count=FULL_ROUND_HOLES)
    )


def build_leaderboard_metrics(season: int | None = None) -> list[dict]:
    round_totals = list(_full_round_totals_queryset(season))

    if not round_totals:
        return [
            {"id": "average_score", "title": "Average Score", "unit": "Schlaege", "direction": "asc", "ranking": []},
            {"id": "win_percentage", "title": "Win Percentage", "unit": "%", "direction": "desc", "ranking": []},
            {"id": "hole_in_one", "title": "Hole-in-One King", "unit": "HIO", "direction": "desc", "ranking": []},
            {"id": "all_time_low", "title": "All-Time Low", "unit": "Schlaege", "direction": "asc", "ranking": []},
        ]

    per_player_acc: dict[int, dict] = {}
    for row in round_totals:
        player_id = row["player_id"]
        acc = per_player_acc.setdefault(
            player_id,
            {
                "player_id": player_id,
                "player_name": row["player__name"],
                "round_totals": [],
            },
        )
        acc["round_totals"].append(row["round_total"])

    wins_by_player: dict[int, int] = defaultdict(int)
    best_total_by_session: dict[int, int] = {}
    for row in round_totals:
        sid = row["session_id"]
        total = row["round_total"]
        current = best_total_by_session.get(sid)
        if current is None or total < current:
            best_total_by_session[sid] = total

    for row in round_totals:
        if row["round_total"] == best_total_by_session[row["session_id"]]:
            wins_by_player[row["player_id"]] += 1

    hio_rows = _base_score_queryset(season).filter(strokes=1).values("player_id").annotate(count=Count("id"))
    hio_by_player = {row["player_id"]: row["count"] for row in hio_rows}

    metrics = {
        "average_score": [],
        "win_percentage": [],
        "hole_in_one": [],
        "all_time_low": [],
    }

    for player_id, row in per_player_acc.items():
        rounds_played = len(row["round_totals"])
        wins = wins_by_player.get(player_id, 0)
        average_score = mean(row["round_totals"]) if row["round_totals"] else 0
        all_time_low = min(row["round_totals"]) if row["round_totals"] else 0

        metrics["average_score"].append(
            {
                "player_id": player_id,
                "player_name": row["player_name"],
                "value": float(average_score),
                "rounds": rounds_played,
            }
        )
        metrics["win_percentage"].append(
            {
                "player_id": player_id,
                "player_name": row["player_name"],
                "value": (wins * 100.0 / rounds_played) if rounds_played else 0.0,
                "wins": wins,
                "rounds": rounds_played,
            }
        )
        metrics["hole_in_one"].append(
            {
                "player_id": player_id,
                "player_name": row["player_name"],
                "value": hio_by_player.get(player_id, 0),
                "rounds": rounds_played,
            }
        )
        metrics["all_time_low"].append(
            {
                "player_id": player_id,
                "player_name": row["player_name"],
                "value": int(all_time_low),
                "rounds": rounds_played,
            }
        )

    metrics["average_score"].sort(key=lambda e: (e["value"], -e["rounds"], e["player_name"].lower()))
    metrics["win_percentage"].sort(key=lambda e: (-e["value"], -e["wins"], e["player_name"].lower()))
    metrics["hole_in_one"].sort(key=lambda e: (-e["value"], -e["rounds"], e["player_name"].lower()))
    metrics["all_time_low"].sort(key=lambda e: (e["value"], -e["rounds"], e["player_name"].lower()))

    return [
        {
            "id": "average_score",
            "title": "Average Score",
            "unit": "Schlaege / 18 Loch",
            "description": "Durchschnittliche Schlaege pro vollstaendiger Runde",
            "direction": "asc",
            "ranking": metrics["average_score"],
        },
        {
            "id": "win_percentage",
            "title": "Win Percentage",
            "unit": "%",
            "description": "Anteil gewonnener Runden",
            "direction": "desc",
            "ranking": metrics["win_percentage"],
        },
        {
            "id": "hole_in_one",
            "title": "Hole-in-One King",
            "unit": "Treffer",
            "description": "Anzahl Bahnen mit einem Schlag",
            "direction": "desc",
            "ranking": metrics["hole_in_one"],
        },
        {
            "id": "all_time_low",
            "title": "All-Time Low",
            "unit": "Schlaege",
            "description": "Bester Gesamt-Score einer 18-Loch-Runde",
            "direction": "asc",
            "ranking": metrics["all_time_low"],
        },
    ]


def build_player_profile_stats(player: Player, season: int | None = None) -> dict:
    score_qs = Score.objects.filter(player=player)
    if season is not None:
        score_qs = score_qs.filter(session__season=season)

    distribution_counts = {stroke: 0 for stroke in range(1, 8)}
    for row in score_qs.values("strokes").annotate(count=Count("id")):
        if 1 <= row["strokes"] <= 7:
            distribution_counts[row["strokes"]] = row["count"]

    hole_avgs = list(score_qs.values("hole__hole_number").annotate(avg_strokes=Avg("strokes"), count=Count("id")))

    best_hole = None
    worst_hole = None
    if hole_avgs:
        best = min(hole_avgs, key=lambda x: (x["avg_strokes"], x["hole__hole_number"]))
        worst = max(hole_avgs, key=lambda x: (x["avg_strokes"], -x["hole__hole_number"]))
        best_hole = {
            "hole_number": best["hole__hole_number"],
            "avg_strokes": float(best["avg_strokes"]),
            "sample_size": best["count"],
        }
        worst_hole = {
            "hole_number": worst["hole__hole_number"],
            "avg_strokes": float(worst["avg_strokes"]),
            "sample_size": worst["count"],
        }

    round_rows = score_qs.values("session_id", "hole__hole_number", "strokes")
    rounds: dict[int, dict[int, int]] = defaultdict(dict)
    for row in round_rows:
        rounds[row["session_id"]][row["hole__hole_number"]] = row["strokes"]

    bounce_back_scores: list[int] = []
    front_totals: list[int] = []
    back_totals: list[int] = []
    for holes in rounds.values():
        front = [holes.get(h) for h in range(1, 10)]
        back = [holes.get(h) for h in range(10, 19)]

        if all(v is not None for v in front):
            front_totals.append(sum(front))
        if all(v is not None for v in back):
            back_totals.append(sum(back))

        for hole in range(2, 19):
            prev_score = holes.get(hole - 1)
            curr_score = holes.get(hole)
            if prev_score == MAX_STROKES_FOR_BOUNCE_BACK and curr_score is not None:
                bounce_back_scores.append(curr_score)

    return {
        "player": {
            "id": player.id,
            "name": player.name,
        },
        "score_distribution": {
            "labels": [str(i) for i in range(1, 8)],
            "values": [distribution_counts[i] for i in range(1, 8)],
        },
        "best_hole": best_hole,
        "worst_hole": worst_hole,
        "bounce_back_rate": float(mean(bounce_back_scores)) if bounce_back_scores else None,
        "bounce_back_samples": len(bounce_back_scores),
        "front9_avg_total": float(mean(front_totals)) if front_totals else None,
        "back9_avg_total": float(mean(back_totals)) if back_totals else None,
        "round_samples": len(rounds),
    }
