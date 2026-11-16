from django.contrib import admin

from .models import Duel, DuelVote, FriendRequest, Friendship, Meme, Profile, Round, Vote


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "topic",
        "created_by",
        "visibility",
        "status_display",
        "starts_at",
        "ends_at",
    )
    readonly_fields = ("status_display",)
    search_fields = ("title", "topic")

    @admin.display(description="статус")
    def status_display(self, obj):
        return obj.get_status_display()


@admin.register(Meme)
class MemeAdmin(admin.ModelAdmin):
    list_display = ("caption", "author", "round", "created_at")
    list_filter = ("round",)
    search_fields = ("caption", "author__username")


admin.site.register(Profile)
admin.site.register(Vote)
admin.site.register(Duel)
admin.site.register(DuelVote)
admin.site.register(Friendship)
admin.site.register(FriendRequest)
