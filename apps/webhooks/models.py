"""
Webhook models for TradingView integration
"""
from django.db import models
from django.conf import settings
from core.models import TimeStampedModel


class WebhookLog(TimeStampedModel):
    """Log of all webhook requests for debugging and monitoring."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='webhook_logs'
    )
    webhook_id = models.CharField(max_length=50, blank=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    payload = models.JSONField()
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    processing_time_ms = models.IntegerField(null=True, blank=True)
    is_successful = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'webhooks_logs'
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['webhook_id']),
            models.Index(fields=['is_successful']),
        ]