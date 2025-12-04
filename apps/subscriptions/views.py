"""
Views for Telegram signals subscription management
"""
from rest_framework import viewsets, status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.subscriptions.models import (
    TelegramSignalPlan, TelegramChannel, TelegramSubscription,
    TradingSignal, SignalResult, SignalStatistics
)
from rest_framework import serializers


# Simple serializers for the viewsets
class TelegramSignalPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramSignalPlan
        fields = '__all__'


class TelegramChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramChannel
        fields = '__all__'


class TelegramSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramSubscription
        fields = '__all__'


class TradingSignalSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingSignal
        fields = '__all__'


class SignalResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignalResult
        fields = '__all__'


class TelegramSignalPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Telegram signal plans
    """
    queryset = TelegramSignalPlan.objects.filter(is_active=True)
    serializer_class = TelegramSignalPlanSerializer
    permission_classes = [IsAuthenticated]


class TelegramSubscriptionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user Telegram subscriptions
    """
    queryset = TelegramSubscription.objects.all()
    serializer_class = TelegramSubscriptionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return TelegramSubscription.objects.filter(user=self.request.user)


class TelegramChannelViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Telegram channels
    """
    queryset = TelegramChannel.objects.filter(is_active=True)
    serializer_class = TelegramChannelSerializer
    permission_classes = [IsAuthenticated]


class TradingSignalViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for trading signals
    """
    queryset = TradingSignal.objects.filter(is_active=True)
    serializer_class = TradingSignalSerializer
    permission_classes = [IsAuthenticated]


class SignalResultViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for signal results
    """
    queryset = SignalResult.objects.all()
    serializer_class = SignalResultSerializer
    permission_classes = [IsAuthenticated]


# Additional Views
class PublicPlanListView(generics.ListAPIView):
    """
    List public subscription plans
    """
    queryset = TelegramSignalPlan.objects.filter(is_active=True)
    serializer_class = TelegramSignalPlanSerializer
    permission_classes = [AllowAny]


class CreateSubscriptionView(APIView):
    """
    Create a new subscription
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)


class MySubscriptionView(APIView):
    """
    Get current user subscription
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = TelegramSubscription.objects.filter(user=request.user, status='active').first()
        if subscription:
            serializer = TelegramSubscriptionSerializer(subscription)
            return Response(serializer.data)
        return Response({'message': 'No active subscription'}, status=status.HTTP_404_NOT_FOUND)


class ExtendSubscriptionView(APIView):
    """
    Extend current subscription
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)


class CancelSubscriptionView(APIView):
    """
    Cancel current subscription
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)


class AdminChannelListView(generics.ListAPIView):
    """
    List all channels for admin
    """
    queryset = TelegramChannel.objects.all()
    serializer_class = TelegramChannelSerializer
    permission_classes = [IsAdminUser]


class AdminCreateChannelView(generics.CreateAPIView):
    """
    Create a new channel (admin only)
    """
    queryset = TelegramChannel.objects.all()
    serializer_class = TelegramChannelSerializer
    permission_classes = [IsAdminUser]


class SignalStatisticsView(APIView):
    """
    Get signal statistics
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)