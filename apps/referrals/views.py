"""
Referrals App Views - Complete Implementation
"""
from django.db.models import Sum
from django.utils import timezone
from rest_framework import viewsets, permissions, serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from decimal import Decimal

from apps.referrals.models import Referral
from django.contrib.auth import get_user_model

User = get_user_model()


class ReferralStatsSerializer(serializers.Serializer):
    """Serializer for referral stats response"""
    referral_code = serializers.CharField(max_length=20)
    total_referrals = serializers.IntegerField(read_only=True)
    total_bonus_usdt = serializers.DecimalField(max_digits=20, decimal_places=8, read_only=True)
    referral_link = serializers.SerializerMethodField()
    
    def get_referral_link(self, obj):
        return f"https://torgovo.com/signup?ref={obj['referral_code']}"


class ApplyReferralCodeSerializer(serializers.Serializer):
    """Serializer for applying referral code"""
    referral_code = serializers.CharField(max_length=20)


class MyReferralStatsView(APIView):
    """
    GET /api/referrals/my-stats/
    Returns user's referral statistics
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        # Get or create referral code for user
        referral = Referral.objects.filter(referrer=user).first()
        if not referral:
            # Generate unique code
            code = f"TOR{user.id:06d}{user.date_joined.strftime('%m%d')}"[:20]
            referral = Referral.objects.create(
                referrer=user,
                code=code,
                bonus_amount=Decimal('0'),
                status='pending'
            )
        
        # Calculate stats
        referrals_made = Referral.objects.filter(referrer=user)
        stats = {
            'referral_code': referral.code,
            'total_referrals': referrals_made.filter(status='paid').count(),
            'total_bonus_usdt': referrals_made.aggregate(total=Sum('bonus_amount'))['total'] or Decimal('0'),
            'referral_link': f"https://torgovo.com/signup?ref={referral.code}"
        }
        
        return Response(stats)


class ApplyReferralCodeView(APIView):
    """
    POST /api/referrals/apply/
    Apply referral code to authenticated user
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = ApplyReferralCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        referral_code = serializer.validated_data['referral_code']
        
        # Check if user already has a referrer
        existing_referral = Referral.objects.filter(referred_user=request.user).first()
        if existing_referral:
            return Response(
                {'error': 'Referral code already applied'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Find the referrer by code
        referrer_referral = Referral.objects.filter(code=referral_code).first()
        if not referrer_referral:
            return Response(
                {'error': 'Invalid referral code'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Prevent self-referral
        if referrer_referral.referrer_id == request.user.id:
            return Response(
                {'error': 'Cannot apply your own referral code'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update the referral record to mark this user as referred
        referrer_referral.referred_user = request.user
        referrer_referral.status = 'pending'  # Will be 'paid' when criteria met
        referrer_referral.save()
        
        return Response({
            'message': 'Referral code applied successfully',
            'referrer': referrer_referral.referrer.email
        })


# For registration enhancement - will be imported in authentication.views
class ReferralRegistrationMixin:
    """Mixin to handle referral codes during registration"""
    
    def apply_referral_after_registration(self, user, referral_code):
        """Apply referral code after successful registration"""
        if not referral_code:
            return
        
        # Find referrer by code
        referrer_referral = Referral.objects.filter(code=referral_code).first()
        if referrer_referral and referrer_referral.referrer_id != user.id:
            # Complete the referral
            referrer_referral.referred_user = user
            referrer_referral.status = 'pending'
            referrer_referral.save()
            return {
                'referral_applied': True,
                'referrer': referrer_referral.referrer.email
            }
        return None