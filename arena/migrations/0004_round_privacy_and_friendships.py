import secrets

import arena.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def populate_round_access_codes(apps, schema_editor):
    Round = apps.get_model("arena", "Round")
    for round_obj in Round.objects.filter(access_code__isnull=True).iterator():
        round_obj.access_code = secrets.token_urlsafe(18)
        round_obj.save(update_fields=["access_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("arena", "0003_round_created_by"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="round",
            name="visibility",
            field=models.CharField(
                choices=[
                    ("public", "Для всіх"),
                    ("link", "За секретним посиланням"),
                    ("friends", "Тільки для друзів"),
                ],
                default="public",
                max_length=10,
                verbose_name="хто може бачити раунд",
            ),
        ),
        migrations.AddField(
            model_name="round",
            name="access_code",
            field=models.CharField(
                blank=True,
                max_length=32,
                null=True,
                verbose_name="код запрошення",
            ),
        ),
        migrations.RunPython(populate_round_access_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="round",
            name="access_code",
            field=models.CharField(
                default=arena.models.generate_round_access_code,
                editable=False,
                max_length=32,
                unique=True,
                verbose_name="код запрошення",
            ),
        ),
        migrations.CreateModel(
            name="Friendship",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="додано в друзі")),
                (
                    "user_one",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="friendships_as_one",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user_two",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="friendships_as_two",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="friendship",
            constraint=models.UniqueConstraint(
                fields=("user_one", "user_two"), name="unique_friendship_pair"
            ),
        ),
        migrations.AddConstraint(
            model_name="friendship",
            constraint=models.CheckConstraint(
                condition=~models.Q(("user_one", models.F("user_two"))),
                name="friendship_users_must_differ",
            ),
        ),
        migrations.CreateModel(
            name="FriendRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Очікує підтвердження"),
                            ("accepted", "Підтверджений"),
                            ("rejected", "Відхилений"),
                        ],
                        default="pending",
                        max_length=10,
                        verbose_name="статус",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="надіслано")),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="received_friend_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "sender",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sent_friend_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="friendrequest",
            constraint=models.UniqueConstraint(
                fields=("sender", "recipient"), name="unique_friend_request_direction"
            ),
        ),
        migrations.AddConstraint(
            model_name="friendrequest",
            constraint=models.CheckConstraint(
                condition=~models.Q(("sender", models.F("recipient"))),
                name="friend_request_users_must_differ",
            ),
        ),
    ]
