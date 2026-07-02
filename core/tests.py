from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from core.models import ContactMessage, LegalPage, LegalSection


class LegalPagesTests(TestCase):
	def setUp(self):
		self.legal = LegalPage.objects.create(
			page_type="legal",
			title="Mentions legales",
			introduction="Intro",
			status="published",
		)
		self.privacy = LegalPage.objects.create(
			page_type="privacy",
			title="Confidentialite",
			introduction="Intro",
			status="published",
		)
		self.terms = LegalPage.objects.create(
			page_type="terms",
			title="Conditions d'utilisation",
			introduction="Intro",
			status="published",
		)

		for page in [self.legal, self.privacy, self.terms]:
			LegalSection.objects.create(
				page=page,
				title="Section 1",
				content="Contenu test",
				is_active=True,
				order=1,
			)

	def test_legal_pages_are_accessible_when_published(self):
		urls = [
			reverse("core:legal_notice"),
			reverse("core:privacy_policy"),
			reverse("core:terms_of_service"),
		]

		for url in urls:
			with self.subTest(url=url):
				response = self.client.get(url)
				self.assertEqual(response.status_code, 200)

	def test_legal_page_returns_404_when_not_published(self):
		self.terms.status = "draft"
		self.terms.save(update_fields=["status"])

		response = self.client.get(reverse("core:terms_of_service"))
		self.assertEqual(response.status_code, 404)

	def test_legal_pdf_export_works(self):
		response = self.client.get(reverse("core:legal_pdf", args=["legal"]))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response["Content-Type"], "application/pdf")


class SeoPlatformTests(TestCase):
	def test_home_contains_core_seo_tags(self):
		response = self.client.get(reverse("core:home"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '<meta name="description"', html=False)
		self.assertContains(response, '<link rel="canonical"', html=False)

	def test_robots_txt_exists(self):
		response = self.client.get(reverse("core:robots_txt"))
		self.assertEqual(response.status_code, 200)
		self.assertIn("text/plain", response["Content-Type"])
		self.assertContains(response, "Sitemap:", html=False)

	def test_sitemap_xml_exists(self):
		response = self.client.get("/sitemap.xml")
		self.assertEqual(response.status_code, 200)
		self.assertIn("xml", response["Content-Type"])


class ContactFormTests(TestCase):
	@patch("core.views.NotificationBus.send_email")
	def test_contact_post_creates_message_without_serialization_error(self, mock_send):
		response = self.client.post(
			reverse("core:contact"),
			data={
				"full_name": "Awa Traore",
				"email": "awa@example.com",
				"phone": "+22370000000",
				"subject": "admission",
				"message": "Je souhaite contacter l'ecole.",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(ContactMessage.objects.count(), 1)
		self.assertContains(response, "Votre message a bien ete transmis", html=False)
		self.assertEqual(mock_send.call_count, 2)

