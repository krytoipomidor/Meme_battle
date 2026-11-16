import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Count
from django.utils import timezone


def generate_round_access_code():
    return secrets.token_urlsafe(18)


class Friendship(models.Model):
    user_one = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friendships_as_one",
    )
    user_two = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friendships_as_two",
    )
    created_at = models.DateTimeField("додано в друзі", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user_one", "user_two"], name="unique_friendship_pair"
            ),
            models.CheckConstraint(
                condition=~models.Q(user_one=models.F("user_two")),
                name="friendship_users_must_differ",
            ),
        ]

    @classmethod
    def connect(cls, user_one, user_two):
        first, second = sorted((user_one, user_two), key=lambda user: user.pk)
        return cls.objects.get_or_create(user_one=first, user_two=second)

    @classmethod
    def are_friends(cls, user_one, user_two):
        if not user_one.is_authenticated or not user_two.is_authenticated:
            return False
        first_id, second_id = sorted((user_one.pk, user_two.pk))
        return cls.objects.filter(user_one_id=first_id, user_two_id=second_id).exists()

    def other_user(self, user):
        if self.user_one_id == user.pk:
            return self.user_two
        if self.user_two_id == user.pk:
            return self.user_one
        return None

    def __str__(self):
        return f"{self.user_one} ↔ {self.user_two}"


class FriendRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Очікує підтвердження"
        ACCEPTED = "accepted", "Підтверджений"
        REJECTED = "rejected", "Відхилений"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_friend_requests",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_friend_requests",
    )
    status = models.CharField(
        "статус",
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField("надіслано", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["sender", "recipient"], name="unique_friend_request_direction"
            ),
            models.CheckConstraint(
                condition=~models.Q(sender=models.F("recipient")),
                name="friend_request_users_must_differ",
            ),
        ]

    def __str__(self):
        return f"{self.sender} → {self.recipient} ({self.get_status_display()})"


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    bio = models.CharField("про себе", max_length=180, blank=True)
    created_at = models.DateTimeField("зареєстровано", auto_now_add=True)

    def __str__(self):
        return self.user.get_username()


class Round(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Для всіх"
        LINK = "link", "За секретним посиланням"
        FRIENDS = "friends", "Тільки для друзів"

    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Запланований"
        ACTIVE = "active", "Триває"
        FINISHED = "finished", "Завершений"

    title = models.CharField("назва раунду", max_length=100)
    topic = models.CharField("тема", max_length=180)
    description = models.TextField("опис", blank=True)
    visibility = models.CharField(
        "хто може бачити раунд",
        max_length=10,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    access_code = models.CharField(
        "код запрошення",
        max_length=32,
        default=generate_round_access_code,
        unique=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_rounds",
        verbose_name="автор раунду",
        null=True,
        blank=True,
    )
    starts_at = models.DateTimeField("початок", default=timezone.now)
    ends_at = models.DateTimeField("завершення")
    created_at = models.DateTimeField("створено", auto_now_add=True)

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return f"{self.title}: {self.topic}"

    def clean(self):
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "Час завершення має бути пізніше за початок."})

    @property
    def status(self):
        if not self.starts_at or not self.ends_at:
            return self.Status.UPCOMING
        now = timezone.now()
        if now < self.starts_at:
            return self.Status.UPCOMING
        if now < self.ends_at:
            return self.Status.ACTIVE
        return self.Status.FINISHED

    def get_status_display(self):
        return dict(self.Status.choices)[self.status]

    @property
    def accepts_entries(self):
        now = timezone.now()
        return self.starts_at <= now < self.ends_at

    @property
    def voting_open(self):
        return self.accepts_entries

    def ranked_memes(self):
        return (
            self.memes.select_related("author")
            .annotate(vote_count=Count("votes"))
            .order_by("-vote_count", "created_at")
        )


class Meme(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="memes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memes"
    )
    image = models.ImageField(
        "зображення",
        upload_to="memes/%Y/%m/",
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
    )
    caption = models.CharField("підпис", max_length=280)
    created_at = models.DateTimeField("опубліковано", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Мем від {self.author} — {self.round}"

class Vote(models.Model):
    meme = models.ForeignKey(Meme, on_delete=models.CASCADE, related_name="votes")
    voter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meme_votes"
    )
    created_at = models.DateTimeField("час голосування", auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["meme", "voter"], name="one_vote_per_meme_user")
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.voter} → {self.meme_id}"


class Duel(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="duels")
    meme_one = models.ForeignKey(
        Meme, on_delete=models.CASCADE, related_name="duels_as_one"
    )
    meme_two = models.ForeignKey(
        Meme, on_delete=models.CASCADE, related_name="duels_as_two"
    )
    created_at = models.DateTimeField("створено", auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["round", "meme_one", "meme_two"], name="unique_duel_pair"
            )
        ]

    def __str__(self):
        return f"Дуель #{self.pk} — {self.round}"

    @property
    def winner(self):
        return self.votes.values("meme").annotate(total=Count("id")).order_by(
            "-total", "meme"
        ).values_list("meme", flat=True).first()


class DuelVote(models.Model):
    duel = models.ForeignKey(Duel, on_delete=models.CASCADE, related_name="votes")
    meme = models.ForeignKey(Meme, on_delete=models.CASCADE, related_name="duel_votes")
    voter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="duel_votes"
    )
    created_at = models.DateTimeField("час голосування", auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["duel", "voter"], name="one_duel_vote_per_user")
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.voter} → дуель {self.duel_id}"


class ViewHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="view_history"
    )
    round = models.ForeignKey(
        Round,
        on_delete=models.CASCADE,
        related_name="view_history",
        null=True,
        blank=True,
    )
    duel = models.ForeignKey(
        Duel,
        on_delete=models.CASCADE,
        related_name="view_history",
        null=True,
        blank=True,
    )
    last_viewed_at = models.DateTimeField("останній перегляд", default=timezone.now)

    class Meta:
        ordering = ["-last_viewed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "round"],
                condition=models.Q(round__isnull=False),
                name="unique_user_round_view_history",
            ),
            models.UniqueConstraint(
                fields=["user", "duel"],
                condition=models.Q(duel__isnull=False),
                name="unique_user_duel_view_history",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(round__isnull=False, duel__isnull=True)
                    | models.Q(round__isnull=True, duel__isnull=False)
                ),
                name="view_history_one_target",
            ),
        ]

    def __str__(self):
        target = self.round if self.round_id else self.duel
        return f"{self.user} переглянув(-ла): {target}"
