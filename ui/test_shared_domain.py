from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django_components import registry

from ui.components.account.profile_card import ProfileCard
from ui.components.account.profile_dropdown import ProfileDropdown
from ui.components.account.profile_view import ProfileView
from ui.components.account.profile_editor import ProfileEditor
from ui.components.account.security_settings import SecuritySettings
from ui.components.account.preference_settings import PreferenceSettings
from ui.components.notifications.bell import NotificationBell
from ui.components.notifications.badge import NotificationBadge
from ui.components.notifications.item import NotificationItem
from ui.components.notifications.list import NotificationList
from ui.components.notifications.drawer import NotificationDrawer
from ui.components.student.identity_card import StudentIdentityCard
from ui.components.student.status_card import StudentStatusCard
from ui.components.student.progress_card import StudentProgressCard
from ui.components.shop.product_card import ProductCard
from ui.components.shop.product_grid import ProductGrid
from ui.components.shop.product_detail_drawer import ProductDetailDrawer


SHARED_DOMAIN_NAMES = {
    "account.profile_card",
    "account.profile_dropdown",
    "account.profile_view",
    "account.profile_editor",
    "account.security_settings",
    "account.preference_settings",
    "notifications.bell",
    "notifications.badge",
    "notifications.item",
    "notifications.list",
    "notifications.drawer",
    "student.identity_card",
    "student.status_card",
    "student.progress_card",
    "shop.product_card",
    "shop.product_grid",
    "shop.product_detail_drawer",
}


class SharedDomainComponentRegistrationTests(SimpleTestCase):
    def test_all_shared_domain_components_are_registered(self):
        registered = registry.all()
        for name in SHARED_DOMAIN_NAMES:
            self.assertIn(name, registered, f"{name} not registered")

    def test_shared_domain_templates_exist(self):
        registered = registry.all()
        base_template_dir = Path(settings.BASE_DIR, "ui", "templates")
        for name in SHARED_DOMAIN_NAMES:
            comp = registered[name]
            template_name = comp.template_name
            self.assertTrue(template_name, f"{name} has no template")
            template_path = base_template_dir / template_name
            self.assertTrue(template_path.is_file(), f"{name}: template {template_path} not found")

    def test_no_legacy_collisions(self):
        registered = registry.all()
        self.assertIsNot(registered.get("stat_card"), registered.get("ui_core.stat_card"))


class AccountProfileCardTests(SimpleTestCase):
    def test_renders_with_defaults(self):
        html = ProfileCard.render(kwargs={})
        self.assertIn('data-ui-core="profile-card"', html)
        self.assertIn("Utilisateur", html)

    def test_renders_with_user_data(self):
        html = ProfileCard.render(kwargs={
            "display_name": "Moussa Diarra",
            "role": "Gestionnaire",
            "branch": "Bamako",
            "status": "active",
        })
        self.assertIn("Moussa Diarra", html)
        self.assertIn("Gestionnaire", html)
        self.assertIn("Bamako", html)

    def test_compact_mode(self):
        html = ProfileCard.render(kwargs={"compact": True, "display_name": "Test"})
        self.assertNotIn("rounded-ui-card", html.split('data-ui-core="profile-card"')[1].split("</div>")[0])

    def test_long_content_renders(self):
        long_name = "N" * 200
        html = ProfileCard.render(kwargs={"display_name": long_name})
        self.assertIn(long_name, html)


class AccountProfileDropdownTests(SimpleTestCase):
    def test_renders_with_defaults(self):
        html = ProfileDropdown.render(kwargs={})
        self.assertIn('data-ui-core="profile-dropdown"', html)
        self.assertIn("aria-haspopup", html)

    def test_renders_with_links(self):
        html = ProfileDropdown.render(kwargs={
            "display_name": "Awa Koné",
            "profile_url": "/profile/",
            "edit_url": "/profile/edit/",
            "logout_url": "/logout/",
        })
        self.assertIn("Awa Koné", html)
        self.assertIn("/profile/", html)
        self.assertIn("Mon profil", html)
        self.assertIn("/logout/", html)


    def test_falls_back_to_profile_avatar_url(self):
        class DummyProfile:
            avatar_url = "/media/profiles/1/avatar/awa.png"

        class DummyUser:
            username = "awa"
            profile = DummyProfile()

            def get_full_name(self):
                return "Awa Koné"

        html = ProfileDropdown.render(kwargs={"user": DummyUser()})
        self.assertIn("/media/profiles/1/avatar/awa.png", html)


class AccountProfileViewTests(SimpleTestCase):
    def test_renders_with_defaults(self):
        html = ProfileView.render(kwargs={})
        self.assertIn('data-ui-core="profile-view"', html)
        self.assertIn("Utilisateur", html)

    def test_renders_with_full_data(self):
        html = ProfileView.render(kwargs={
            "display_name": "Fatoumata Koné",
            "email": "fatou@test.com",
            "role": "Secrétaire",
            "branch": "Sikasso",
            "phone": "+223 76 00 00 00",
        })
        self.assertIn("Fatoumata Koné", html)
        self.assertIn("fatou@test.com", html)
        self.assertIn("+223 76 00 00 00", html)

    def test_extra_fields_render(self):
        html = ProfileView.render(kwargs={
            "extra_fields": [{"label": "Matricule", "value": "STU-001"}],
        })
        self.assertIn("Matricule", html)
        self.assertIn("STU-001", html)


class AccountProfileEditorTests(SimpleTestCase):
    def test_renders_with_defaults(self):
        html = ProfileEditor.render(kwargs={})
        self.assertIn('data-ui-core="profile-editor"', html)
        self.assertIn("Modifier le profil", html)

    def test_htmx_attributes(self):
        html = ProfileEditor.render(kwargs={
            "hx_post": "/profile/edit/",
            "hx_target": "#profile-container",
        })
        self.assertIn('hx-post="/profile/edit/"', html)
        self.assertIn('hx-target="#profile-container"', html)


class AccountSecuritySettingsTests(SimpleTestCase):
    def test_renders_with_defaults(self):
        html = SecuritySettings.render(kwargs={})
        self.assertIn('data-ui-core="security-settings"', html)
        self.assertIn("Changer le mot de passe", html)


class AccountPreferenceSettingsTests(SimpleTestCase):
    def test_renders_with_defaults(self):
        html = PreferenceSettings.render(kwargs={})
        self.assertIn('data-ui-core="preference-settings"', html)
        self.assertIn("Préférences", html)


class NotificationBellTests(SimpleTestCase):
    def test_renders_zero_state(self):
        html = NotificationBell.render(kwargs={"unread_count": 0})
        self.assertIn('data-ui-core="notification-bell"', html)
        self.assertNotIn("bg-ui-danger", html)

    def test_renders_with_count(self):
        html = NotificationBell.render(kwargs={"unread_count": 5})
        self.assertIn("5", html)
        self.assertIn("bg-ui-danger", html)

    def test_renders_over_99(self):
        html = NotificationBell.render(kwargs={"unread_count": 150})
        self.assertIn("99+", html)


class NotificationBadgeTests(SimpleTestCase):
    def test_zero_hides_badge(self):
        html = NotificationBadge.render(kwargs={"count": 0})
        self.assertNotIn("notification-badge", html)

    def test_shows_count(self):
        html = NotificationBadge.render(kwargs={"count": 42})
        self.assertIn("42", html)

    def test_over_max(self):
        html = NotificationBadge.render(kwargs={"count": 150, "max_count": 99})
        self.assertIn("99+", html)


class NotificationItemTests(SimpleTestCase):
    def test_renders_unread(self):
        html = NotificationItem.render(kwargs={
            "title": "Nouvelle inscription",
            "is_read": False,
        })
        self.assertIn("Nouvelle inscription", html)
        self.assertIn("bg-ui-info/5", html)

    def test_renders_read(self):
        html = NotificationItem.render(kwargs={
            "title": "Ancienne notif",
            "is_read": True,
        })
        self.assertNotIn("bg-ui-info/5", html)

    def test_high_priority(self):
        html = NotificationItem.render(kwargs={
            "title": "Urgent",
            "priority": "high",
        })
        self.assertIn("bg-ui-danger/10", html)


class NotificationListTests(SimpleTestCase):
    def test_empty_state(self):
        html = NotificationList.render(kwargs={"notifications": []})
        self.assertIn("Aucune notification", html)

    def test_loading_state(self):
        html = NotificationList.render(kwargs={"loading": True})
        self.assertIn("animate-spin", html)


class NotificationDrawerTests(SimpleTestCase):
    def test_renders_overlay(self):
        html = NotificationDrawer.render(kwargs={})
        self.assertIn('data-ui-core="notification-drawer"', html)
        self.assertIn("uiOverlay", html)
        self.assertIn("@keydown.escape.window", html)


class StudentIdentityCardTests(SimpleTestCase):
    def test_renders_with_defaults(self):
        html = StudentIdentityCard.render(kwargs={})
        self.assertIn('data-ui-core="student-identity-card"', html)
        self.assertIn("Étudiant", html)

    def test_renders_with_data(self):
        html = StudentIdentityCard.render(kwargs={
            "full_name": "Moussa Diakité",
            "matricule": "STU-2024-001",
            "classe": "6e A",
            "niveau": "6ème",
        })
        self.assertIn("Moussa Diakité", html)
        self.assertIn("STU-2024-001", html)
        self.assertIn("6e A", html)

    def test_inactive_state(self):
        html = StudentIdentityCard.render(kwargs={"is_active": False})
        self.assertIn("Inactif", html)


class StudentStatusCardTests(SimpleTestCase):
    def test_promoted(self):
        html = StudentStatusCard.render(kwargs={"status": "promoted", "status_label": "Promu"})
        self.assertIn("Promu", html)
        self.assertIn("bg-ui-success/10", html)

    def test_repeated(self):
        html = StudentStatusCard.render(kwargs={"status": "repeated", "status_label": "Redoublant"})
        self.assertIn("Redoublant", html)
        self.assertIn("bg-ui-warning/10", html)


class StudentProgressCardTests(SimpleTestCase):
    def test_empty(self):
        html = StudentProgressCard.render(kwargs={})
        self.assertIn('data-ui-core="student-progress-card"', html)
        self.assertIn("Progression académique", html)

    def test_with_items(self):
        html = StudentProgressCard.render(kwargs={
            "items": [{"label": "Maths", "percentage": 75}, {"label": "Français", "percentage": 45}],
            "overall_percentage": 60,
        })
        self.assertIn("Maths", html)
        self.assertIn("60%", html)


class ShopProductCardTests(SimpleTestCase):
    def test_renders_with_defaults(self):
        html = ProductCard.render(kwargs={})
        self.assertIn('data-ui-core="product-card"', html)
        self.assertIn("Produit", html)

    def test_unavailable(self):
        html = ProductCard.render(kwargs={"is_available": False})
        self.assertIn("Indisponible", html)

    def test_out_of_stock(self):
        html = ProductCard.render(kwargs={"stock": 0, "is_available": True})
        self.assertIn("Rupture de stock", html)

    def test_with_data(self):
        html = ProductCard.render(kwargs={
            "name": "Blouse ESFE",
            "price": "5 000 FCFA",
            "category": "Uniforme",
            "stock": 12,
        })
        self.assertIn("Blouse ESFE", html)
        self.assertIn("5 000 FCFA", html)


class ShopProductGridTests(SimpleTestCase):
    def test_empty(self):
        html = ProductGrid.render(kwargs={})
        self.assertIn("Aucun produit disponible", html)

    def test_loading(self):
        html = ProductGrid.render(kwargs={"loading": True})
        self.assertIn("animate-pulse", html)


class ShopProductDetailDrawerTests(SimpleTestCase):
    def test_renders_overlay(self):
        html = ProductDetailDrawer.render(kwargs={})
        self.assertIn('data-ui-core="product-detail-drawer"', html)
        self.assertIn("uiOverlay", html)
        self.assertIn("@keydown.escape.window", html)


class SharedDomainArchitectureTests(SimpleTestCase):
    def test_shared_components_do_not_import_business_apps(self):
        root = Path(settings.BASE_DIR, "ui", "components")
        forbidden_roots = {
            "academic_cycle", "academics", "accounts", "admissions",
            "branches", "inscriptions", "payments", "portal",
            "secretary", "students", "superadmin", "notifier",
        }
        import ast
        failures = []
        for domain in ("account", "notifications", "student", "shop"):
            domain_root = root / domain
            if not domain_root.exists():
                continue
            for path in domain_root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    modules = []
                    if isinstance(node, ast.Import):
                        modules = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        modules = [node.module]
                    for module in modules:
                        if module.split(".", 1)[0] in forbidden_roots:
                            failures.append(f"{path.relative_to(root)} -> {module}")
                        if module == "django.db" or module.startswith("django.db."):
                            failures.append(f"{path.relative_to(root)} -> {module}")
                    if isinstance(node, ast.Attribute) and node.attr == "objects":
                        failures.append(f"{path.relative_to(root)} -> ORM .objects")
        self.assertEqual(failures, [])


class DomainCatalogTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="catalog-user", password="test-password"
        )
        self.client.force_login(self.user)

    @override_settings(DEBUG=True)
    def test_domain_components_in_system_page(self):
        response = self.client.get(reverse("ui:system"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Composants Métier")
        self.assertContains(response, "domain-account")
        self.assertContains(response, "domain-notifications")
        self.assertContains(response, "domain-student")
        self.assertContains(response, "domain-shop")
