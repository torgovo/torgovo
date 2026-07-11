"""
Corrected views for Torgovo subscriptions implementation
- Main SubscriptionPlan endpoints in payments app
- Telegram signals endpoints in subscriptions app (separate path)
- All properly integrated without fragmentation
"""

# apps/subscriptions/views.py - Add these endpoints at the end

def integrate_telegram_endpoints():
    """
    Telegram signal endpoints (separate from main subscriptions)
    These will be mounted at /api/telegram/ 
    """
    from rest_framework import serializers, status
    from rest_framework.response import Response
    from rest_framework.views import APIView
    from rest_framework.permissions import IsAuthenticated, AllowAny
    from django.core.cache import cache
    from django.utils import timezone
    from decimal import Decimal
    from django.db.models import Sum
    
    from apps.subscriptions.models import TelegramSignalPlan, TelegramSubscription, TelegramChannel
    
    # Telegram plans serializer
    class TelegramPlanFeaturesSerializer(serializers.Serializer):
        max_daily_signals = serializers.IntegerField(default=50)
        exchanges_covered = serializers.ListField(child=serializers.CharField())
        risk_level = serializers.CharField()
        
    class TelegramSignalPlanSerializer(serializers.ModelSerializer):
        features = TelegramPlanFeaturesSerializer(source='feature_dict', read_only=True)
        
        class Meta:
            model = TelegramSignalPlan
            fields = ['id', 'name', 'slug', 'description', 'price_monthly', 'price_quarterly', 
                      'price_yearly', 'features', 'signals_per_day', 'exchanges_covered',
                      'risk_level', 'success_rate', 'max_subscribers', 'is_active', 'trial_days']
        
        @property
        def feature_dict(self):
            if isinstance(self.instance.features, dict):
                return self.instance.features
            return {
                'max_daily_signals': self.instance.signals_per_day,
                'exchanges_covered': self.instance.exchanges_covered,
                'risk_level': self.instance.risk_level,
            }
    
    # Telegram wide plan list
    class TelegramPlanListView(APIView):
        """
        GET /api/telegram/plans/
        List all Telegram signal plans (public)
        """
        permission_classes = [AllowAny]
        
        def get(self, request):
            cache_key = 'telegram_plans_v1'
            data = cache.get(cache_key)
            
            if not data:
                plans = TelegramSignalPlan.objects.filter(is_active=True).order_by('price_monthly')
                serializer = TelegramSignalPlanSerializer(plans, many=True)
                data = {"plans": serializer.data}
                cache.set(cache_key, data, 3600)  # Cache 1 hour
            
            return Response(data)
    
    # User's telegram subscription status
    class MyTelegramUsageView(APIView):
        """
        GET /api/telegram/my-usage/
        Get user's Telegram subscription usage
        """
        permission_classes = [IsAuthenticated]
        
        def get(self, request):
            user = request.user
            usage = {
                'plan': None,
                'limits': {'max_daily_signals': 50, 'exchanges': []},
                'usage': {'signals_received': 0, 'last_signal_date': None},
                'is_active': False
            }
            
            active_sub = TelegramSubscription.objects.filter(
                user=user, status='active', end_date__gte=timezone.now()
            ).select_related('plan').first()
            
            if active_sub:
                usage['plan'] = active_sub.plan.name
                usage['limits'] = {
                    'max_daily_signals': active_sub.plan.signals_per_day,
                    'exchanges': active_sub.plan.exchanges_covered
                }
                usage['usage'] = {
                    'signals_received': active_sub.signals_received,
                    'last_signal_date': active_sub.last_signal_date
                }
                usage['is_active'] = True
                usage['expires_at'] = active_sub.end_date
            
            return Response(usage)
    
    # Subscribe to Telegram signals
    class TelegramSubscribeView(APIView):
        """
        POST /api/telegram/subscribe/
        Subscribe to Telegram signal plan
        """
        permission_classes = [IsAuthenticated]
        
        def post(self, request):
            plan_id = request.data.get('plan_id')
            telegram_handle = request.data.get('telegram_handle', '').strip()
            
            if not plan_id:
                return Response({'error': 'plan_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            if not telegram_handle:
                return Response({'error': 'telegram_handle is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                plan = TelegramSignalPlan.objects.get(id=plan_id, is_active=True)
            except TelegramSignalPlan.DoesNotExist:
                return Response({'error': 'Invalid plan_id'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Handle crypto payment proof
            payment_screenshot = request.FILES.get('payment_screenshot')
            payment_tx_hash = request.data.get('payment_transaction_hash', '')
            payment_blockchain = request.data.get('payment_blockchain', '')
            
            if not (payment_screenshot or payment_tx_hash):
                return Response(
                    {'error': 'Payment proof required (screenshot or transaction hash)'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create pending subscription
            subscription = TelegramSubscription.objects.create(
                user=user,
                plan=plan,
                status='pending_approval',
                telegram_handle=telegram_handle,
                payment_screenshot=payment_screenshot,
                payment_transaction_hash=payment_tx_hash,
                payment_blockchain=payment_blockchain,
                amount_paid=plan.price_monthly,  # Default to monthly
                billing_cycle='monthly'
            )
            
            # Clear cache
            cache.delete('telegram_plans_v1')
            
            return Response({
                'subscription_id': str(subscription.id),
                'status': subscription.status,
                'message': 'Payment received. Admin approval pending.'
            }, status=status.HTTP_201_CREATED)
    
    return {
        'TelegramPlanListView': TelegramPlanListView,
        'MyTelegramUsageView': MyTelegramUsageView, 
        'TelegramSubscribeView': TelegramSubscribeView
    }