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
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost","192.168.93.68"]

# ==================================================
# APPLICATIONS
# ==================================================

INSTALLED_APPS = [

    # 🔥 django-components
    "django_components",

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

    # Métier
    "admissions.apps.AdmissionsConfig",
    "inscriptions.apps.InscriptionsConfig",
    "payments.apps.PaymentsConfig",
    "students",
    "formations",

    # Contenu
    "blog.apps.BlogConfig",
    "news",
    "community",
    "accounts",
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
# URLS / WSGI
# ==================================================

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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
# EMAIL (DEV)
# ==================================================

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

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

STUDENT_LOGIN_URL = "http://127.0.0.1:8000/student/login/"