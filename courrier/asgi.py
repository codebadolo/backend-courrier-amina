"""
ASGI config for courrier project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

"""
ASGI config for courrier project.
"""

import os
import django
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courrier.settings')

# ── BUG 3 : django.setup() doit être appelé AVANT les imports channels ──
# Sans ça, les apps Django ne sont pas initialisées quand channels
# charge les consumers → ImportError ou AppRegistryNotReady
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from courriers import routing

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    # ── BUG 4 : AllowedHostsOriginValidator manquant ──
    # Sans ce wrapper, n'importe quel domaine peut ouvrir un WebSocket
    # (problème de sécurité + peut causer des erreurs CORS WebSocket)
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                routing.websocket_urlpatterns
            )
        )
    ),
})