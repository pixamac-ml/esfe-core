from .settings import *

# Local test settings to run isolated app tests without Postgres privileges.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
    }
}

# Limit URL checks to core routes for focused legal-page smoke tests.
ROOT_URLCONF = "config.urls_test_local"

# Avoid Redis dependency during local test execution.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

