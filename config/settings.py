"""
Django settings for config project.
Configuration DEV stable ESFE
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ==================================================
# BASE
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ==================================================
# SECURITY
# ==================================================

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = os.getenv("DEBUG", "True").strip().lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "ALLOWED_HOSTS",
        "127.0.0.1,localhost,192.168.93.68,192.168.2.5",
    ).split(",")
    if host.strip()
]

# ==================================================
# APPLICATIONS
# ==================================================

INSTALLED_APPS = [

    # 🔥 django-components
    "django_components",
    "channels",
    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # Dev tools
    "django_browser_reload",

    # UI / Core
    "ui.apps.UiConfig",
    "core.apps.CoreConfig",

    # ✅ CKEditor 5 (UNIQUEMENT celui-ci)
    "django_ckeditor_5",
    'superadmin',
    # Métier
    "admissions.apps.AdmissionsConfig",
    "inscriptions.apps.InscriptionsConfig",
    "payments.apps.PaymentsConfig",
    "students",
    "formations",
    "branches",
    # Contenu
    "blog.apps.BlogConfig",
    "news",
    "community.apps.CommunityConfig",
    "accounts.apps.AccountsConfig",
]

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
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # Dev
    "django_browser_reload.middleware.BrowserReloadMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

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
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ==================================================
# DATABASE
# ==================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "esfe_db"),
        "USER": os.getenv("DB_USER", "esfe_user"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}


# ==================================================
# DJANGO CHANNELS (WebSockets)
# ==================================================

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
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

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ==================================================
# MEDIA FILES
# ==================================================

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ==================================================
# DEFAULT PK
# ==================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==================================================
# URLS ABSOLUES (EMAILS / LIENS EXTERNES)
# ==================================================

BASE_URL = os.getenv("BASE_URL", "https://www.esfe-mali.org").rstrip("/")
EMAIL_LOGO_PATH = os.getenv("EMAIL_LOGO_PATH", "static/images/logo-esfe.png")

# ==================================================
# EMAIL (DEV)
# ==================================================

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").strip().lower() in {"1", "true", "yes", "on"}
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "noreply@esfe-mali.org")

# ==================================================
# AUTH REDIRECTS
# ==================================================

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "accounts:profile"
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
