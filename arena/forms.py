from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Meme


class SignUpForm(UserCreationForm):
    email = forms.EmailField(label="Електронна пошта")

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]
        labels = {"username": "Ім'я користувача"}


class MemeForm(forms.ModelForm):
    class Meta:
        model = Meme
        fields = ["image", "caption"]
        widgets = {
            "caption": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Додай підпис до свого мему…"}
            )
        }

    def clean_image(self):
        image = self.cleaned_data["image"]
        if image.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Зображення має бути не більшим за 5 МБ.")
        return image
