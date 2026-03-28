from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class AdminPanelDashboardLinksTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='paneladmin',
            email='paneladmin@test.com',
            password='adminpass123'
        )

    def test_dashboard_renders_admin_links(self):
        self.client.login(username='paneladmin', password='adminpass123')

        response = self.client.get(reverse('admin_panel:dashboard'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(reverse('admin:index'), content)
        self.assertIn(reverse('admin:auth_user_changelist'), content)
        self.assertIn(reverse('admin:auth_group_changelist'), content)
        self.assertIn(reverse('admin:auth_permission_changelist'), content)
        self.assertNotIn('系统配置', content)

    def test_scheduled_tasks_page_renders_admin_link(self):
        self.client.login(username='paneladmin', password='adminpass123')

        response = self.client.get(reverse('admin_panel:scheduled_tasks'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(reverse('admin:index'), response.content.decode())