from django.contrib.auth.views import LoginView
from django.urls import path

from . import views

urlpatterns = [
    # Health check (no auth)
    path("health/", views.health_check, name="health"),
    # Auth
    path("login/", LoginView.as_view(template_name="core/login.html"), name="login"),
    path("logout/", views.logout, name="logout"),
    path("signup/", views.signup, name="signup"),
    # Dashboard
    path("", views.dashboard, name="dashboard"),
    # Players
    path("players/", views.player_list, name="player_list"),
    path("players/create/", views.player_create, name="player_create"),
    path("players/<int:pk>/edit/", views.player_edit, name="player_edit"),
    # Courses
    path("courses/", views.course_list, name="course_list"),
    path("courses/create/", views.course_create, name="course_create"),
    path("courses/<int:pk>/", views.course_detail, name="course_detail"),
    path("courses/<int:pk>/edit/", views.course_edit, name="course_edit"),
    # Sessions
    path("sessions/", views.session_list, name="session_list"),
    path("sessions/create/", views.session_create, name="session_create"),
    path("games/ai-import", views.ai_import, name="ai_import"),
    path("sessions/<int:pk>/", views.session_detail, name="session_detail"),
    path("sessions/<int:pk>/complete/", views.session_complete, name="session_complete"),
    # Scoring
    path("sessions/<int:pk>/scoring/", views.scoring, name="scoring"),
    path("sessions/<int:session_pk>/score/", views.score_save, name="score_save"),
    # Stats
    path("stats/", views.stats_overview, name="stats"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
]
