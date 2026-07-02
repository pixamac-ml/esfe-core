"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
import asyncio

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_asgi_app = get_asgi_application()


class ClientDisconnectSafeASGIApp:
	"""Treat HTTP client disconnect cancellations as completed ASGI requests."""

	def __init__(self, app):
		self.app = app

	def _install_cancelled_error_handler(self):
		loop = asyncio.get_running_loop()
		if getattr(loop, "_esfe_cancelled_error_handler", False):
			return

		previous_handler = loop.get_exception_handler()

		def handle_exception(loop, context):
			message = context.get("message", "")
			exception = context.get("exception")
			if isinstance(exception, asyncio.CancelledError) and "CancelledError" in message:
				return
			if previous_handler:
				previous_handler(loop, context)
			else:
				loop.default_exception_handler(context)

		loop.set_exception_handler(handle_exception)
		loop._esfe_cancelled_error_handler = True

	async def __call__(self, scope, receive, send):
		self._install_cancelled_error_handler()
		try:
			await self.app(scope, receive, send)
		except asyncio.CancelledError:
			if scope.get("type") == "http":
				return
			raise


http_asgi_app = ClientDisconnectSafeASGIApp(django_asgi_app)

if os.getenv("ENABLE_WEBSOCKETS", "True").strip().lower() in {"1", "true", "yes", "on"}:
	from channels.auth import AuthMiddlewareStack
	from channels.routing import ProtocolTypeRouter, URLRouter
	from notifier.realtime.routing import websocket_urlpatterns

	application = ProtocolTypeRouter(
		{
			"http": http_asgi_app,
			"websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
		}
	)
else:
	application = http_asgi_app
