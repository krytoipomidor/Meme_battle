from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from .forms import RoundForm
from .models import Duel, DuelVote, FriendRequest, Friendship, Meme, Round, Vote


class ArenaFlowTests(TestCase):
    def setUp(self):
        media_directory = TemporaryDirectory()
        media_settings = override_settings(MEDIA_ROOT=media_directory.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.addCleanup(media_directory.cleanup)

        now = timezone.now()
        self.round = Round.objects.create(
            title="Тестовий раунд",
            topic="Понеділок",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(days=1),
        )
        self.author = User.objects.create_user(username="author", password="pass12345")
        self.voter = User.objects.create_user(username="voter", password="pass12345")
        self.other_author = User.objects.create_user(
            username="other", password="pass12345"
        )
        self.meme = Meme.objects.create(
            round=self.round,
            author=self.author,
            image="memes/test.png",
            caption="Тестовий мем",
        )
        self.other_meme = Meme.objects.create(
            round=self.round,
            author=self.other_author,
            image="memes/other.png",
            caption="Інший мем",
        )

    def test_round_and_duel_pages_render(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(
            self.client.get(f"/round/{self.round.pk}/").status_code, 200
        )
        self.assertEqual(self.client.get(f"/round/{self.round.pk}/duels/").status_code, 200)
        self.assertEqual(self.client.get(f"/round/{self.round.pk}/results/").status_code, 200)
        self.assertContains(self.client.get("/"), "meme-theme.css")

    def test_round_page_contains_meme_text_editor(self):
        response = self.client.get(f"/round/{self.round.pk}/")

        self.assertContains(response, 'id="meme-editor"')
        self.assertContains(response, 'id="add-text-block"')
        self.assertContains(response, 'id="text-block-font"')
        self.assertContains(response, 'id="text-block-size"')
        self.assertContains(response, 'id="text-block-color"')
        self.assertContains(response, "meme-editor.js")

    def test_round_status_changes_automatically_at_scheduled_times(self):
        self.assertEqual(Round().status, Round.Status.UPCOMING)

        start = timezone.now() + timedelta(minutes=10)
        scheduled = Round.objects.create(
            title="Запланований",
            topic="Тема",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )

        with patch("arena.models.timezone.now", return_value=start - timedelta(seconds=1)):
            self.assertEqual(scheduled.status, Round.Status.UPCOMING)
            self.assertFalse(scheduled.accepts_entries)
        with patch("arena.models.timezone.now", return_value=start):
            self.assertEqual(scheduled.status, Round.Status.ACTIVE)
            self.assertTrue(scheduled.accepts_entries)
        with patch(
            "arena.models.timezone.now", return_value=start + timedelta(hours=1)
        ):
            self.assertEqual(scheduled.status, Round.Status.FINISHED)
            self.assertFalse(scheduled.accepts_entries)

    def test_vote_is_only_accepted_during_the_scheduled_round(self):
        start = timezone.now() + timedelta(minutes=10)
        scheduled = Round.objects.create(
            title="Запланований",
            topic="Тема",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        meme = Meme.objects.create(
            round=scheduled,
            author=self.author,
            image="memes/scheduled.png",
            caption="Мем запланованого раунду",
        )
        self.client.force_login(self.voter)
        vote_url = f"/round/{scheduled.pk}/vote/{meme.pk}/"

        with patch("arena.models.timezone.now", return_value=start - timedelta(seconds=1)):
            self.client.post(vote_url)
        with patch("arena.models.timezone.now", return_value=start):
            self.client.post(vote_url)
        with patch(
            "arena.models.timezone.now", return_value=start + timedelta(hours=1)
        ):
            self.client.post(vote_url)

        self.assertEqual(Vote.objects.filter(meme=meme, voter=self.voter).count(), 1)

    def test_home_lists_rounds_by_schedule_not_manual_status(self):
        start = timezone.now() + timedelta(minutes=10)
        scheduled = Round.objects.create(
            title="Майбутній раунд",
            topic="Скоро",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )

        with patch("arena.views.timezone.now", return_value=start - timedelta(minutes=1)):
            response = self.client.get("/")

        self.assertIn(scheduled, response.context["upcoming_rounds"])

    def test_round_creation_requires_login(self):
        response = self.client.get(reverse("create_round"))

        self.assertRedirects(
            response, f"{reverse('login')}?next={reverse('create_round')}"
        )

    def test_logged_in_user_can_create_a_public_scheduled_round(self):
        self.client.force_login(self.voter)
        starts_at = timezone.localtime() + timedelta(hours=1)
        ends_at = starts_at + timedelta(hours=2)

        response = self.client.post(
            reverse("create_round"),
            {
                "title": "Раунд від учасника",
                "topic": "Університетські будні",
                "description": "Покажи найкращий мем про навчання.",
                "visibility": Round.Visibility.PUBLIC,
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": ends_at.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 302)
        round_obj = Round.objects.get(title="Раунд від учасника")
        self.assertEqual(round_obj.created_by, self.voter)
        self.assertEqual(round_obj.status, Round.Status.UPCOMING)
        self.assertRedirects(response, reverse("round_detail", args=[round_obj.pk]))
        home_response = self.client.get(reverse("home"))
        self.assertContains(home_response, "Університетські будні")
        self.assertContains(home_response, self.voter.username)

    def test_round_creator_can_choose_friends_only_visibility(self):
        self.client.force_login(self.voter)
        starts_at = timezone.localtime() + timedelta(hours=1)
        response = self.client.post(
            reverse("create_round"),
            {
                "title": "Раунд для друзів",
                "topic": "Наші жарти",
                "visibility": Round.Visibility.FRIENDS,
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (starts_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 302)
        round_obj = Round.objects.get(title="Раунд для друзів")
        self.assertEqual(round_obj.visibility, Round.Visibility.FRIENDS)
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("home")), "Наші жарти")

    def test_link_round_requires_its_invitation_url(self):
        link_round = Round.objects.create(
            title="За посиланням",
            topic="Секретна тема",
            visibility=Round.Visibility.LINK,
            created_by=self.author,
            starts_at=timezone.now() - timedelta(minutes=1),
            ends_at=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(link_round.access_code)
        self.assertNotContains(self.client.get(reverse("home")), "Секретна тема")
        self.assertEqual(
            self.client.get(reverse("round_detail", args=[link_round.pk])).status_code,
            302,
        )

        invite_response = self.client.get(
            reverse("round_invite", args=[link_round.access_code])
        )

        self.assertRedirects(invite_response, reverse("round_detail", args=[link_round.pk]))
        self.assertEqual(
            self.client.get(reverse("round_detail", args=[link_round.pk])).status_code,
            200,
        )

    def test_staff_can_browse_private_rounds_but_regular_users_cannot(self):
        private_round = Round.objects.create(
            title="Адмінський перегляд",
            topic="Приватний батл",
            visibility=Round.Visibility.LINK,
            created_by=self.author,
            starts_at=timezone.now() - timedelta(minutes=1),
            ends_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.voter)
        self.assertNotContains(self.client.get(reverse("home")), "Приватний батл")
        self.assertEqual(
            self.client.get(reverse("round_detail", args=[private_round.pk])).status_code,
            302,
        )

        staff_user = User.objects.create_user(
            username="round-moderator", password="pass12345", is_staff=True
        )
        self.client.force_login(staff_user)
        self.assertContains(self.client.get(reverse("home")), "Приватний батл")
        self.assertEqual(
            self.client.get(reverse("round_detail", args=[private_round.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("results", args=[private_round.pk])).status_code,
            200,
        )
        self.assertNotContains(
            self.client.get(reverse("round_detail", args=[private_round.pk])),
            "id=\"meme-editor-form\"",
        )

        # Staff can inspect private rounds but cannot submit actions without access.
        self.assertEqual(
            self.client.post(
                reverse("create_duels", args=[private_round.pk])
            ).status_code,
            302,
        )
        self.assertFalse(private_round.duels.exists())

    def test_friend_request_must_be_accepted_before_friends_only_access(self):
        private_round = Round.objects.create(
            title="Тільки друзям",
            topic="Приватна тема",
            visibility=Round.Visibility.FRIENDS,
            created_by=self.author,
            starts_at=timezone.now() - timedelta(minutes=1),
            ends_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.voter)
        response = self.client.post(
            reverse("send_friend_request"), {"username": self.author.username}
        )
        friend_request = FriendRequest.objects.get(sender=self.voter, recipient=self.author)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(friend_request.status, FriendRequest.Status.PENDING)
        self.assertEqual(
            self.client.get(reverse("round_detail", args=[private_round.pk])).status_code,
            302,
        )
        self.assertEqual(
            self.client.get(reverse("results", args=[private_round.pk])).status_code, 302
        )
        self.assertEqual(
            self.client.get(reverse("duels", args=[private_round.pk])).status_code, 302
        )
        self.assertEqual(
            self.client.post(
                reverse("create_duels", args=[private_round.pk])
            ).status_code,
            302,
        )

        self.client.force_login(self.author)
        self.client.post(
            reverse("accept_friend_request", args=[friend_request.pk])
        )
        self.assertTrue(Friendship.are_friends(self.voter, self.author))
        self.client.force_login(self.voter)
        self.assertEqual(
            self.client.get(reverse("round_detail", args=[private_round.pk])).status_code,
            200,
        )
        self.assertContains(self.client.get(reverse("home")), "Приватна тема")

    def test_profile_shows_friends_created_rounds_and_participation(self):
        Friendship.connect(self.voter, self.author)
        created_round = Round.objects.create(
            title="Мій раунд",
            topic="Моя тема",
            created_by=self.voter,
            starts_at=timezone.now() + timedelta(hours=1),
            ends_at=timezone.now() + timedelta(hours=2),
        )
        Vote.objects.create(meme=self.meme, voter=self.voter)
        self.client.force_login(self.voter)

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "author")
        self.assertContains(response, "Моя тема")
        self.assertIn(created_round, response.context["created_rounds"])
        self.assertIn(self.round, response.context["participated_rounds"])

    def test_round_creation_rejects_past_start_and_end_before_start(self):
        starts_at = timezone.localtime() + timedelta(hours=1)
        valid_data = {
            "title": "Некоректний раунд",
            "topic": "Тема",
            "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
            "ends_at": (starts_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        }
        past_form = RoundForm(
            {
                **valid_data,
                "starts_at": (timezone.localtime() - timedelta(hours=1)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
            }
        )
        self.assertFalse(past_form.is_valid())
        self.assertIn("starts_at", past_form.errors)

        end_before_start_form = RoundForm(
            {
                **valid_data,
                "ends_at": (starts_at - timedelta(minutes=1)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
            }
        )
        self.assertFalse(end_before_start_form.is_valid())
        self.assertIn("ends_at", end_before_start_form.errors)
        self.assertFalse(Round.objects.filter(title="Некоректний раунд").exists())

    def test_admin_can_open_the_add_round_form(self):
        admin_user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="admin-password"
        )
        self.client.force_login(admin_user)

        response = self.client.get("/admin/arena/round/add/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "status_display")

    def test_admin_panel_link_is_only_shown_to_active_staff_users(self):
        response = self.client.get("/")
        self.assertNotContains(response, "/admin/")

        regular_user = User.objects.create_user(username="regular", password="pass12345")
        self.client.force_login(regular_user)
        response = self.client.get("/")
        self.assertNotContains(response, "/admin/")

        staff_user = User.objects.create_user(
            username="staff", password="pass12345", is_staff=True
        )
        self.client.force_login(staff_user)
        response = self.client.get("/")
        self.assertContains(response, "/admin/")

    def test_user_can_submit_an_image_and_caption(self):
        image_data = BytesIO()
        Image.new("RGB", (10, 10), color="purple").save(image_data, format="PNG")
        image = SimpleUploadedFile(
            "new-meme.png", image_data.getvalue(), content_type="image/png"
        )
        self.client.force_login(self.author)

        response = self.client.post(
            f"/round/{self.round.pk}/",
            {"caption": "Мій мем", "image": image},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Meme.objects.filter(author=self.author, caption="Мій мем").exists())

    def test_user_can_vote_once_per_meme(self):
        self.client.force_login(self.voter)
        url = f"/round/{self.round.pk}/vote/{self.meme.pk}/"

        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)

        self.assertEqual(Vote.objects.filter(meme=self.meme, voter=self.voter).count(), 1)

    def test_author_cannot_vote_for_own_meme(self):
        self.client.force_login(self.author)
        self.client.post(f"/round/{self.round.pk}/vote/{self.meme.pk}/")

        self.assertFalse(Vote.objects.filter(meme=self.meme, voter=self.author).exists())

    def test_random_duels_and_single_duel_vote(self):
        self.client.force_login(self.voter)
        self.client.post(f"/round/{self.round.pk}/duels/create/")

        duel = Duel.objects.get(round=self.round)
        self.assertCountEqual(
            [duel.meme_one_id, duel.meme_two_id], [self.meme.pk, self.other_meme.pk]
        )

        url = f"/round/{self.round.pk}/duels/{duel.pk}/vote/"
        self.client.post(url, {"meme_id": self.meme.pk})
        self.client.post(url, {"meme_id": self.other_meme.pk})
        self.assertEqual(DuelVote.objects.filter(duel=duel, voter=self.voter).count(), 1)

        response = self.client.get(f"/round/{self.round.pk}/duels/")
        self.assertContains(response, "1 голосів")

    def test_history_keeps_only_the_latest_view_per_round_and_duel(self):
        self.client.force_login(self.voter)
        self.client.get(f"/round/{self.round.pk}/")
        self.client.get(f"/round/{self.round.pk}/")

        self.client.post(f"/round/{self.round.pk}/duels/create/")
        duel = Duel.objects.get(round=self.round)
        self.client.get(f"/round/{self.round.pk}/duels/")
        self.client.get(f"/round/{self.round.pk}/duels/")

        self.assertEqual(self.voter.view_history.filter(round=self.round).count(), 1)
        self.assertEqual(self.voter.view_history.filter(duel=duel).count(), 1)
        response = self.client.get("/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["entries"]), 2)

    def test_history_requires_login_and_does_not_record_anonymous_visits(self):
        self.client.get(f"/round/{self.round.pk}/")

        response = self.client.get("/history/")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.round.view_history.exists())

    def test_author_results_aggregate_votes_and_distinct_meme_count(self):
        extra_meme = Meme.objects.create(
            round=self.round,
            author=self.author,
            image="memes/extra.png",
            caption="Ще один мем",
        )
        Vote.objects.create(meme=self.meme, voter=self.voter)
        Vote.objects.create(meme=extra_meme, voter=self.other_author)

        response = self.client.get(f"/round/{self.round.pk}/results/")

        self.assertContains(response, "author")
        author_result = next(
            author for author in response.context["authors"] if author["author_id"] == self.author.id
        )
        self.assertEqual(author_result["total_votes"], 2)
        self.assertEqual(author_result["meme_count"], 2)

    def test_signup_creates_profile(self):
        response = self.client.post(
            "/signup/",
            {
                "username": "new-user",
                "email": "new@example.com",
                "password1": "A-strong-password-123",
                "password2": "A-strong-password-123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(username="new-user").profile)
