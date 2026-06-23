"""Filigrane par utilisateur, incrusté côté serveur avec cache.

Approche retenue par défaut (cf. spec §6.2) : filigrane serveur avec Pillow,
mis en cache par (identité, mémoire, page) pour éviter de recalculer à
chaque requête. Alternative plus légère (overlay CSS/JS côté client) écartée
car retirable via devtools — documentée ici pour mémoire du compromis.
"""

import hashlib
from datetime import datetime, timezone as dt_timezone
from io import BytesIO

from django.core.cache import cache
from PIL import Image, ImageDraw, ImageFont

CACHE_TIMEOUT = 60 * 60 * 24  # 24h : l'horodatage du filigrane reste correct à la journée près.


def watermark_identity(request):
    """Identité affichée dans le filigrane : email si connecté, IP sinon."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user.email or user.get_username()
    return f"Visiteur {request.META.get('REMOTE_ADDR', 'inconnu')}"


def _cache_key(memoire_id, numero, identity):
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    jour = datetime.now(dt_timezone.utc).strftime("%Y%m%d")
    return f"memoire:watermark:{memoire_id}:{numero}:{digest}:{jour}"


def _draw_watermark(image_bytes, identity):
    image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    texte = f"{identity} • {datetime.now(dt_timezone.utc):%Y-%m-%d %H:%M} UTC"
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), texte, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    step_x = max(text_w + 60, 200)
    step_y = max(text_h + 60, 120)

    for y in range(0, image.size[1] + step_y, step_y):
        offset = (y // step_y) % 2
        for x in range(-step_x, image.size[0] + step_x, step_x):
            draw.text(
                (x + offset * step_x // 2, y),
                texte,
                font=font,
                fill=(120, 120, 120, 90),
            )

    watermarked = Image.alpha_composite(image, overlay).convert("RGB")
    buffer = BytesIO()
    watermarked.save(buffer, format="WEBP", quality=85)
    return buffer.getvalue()


def get_watermarked_page(page_memoire, identity):
    """Retourne les octets WebP de la page filigranée, en cache par identité."""
    key = _cache_key(page_memoire.memoire_id, page_memoire.numero, identity)
    cached = cache.get(key)
    if cached is not None:
        return cached

    with page_memoire.image.open("rb") as source:
        original_bytes = source.read()

    watermarked_bytes = _draw_watermark(original_bytes, identity)
    cache.set(key, watermarked_bytes, CACHE_TIMEOUT)
    return watermarked_bytes
