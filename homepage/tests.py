from django.test import TestCase, Client
from django.contrib.auth.models import User, Permission
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType

from accounts.models import UserProfile


class HomepageViewTestCase(TestCase):
    """Test cases for HomepageView."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create test users
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='admin123'
        )
        
        self.authenticated_user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='testpass123'
        )
        UserProfile.objects.create(
            user=self.authenticated_user,
            role='user',
            permissions={}
        )

        self.readonly_user = User.objects.create_user(
            username='readonly',
            email='readonly@test.com',
            password='readonlypass123'
        )
        UserProfile.objects.create(
            user=self.readonly_user,
            role='readonly',
            permissions={}
        )
        
        self.unauthenticated_user = None  # Not logged in
        
        # Create some permissions for testing
        # Get or create permissions for each module
        self.devices_permission = self._get_or_create_permission('devices', 'view_device')
        self.configs_permission = self._get_or_create_permission('configs', 'view_config')
        self.monitoring_permission = self._get_or_create_permission('monitoring', 'view_monitoring')
    
    def _get_or_create_permission(self, app_label, codename):
        """Helper to get or create a permission."""
        try:
            return Permission.objects.get(
                content_type__app_label=app_label,
                codename=codename
            )
        except Permission.DoesNotExist:
            # Create a dummy content type if it doesn't exist
            content_type, _ = ContentType.objects.get_or_create(
                app_label=app_label,
                model=codename.replace('view_', '')
            )
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type,
                codename=codename,
                defaults={'name': f'Can view {codename}'}
            )
            return permission
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Test that unauthenticated users are redirected to login page."""
        response = self.client.get(reverse('homepage:homepage'))
        
        # Should redirect to login page
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
    
    def test_authenticated_user_sees_homepage(self):
        """Test that authenticated users can see the homepage."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('homepage:homepage'))
        
        # Should return 200 OK
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'homepage/homepage.html')
    
    def test_superuser_sees_all_modules(self):
        """Test that superusers see all 8 modules."""
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('homepage:homepage'))
        
        self.assertEqual(response.status_code, 200)
        modules = response.context['modules']
        
        # Superuser should see all 8 modules
        self.assertEqual(len(modules), 8)

        # Verify all module keys are present
        module_keys = [m['key'] for m in modules]
        expected_keys = ['devices', 'configs', 'monitoring', 'alerts', 'logs', 'backups', 'accounts']
        self.assertEqual(sorted(module_keys), sorted(expected_keys))
    
    def test_user_with_specific_permissions_sees_only_allowed_modules(self):
        """Test that users with specific permissions only see those modules."""
        # Grant only devices and configs permissions
        self.authenticated_user.user_permissions.add(self.devices_permission)
        self.authenticated_user.user_permissions.add(self.configs_permission)
        
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('homepage:homepage'))
        
        self.assertEqual(response.status_code, 200)
        modules = response.context['modules']
        
        # User should only see 2 modules
        self.assertEqual(len(modules), 2)
        
        # Verify only allowed modules are present
        module_keys = [m['key'] for m in modules]
        self.assertIn('devices', module_keys)
        self.assertIn('configs', module_keys)
        self.assertNotIn('monitoring', module_keys)
    
    def test_user_without_permissions_sees_no_modules(self):
        """Test that users without any permissions see no modules."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('homepage:homepage'))
        
        self.assertEqual(response.status_code, 200)
        modules = response.context['modules']
        
        # User without permissions should see no modules
        self.assertEqual(len(modules), 0)

    def test_readonly_user_sees_only_devices_module(self):
        """Test that readonly users only see the devices module."""
        self.client.login(username='readonly', password='readonlypass123')
        response = self.client.get(reverse('homepage:homepage'))

        self.assertEqual(response.status_code, 200)
        modules = response.context['modules']
        self.assertEqual([module['key'] for module in modules], ['devices'])
    
    def test_module_metadata_is_correct(self):
        """Test that module metadata contains all required fields."""
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('homepage:homepage'))
        
        modules = response.context['modules']
        
        # Check that each module has required fields
        for module in modules:
            self.assertIn('key', module)
            self.assertIn('name', module)
            self.assertIn('description', module)
            self.assertIn('url', module)
            self.assertIn('icon', module)
            self.assertIn('permission', module)
    
    def test_module_urls_are_correct(self):
        """Test that module URLs are correctly set."""
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('homepage:homepage'))
        
        modules = response.context['modules']
        
        # Create a mapping of expected URLs
        expected_urls = {
            'devices': '/devices/',
            'configs': '/configs/',
            'monitoring': '/monitoring/',
            'alerts': '/alerts/',
            'logs': '/logs/',
            'backups': '/backups/',
            'accounts': '/accounts/',
        }
        
        for module in modules:
            self.assertEqual(module['url'], expected_urls[module['key']])
    
    def test_template_renders_with_modules(self):
        """Test that the template renders correctly with modules."""
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('homepage:homepage'))
        
        self.assertEqual(response.status_code, 200)
        
        # Check that the response contains module information
        content = response.content.decode()
        
        # Verify that at least some module names appear in the rendered HTML
        self.assertIn('Devices', content)
        self.assertIn('Configs', content)
    
    def test_login_url_is_correct(self):
        """Test that the login_url is set correctly."""
        from homepage.views import HomepageView
        
        view = HomepageView()
        self.assertEqual(view.login_url, 'homepage:login')
    
    def test_template_name_is_correct(self):
        """Test that the template_name is set correctly."""
        from homepage.views import HomepageView
        
        view = HomepageView()
        self.assertEqual(view.template_name, 'homepage/homepage.html')



class LoginViewTestCase(TestCase):
    """Test cases for LoginView."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='testpass123'
        )
    
    def test_unauthenticated_user_sees_login_page(self):
        """Test that unauthenticated users can see the login page."""
        response = self.client.get(reverse('homepage:login'))
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'homepage/login.html')
    
    def test_authenticated_user_redirected_to_homepage(self):
        """Test that authenticated users are redirected to homepage."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('homepage:login'))
        
        # Should redirect to homepage
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('homepage:homepage'), response.url)
    
    def test_login_with_valid_credentials(self):
        """Test login with valid credentials."""
        response = self.client.post(reverse('homepage:login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        
        # Should redirect to homepage
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('homepage:homepage'), response.url)
        
        # Verify user is authenticated
        self.assertTrue(response.wsgi_request.user.is_authenticated)
    
    def test_login_with_invalid_credentials(self):
        """Test login with invalid credentials."""
        response = self.client.post(reverse('homepage:login'), {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        
        # Should return 200 OK with error message
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Invalid username or password', content)
    
    def test_login_with_missing_username(self):
        """Test login with missing username."""
        response = self.client.post(reverse('homepage:login'), {
            'username': '',
            'password': 'testpass123'
        })
        
        # Should return 200 OK with error message
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Username and password are required', content)
    
    def test_login_with_missing_password(self):
        """Test login with missing password."""
        response = self.client.post(reverse('homepage:login'), {
            'username': 'testuser',
            'password': ''
        })
        
        # Should return 200 OK with error message
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Username and password are required', content)


class LogoutViewTestCase(TestCase):
    """Test cases for LogoutView."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='testpass123'
        )
    
    def test_logout_via_get_request(self):
        """Test logout via GET request."""
        # Login first
        self.client.login(username='testuser', password='testpass123')
        
        # Verify user is authenticated
        response = self.client.get(reverse('homepage:homepage'))
        self.assertEqual(response.status_code, 200)
        
        # Logout
        response = self.client.get(reverse('homepage:logout'))
        
        # Should redirect to login page
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('homepage:login'), response.url)
        
        # Verify user is no longer authenticated
        response = self.client.get(reverse('homepage:homepage'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
    
    def test_logout_via_post_request(self):
        """Test logout via POST request."""
        # Login first
        self.client.login(username='testuser', password='testpass123')
        
        # Verify user is authenticated
        response = self.client.get(reverse('homepage:homepage'))
        self.assertEqual(response.status_code, 200)
        
        # Logout via POST
        response = self.client.post(reverse('homepage:logout'))
        
        # Should redirect to login page
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('homepage:login'), response.url)
        
        # Verify user is no longer authenticated
        response = self.client.get(reverse('homepage:homepage'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
    
    def test_logout_clears_session(self):
        """Test that logout clears the session."""
        # Login first
        self.client.login(username='testuser', password='testpass123')
        
        # Get session key
        session_key_before = self.client.session.session_key
        self.assertIsNotNone(session_key_before)
        
        # Logout
        self.client.get(reverse('homepage:logout'))
        
        # Session should be cleared
        # After logout, accessing a protected page should redirect to login
        response = self.client.get(reverse('homepage:homepage'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
    
    def test_logout_unauthenticated_user(self):
        """Test logout for unauthenticated user."""
        # Try to logout without being logged in
        response = self.client.get(reverse('homepage:logout'))
        
        # Should redirect to login page
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('homepage:login'), response.url)
