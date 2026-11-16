from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import FriendRequestForm, MemeForm, RoundForm, SignUpForm
from .models import Duel, DuelVote, FriendRequest, Friendship, Meme, Round, ViewHistory, Vote


def home(request):
    now = timezone.now()
    visible_rounds = Q(visibility=Round.Visibility.PUBLIC)
    if request.user.is_authenticated and request.user.is_active and request.user.is_staff:
        visible_rounds = Q()
    elif request.user.is_authenticated:
        friendship_ids = Friendship.objects.filter(
            Q(user_one=request.user) | Q(user_two=request.user)
        ).values_list("user_one_id", "user_two_id")
        friend_ids = {
            user_id
            for pair in friendship_ids
            for user_id in pair
            if user_id != request.user.pk
        }
        visible_rounds |= Q(created_by=request.user) | Q(
            visibility=Round.Visibility.FRIENDS, created_by_id__in=friend_ids
        )
    rounds = Round.objects.filter(visible_rounds)
    return render(
        request,
        "arena/home.html",
        {
            "active_rounds": rounds.filter(starts_at__lte=now, ends_at__gt=now),
            "upcoming_rounds": rounds.filter(starts_at__gt=now).order_by("starts_at"),
            "finished_rounds": rounds.filter(ends_at__lte=now).order_by("-ends_at")[:3],
        },
    )


def can_access_round(request, round_obj):
    if (
        request.method == "GET"
        and request.user.is_authenticated
        and request.user.is_active
        and request.user.is_staff
    ):
        return True
    return can_participate_in_round(request, round_obj)


def can_participate_in_round(request, round_obj):
    if round_obj.visibility == Round.Visibility.PUBLIC:
        return True
    if request.user.is_authenticated and round_obj.created_by_id == request.user.pk:
        return True
    if round_obj.visibility == Round.Visibility.LINK:
        return request.session.get(f"round_access_{round_obj.pk}") == round_obj.access_code
    return bool(
        round_obj.visibility == Round.Visibility.FRIENDS
        and request.user.is_authenticated
        and round_obj.created_by_id
        and Friendship.are_friends(request.user, round_obj.created_by)
    )


def require_round_access(request, round_obj):
    if can_access_round(request, round_obj):
        return None
    messages.error(
        request, "Цей раунд доступний лише за запрошенням або друзям його автора."
    )
    return redirect("home")


@login_required
def create_round(request):
    form = RoundForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        round_obj = form.save(commit=False)
        round_obj.created_by = request.user
        round_obj.save()
        messages.success(
            request,
            "Раунд створено! Він автоматично почнеться у запланований час.",
        )
        if round_obj.visibility == Round.Visibility.LINK:
            request.session[f"round_access_{round_obj.pk}"] = round_obj.access_code
        return redirect("round_detail", round_id=round_obj.pk)
    return render(request, "arena/create_round.html", {"form": form})


def round_invite(request, access_code):
    round_obj = get_object_or_404(
        Round, access_code=access_code, visibility=Round.Visibility.LINK
    )
    request.session[f"round_access_{round_obj.pk}"] = round_obj.access_code
    return redirect("round_detail", round_id=round_obj.pk)


def record_view(request, *, round_obj=None, duel=None):
    if not request.user.is_authenticated:
        return
    target = {"round": round_obj} if round_obj else {"duel": duel}
    ViewHistory.objects.update_or_create(
        user=request.user,
        **target,
        defaults={"last_viewed_at": timezone.now()},
    )


def round_detail(request, round_id):
    round_obj = get_object_or_404(Round, pk=round_id)
    access_response = require_round_access(request, round_obj)
    if access_response:
        return access_response
    if request.method == "GET":
        record_view(request, round_obj=round_obj)
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
            "can_submit": round_obj.accepts_entries
            and can_participate_in_round(request, round_obj),
        },
    )


@login_required
@require_POST
def vote(request, round_id, meme_id):
    round_obj = get_object_or_404(Round, pk=round_id)
    access_response = require_round_access(request, round_obj)
    if access_response:
        return access_response
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
    access_response = require_round_access(request, round_obj)
    if access_response:
        return access_response
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
    access_response = require_round_access(request, round_obj)
    if access_response:
        return access_response
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
    access_response = require_round_access(request, round_obj)
    if access_response:
        return access_response
    if request.method == "GET" and request.user.is_authenticated:
        for duel in round_obj.duels.only("id"):
            record_view(request, duel=duel)
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
        {
            "round": round_obj,
            "duels": duels_list,
            "voted_ids": voted_ids,
            "can_participate": can_participate_in_round(request, round_obj),
        },
    )


@login_required
@require_POST
def duel_vote(request, round_id, duel_id):
    duel = get_object_or_404(Duel, pk=duel_id, round_id=round_id)
    access_response = require_round_access(request, duel.round)
    if access_response:
        return access_response
    try:
        selected_meme = int(request.POST.get("meme_id", ""))
    except ValueError:
        selected_meme = None

    if selected_meme not in (duel.meme_one_id, duel.meme_two_id):
        messages.error(request, "Обери один із мемів у цій дуелі.")
    elif not duel.round.voting_open:
        messages.error(request, "Голосування за дуелі зараз закрите.")
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


@login_required
def history(request):
    entries = []
    for item in ViewHistory.objects.filter(user=request.user).select_related(
        "round", "duel__round", "duel__meme_one", "duel__meme_two"
    ):
        if item.round_id:
            entries.append(
                {
                    "kind": "round",
                    "title": item.round.topic,
                    "subtitle": item.round.title,
                    "viewed_at": item.last_viewed_at,
                    "url": reverse("round_detail", args=[item.round_id]),
                }
            )
        else:
            duel = item.duel
            entries.append(
                {
                    "kind": "duel",
                    "title": f"{duel.meme_one.caption} vs {duel.meme_two.caption}",
                    "subtitle": duel.round.topic,
                    "viewed_at": item.last_viewed_at,
                    "url": f"{reverse('duels', args=[duel.round_id])}#duel-{duel.id}",
                }
            )
    entries.sort(key=lambda entry: entry["viewed_at"], reverse=True)
    return render(request, "arena/history.html", {"entries": entries[:100]})


@login_required
def profile(request):
    friendships = Friendship.objects.filter(
        Q(user_one=request.user) | Q(user_two=request.user)
    ).select_related("user_one", "user_two")
    friends = [friendship.other_user(request.user) for friendship in friendships]
    incoming_requests = FriendRequest.objects.filter(
        recipient=request.user, status=FriendRequest.Status.PENDING
    ).select_related("sender")
    outgoing_requests = FriendRequest.objects.filter(
        sender=request.user, status=FriendRequest.Status.PENDING
    ).select_related("recipient")
    participated_rounds = (
        Round.objects.filter(
            Q(memes__author=request.user)
            | Q(memes__votes__voter=request.user)
            | Q(duels__votes__voter=request.user)
        )
        .distinct()
        .order_by("-starts_at")
    )
    return render(
        request,
        "arena/profile.html",
        {
            "friend_form": FriendRequestForm(user=request.user),
            "friends": friends,
            "incoming_requests": incoming_requests,
            "outgoing_requests": outgoing_requests,
            "created_rounds": Round.objects.filter(created_by=request.user).order_by(
                "-starts_at"
            ),
            "participated_rounds": participated_rounds,
        },
    )


@login_required
@require_POST
def send_friend_request(request):
    form = FriendRequestForm(request.POST, user=request.user)
    if not form.is_valid():
        for error in form.errors.get("username", []):
            messages.error(request, error)
        return redirect("profile")

    recipient = form.cleaned_data["username"]
    if FriendRequest.objects.filter(
        sender=recipient,
        recipient=request.user,
        status=FriendRequest.Status.PENDING,
    ).exists():
        messages.info(
            request,
            "Цей користувач уже надіслав тобі запит. Підтверди його нижче.",
        )
        return redirect("profile")

    friend_request, created = FriendRequest.objects.get_or_create(
        sender=request.user,
        recipient=recipient,
        defaults={"status": FriendRequest.Status.PENDING},
    )
    if not created and friend_request.status == FriendRequest.Status.REJECTED:
        friend_request.status = FriendRequest.Status.PENDING
        friend_request.save(update_fields=["status"])
    messages.success(request, f"Запит у друзі надіслано: {recipient.username}.")
    return redirect("profile")


@login_required
@require_POST
def accept_friend_request(request, request_id):
    friend_request = get_object_or_404(
        FriendRequest,
        pk=request_id,
        recipient=request.user,
        status=FriendRequest.Status.PENDING,
    )
    with transaction.atomic():
        Friendship.connect(request.user, friend_request.sender)
        friend_request.status = FriendRequest.Status.ACCEPTED
        friend_request.save(update_fields=["status"])
    messages.success(request, f"Тепер ви друзі з {friend_request.sender.username}.")
    return redirect("profile")


@login_required
@require_POST
def reject_friend_request(request, request_id):
    friend_request = get_object_or_404(
        FriendRequest,
        pk=request_id,
        recipient=request.user,
        status=FriendRequest.Status.PENDING,
    )
    friend_request.status = FriendRequest.Status.REJECTED
    friend_request.save(update_fields=["status"])
    messages.info(request, "Запит у друзі відхилено.")
    return redirect("profile")


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
