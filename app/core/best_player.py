from __future__ import annotations

from django.db.models import Min

from .models import Hole, Player, Score, Session, SessionPlayer


BEST_PLAYER_NAME = "Best"


def is_best_player_name(name: str | None) -> bool:
    if not name:
        return False
    return name.strip().casefold() == BEST_PLAYER_NAME.casefold()


def get_or_create_best_player() -> Player:
    best_player, _ = Player.objects.get_or_create(
        name=BEST_PLAYER_NAME,
        defaults={"active": False},
    )
    # Keep Best as system-managed pseudo player.
    if best_player.active:
        best_player.active = False
        best_player.save(update_fields=["active"])
    return best_player


def ensure_best_player_in_session(session: Session) -> Player:
    best_player = get_or_create_best_player()
    SessionPlayer.objects.get_or_create(session=session, player=best_player)
    return best_player


def recompute_best_scores_for_session(session: Session, hole_ids: list[int] | None = None) -> Player:
    best_player = ensure_best_player_in_session(session)

    source_player_ids = list(
        session.session_players.exclude(player_id=best_player.id).values_list("player_id", flat=True)
    )

    if hole_ids is None:
        holes = Hole.objects.filter(course=session.course).values_list("id", flat=True)
        hole_ids = list(holes)

    for hole_id in hole_ids:
        best_strokes = (
            Score.objects.filter(
                session=session,
                hole_id=hole_id,
                player_id__in=source_player_ids,
            )
            .aggregate(min_strokes=Min("strokes"))
            .get("min_strokes")
        )

        if best_strokes is None:
            Score.objects.filter(
                session=session,
                player=best_player,
                hole_id=hole_id,
            ).delete()
        else:
            Score.objects.update_or_create(
                session=session,
                player=best_player,
                hole_id=hole_id,
                defaults={"strokes": best_strokes},
            )

    return best_player