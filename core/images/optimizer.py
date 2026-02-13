# core/images/optimizer.py
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile

def optimize_image(
    image_field,
    max_width=1600,
    quality=75,
    format='JPEG'
):
    img = Image.open(image_field)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    buffer = BytesIO()
    img.save(
        buffer,
        format=format,
        quality=quality,
        optimize=True
    )

    return ContentFile(
        buffer.getvalue(),
        name=image_field.name
    )
