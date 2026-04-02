"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_asgi_app = get_asgi_application()

if os.getenv("ENABLE_WEBSOCKETS", "True").strip().lower() in {"1", "true", "yes", "on"}:
	from channels.auth import AuthMiddlewareStack
	from channels.routing import ProtocolTypeRouter, URLRouter
	from community.routing import websocket_urlpatterns

	application = ProtocolTypeRouter(
		{
			"http": django_asgi_app,
			"websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
		}
	)
else:
	application = django_asgi_app
