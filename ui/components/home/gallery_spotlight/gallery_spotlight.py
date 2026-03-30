from django_components import component
import json

from news.models import MediaItem


@component.register("gallery_spotlight")
class GallerySpotlight(component.Component):
    template_name = "home/gallery_spotlight/gallery_spotlight.html"

    def get_context_data(self, **kwargs):
        base_qs = (
            MediaItem.objects
            .filter(media_type=MediaItem.IMAGE, event__is_published=True)
            .select_related("event", "event__event_type")
            .order_by("-created_at")
        )

        featured = list(base_qs.filter(is_featured=True)[:30])
        if len(featured) < 30:
            featured_ids = [item.id for item in featured]
            featured.extend(list(base_qs.exclude(id__in=featured_ids)[:30 - len(featured)]))

        gallery_images = []
        for item in featured[:30]:
            if not item.image:
                continue
            gallery_images.append({
                "id": item.id,
                "src": item.thumbnail.url if item.thumbnail else item.image.url,
                "full_src": item.image.url,
                "title": item.caption or item.event.title,
                "date": item.event.event_date.strftime("%d/%m/%Y") if item.event.event_date else "",
                "category": item.event.event_type.name if item.event.event_type else "Galerie",
            })

        modal_images = gallery_images[:20]

        return {
            "images": gallery_images,
            "modal_images": modal_images,
            "images_json": json.dumps(gallery_images),
            "modal_images_json": json.dumps(modal_images),
            "section_title": kwargs.get('title', "Instants Capturés"),
            "section_subtitle": kwargs.get('subtitle', "Revivez les moments forts de notre communauté"),
            "gallery_url": kwargs.get('gallery_url', "/galerie/"),
            "total_count": base_qs.count(),
        }