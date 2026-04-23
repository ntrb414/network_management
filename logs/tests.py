from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from accounts.models import UserProfile
from devices.models import Device
from logs.models import SystemLog
from logs.services import LogService
from alerts.models import Alert


class LogPageNavigationTestCase(TestCase):
    """Test cases for log page navigation links."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()

        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='testpass123'
        )

        # Create user profile with logs.view permission
        UserProfile.objects.create(
            user=self.user,
            role='user',
            permissions={'logs': ['view']}
        )

    def test_log_list_has_back_to_homepage_link(self):
        """Test that log list page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('logs:log_list'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check for back to homepage link
        self.assertIn(reverse('homepage:homepage'), content)

    def test_log_list_has_user_info(self):
        """Test that log list page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('logs:log_list'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check for user info
        self.assertIn('testuser', content)

    def test_log_list_has_logout_button(self):
        """Test that log list page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('logs:log_list'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check for logout button
        self.assertIn('退出', content)
        self.assertIn(reverse('homepage:logout'), content)

    def test_log_list_does_not_show_total_stat_card(self):
        """Test that log list page no longer displays total stat card."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('logs:log_list'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertNotIn('总计', content)


# ==================== Service Tests ====================

class LogServiceTestCase(TestCase):
    """测试日志服务"""

    def setUp(self):
        self.service = LogService()
        self.user = User.objects.create_user(
            username='loguser', email='log@test.com', password='testpass123'
        )
        self.device = Device.objects.create(
            name='log-test-device', device_type='router', ip_address='192.168.50.1', status='online',
        )

    def test_collect_device_log(self):
        """测试收集设备日志"""
        log = self.service.collect_device_log(
            device=self.device,
            log_type='alert',
            message='Test alert log',
            details={'test': 'data'}
        )

        self.assertIsNotNone(log.id)
        self.assertEqual(log.log_type, 'alert')
        self.assertEqual(log.message, 'Test alert log')

    def test_create_alert_log(self):
        """测试创建告警日志"""
        log = self.service.create_alert_log(
            device=self.device,
            message='Device is down',
        )

        self.assertIsNotNone(log.id)
        self.assertEqual(log.log_type, 'alert')

    def test_create_system_log(self):
        """测试创建系统日志"""
        log = self.service.create_system_log(
            message='System started',
        )

        self.assertIsNotNone(log.id)
        self.assertEqual(log.log_type, 'system')

    def test_query_logs(self):
        """测试查询日志"""
        # 创建一些日志
        self.service.create_alert_log(self.device, 'Alert 1')
        self.service.create_system_log('System 1')

        result = self.service.query_logs()

        self.assertIn('logs', result)
        self.assertIn('total', result)
        self.assertEqual(result['total'], 2)

    def test_query_logs_by_type(self):
        """测试按类型筛选日志"""
        self.service.create_alert_log(self.device, 'Alert 1')
        self.service.create_system_log('System 1')

        result = self.service.query_logs(log_type='alert')

        self.assertEqual(result['total'], 1)

    def test_query_logs_by_keyword(self):
        """测试关键字搜索"""
        self.service.create_alert_log(self.device, 'Error occurred')
        self.service.create_system_log('System normal')

        result = self.service.query_logs(keyword='Error')

        self.assertEqual(result['total'], 1)
        self.assertIn('Error', result['logs'][0]['message'])

    def test_get_statistics(self):
        """测试日志统计"""
        # 创建一些日志
        self.service.create_alert_log(self.device, 'Alert 1')
        self.service.create_system_log('System 1')

        stats = self.service.get_statistics(days=7)

        self.assertIn('total', stats)
        self.assertIn('by_type', stats)
        self.assertIn('by_date', stats)

    def test_cleanup_old_logs(self):
        """测试清理老旧日志"""
        # 创建日志
        self.service.create_alert_log(self.device, 'Old alert')

        result = self.service.cleanup_old_logs(days=0)

        self.assertIn('deleted_count', result)

    def test_process_syslog_message(self):
        """测试Syslog报文处理与落库"""
        self.device.syslog_enabled = True
        self.device.save(update_fields=['syslog_enabled'])

        payload = '<190>Apr 21 10:20:30 edge-sw01 IFNET: Interface GigabitEthernet1/0/1 down'
        result = self.service.process_syslog_message(
            source_ip=self.device.ip_address,
            raw_message=payload,
        )

        self.assertTrue(result['success'])
        log = SystemLog.objects.get(id=result['log_id'])
        self.assertEqual(log.log_type, 'system')
        self.assertEqual(log.device_id, self.device.id)
        self.assertEqual((log.details or {}).get('source'), 'syslog')
        self.assertEqual((log.details or {}).get('source_ip'), self.device.ip_address)
        self.assertGreaterEqual(Alert.objects.filter(device=self.device).count(), 1)


# ==================== API Tests ====================

from rest_framework.test import APIClient
from rest_framework import status


class LogAPITestCase(TestCase):
    """测试日志API"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='log_api_user', email='logapi@test.com', password='testpass123'
        )
        UserProfile.objects.create(user=self.user, role='admin')
        self.device = Device.objects.create(
            name='log-api-device', device_type='router', ip_address='10.0.50.1', status='online',
        )
        self.service = LogService()
        self.service.create_alert_log(self.device, 'Test alert')

    def test_log_list_api(self):
        """测试日志列表API"""
        self.client.login(username='log_api_user', password='testpass123')
        response = self.client.get('/logs/api/list/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('logs', response.data)

    def test_log_detail_api(self):
        """测试日志详情API"""
        log = SystemLog.objects.first()
        self.client.login(username='log_api_user', password='testpass123')
        response = self.client.get(reverse('logs:log_detail_api', args=[log.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Test alert')

    def test_log_statistics_api(self):
        """测试日志统计API"""
        self.client.login(username='log_api_user', password='testpass123')
        response = self.client.get('/logs/api/statistics/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total', response.data)

    def test_log_filter_by_type(self):
        """测试按类型筛选"""
        self.client.login(username='log_api_user', password='testpass123')
        response = self.client.get('/logs/api/list/?log_type=alert')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_log_api_requires_auth(self):
        """测试日志API需要认证"""
        response = self.client.get('/logs/api/list/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_runtime_log_list_api(self):
        """测试设备运行日志API"""
        self.device.syslog_enabled = True
        self.device.save(update_fields=['syslog_enabled'])
        self.service.process_syslog_message(
            source_ip=self.device.ip_address,
            raw_message='<190>Apr 21 10:20:30 edge-sw01 IFNET: Interface GigabitEthernet1/0/1 down',
        )

        self.client.login(username='log_api_user', password='testpass123')
        response = self.client.get('/logs/api/runtime/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('logs', response.data)
        self.assertGreaterEqual(response.data.get('total', 0), 1)

    def test_device_syslog_config_api(self):
        """测试设备Syslog配置API"""
        self.client.login(username='log_api_user', password='testpass123')

        response = self.client.put(
            f'/logs/api/devices/{self.device.id}/syslog-config/',
            {
                'enabled': True,
                'server_ip': '192.168.50.132',
                'server_port': 10514,
                'protocol': 'udp',
                'severity_threshold': 'warning',
                'push_to_device': False,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.device.refresh_from_db()
        self.assertTrue(self.device.syslog_enabled)
        self.assertEqual(self.device.syslog_server_ip, '192.168.50.132')
        self.assertEqual(self.device.syslog_server_port, 10514)
        self.assertEqual(self.device.syslog_protocol, 'udp')
        self.assertEqual(self.device.syslog_severity_threshold, 'warning')
