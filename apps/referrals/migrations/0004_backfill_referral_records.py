from django.db import migrations


def backfill_referral_records(apps, schema_editor):
    UserProfile = apps.get_model("authentication", "UserProfile")
    Referral = apps.get_model("referrals", "Referral")

    for profile in UserProfile.objects.all().select_related("user").iterator():
        if not profile.referral_code:
            continue

        Referral.objects.update_or_create(
            referrer=profile.user,
            defaults={
                "code": profile.referral_code,
                "status": "pending",
            },
        )

        if profile.referred_by:
            Referral.objects.filter(
                referred_user=profile.user,
            ).update(status="paid")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("referrals", "0003_alter_referral_referred_user"),
        ("authentication", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_referral_records, noop),
    ]
