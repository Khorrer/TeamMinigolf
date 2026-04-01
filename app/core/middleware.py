from __future__ import annotations

from typing import Any, Callable


MOBILE_USER_AGENT_HINTS = (
    "android",
    "iphone",
    "ipad",
    "ipod",
    "mobile",
    "windows phone",
    "opera mini",
    "blackberry",
)


class MobileDetectionMiddleware:
    """Attach a lightweight mobile flag to each request for templates."""

    def __init__(self, get_response: Callable[[Any], Any]) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        # Manual override for quick testing: ?mobile=1 or ?mobile=0
        force_mobile = request.GET.get("mobile")
        if force_mobile == "1":
            request.mobile = True
        elif force_mobile == "0":
            request.mobile = False
        else:
            user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
            request.mobile = any(hint in user_agent for hint in MOBILE_USER_AGENT_HINTS)

        return self.get_response(request)
