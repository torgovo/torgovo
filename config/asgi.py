"""
ASGI config for Torgovo Crypto Trading Platform
"""
import os
import django
from channels.routing import get_default_application
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()

application = get_asgi_application()

# WebSocket support for future real-time features
# application = ProtocolTypeRouter({
#     "http": get_asgi_application(),
#     "websocket": AllowedHostsOriginValidator(
#         AuthMiddlewareStack(
#             URLRouter(
#                 apps.routing.websocket_urlpatterns
#             )
#         )
#     ),
# })