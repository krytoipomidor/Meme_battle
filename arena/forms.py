from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Meme, Round


class SignUpForm(UserCreationForm):
    email = forms.EmailField(label="Електронна пошта")

    class Meta:
        model = get_user_model()
        fields = ["username", "email", "password1", "password2"]
        labels = {"username": "Ім'я користувача"}


class MemeForm(forms.ModelForm):
    class Meta:
        model = Meme
        fields = ["image", "caption"]
        widgets = {
            "image": forms.ClearableFileInput(
                attrs={"accept": "image/jpeg,image/png,image/webp"}
            ),
            "caption": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Додай підпис до свого мему…"}
            )
        }

    def clean_image(self):
        image = self.cleaned_data["image"]
        if image.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Зображення має бути не більшим за 5 МБ.")
        return image


class RoundForm(forms.ModelForm):
    class Meta:
        model = Round
        fields = [
            "title",
            "topic",
            "description",
            "visibility",
            "starts_at",
            "ends_at",
        ]
        labels = {
            "title": "Назва раунду",
            "topic": "Тема раунду",
            "description": "Опис (необов'язково)",
            "visibility": "Хто може бачити раунд",
            "starts_at": "Початок",
            "ends_at": "Завершення",
        }
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Розкажи учасникам про тему раунду"}
            ),
            "starts_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "ends_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            start = timezone.localtime() + timezone.timedelta(minutes=5)
            end = start + timezone.timedelta(days=1)
            self.initial.setdefault("starts_at", start.strftime("%Y-%m-%dT%H:%M"))
            self.initial.setdefault("ends_at", end.strftime("%Y-%m-%dT%H:%M"))

    def clean_starts_at(self):
        starts_at = self.cleaned_data["starts_at"]
        if starts_at < timezone.now():
            raise forms.ValidationError("Початок раунду має бути в майбутньому.")
        return starts_at

    def clean(self):
        cleaned_data = super().clean()
        starts_at = cleaned_data.get("starts_at")
        ends_at = cleaned_data.get("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", "Завершення має бути пізніше за початок.")
        return cleaned_data


class FriendRequestForm(forms.Form):
    username = forms.CharField(
        label="Ім'я користувача",
        max_length=150,
        widget=forms.TextInput(
            attrs={"placeholder": "Введи ім'я друга", "autocomplete": "off"}
        ),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        user_model = get_user_model()
        try:
            target = user_model.objects.get(username__iexact=username, is_active=True)
        except user_model.DoesNotExist as error:
            raise forms.ValidationError("Користувача з таким ім'ям не знайдено.") from error
        if target.pk == self.user.pk:
            raise forms.ValidationError("Не можна додати самого себе.")
        return target

    def clean(self):
        cleaned_data = super().clean()
        target = cleaned_data.get("username")
        if target and self.user.pk:
            from .models import FriendRequest, Friendship

            if Friendship.are_friends(self.user, target):
                self.add_error("username", "Ви вже друзі.")
            elif FriendRequest.objects.filter(
                sender=self.user, recipient=target, status=FriendRequest.Status.PENDING
            ).exists():
                self.add_error("username", "Запит цій людині вже надіслано.")
        return cleaned_data
