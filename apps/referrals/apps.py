"""
Referrals App Configuration
"""
from django.apps import AppConfig

class ReferralsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.referrals'
    verbose_name = 'Referral System'