from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from .models import Duel, DuelVote, Meme, Round, Vote


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
            status=Round.Status.ACTIVE,
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
