from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Count
from django.utils import timezone


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    bio = models.CharField("про себе", max_length=180, blank=True)
    created_at = models.DateTimeField("зареєстровано", auto_now_add=True)

    def __str__(self):
        return self.user.get_username()


class Round(models.Model):
    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Запланований"
        ACTIVE = "active", "Триває"
        FINISHED = "finished", "Завершений"

    title = models.CharField("назва раунду", max_length=100)
    topic = models.CharField("тема", max_length=180)
    description = models.TextField("опис", blank=True)
    status = models.CharField(
        "статус", max_length=10, choices=Status.choices, default=Status.UPCOMING
    )
    starts_at = models.DateTimeField("початок", default=timezone.now)
    ends_at = models.DateTimeField("завершення")
    created_at = models.DateTimeField("створено", auto_now_add=True)

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return f"{self.title}: {self.topic}"

    @property
    def accepts_entries(self):
        now = timezone.now()
        return self.status == self.Status.ACTIVE and self.starts_at <= now < self.ends_at

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
