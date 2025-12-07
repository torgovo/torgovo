"""
Referrals App Views - Placeholder
"""
from rest_framework import viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

# Placeholder views to prevent import errors
class PlaceholderViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request):
        return Response({'message': 'Referrals module under construction'})

# Create a viewset instance for the router
class ReferralViewSet(PlaceholderViewSet):
    pass