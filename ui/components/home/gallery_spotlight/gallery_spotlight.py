from django_components import component


@component.register("gallery_spotlight")
class GallerySpotlight(component.Component):
    template_name = "home/gallery_spotlight/gallery_spotlight.html"

    def get_context_data(self, **kwargs):
        # Images de démonstration - à remplacer par vos vraies données
        # En production : GalleryImage.objects.filter(featured=True)[:6]

        gallery_images = kwargs.get('images', [
            {
                "id": 1,
                "src": "/static/images/gallery/ceremonie-1.jpg",
                "title": "Cérémonie de Diplomation",
                "date": "Mars 2024",
                "category": "Cérémonie"
            },
            {
                "id": 2,
                "src": "/static/images/gallery/stage-1.jpg",
                "title": "Stage Pratique CHU",
                "date": "Février 2024",
                "category": "Formation"
            },
            {
                "id": 3,
                "src": "/static/images/gallery/sport-1.jpg",
                "title": "Journée Sportive Inter-Écoles",
                "date": "Janvier 2024",
                "category": "Vie Étudiante"
            },
            {
                "id": 4,
                "src": "/static/images/gallery/labo-1.jpg",
                "title": "Travaux Pratiques Laboratoire",
                "date": "Décembre 2023",
                "category": "Formation"
            },
            {
                "id": 5,
                "src": "/static/images/gallery/rentree-1.jpg",
                "title": "Rentrée Académique 2024",
                "date": "Octobre 2023",
                "category": "Événement"
            },
            {
                "id": 6,
                "src": "/static/images/gallery/conference-1.jpg",
                "title": "Conférence Santé Publique",
                "date": "Novembre 2023",
                "category": "Conférence"
            },
        ])

        # Convertir en JSON pour Alpine.js
        import json

        return {
            "images": gallery_images,
            "images_json": json.dumps(gallery_images),
            "section_title": kwargs.get('title', "Instants Capturés"),
            "section_subtitle": kwargs.get('subtitle', "Revivez les moments forts de notre communauté"),
            "gallery_url": kwargs.get('gallery_url', "/galerie/"),
            "total_count": kwargs.get('total_count', 48),
        }