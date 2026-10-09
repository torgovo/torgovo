"""
Serializers for user-facing account management endpoints
(deactivation and GDPR data export). Distinct from admin_serializers.py,
which handles the admin-only user management UI.
"""

from rest_framework import serializers


class DeactivateAccountSerializer(serializers.Serializer):
    """Confirm account deactivation by re-authenticating with the current password.

    Deactivation is a destructive, GDPR-visible action, so the user must prove
    knowledge of their password before the account is disabled. The password is
    never stored or returned.
    """

    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        """Reject the request unless the submitted password matches."""
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value
