from config.settings_test_local import *
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "dev_dg_test.sqlite3",
    }
}
DEBUG = True
ALLOWED_HOSTS = ["*"]
