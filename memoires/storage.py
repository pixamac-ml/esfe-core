"""Stockage privé pour les fichiers de l'app memoires.

Bascule automatiquement sur un backend S3 (bucket privé, URLs signées) si les
variables d'environnement S3_* sont renseignées. Sinon, retombe sur un
répertoire local hors de MEDIA_ROOT (jamais servi par config.urls), ce qui
permet de développer/tester sans dépendre d'un fournisseur S3.
"""

from django.conf import settings
from django.core.files.storage import FileSystemStorage


def _build_storage():
    if getattr(settings, "MEMOIRES_S3_CONFIGURED", False):
        from storages.backends.s3 import S3Storage

        class MemoirePrivateS3Storage(S3Storage):
            bucket_name = settings.MEMOIRES_S3_BUCKET
            endpoint_url = settings.MEMOIRES_S3_ENDPOINT_URL
            access_key = settings.MEMOIRES_S3_ACCESS_KEY
            secret_key = settings.MEMOIRES_S3_SECRET_KEY
            default_acl = "private"
            querystring_auth = True
            querystring_expire = 300
            file_overwrite = False

        return MemoirePrivateS3Storage()

    settings.MEMOIRES_PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    return FileSystemStorage(location=str(settings.MEMOIRES_PRIVATE_ROOT))


memoire_private_storage = _build_storage()
