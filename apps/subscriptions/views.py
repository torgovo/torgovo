"""
Views for subscription management endpoints
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import (
    SubscriptionPlan, UserSubscription, SubscriptionDiscount,
    SubscriptionUsage, SubscriptionFeature
)
from .serializers import (
    SubscriptionPlanSerializer, UserSubscriptionSerializer,
    SubscriptionDiscountSerializer, SubscriptionUsageSerializer,
    SubscriptionFeatureSerializer
)

logger = logging.getLogger('apps')


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing available subscription plans.
    """
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.filter(is_active=True)

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get only active subscription plans."""
        active_plans = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(active_plans, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def features(self, request, pk=None):
        """Get features for a specific subscription plan."""
        plan = self.get_object()
        features = SubscriptionFeature.objects.filter(
            subscription_plan=plan,
            is_active=True
        )
        serializer = SubscriptionFeatureSerializer(features, many=True)
        return Response(serializer.data)


class UserSubscriptionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user subscriptions.
    """
    serializer_class = UserSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserSubscription.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current active subscription."""
        current_subscription = UserSubscription.objects.filter(
            user=request.user,
            status='active'
        ).first()

        if current_subscription:
            serializer = self.get_serializer(current_subscription)
            return Response(serializer.data)
        else:
            return Response({
                'message': 'No active subscription found',
                'plan': None
            })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a subscription."""
        subscription = self.get_object()

        if subscription.status != 'active':
            return Response({
                'success': False,
                'error': 'Only active subscriptions can be cancelled'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Set subscription to cancel at period end
        subscription.cancel_at_period_end = True
        subscription.cancelled_at = timezone.now()
        subscription.save()

        return Response({
            'success': True,
            'message': 'Subscription will be cancelled at the end of the billing period',
            'end_date': subscription.end_date
        })

    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        """Reactivate a cancelled subscription."""
        subscription = self.get_object()

        if not subscription.cancel_at_period_end:
            return Response({
                'success': False,
                'error': 'Subscription is not scheduled for cancellation'
            }, status=status.HTTP_400_BAD_REQUEST)

        if subscription.end_date and subscription.end_date <= timezone.now():
            return Response({
                'success': False,
                'error': 'Cannot reactivate expired subscription'
            }, status=status.HTTP_400_BAD_REQUEST)

        subscription.cancel_at_period_end = False
        subscription.cancelled_at = None
        subscription.save()

        return Response({
            'success': True,
            'message': 'Subscription reactivated successfully'
        })

    @action(detail=True, methods=['post'])
    def upgrade(self, request, pk=None):
        """Upgrade subscription to a higher tier."""
        subscription = self.get_object()

        new_plan_id = request.data.get('plan_id')
        if not new_plan_id:
            return Response({
                'success': False,
                'error': 'New plan ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_plan = get_object_or_404(SubscriptionPlan, id=new_plan_id, is_active=True)

            # Validate that it's actually an upgrade
            if new_plan.price_per_month <= subscription.plan.price_per_month:
                return Response({
                    'success': False,
                    'error': 'New plan must be more expensive than current plan'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Process upgrade (prorate the difference)
            # This would integrate with payment gateway
            subscription.plan = new_plan
            subscription.save()

            return Response({
                'success': True,
                'message': 'Subscription upgraded successfully',
                'new_plan': SubscriptionPlanSerializer(new_plan).data
            })

        except Exception as e:
            logger.error(f"Error upgrading subscription: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to upgrade subscription'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def history(self, request):
        """Get subscription history."""
        subscriptions = self.get_queryset()
        serializer = self.get_serializer(subscriptions, many=True)
        return Response(serializer.data)


class SubscriptionDiscountViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for subscription discounts and promotions.
    """
    serializer_class = SubscriptionDiscountSerializer
    queryset = SubscriptionDiscount.objects.filter(is_active=True)

    @action(detail=False, methods=['post'])
    def validate_code(self, request):
        """Validate a discount code."""
        code = request.data.get('code', None)
        plan_id = request.data.get('plan_id', None)

        if not code:
            return Response({
                'success': False,
                'error': 'Discount code is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            discount = get_object_or_404(
                SubscriptionDiscount,
                code__iexact=code,
                is_active=True
            )

            # Check if discount is still valid
            if discount.start_date and discount.start_date > timezone.now():
                return Response({
                    'success': False,
                    'error': 'Discount code is not yet active'
                }, status=status.HTTP_400_BAD_REQUEST)

            if discount.end_date and discount.end_date < timezone.now():
                return Response({
                    'success': False,
                    'error': 'Discount code has expired'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check if user has used this discount before
            if discount.usage_limit_per_user:
                user_usage = UserSubscription.objects.filter(
                    user=request.user,
                    discount=discount,
                    status__in=['active', 'completed']
                ).count()
                if user_usage >= discount.usage_limit_per_user:
                    return Response({
                        'success': False,
                        'error': 'You have already used this discount code'
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Calculate discount amount
            plan_price = Decimal('0.00')
            if plan_id:
                try:
                    plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
                    plan_price = plan.price_per_month
                except SubscriptionPlan.DoesNotExist:
                    pass

            if discount.discount_type == 'percentage':
                discount_amount = (plan_price * discount.discount_value) / 100
            else:
                discount_amount = min(discount.discount_value, plan_price)

            final_price = max(0, plan_price - discount_amount)

            return Response({
                'success': True,
                'discount': {
                    'code': discount.code,
                    'description': discount.description,
                    'discount_type': discount.discount_type,
                    'discount_value': discount.discount_value,
                    'discount_amount': discount_amount,
                    'final_price': final_price
                }
            })

        except SubscriptionDiscount.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Invalid discount code'
            }, status=status.HTTP_404_NOT_FOUND)


class SubscriptionUsageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for tracking subscription usage.
    """
    serializer_class = SubscriptionUsageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SubscriptionUsage.objects.filter(
            user=self.request.user
        ).order_by('-date')

    @action(detail=False, methods=['get'])
    def current_month(self, request):
        """Get usage statistics for the current month."""
        current_month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        current_usage = self.get_queryset().filter(date__gte=current_month_start)
        serializer = self.get_serializer(current_usage, many=True)

        # Aggregate usage by feature
        usage_summary = {}
        for usage in current_usage:
            feature_name = usage.feature.name
            if feature_name not in usage_summary:
                usage_summary[feature_name] = {
                    'usage_count': 0,
                    'usage_limit': usage.feature.usage_limit,
                    'reset_date': (current_month_start + timedelta(days=32)).replace(day=1)
                }
            usage_summary[feature_name]['usage_count'] += usage.usage_count

        return Response({
            'summary': usage_summary,
            'detailed_usage': serializer.data
        })

    @action(detail=False, methods=['get'])
    def limits(self, request):
        """Get current subscription limits and usage."""
        current_subscription = UserSubscription.objects.filter(
            user=request.user,
            status='active'
        ).first()

        if not current_subscription:
            return Response({
                'success': False,
                'error': 'No active subscription found'
            }, status=status.HTTP_404_NOT_FOUND)

        features = SubscriptionFeature.objects.filter(
            subscription_plan=current_subscription.plan,
            is_active=True
        )

        limits = []
        for feature in features:
            # Get current usage for this feature
            current_month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            usage = SubscriptionUsage.objects.filter(
                user=request.user,
                feature=feature,
                date__gte=current_month_start
            ).aggregate(models.Sum('usage_count'))['usage_count__sum'] or 0

            limits.append({
                'feature': feature.name,
                'description': feature.description,
                'current_usage': usage,
                'limit': feature.usage_limit,
                'usage_percentage': (usage / feature.usage_limit * 100) if feature.usage_limit > 0 else 0,
                'reset_date': (current_month_start + timedelta(days=32)).replace(day=1)
            })

        return Response({
            'success': True,
            'plan': current_subscription.plan.name,
            'limits': limits
        })


class SubscriptionFeatureViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for subscription features.
    """
    serializer_class = SubscriptionFeatureSerializer
    queryset = SubscriptionFeature.objects.filter(is_active=True)

    def get_queryset(self):
        queryset = SubscriptionFeature.objects.filter(is_active=True)
        plan_id = self.request.query_params.get('plan_id', None)
        if plan_id:
            queryset = queryset.filter(subscription_plan_id=plan_id)
        return queryset