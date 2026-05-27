def archive_media(media, *, actor=None):
    media.is_archived = True
    media.save(update_fields=["is_archived"])
    return media


def restore_media(media, *, actor=None):
    media.is_archived = False
    media.save(update_fields=["is_archived"])
    return media
