from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


class SharedDomainCatalogTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="catalog-user",
            password="test-password",
        )
        self.client.force_login(self.user)

    @override_settings(DEBUG=True)
    def test_catalog_route_is_interactive(self):
        response = self.client.get(reverse("ui:system_domains"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Catalogue des composants")
        self.assertContains(response, "Voir la démonstration")
        self.assertContains(response, "domain-component-drawer")

    @override_settings(DEBUG=True)
    def test_component_detail_fragment(self):
        response = self.client.get(
            reverse("ui:system_domain_component", kwargs={"slug": "account-profile-card"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Carte Profil")
        self.assertContains(response, 'hx-get="/ui/system/domains/demo/account-profile-card/"')

    @override_settings(DEBUG=False)
    def test_catalog_route_is_protected_in_production(self):
        response = self.client.get(reverse("ui:system_domains"))
        self.assertEqual(response.status_code, 403)
