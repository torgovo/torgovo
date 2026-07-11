"""
Production tasks backend implementation - Module 1 + Module 3
User-facing endpoints for subscriptions, referrals, withdrawals
"""

# MODIFIED: apps/subscriptions/views.py
# Add these to the END of the existing file

# Telegram signal endpoints (separate from main subscriptions)
from django.core.cache import cache
from django.db.models import Sum

class TelegramPlanListView(APIView):
    """
    GET /api/telegram/plans/
    Public endpoint for Telegram signal plans
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        cache_key = 'telegram_plans_v1'
        data = cache.get(cache_key)
        
        if not data:
            plans = TelegramSignalPlan.objects.filter(is_active=True).order_by('price_monthly')
            serializer = TelegramSignalPlanSerializer(plans, many=True)
            data = {"plans": serializer.data}
            cache.set(cache_key, data, 3600)
        
        return Response(data)

class MyTelegramUsageView(APIView):
    """
    GET /api/telegram/my-usage/
    Get user's Telegram subscription usage
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        usage = {'plan': None, 'limits': {}, 'usage': {}, 'is_active': False}
        
        active_sub = TelegramSubscription.objects.filter(
            user=user, status='active', end_date__gte=timezone.now()
        ).select_related('plan').first()
        
        if active_sub:
            plan = active_sub.plan
            usage['plan'] = plan.name
            usage['limits'] = {
                'max_daily_signals': plan.signals_per_day,
                'exchanges': plan.exchanges_covered
            }
            usage['usage'] = {
                'signals_received': active_sub.signals_received,
                'last_signal_date': active_sub.last_signal_date
            }
            usage['is_active'] = True
            usage['expires_at'] = active_sub.end_date
        
        return Response(usage)

class TelegramSubscribeView(APIView):
    """
    POST /api/telegram/subscribe/
    Subscribe to Telegram signal plan with payment proof
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        plan_id = request.data.get('plan_id')
        telegram_handle = request.data.get('telegram_handle', '').strip()
        
        if not plan_id or not telegram_handle:
            return Response({'error': 'plan_id and telegram_handle required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            plan = TelegramSignalPlan.objects.get(id=plan_id, is_active=True)
        except TelegramSignalPlan.DoesNotExist:
            return Response({'error': 'Invalid plan_id'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Payment validation
        payment_screenshot = request.FILES.get('payment_screenshot')
        payment_tx_hash = request.data.get('payment_transaction_hash', '')
        payment_blockchain = request.data.get('payment_blockchain', '')
        
        if not (payment_screenshot or payment_tx_hash):
            return Response({'error': 'Payment proof required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        # Create subscription
        subscription = TelegramSubscription.objects.create(
            user=request.user,
            plan=plan,
            status='pending_approval',
            telegram_handle=telegram_handle,
            payment_screenshot=payment_screenshot,
            payment_transaction_hash=payment_tx_hash,
            payment_blockchain=payment_blockchain,
            amount_paid=plan.price_monthly,
            billing_cycle='monthly'
        )
        
        cache.delete('telegram_plans_v1')
        
        return Response({
            'subscription_id': str(subscription.id),
            'status': subscription.status,
            'message': 'Payment received. Admin approval pending.'
        }, status=status.HTTP_201_CREATED)

# Add to subscriptions/urls.py
# path('telegram/plans/', TelegramPlanListView.as_view(), name='telegram-plan-list'),
# path('telegram/my-usage/', MyTelegramUsageView.as_view(), name='telegram-my-usage'),
# path('telegram/subscribe/', TelegramSubscribeView.as_view(), name='telegram-subscribe'),