import fitz
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from formations.models import Filiere

from .forms import MemoireForm
from .models import ConsultationLog, Memoire, PageMemoire
from .services.rendering import render_memoire_pages


def _pdf_bytes(nb_pages=2):
    document = fitz.open()
    for _ in range(nb_pages):
        document.new_page(width=200, height=200)
    data = document.tobytes()
    document.close()
    return data


class MemoireModelTests(TestCase):
    def setUp(self):
        self.filiere = Filiere.objects.create(name="Informatique")

    def _creer_memoire(self, statut=Memoire.Statut.BROUILLON, **extra):
        defaults = dict(
            titre="Etude des systemes",
            slug="etude-des-systemes",
            auteurs="Jean Dupont",
            filiere=self.filiere,
            niveau=Memoire.Niveau.MASTER,
            annee=2026,
            resume="<p>Resume</p>",
            statut=statut,
            fichier_source=SimpleUploadedFile(
                "memoire.pdf", _pdf_bytes(), content_type="application/pdf"
            ),
        )
        defaults.update(extra)
        return Memoire.objects.create(**defaults)

    def test_publication_renseigne_date_publication(self):
        memoire = self._creer_memoire(statut=Memoire.Statut.PUBLIE)
        self.assertIsNotNone(memoire.date_publication)

    def test_render_memoire_pages_genere_les_pages(self):
        memoire = self._creer_memoire()
        nb_pages = render_memoire_pages(memoire)

        self.assertEqual(nb_pages, 2)
        memoire.refresh_from_db()
        self.assertEqual(memoire.nb_pages, 2)
        self.assertEqual(PageMemoire.objects.filter(memoire=memoire).count(), 2)

    def test_render_est_idempotent(self):
        memoire = self._creer_memoire()
        render_memoire_pages(memoire)
        render_memoire_pages(memoire)

        self.assertEqual(PageMemoire.objects.filter(memoire=memoire).count(), 2)


class MemoireAdminFormTests(TestCase):
    def setUp(self):
        self.filiere = Filiere.objects.create(name="Gestion")

    def _donnees_valides(self):
        return dict(
            titre="Gestion des stocks",
            slug="gestion-des-stocks",
            auteurs="Awa Traore",
            filiere=self.filiere.pk,
            niveau=Memoire.Niveau.LICENCE,
            annee=2025,
            resume="Resume",
            mots_cles="stock, gestion",
            statut=Memoire.Statut.BROUILLON,
        )

    def test_rejette_fichier_non_pdf(self):
        fichier = SimpleUploadedFile("memoire.txt", b"pas un pdf", content_type="text/plain")
        form = MemoireForm(data=self._donnees_valides(), files={"fichier_source": fichier})

        self.assertFalse(form.is_valid())
        self.assertIn("fichier_source", form.errors)

    def test_rejette_contenu_sans_entete_pdf(self):
        fichier = SimpleUploadedFile("memoire.pdf", b"contenu invalide", content_type="application/pdf")
        form = MemoireForm(data=self._donnees_valides(), files={"fichier_source": fichier})

        self.assertFalse(form.is_valid())
        self.assertIn("fichier_source", form.errors)

    def test_accepte_pdf_valide(self):
        fichier = SimpleUploadedFile("memoire.pdf", _pdf_bytes(1), content_type="application/pdf")
        form = MemoireForm(data=self._donnees_valides(), files={"fichier_source": fichier})

        self.assertTrue(form.is_valid(), form.errors)


class MemoirePublicViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.filiere = Filiere.objects.create(name="Sante")
        self.memoire_publie = Memoire.objects.create(
            titre="Memoire publie",
            slug="memoire-publie",
            auteurs="Fatou Kone",
            filiere=self.filiere,
            niveau=Memoire.Niveau.MASTER,
            annee=2026,
            resume="Resume public",
            mots_cles="sante, public",
            statut=Memoire.Statut.PUBLIE,
            fichier_source=SimpleUploadedFile(
                "memoire.pdf", _pdf_bytes(2), content_type="application/pdf"
            ),
        )
        render_memoire_pages(self.memoire_publie)

        self.memoire_brouillon = Memoire.objects.create(
            titre="Memoire brouillon",
            slug="memoire-brouillon",
            auteurs="Inconnu",
            filiere=self.filiere,
            niveau=Memoire.Niveau.LICENCE,
            annee=2025,
            resume="Resume prive",
            statut=Memoire.Statut.BROUILLON,
            fichier_source=SimpleUploadedFile(
                "memoire2.pdf", _pdf_bytes(1), content_type="application/pdf"
            ),
        )

    def test_liste_ne_montre_que_les_publies(self):
        response = self.client.get(reverse("memoires:liste"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Memoire publie")
        self.assertNotContains(response, "Memoire brouillon")

    def test_detail_brouillon_renvoie_404(self):
        response = self.client.get(
            reverse("memoires:detail", kwargs={"slug": self.memoire_brouillon.slug})
        )

        self.assertEqual(response.status_code, 404)

    def test_detail_incremente_la_vue_une_fois_par_session(self):
        url = reverse("memoires:detail", kwargs={"slug": self.memoire_publie.slug})

        self.client.get(url)
        self.client.get(url)

        self.memoire_publie.refresh_from_db()
        self.assertEqual(self.memoire_publie.nombre_vues, 1)
        self.assertEqual(ConsultationLog.objects.filter(memoire=self.memoire_publie).count(), 1)

    def test_servir_page_renvoie_du_webp_avec_entetes_anticache(self):
        url = reverse(
            "memoires:page", kwargs={"slug": self.memoire_publie.slug, "numero": 1}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/webp")
        self.assertIn("no-store", response["Cache-Control"])

    def test_servir_page_404_si_memoire_non_publie(self):
        memoire_brouillon = self.memoire_brouillon
        render_memoire_pages(memoire_brouillon)
        url = reverse(
            "memoires:page", kwargs={"slug": memoire_brouillon.slug, "numero": 1}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
