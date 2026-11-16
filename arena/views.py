from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import MemeForm, SignUpForm
from .models import Duel, DuelVote, Meme, Round, Vote


def home(request):
    rounds = Round.objects.all()
    return render(
        request,
        "arena/home.html",
        {
            "active_rounds": rounds.filter(status=Round.Status.ACTIVE),
            "upcoming_rounds": rounds.filter(status=Round.Status.UPCOMING),
            "finished_rounds": rounds.filter(status=Round.Status.FINISHED)[:3],
        },
    )


def round_detail(request, round_id):
    round_obj = get_object_or_404(Round, pk=round_id)
    memes = round_obj.ranked_memes()
    voted_ids = set()
    if request.user.is_authenticated:
        voted_ids = set(
            Vote.objects.filter(voter=request.user, meme__round=round_obj).values_list(
                "meme_id", flat=True
            )
        )

    form = MemeForm()
    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.info(request, "Увійди, щоб опублікувати мем.")
            return redirect("login")
        if not round_obj.accepts_entries:
            messages.error(request, "Цей раунд зараз не приймає нові роботи.")
            return redirect("round_detail", round_id=round_obj.pk)
        form = MemeForm(request.POST, request.FILES)
        if form.is_valid():
            meme = form.save(commit=False)
            meme.author = request.user
            meme.round = round_obj
            meme.save()
            messages.success(request, "Твій мем опубліковано!")
            return redirect("round_detail", round_id=round_obj.pk)

    return render(
        request,
        "arena/round_detail.html",
        {
            "round": round_obj,
            "memes": memes,
            "form": form,
            "voted_ids": voted_ids,
            "user_meme_ids": set(
                memes.filter(author=request.user).values_list("id", flat=True)
            ) if request.user.is_authenticated else set(),
            "can_submit": round_obj.accepts_entries,
        },
    )


@login_required
@require_POST
def vote(request, round_id, meme_id):
    round_obj = get_object_or_404(Round, pk=round_id)
    meme = get_object_or_404(Meme, pk=meme_id, round=round_obj)
    if not round_obj.voting_open:
        messages.error(request, "Голосування в цьому раунді закрите.")
    elif meme.author_id == request.user.id:
        messages.error(request, "За власну роботу голосувати не можна.")
    else:
        _, created = Vote.objects.get_or_create(meme=meme, voter=request.user)
        if created:
            messages.success(request, "Голос зараховано!")
        else:
            messages.info(request, "Ти вже голосував(-ла) за цей мем.")
    return redirect("round_detail", round_id=round_obj.pk)


def results(request, round_id):
    round_obj = get_object_or_404(Round, pk=round_id)
    return render(
        request,
        "arena/results.html",
        {
            "round": round_obj,
            "memes": round_obj.ranked_memes(),
            "authors": round_obj.memes.values(
                "author_id", "author__username"
            ).annotate(
                total_votes=Count("votes"), meme_count=Count("id", distinct=True)
            ).order_by("-total_votes", "author__username"),
        },
    )


@login_required
@require_POST
def create_duels(request, round_id):
    round_obj = get_object_or_404(Round, pk=round_id)
    if round_obj.status == Round.Status.UPCOMING:
        messages.error(request, "Дуелі ще не можна створити до початку раунду.")
        return redirect("duels", round_id=round_obj.pk)

    with transaction.atomic():
        if not round_obj.duels.exists():
            memes = list(round_obj.memes.order_by("?"))
            for index in range(0, len(memes) - 1, 2):
                Duel.objects.create(
                    round=round_obj, meme_one=memes[index], meme_two=memes[index + 1]
                )
    if round_obj.duels.exists():
        messages.success(request, "Випадкові пари готові!")
    else:
        messages.info(request, "Для дуелей потрібно щонайменше два меми.")
    return redirect("duels", round_id=round_obj.pk)


def duels(request, round_id):
    round_obj = get_object_or_404(Round, pk=round_id)
    duels_list = round_obj.duels.select_related(
        "meme_one__author", "meme_two__author"
    ).annotate(
        meme_one_vote_count=Count(
            "votes", filter=Q(votes__meme_id=F("meme_one_id"))
        ),
        meme_two_vote_count=Count(
            "votes", filter=Q(votes__meme_id=F("meme_two_id"))
        ),
    )
    voted_ids = set()
    if request.user.is_authenticated:
        voted_ids = set(
            DuelVote.objects.filter(duel__round=round_obj, voter=request.user).values_list(
                "duel_id", flat=True
            )
        )
    return render(
        request,
        "arena/duels.html",
        {"round": round_obj, "duels": duels_list, "voted_ids": voted_ids},
    )


@login_required
@require_POST
def duel_vote(request, round_id, duel_id):
    duel = get_object_or_404(Duel, pk=duel_id, round_id=round_id)
    try:
        selected_meme = int(request.POST.get("meme_id", ""))
    except ValueError:
        selected_meme = None

    if selected_meme not in (duel.meme_one_id, duel.meme_two_id):
        messages.error(request, "Обери один із мемів у цій дуелі.")
    elif duel.round.status == Round.Status.UPCOMING:
        messages.error(request, "Голосування за дуелі ще не почалося.")
    elif Meme.objects.filter(pk=selected_meme, author=request.user).exists():
        messages.error(request, "Не можна голосувати за власний мем.")
    else:
        _, created = DuelVote.objects.get_or_create(
            duel=duel, voter=request.user, defaults={"meme_id": selected_meme}
        )
        if created:
            messages.success(request, "Голос у дуелі зараховано!")
        else:
            messages.info(request, "Ти вже голосував(-ла) у цій дуелі.")
    return redirect("duels", round_id=round_id)


def signup(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Ласкаво просимо до Meme Arena!")
        return redirect("home")
    return render(request, "arena/signup.html", {"form": form})
