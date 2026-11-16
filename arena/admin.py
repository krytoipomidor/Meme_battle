from django.contrib import admin

from .models import Duel, DuelVote, Meme, Profile, Round, Vote


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ("title", "topic", "status", "starts_at", "ends_at")
    list_filter = ("status",)
    search_fields = ("title", "topic")


@admin.register(Meme)
class MemeAdmin(admin.ModelAdmin):
    list_display = ("caption", "author", "round", "created_at")
    list_filter = ("round",)
    search_fields = ("caption", "author__username")


admin.site.register(Profile)
admin.site.register(Vote)
admin.site.register(Duel)
admin.site.register(DuelVote)
