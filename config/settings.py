"""
Django settings for config project.
Configuration DEV stable ESFE
"""

import os
import importlib.util
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# ==================================================
# BASE
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# URL absolue du site, utilisee par SEO, emails et securite CSRF.
BASE_URL = os.getenv("BASE_URL", "https://www.esfe-mali.org").rstrip("/")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]

# ==================================================
# SECURITY
# ==================================================

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY must be set in .env — generate one with: python -c \"import secrets; print(secrets.token_urlsafe(50))\"")
DEBUG = env_bool("DEBUG", False)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", BASE_URL)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost")
ENABLE_BROWSER_RELOAD = DEBUG and env_bool("ENABLE_BROWSER_RELOAD", True)
ENABLE_WEBSOCKETS = env_bool("ENABLE_WEBSOCKETS", True)
REDIS_URL = os.getenv("REDIS_URL", "").strip()

# ==================================================
# APPLICATIONS
# ==================================================

INSTALLED_APPS = [

    # 🔥 django-components
    "django_components",
    "daphne",
    "channels",
    "axes",
    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sitemaps",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # UI / Core
    "ui.apps.UiConfig",
    "core.apps.CoreConfig",
    "communication.apps.CommunicationConfig",
    "marketing.apps.MarketingConfig",

    # ✅ CKEditor 5 (UNIQUEMENT celui-ci)
    "django_ckeditor_5",
    'superadmin',
    # Métier
    "admissions.apps.AdmissionsConfig",
    "inscriptions.apps.InscriptionsConfig",
    "payments.apps.PaymentsConfig",
    "academic_cycle.apps.AcademicCycleConfig",
    "students",
    "formations",
    "branches",
    "academics",
    "shop.apps.ShopConfig",
    # Contenu
    "blog.apps.BlogConfig",
    "news",
    "community.apps.CommunityConfig",
    "accounts.apps.AccountsConfig",
    "portal.apps.PortalConfig",
    "secretary",
    "memoires.apps.MemoiresConfig",
]

if ENABLE_BROWSER_RELOAD and importlib.util.find_spec("django_browser_reload"):
    INSTALLED_APPS.append("django_browser_reload")

# ==================================================
# DJANGO-COMPONENTS CONFIG
# ==================================================

COMPONENTS = {
    "template_cache_size": 128,
}

# ==================================================
# MIDDLEWARE
# ==================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

if ENABLE_BROWSER_RELOAD and importlib.util.find_spec("django_browser_reload"):
    MIDDLEWARE.append("django_browser_reload.middleware.BrowserReloadMiddleware")

MIDDLEWARE.append("axes.middleware.AxesMiddleware")

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ==================================================
# DJANGO-AXES (protection brute-force connexion)
# ==================================================
# Par defaut, axes bloque apres 3 echecs SANS jamais debloquer
# automatiquement (AXES_COOLOFF_TIME=None -> blocage permanent tant
# qu'un admin ne lance pas "manage.py axes_reset_username <user>").
# On assouplit le seuil et on ajoute un deblocage automatique.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=30)
AXES_RESET_ON_SUCCESS = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "ignore_client_cancelled": {
            "()": "core.logging.IgnoreClientCancelledError",
        },
    },
    "loggers": {
        "django.request": {
            "filters": ["ignore_client_cancelled"],
        },
        "django.server": {
            "filters": ["ignore_client_cancelled"],
        },
        "django.core.handlers.asgi": {
            "filters": ["ignore_client_cancelled"],
        },
        "asgiref": {
            "filters": ["ignore_client_cancelled"],
        },
        "uvicorn.error": {
            "filters": ["ignore_client_cancelled"],
        },
        "uvicorn.access": {
            "filters": ["ignore_client_cancelled"],
        },
        "daphne.server": {
            "filters": ["ignore_client_cancelled"],
        },
        "daphne.http_protocol": {
            "filters": ["ignore_client_cancelled"],
        },
        "channels.server": {
            "filters": ["ignore_client_cancelled"],
        },
    },
}

# ==================================================
# URLS / WSGI / ASGI
# ==================================================

ROOT_URLCONF = "config.urls"

# WSGI (HTTP classique)
WSGI_APPLICATION = "config.wsgi.application"

# ASGI (WebSockets / temps réel)
ASGI_APPLICATION = "config.asgi.application"

# ==================================================
# TEMPLATES
# ==================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates", BASE_DIR / "ui" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.seo_defaults",
                "communication.context_processors.notification_widget",
            ],
        },
    },
]

# ==================================================
# DATABASE
# ==================================================

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "60")),
            ssl_require=env_bool("DB_SSL_REQUIRE", not DEBUG),
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "esfe_db"),
            "USER": os.getenv("DB_USER", "esfe_user"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        }
    }


# ==================================================
# DJANGO CHANNELS (WebSockets)
# ==================================================

HAS_CHANNELS_REDIS = importlib.util.find_spec("channels_redis") is not None

if ENABLE_WEBSOCKETS and REDIS_URL and HAS_CHANNELS_REDIS:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        }
    }
else:
    if ENABLE_WEBSOCKETS and REDIS_URL and not HAS_CHANNELS_REDIS and not DEBUG:
        raise ImproperlyConfigured(
            "REDIS_URL is configured but channels_redis is not installed. "
            "Install channels_redis or unset REDIS_URL."
        )
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

# ==================================================
# PASSWORD VALIDATION
# ==================================================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ==================================================
# INTERNATIONALIZATION
# ==================================================

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ==================================================
# STATIC FILES
# ==================================================
if DEBUG:
    STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
else:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_MAX_AGE = int(os.getenv("WHITENOISE_MAX_AGE", "31536000" if not DEBUG else "0"))

# ==================================================
# MEDIA FILES
# ==================================================

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ==================================================
# STOCKAGE PRIVÉ — APP MEMOIRES
# ==================================================
# Bucket S3 privé pour les mémoires (sources PDF + pages rendues). Si les
# variables S3_* ne sont pas renseignées, memoires.storage retombe sur un
# répertoire local non exposé par config.urls (dev/test sans fournisseur S3).

MEMOIRES_S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "").strip()
MEMOIRES_S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
MEMOIRES_S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "").strip()
MEMOIRES_S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "").strip()
MEMOIRES_S3_CONFIGURED = bool(
    MEMOIRES_S3_BUCKET and MEMOIRES_S3_ACCESS_KEY and MEMOIRES_S3_SECRET_KEY
)
MEMOIRES_PRIVATE_ROOT = BASE_DIR / "private_media" / "memoires"

MEMOIRE_UPLOAD_MAX_MB = int(os.getenv("MEMOIRE_UPLOAD_MAX_MB", "50"))
MEMOIRE_RENDER_DPI = int(os.getenv("MEMOIRE_RENDER_DPI", "130"))

# ==================================================
# DEFAULT PK
# ==================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==================================================
# URLS ABSOLUES (EMAILS / LIENS EXTERNES)
# ==================================================

EMAIL_LOGO_PATH = os.getenv("EMAIL_LOGO_PATH", "static/images/logo-esfe.png")

if BASE_URL and BASE_URL not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(BASE_URL)

# ==================================================
# EMAIL (DEV)
# ==================================================

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "core.mail_backends.StableSMTPEmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").strip().lower() in {"1", "true", "yes", "on"}
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").strip().lower() in {"1", "true", "yes", "on"}
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "noreply@esfe-mali.org")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "ESFE Core")
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "20"))
EMAIL_LOCAL_HOSTNAME = os.getenv("EMAIL_LOCAL_HOSTNAME", "localhost")
COMMUNICATION_EMAIL_PROVIDER = os.getenv("COMMUNICATION_EMAIL_PROVIDER", "brevo")
COMMUNICATION_EMAIL_PROVIDER_MODE = os.getenv("COMMUNICATION_EMAIL_PROVIDER_MODE", "smtp")

# ==================================================
# AUTH REDIRECTS
# ==================================================

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "accounts_portal:portal_dashboard"
LOGOUT_REDIRECT_URL = "community:topic_list"

# ==================================================
# CKEDITOR 5 CONFIG
# ==================================================

CKEDITOR_5_CONFIGS = {
    "default": {
        "toolbar": [
            "heading", "|",
            "bold", "italic", "link",
            "bulletedList", "numberedList",
            "blockQuote", "|",
            "insertImage", "|",
            "undo", "redo"
        ],
        "height": 400,
        "width": "100%",
    }
}

# ==================================================
# CUSTOM
# ==================================================

STUDENT_LOGIN_URL = os.getenv("STUDENT_LOGIN_URL", f"{BASE_URL}/student/login/")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")

# Clé dédiée à la signature HMAC des cartes étudiantes.
# Distincte de SECRET_KEY pour rotation indépendante.
# Générer : python -c "import secrets; print(secrets.token_urlsafe(50))"
CARD_SIGNING_KEY = os.getenv("CARD_SIGNING_KEY", "")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = env_bool("USE_X_FORWARDED_HOST", not DEBUG)
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.getenv("SECURE_REFERRER_POLICY", "strict-origin-when-cross-origin")
# Le dashboard integre certains contenus (PDF, previews) via iframe.
# SAMEORIGIN garde la protection clickjacking tout en autorisant l'integration interne.
X_FRAME_OPTIONS = os.getenv("X_FRAME_OPTIONS", "SAMEORIGIN")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 28800  # 8 heures
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

if DEBUG:
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

