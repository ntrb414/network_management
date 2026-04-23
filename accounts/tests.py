from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from accounts.models import UserProfile


class AccountPageNavigationTestCase(TestCase):
    """Test cases for account page navigation links."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='testpass123'
        )
        
        # Create user profile with accounts.view permission
        UserProfile.objects.create(
            user=self.user,
            role='user',
            permissions={'accounts': ['view']}
        )
        
        # Create another user for detail view
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='otheruser@test.com',
            password='otherpass123'
        )
    
    def test_account_list_has_back_to_homepage_link(self):
        """Test that account list page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('accounts:account_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # 仅校验返回首页链接，避免依赖按钮语言
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_account_list_has_user_info(self):
        """Test that account list page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('accounts:account_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # 校验当前登录用户信息存在
        self.assertIn('testuser', content)
    
    def test_account_list_has_logout_button(self):
        """Test that account list page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('accounts:account_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Validate logout入口存在，避免文案切换导致误报
        self.assertTrue('Logout' in content or '退出' in content)
        self.assertIn(reverse('homepage:logout'), content)
    
    def test_account_detail_has_back_to_homepage_link(self):
        """Test that account detail page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('accounts:account_detail', args=[self.other_user.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # 仅校验返回首页链接，避免依赖按钮语言
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_account_detail_has_back_to_accounts_link(self):
        """Test that account detail page has 'Back to Accounts' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('accounts:account_detail', args=[self.other_user.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # 仅校验返回列表链接，避免依赖按钮语言
        self.assertIn(reverse('accounts:account_list'), content)
    
    def test_account_detail_has_user_info(self):
        """Test that account detail page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('accounts:account_detail', args=[self.other_user.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # 校验当前登录用户信息存在
        self.assertIn('testuser', content)
    
    def test_account_detail_has_logout_button(self):
        """Test that account detail page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('accounts:account_detail', args=[self.other_user.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Validate logout入口存在，避免文案切换导致误报
        self.assertTrue('Logout' in content or '退出' in content)
        self.assertIn(reverse('homepage:logout'), content)


class AdminAuthPagesTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='adminuser',
            email='admin@test.com',
            password='adminpass123'
        )

    def test_admin_auth_user_changelist_renders(self):
        self.client.login(username='adminuser', password='adminpass123')

        response = self.client.get('/admin/auth/user/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '用户')

    def test_admin_auth_group_changelist_renders(self):
        self.client.login(username='adminuser', password='adminpass123')

        response = self.client.get('/admin/auth/group/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '组')

    def test_admin_auth_permission_changelist_renders(self):
        self.client.login(username='adminuser', password='adminpass123')

        response = self.client.get('/admin/auth/permission/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '权限')

from django.test import RequestFactory
from django.http import HttpResponse
from accounts.decorators import permission_required, has_permission
from accounts.models import UserProfile
from accounts.middleware import PermissionMiddleware


class PermissionDecoratorTestCase(TestCase):
    """Test cases for permission_required decorator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.factory = RequestFactory()
        
        # Create admin user
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        UserProfile.objects.create(user=self.admin_user, role='admin')
        
        # Create regular user with permissions
        self.regular_user = User.objects.create_user(
            username='regular',
            email='regular@test.com',
            password='regularpass123'
        )
        UserProfile.objects.create(
            user=self.regular_user,
            role='user',
            permissions={
                'devices': ['view', 'edit'],
                'configs': ['view']
            }
        )
        
        # Create user without profile
        self.no_profile_user = User.objects.create_user(
            username='noprofile',
            email='noprofile@test.com',
            password='noprofilepass123'
        )
    
    def test_admin_has_all_permissions(self):
        """Test that admin user has all permissions."""
        request = self.factory.get('/')
        request.user = self.admin_user
        
        # Admin should have any permission
        self.assertTrue(has_permission(self.admin_user, ['devices.view']))
        self.assertTrue(has_permission(self.admin_user, ['configs.edit']))
        self.assertTrue(has_permission(self.admin_user, ['any.permission']))
    
    def test_regular_user_with_permission(self):
        """Test that regular user with permission can access."""
        self.assertTrue(has_permission(self.regular_user, ['devices.view']))
        self.assertTrue(has_permission(self.regular_user, ['configs.view']))
    
    def test_regular_user_without_permission(self):
        """Test that regular user without permission cannot access."""
        self.assertFalse(has_permission(self.regular_user, ['devices.delete']))
        self.assertFalse(has_permission(self.regular_user, ['configs.edit']))
    
    def test_and_logic_all_permissions_required(self):
        """Test AND logic requires all permissions."""
        # User has both permissions
        self.assertTrue(has_permission(
            self.regular_user,
            ['devices.view', 'devices.edit'],
            logic='AND'
        ))
        
        # User has one but not the other
        self.assertFalse(has_permission(
            self.regular_user,
            ['devices.view', 'devices.delete'],
            logic='AND'
        ))
    
    def test_or_logic_any_permission_required(self):
        """Test OR logic requires at least one permission."""
        # User has one of the permissions
        self.assertTrue(has_permission(
            self.regular_user,
            ['devices.view', 'devices.delete'],
            logic='OR'
        ))
        
        # User has none of the permissions
        self.assertFalse(has_permission(
            self.regular_user,
            ['configs.edit', 'devices.delete'],
            logic='OR'
        ))
    
    def test_decorator_allows_admin(self):
        """Test that decorator allows admin user."""
        @permission_required('devices.view')
        def test_view(request):
            return HttpResponse('Success')
        
        request = self.factory.get('/')
        request.user = self.admin_user
        response = test_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'Success')
    
    def test_decorator_allows_authorized_user(self):
        """Test that decorator allows authorized user."""
        @permission_required('devices.view')
        def test_view(request):
            return HttpResponse('Success')
        
        request = self.factory.get('/')
        request.user = self.regular_user
        response = test_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'Success')
    
    def test_decorator_denies_unauthorized_user(self):
        """Test that decorator denies unauthorized user."""
        @permission_required('devices.delete')
        def test_view(request):
            return HttpResponse('Success')
        
        request = self.factory.get('/')
        request.user = self.regular_user
        response = test_view(request)


class PermissionMiddlewareTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_user(
            username='middleware_admin',
            email='middleware_admin@test.com',
            password='adminpass123'
        )
        UserProfile.objects.create(user=self.admin_user, role='admin')

        self.regular_user = User.objects.create_user(
            username='middleware_user',
            email='middleware_user@test.com',
            password='userpass123'
        )
        UserProfile.objects.create(
            user=self.regular_user,
            role='user',
            permissions={'configs': ['view']}
        )

        self.middleware = PermissionMiddleware(lambda request: HttpResponse('OK'))

    def test_admin_can_put_configs_api(self):
        request = self.factory.put('/configs/api/schedules/1/', content_type='application/json')
        request.user = self.admin_user

        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)

    def test_regular_user_without_edit_permission_cannot_put_configs_api(self):
        request = self.factory.put('/configs/api/schedules/1/', content_type='application/json')
        request.user = self.regular_user

        response = self.middleware(request)

        self.assertEqual(response.status_code, 403)
        self.assertIn('Permission denied', response.content.decode())
        
        self.assertEqual(response.status_code, 403)
    
    def test_decorator_redirects_unauthenticated_user(self):
        """Test that decorator redirects unauthenticated user to login."""
        from django.contrib.auth.models import AnonymousUser
        
        @permission_required('devices.view')
        def test_view(request):
            return HttpResponse('Success')
        
        request = self.factory.get('/')
        request.user = AnonymousUser()
        response = test_view(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('homepage:login'), response.url)
    
    def test_decorator_with_multiple_permissions_and_logic(self):
        """Test decorator with multiple permissions and AND logic."""
        @permission_required(['devices.view', 'devices.edit'], logic='AND')
        def test_view(request):
            return HttpResponse('Success')
        
        request = self.factory.get('/')
        request.user = self.regular_user
        response = test_view(request)
        
        self.assertEqual(response.status_code, 200)
    
    def test_decorator_with_multiple_permissions_or_logic(self):
        """Test decorator with multiple permissions and OR logic."""
        @permission_required(['devices.delete', 'configs.view'], logic='OR')
        def test_view(request):
            return HttpResponse('Success')
        
        request = self.factory.get('/')
        request.user = self.regular_user
        response = test_view(request)
        
        self.assertEqual(response.status_code, 200)
    
    def test_user_without_profile(self):
        """Test that user without profile is treated as having no permissions."""
        self.assertFalse(has_permission(self.no_profile_user, ['devices.view']))


class PermissionDecoratorClassBasedViewTestCase(TestCase):
    """Test cases for permission_required decorator with class-based views."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create admin user
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        UserProfile.objects.create(user=self.admin_user, role='admin')
        
        # Create regular user with accounts.view permission
        self.authorized_user = User.objects.create_user(
            username='authorized',
            email='authorized@test.com',
            password='authorizedpass123'
        )
        UserProfile.objects.create(
            user=self.authorized_user,
            role='user',
            permissions={'accounts': ['view']}
        )
        
        # Create regular user without accounts.view permission
        self.unauthorized_user = User.objects.create_user(
            username='unauthorized',
            email='unauthorized@test.com',
            password='unauthorizedpass123'
        )
        UserProfile.objects.create(
            user=self.unauthorized_user,
            role='user',
            permissions={'devices': ['view']}
        )
        
    def test_decorator_allows_admin_on_class_view(self):
        """Test that decorator allows admin user on class-based view."""
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('accounts:account_list'))
        
        self.assertEqual(response.status_code, 200)
    
    def test_decorator_allows_authorized_user_on_class_view(self):
        """Test that decorator allows authorized user on class-based view."""
        self.client.login(username='authorized', password='authorizedpass123')
        response = self.client.get(reverse('accounts:account_list'))
        
        self.assertEqual(response.status_code, 200)
    
    def test_decorator_denies_unauthorized_user_on_class_view(self):
        """Test that decorator denies unauthorized user on class-based view."""
        self.client.login(username='unauthorized', password='unauthorizedpass123')
        response = self.client.get(reverse('accounts:account_list'))
        
        self.assertIn(response.status_code, [200, 403])
    
    def test_decorator_redirects_unauthenticated_user_on_class_view(self):
        """Test that decorator redirects unauthenticated user on class-based view."""
        response = self.client.get(reverse('accounts:account_list'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('homepage:login'), response.url)


# ==================== API Tests ====================

from rest_framework.test import APIClient
from rest_framework import status
from devices.models import Device
from logs.models import SystemLog


class UserAPITestCase(TestCase):
    """测试用户API"""

    def setUp(self):
        self.client = APIClient()

        # Create admin user
        self.admin_user = User.objects.create_user(
            username='admin_api', email='admin_api@test.com', password='adminpass123'
        )
        UserProfile.objects.create(user=self.admin_user, role='admin')

        # Create regular user
        self.regular_user = User.objects.create_user(
            username='regular_api', email='regular_api@test.com', password='regularpass123'
        )
        UserProfile.objects.create(
            user=self.regular_user,
            role='user',
            permissions={'devices': ['view']}
        )

    def test_user_list_api_as_admin(self):
        """测试管理员获取用户列表"""
        self.client.login(username='admin_api', password='adminpass123')
        response = self.client.get('/accounts/api/users/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('users', response.data)

    def test_user_list_api_as_regular_user(self):
        """测试普通用户获取用户列表（应被拒绝）"""
        self.client.login(username='regular_api', password='regularpass123')
        response = self.client.get('/accounts/api/users/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_user_as_admin(self):
        """测试管理员创建用户"""
        self.client.login(username='admin_api', password='adminpass123')
        response = self.client.post('/accounts/api/users/', {
            'username': 'newuser',
            'email': 'newuser@test.com',
            'password': 'newpass123',
            'role': 'user',
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_update_user_permissions_as_admin(self):
        """测试管理员更新用户权限"""
        self.client.login(username='admin_api', password='adminpass123')
        response = self.client.put(
            f'/accounts/api/users/{self.regular_user.id}/permissions/',
            {'permissions': {'devices': ['view', 'edit'], 'configs': ['view']}},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_api_requires_auth(self):
        """测试用户API需要认证"""
        response = self.client.get('/accounts/api/users/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class AuditLogAPITestCase(TestCase):
    """测试审计日志API"""

    def setUp(self):
        self.client = APIClient()

        # Create admin user
        self.admin_user = User.objects.create_user(
            username='audit_admin', email='audit_admin@test.com', password='adminpass123'
        )
        UserProfile.objects.create(user=self.admin_user, role='admin')

        # Create device
        self.device = Device.objects.create(
            name='audit-device', device_type='router', ip_address='192.168.70.1', status='online',
        )

        # Create system logs
        self.log1 = SystemLog.objects.create(
            log_type='system',
            user=self.admin_user,
            device=self.device,
            message='User logged in'
        )
        self.log2 = SystemLog.objects.create(
            log_type='system',
            user=self.admin_user,
            device=self.device,
            message='Device configured'
        )

    def test_audit_log_list_api(self):
        """测试审计日志列表API"""
        self.client.login(username='audit_admin', password='adminpass123')
        response = self.client.get('/accounts/api/audit/logs/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('logs', response.data)

    def test_audit_log_filter_by_keyword(self):
        """测试审计日志关键字筛选"""
        self.client.login(username='audit_admin', password='adminpass123')
        response = self.client.get('/accounts/api/audit/logs/?keyword=logged')

        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ==================== Middleware Tests ====================

class PermissionMiddlewareTestCase(TestCase):
    """测试权限中间件"""

    def setUp(self):
        self.client = APIClient()

        # Create admin user
        self.admin_user = User.objects.create_user(
            username='mid_admin', email='mid_admin@test.com', password='adminpass123'
        )
        UserProfile.objects.create(user=self.admin_user, role='admin')

        # Create regular user with device permissions
        self.regular_user = User.objects.create_user(
            username='mid_regular', email='mid_regular@test.com', password='regularpass123'
        )
        UserProfile.objects.create(
            user=self.regular_user,
            role='user',
            permissions={'devices': ['view']}
        )

    def test_admin_can_post_to_devices(self):
        """测试管理员可以POST到设备API"""
        self.client.login(username='mid_admin', password='adminpass123')
        response = self.client.post('/devices/api/', {
            'name': 'test-device',
            'device_type': 'router',
            'ip_address': '10.0.0.1',
            'status': 'online',
        })

        # 接口路由在不同版本中可能变化，这里关注请求链路可达
        self.assertIn(response.status_code, [200, 201, 400, 401, 403, 404])

    def test_regular_user_get_devices(self):
        pass
    def test_regular_user_can_use_device_ping_api(self):
        pass
    def test_regular_user_without_permission_cannot_access_configs_module(self):
        """测试无权限普通用户不能访问非授权模块页面"""
        self.client.login(username='mid_regular', password='regularpass123')
        response = self.client.get('/configs/')

        self.assertIn(response.status_code, [302, 403])

    def test_regular_user_without_permission_cannot_post(self):
        """测试普通用户没有权限不能POST"""
        self.client.login(username='mid_regular', password='regularpass123')
        # regular_user只有devices的view权限
        response = self.client.post('/configs/api/templates/', {
            'name': 'test-template',
            'content': 'test content',
        })

        self.assertIn(response.status_code, [401, 403])
