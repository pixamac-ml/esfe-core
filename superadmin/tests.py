from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from news.models import Event, EventType, MediaItem, ResultSession
from core.models import ContactMessage, LegalPage
from branches.models import Branch
from payments.models import PaymentAgent


User = get_user_model()


class SuperadminAccessPolicyTests(TestCase):
    def test_superuser_can_access_superadmin_dashboard(self):
        admin_user = User.objects.create_superuser(
            username='admin_root',
            email='admin_root@example.com',
            password='pass1234',
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse('superadmin:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_staff_user_is_denied_superadmin_dashboard(self):
        staff_user = User.objects.create_user(
            username='staff_ops',
            email='staff_ops@example.com',
            password='pass1234',
            is_staff=True,
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse('superadmin:dashboard'))
        self.assertEqual(response.status_code, 302)


class SuperadminUserManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin_users',
            email='admin_users@example.com',
            password='pass1234',
        )
        self.client.force_login(self.user)
        self.branch = Branch.objects.create(name='Annexe Test', code='ATS', slug='annexe-test')

    def test_create_user_with_role_and_group(self):
        list_response = self.client.get(reverse('superadmin:user_list'))
        self.assertEqual(list_response.status_code, 200)
        group_id = str(list_response.context['groups'].first().id)

        response = self.client.post(
            reverse('superadmin:user_create'),
            {
                'username': 'agent_adm',
                'email': 'agent_adm@example.com',
                'first_name': 'Agent',
                'last_name': 'Admission',
                'password': 'pass1234',
                'role': 'admissions',
                'branch': str(self.branch.pk),
                'groups': [group_id],
                'is_staff': 'on',
                'is_active': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        created = User.objects.get(username='agent_adm')
        self.assertTrue(created.is_staff)
        self.assertTrue(created.is_active)
        self.assertEqual(created.profile.role, 'admissions')
        self.assertEqual(created.profile.branch_id, self.branch.pk)
        self.assertTrue(created.groups.exists())

    def test_edit_user_updates_role_groups(self):
        target = User.objects.create_user(
            username='agent_finance',
            email='agent_finance@example.com',
            password='pass1234',
            is_staff=True,
        )

        list_response = self.client.get(reverse('superadmin:user_list'))
        self.assertEqual(list_response.status_code, 200)
        group_id = str(list_response.context['groups'].first().id)

        response = self.client.post(
            reverse('superadmin:user_edit', args=[target.pk]),
            {
                'username': 'agent_finance',
                'email': 'agent_finance@example.com',
                'first_name': 'Agent',
                'last_name': 'Finance',
                'role': 'finance',
                'branch': str(self.branch.pk),
                'groups': [group_id],
                'is_staff': 'on',
                'is_active': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertEqual(target.profile.role, 'finance')
        self.assertEqual(target.profile.branch_id, self.branch.pk)
        self.assertEqual(target.groups.count(), 1)

    def test_non_staff_user_is_denied_superadmin_dashboard(self):
        basic_user = User.objects.create_user(
            username='basic_user',
            email='basic_user@example.com',
            password='pass1234',
            is_staff=False,
        )
        self.client.force_login(basic_user)

        response = self.client.get(reverse('superadmin:dashboard'))
        self.assertEqual(response.status_code, 302)


class GalleryBulkUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='pass1234',
        )
        self.client.force_login(self.user)

        self.event_type = EventType.objects.create(name='Conference', slug='conference')
        self.event = Event.objects.create(
            title='Journee portes ouvertes',
            event_type=self.event_type,
            event_date='2026-03-29',
            is_published=True,
        )

    def _make_image(self, name='image.png'):
        buffer = BytesIO()
        image = Image.new('RGB', (80, 80), color='blue')
        image.save(buffer, format='PNG')
        return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')

    def test_bulk_upload_creates_image_and_video(self):
        image_file = self._make_image()
        video_file = SimpleUploadedFile('clip.mp4', b'fake-video-data', content_type='video/mp4')

        response = self.client.post(
            reverse('superadmin:gallery_bulk_upload'),
            {
                'event': str(self.event.pk),
                'use_filename_caption': 'on',
                'media_files': [image_file, video_file],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(MediaItem.objects.filter(event=self.event).count(), 2)
        self.assertEqual(MediaItem.objects.filter(event=self.event, media_type=MediaItem.IMAGE).count(), 1)
        self.assertEqual(MediaItem.objects.filter(event=self.event, media_type=MediaItem.VIDEO).count(), 1)

    def test_bulk_upload_ignores_unsupported_extension(self):
        file_unknown = SimpleUploadedFile('notes.txt', b'text', content_type='text/plain')

        response = self.client.post(
            reverse('superadmin:gallery_bulk_upload'),
            {
                'event': str(self.event.pk),
                'media_files': [file_unknown],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(MediaItem.objects.filter(event=self.event).count(), 0)

    def test_bulk_action_feature_on_and_delete(self):
        item_a = MediaItem.objects.create(
            event=self.event,
            media_type=MediaItem.IMAGE,
            image=self._make_image('a.png'),
        )
        item_b = MediaItem.objects.create(
            event=self.event,
            media_type=MediaItem.IMAGE,
            image=self._make_image('b.png'),
        )

        response_feature = self.client.post(
            reverse('superadmin:gallery_bulk_action'),
            {
                'action': 'feature_on',
                'media_ids': [str(item_a.pk), str(item_b.pk)],
            },
        )
        self.assertEqual(response_feature.status_code, 302)
        self.assertEqual(MediaItem.objects.filter(pk__in=[item_a.pk, item_b.pk], is_featured=True).count(), 2)

        response_delete = self.client.post(
            reverse('superadmin:gallery_bulk_action'),
            {
                'action': 'delete',
                'media_ids': [str(item_a.pk), str(item_b.pk)],
            },
        )
        self.assertEqual(response_delete.status_code, 302)
        self.assertEqual(MediaItem.objects.filter(pk__in=[item_a.pk, item_b.pk]).count(), 0)


class MessageModuleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin_messages',
            email='admin_messages@example.com',
            password='pass1234',
        )
        self.client.force_login(self.user)

        self.msg_new = ContactMessage.objects.create(
            full_name='Alice Contact',
            email='alice@example.com',
            subject='admission',
            message='Bonjour, je veux des infos.',
            status='new',
        )
        self.msg_progress = ContactMessage.objects.create(
            full_name='Bob Contact',
            email='bob@example.com',
            subject='payment',
            message='Question paiement.',
            status='in_progress',
        )

    def test_message_list_filters_by_status(self):
        response = self.client.get(reverse('superadmin:message_list'), {'status': 'new'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice Contact')
        self.assertNotContains(response, 'Bob Contact')

    def test_update_message_status_answered_sets_answered_at(self):
        response = self.client.post(
            reverse('superadmin:message_status', args=[self.msg_new.pk]),
            {'status': 'answered'},
        )
        self.assertEqual(response.status_code, 302)
        self.msg_new.refresh_from_db()
        self.assertEqual(self.msg_new.status, 'answered')
        self.assertIsNotNone(self.msg_new.answered_at)

    def test_update_message_status_can_save_reply(self):
        response = self.client.post(
            reverse('superadmin:message_status', args=[self.msg_new.pk]),
            {
                'status': 'answered',
                'reply': 'Bonjour, voici les informations demandees.',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.msg_new.refresh_from_db()
        self.assertEqual(self.msg_new.status, 'answered')
        self.assertEqual(self.msg_new.reply, 'Bonjour, voici les informations demandees.')
        self.assertIsNotNone(self.msg_new.answered_at)

    def test_bulk_action_mark_closed(self):
        response = self.client.post(
            reverse('superadmin:bulk_action'),
            {
                'model_type': 'message',
                'action': 'mark_closed',
                'selected_ids': [str(self.msg_new.pk), str(self.msg_progress.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.filter(status='closed').count(), 2)


class EventModuleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin_events',
            email='admin_events@example.com',
            password='pass1234',
        )
        self.client.force_login(self.user)

        self.event_type = EventType.objects.create(name='Salon', slug='salon')
        self.event_a = Event.objects.create(
            title='Event A',
            event_type=self.event_type,
            event_date='2026-03-01',
            is_published=False,
        )
        self.event_b = Event.objects.create(
            title='Event B',
            event_type=self.event_type,
            event_date='2026-03-02',
            is_published=True,
        )

    def test_bulk_publish_and_unpublish_events(self):
        response_publish = self.client.post(
            reverse('superadmin:bulk_action'),
            {
                'model_type': 'event',
                'action': 'publish',
                'selected_ids': [str(self.event_a.pk), str(self.event_b.pk)],
            },
        )
        self.assertEqual(response_publish.status_code, 302)
        self.assertEqual(Event.objects.filter(pk__in=[self.event_a.pk, self.event_b.pk], is_published=True).count(), 2)

        response_unpublish = self.client.post(
            reverse('superadmin:bulk_action'),
            {
                'model_type': 'event',
                'action': 'unpublish',
                'selected_ids': [str(self.event_a.pk), str(self.event_b.pk)],
            },
        )
        self.assertEqual(response_unpublish.status_code, 302)
        self.assertEqual(Event.objects.filter(pk__in=[self.event_a.pk, self.event_b.pk], is_published=False).count(), 2)

    def test_bulk_delete_events(self):
        response_delete = self.client.post(
            reverse('superadmin:bulk_action'),
            {
                'model_type': 'event',
                'action': 'delete',
                'selected_ids': [str(self.event_a.pk), str(self.event_b.pk)],
            },
        )
        self.assertEqual(response_delete.status_code, 302)
        self.assertEqual(Event.objects.filter(pk__in=[self.event_a.pk, self.event_b.pk]).count(), 0)


class PaymentAgentModuleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin_payments_agents',
            email='admin_payments_agents@example.com',
            password='pass1234',
        )
        self.client.force_login(self.user)

        self.staff_a = User.objects.create_user(
            username='cashier_a',
            email='cashier_a@example.com',
            password='pass1234',
            is_staff=True,
        )
        self.staff_b = User.objects.create_user(
            username='cashier_b',
            email='cashier_b@example.com',
            password='pass1234',
            is_staff=True,
        )

        self.branch_a = Branch.objects.create(name='Annexe A', code='ANA', slug='annexe-a')
        self.branch_b = Branch.objects.create(name='Annexe B', code='ANB', slug='annexe-b')

    def test_create_payment_agent(self):
        response = self.client.post(
            reverse('superadmin:payment_agent_create'),
            {
                'user': str(self.staff_a.pk),
                'branch': str(self.branch_a.pk),
                'is_active': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PaymentAgent.objects.filter(user=self.staff_a, branch=self.branch_a, is_active=True).exists())

    def test_edit_payment_agent_branch_assignment(self):
        agent = PaymentAgent.objects.create(user=self.staff_a, branch=self.branch_a, is_active=True)

        response = self.client.post(
            reverse('superadmin:payment_agent_edit', args=[agent.pk]),
            {
                'user': str(self.staff_b.pk),
                'branch': str(self.branch_b.pk),
                'is_active': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        agent.refresh_from_db()
        self.assertEqual(agent.user_id, self.staff_b.pk)
        self.assertEqual(agent.branch_id, self.branch_b.pk)


class ResultModuleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin_results',
            email='admin_results@example.com',
            password='pass1234',
        )
        self.client.force_login(self.user)

    def test_create_result_from_superadmin(self):
        pdf_file = SimpleUploadedFile('res.pdf', b'%PDF-1.4\nfake\n', content_type='application/pdf')

        response = self.client.post(
            reverse('superadmin:result_create'),
            {
                'titre': 'Resultat test',
                'type': 'semestre',
                'annee_academique': '2025-2026',
                'annexe': 'Douala',
                'filiere': 'Informatique',
                'classe': 'L3',
                'is_published': 'on',
                'fichier_pdf': pdf_file,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ResultSession.objects.filter(titre='Resultat test', is_published=True).exists())

    def test_toggle_result_publication(self):
        result = ResultSession.objects.create(
            type='semestre',
            titre='Session test',
            annee_academique='2025-2026',
            annexe='Yaounde',
            filiere='Gestion',
            classe='L2',
            fichier_pdf=SimpleUploadedFile('toggle.pdf', b'%PDF-1.4\nfake\n', content_type='application/pdf'),
            is_published=False,
        )

        response = self.client.post(reverse('superadmin:toggle_result', args=[result.pk]))
        self.assertEqual(response.status_code, 302)
        result.refresh_from_db()
        self.assertTrue(result.is_published)

    def test_result_list_hx_returns_partial_table(self):
        ResultSession.objects.create(
            type='semestre',
            titre='Session HX',
            annee_academique='2025-2026',
            annexe='Douala',
            filiere='Info',
            classe='L1',
            fichier_pdf=SimpleUploadedFile('hx.pdf', b'%PDF-1.4\nhx\n', content_type='application/pdf'),
            is_published=True,
        )

        response = self.client.get(reverse('superadmin:result_list'), HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-table')
        self.assertContains(response, 'Session HX')


class LegalPagesSuperadminTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin_legal',
            email='admin_legal@example.com',
            password='pass1234',
        )
        self.client.force_login(self.user)

    def test_page_list_is_accessible(self):
        response = self.client.get(reverse('superadmin:page_list'))
        self.assertEqual(response.status_code, 200)

    def test_create_legal_page_from_superadmin(self):
        response = self.client.post(
            reverse('superadmin:page_create'),
            {
                'page_type': 'legal',
                'title': 'Mentions legales',
                'introduction': 'Introduction test',
                'version': '1.0',
                'status': 'published',
                'section_id[]': [''],
                'section_title[]': ['Identification'],
                'section_content[]': ['Contenu section'],
                'section_order[]': ['1'],
                'section_is_active[]': ['0'],
                'sidebar_id[]': [''],
                'sidebar_title[]': ['Contact'],
                'sidebar_content[]': ['contact@example.com'],
                'sidebar_order[]': ['1'],
                'sidebar_is_active[]': ['0'],
            },
        )

        self.assertEqual(response.status_code, 302)
        page = LegalPage.objects.get(page_type='legal')
        self.assertEqual(page.status, 'published')
        self.assertEqual(page.sections.count(), 1)
        self.assertEqual(page.sidebar_blocks.count(), 1)

        public_response = self.client.get(reverse('core:legal_notice'))
        self.assertEqual(public_response.status_code, 200)


