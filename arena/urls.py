from django.contrib.auth import views as auth_views
from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("round/<int:round_id>/", views.round_detail, name="round_detail"),
    path("round/<int:round_id>/vote/<int:meme_id>/", views.vote, name="vote"),
    path("round/<int:round_id>/duels/", views.duels, name="duels"),
    path("round/<int:round_id>/duels/create/", views.create_duels, name="create_duels"),
    path("round/<int:round_id>/duels/<int:duel_id>/vote/", views.duel_vote, name="duel_vote"),
    path("round/<int:round_id>/results/", views.results, name="results"),
    path("signup/", views.signup, name="signup"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="arena/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
