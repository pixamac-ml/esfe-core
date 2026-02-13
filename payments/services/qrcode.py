import qrcode
from io import BytesIO
from reportlab.lib.utils import ImageReader


def generate_qr_image(data: str) -> ImageReader:
    """
    Génère un QR Code compatible ReportLab (ImageReader)
    """

    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )

    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return ImageReader(buffer)
