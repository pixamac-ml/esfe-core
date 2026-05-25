try:
    from celery import shared_task
except ImportError:
    def shared_task(func=None, **_kwargs):
        def decorator(inner):
            inner.delay = inner
            return inner
        return decorator(func) if func else decorator
