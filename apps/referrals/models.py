import uuid
from django.db import models
from django.conf import settings
from core.models import TimeStampedModel

class Referral(TimeStampedModel):
    """
    Model to track user referrals and bonuses.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referrals_made'
    )
    referred_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_received'
    )
    code = models.CharField(max_length=20)
    bonus_amount = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    currency = models.CharField(max_length=10, default='USDT')
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('paid', 'Paid'), ('rejected', 'Rejected')],
        default='pending'
    )

    class Meta:
        db_table = 'referrals'
        indexes = [
            models.Index(fields=['referrer']),
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return f"{self.referrer.email} referred {self.referred_user.email}"
