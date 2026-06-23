"""Rendu PDF -> images de pages (pré-génération unique au dépôt)."""

import logging
from io import BytesIO

import fitz
from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image

logger = logging.getLogger(__name__)


def _pixmap_to_webp(pixmap):
    """PyMuPDF ne sait pas encoder en WebP nativement -> on repasse par Pillow."""
    mode = "RGBA" if pixmap.alpha else "RGB"
    image = Image.frombytes(mode, [pixmap.width, pixmap.height], pixmap.samples)
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="WEBP", quality=85)
    return buffer.getvalue()


def render_memoire_pages(memoire):
    """Rend chaque page du fichier source en image WebP et crée les PageMemoire.

    Idempotent : supprime les pages existantes avant de régénérer, afin que
    l'action admin "(Re)générer les images de pages" puisse être rejouée.
    """
    from ..models import PageMemoire

    dpi = settings.MEMOIRE_RENDER_DPI
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    with memoire.fichier_source.open("rb") as source_file:
        pdf_bytes = source_file.read()

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        memoire.pages.all().delete()

        pages_crees = 0
        for numero, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=matrix)
            webp_bytes = _pixmap_to_webp(pixmap)

            page_memoire = PageMemoire(memoire=memoire, numero=numero)
            page_memoire.image.save(
                f"page_{numero:04d}.webp", ContentFile(webp_bytes), save=False
            )
            page_memoire.save()
            pages_crees += 1

        memoire.nb_pages = pages_crees
        memoire.save(update_fields=["nb_pages"])
        return pages_crees
    finally:
        document.close()
