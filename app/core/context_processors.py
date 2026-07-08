from __future__ import annotations

from .models import Session


def mobile_navigation_context(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"open_sessions_count": 0}

    open_sessions_count = Session.objects.filter(status=Session.Status.LIVE).count()
    return {"open_sessions_count": open_sessions_count}
