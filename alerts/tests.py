from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from devices.models import Device
from alerts.models import Alert
from alerts.services import AlertService
from accounts.models import UserProfile


class AlertPageNavigationTestCase(TestCase):
    """Test cases for alert page navigation links."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='testpass123'
        )
        
        # Create user profile with alerts.view permission
        UserProfile.objects.create(
            user=self.user,
            role='user',
            permissions={'alerts': ['view']}
        )
        
        # Create test device
        self.device = Device.objects.create(
            name='Test Device',
            device_type='router',
            ip_address='192.168.1.1',
            status='online',
            ssh_port=22,
            ssh_username='admin',
            snmp_community='public'
        )
        
        # Create test alert
        self.alert = Alert.objects.create(
            device=self.device,
            alert_type='device_down',
            severity='critical',
            message='Device is down',
            status='active'
        )
    
    def test_alert_list_has_back_to_homepage_link(self):
        """Test that alert list page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('alerts:alert_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for back to homepage link
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_alert_list_has_user_info(self):
        """Test that alert list page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('alerts:alert_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for user info
        self.assertIn('testuser', content)
    
    def test_alert_list_has_logout_button(self):
        """Test that alert list page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('alerts:alert_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for logout button
        self.assertIn('退出', content)
        self.assertIn(reverse('homepage:logout'), content)
    
    def test_alert_detail_has_back_to_homepage_link(self):
        """Test that alert detail page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('alerts:alert_detail', args=[self.alert.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for back to homepage link
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_alert_detail_has_back_to_alerts_link(self):
        """Test that alert detail page has 'Back to Alerts' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('alerts:alert_detail', args=[self.alert.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for back to alerts link
        self.assertIn('返回列表', content)
        self.assertIn(reverse('alerts:alert_list'), content)
    
    def test_alert_detail_has_user_info(self):
        """Test that alert detail page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('alerts:alert_detail', args=[self.alert.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for user info
        self.assertIn('testuser', content)
    
    def test_alert_detail_has_logout_button(self):
        """Test that alert detail page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('alerts:alert_detail', args=[self.alert.pk]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check for logout button
        self.assertIn('退出', content)
        self.assertIn(reverse('homepage:logout'), content)


# ==================== 功能测试 ====================

class AlertServiceTestCase(TestCase):
    """测试告警服务"""

    def setUp(self):
        self.service = AlertService()
        self.user = User.objects.create_user(
            username='alertuser', email='alert@test.com', password='testpass123'
        )
        self.device = Device.objects.create(
            name='alert-test-device', device_type='router', ip_address='192.168.100.1', status='online',
        )

    def test_create_alert(self):
        """测试创建告警"""
        alert = self.service.create_alert(
            device=self.device,
            alert_type='device_offline',
            severity='critical',
            message='Test alert message',
        )

        self.assertIsNotNone(alert.id)
        self.assertEqual(alert.alert_type, 'device_offline')
        self.assertEqual(alert.severity, 'critical')
        self.assertEqual(alert.status, 'active')

    def test_create_device_offline_alert(self):
        """测试创建设备离线告警"""
        alert = self.service.create_device_offline_alert(self.device)

        self.assertIsNotNone(alert.id)
        self.assertEqual(alert.alert_type, 'device_offline')
        self.assertEqual(alert.severity, 'critical')
        self.assertIn('已离线', alert.message)

    def test_create_config_failed_alert(self):
        """测试创建配置失败告警"""
        alert = self.service.create_config_failed_alert(self.device, 'SSH connection failed')

        self.assertIsNotNone(alert.id)
        self.assertEqual(alert.alert_type, 'config_failed')
        self.assertEqual(alert.severity, 'important')
        self.assertIn('配置下发失败', alert.message)

    def test_create_metric_abnormal_alert(self):
        """测试创建指标异常告警"""
        alert = self.service.create_metric_abnormal_alert(
            self.device, 'CPU', 85.0, 80.0
        )

        self.assertIsNotNone(alert.id)
        self.assertEqual(alert.alert_type, 'metric_abnormal')
        self.assertEqual(alert.severity, 'important')
        self.assertIn('CPU', alert.message)

    def test_acknowledge_alert(self):
        """测试确认告警"""
        alert = Alert.objects.create(
            device=self.device,
            alert_type='device_offline',
            severity='critical',
            message='Test alert',
            status='active',
        )

        result = self.service.acknowledge_alert(alert, self.user)

        self.assertTrue(result)
        self.assertEqual(alert.status, 'acknowledged')
        self.assertEqual(alert.handled_by, self.user)

    def test_ignore_alert(self):
        """测试忽略告警"""
        alert = Alert.objects.create(
            device=self.device,
            alert_type='device_offline',
            severity='critical',
            message='Test alert',
            status='active',
        )

        result = self.service.ignore_alert(alert, self.user)

        self.assertTrue(result)
        self.assertEqual(alert.status, 'ignored')
        self.assertEqual(alert.handled_by, self.user)

    def test_acknowledge_all_active_alerts(self):
        Alert.objects.create(
            device=self.device,
            alert_type='device_fault',
            severity='critical',
            message='Another alert',
            status='active',
        )

        handled_count = self.service.acknowledge_all_active_alerts(self.user)

        self.assertEqual(handled_count, 1)
        self.assertEqual(Alert.objects.filter(status='acknowledged').count(), 1)

    def test_delete_alerts(self):
        alert = Alert.objects.create(
            device=self.device,
            alert_type='device_fault',
            severity='critical',
            message='Delete me',
            status='active',
        )

        deleted_count = self.service.delete_alerts([alert.id])

        self.assertEqual(deleted_count, 1)
        self.assertFalse(Alert.objects.filter(id=alert.id).exists())

    def test_delete_all_alerts(self):
        Alert.objects.create(
            device=self.device,
            alert_type='device_fault',
            severity='critical',
            message='Delete all 1',
            status='active',
        )
        Alert.objects.create(
            device=self.device,
            alert_type='config_failed',
            severity='important',
            message='Delete all 2',
            status='acknowledged',
        )

        deleted_count = self.service.delete_all_alerts()

        self.assertEqual(deleted_count, 2)
        self.assertEqual(Alert.objects.count(), 0)

    def test_get_alert_statistics(self):
        """测试告警统计"""
        # 创建一些告警
        Alert.objects.create(
            device=self.device, alert_type='device_offline', severity='critical', message='alert1', status='active',
        )
        Alert.objects.create(
            device=self.device, alert_type='config_failed', severity='important', message='alert2', status='active',
        )
        Alert.objects.create(
            device=self.device, alert_type='metric_abnormal', severity='normal', message='alert3', status='acknowledged',
        )

        stats = self.service.get_alert_statistics(days=7)

        self.assertIn('total', stats)
        self.assertIn('by_type', stats)
        self.assertIn('by_severity', stats)


class AlertAPITestCase(TestCase):
    """测试告警API"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='alertapi', email='alertapi@test.com', password='testpass123')
        UserProfile.objects.create(user=self.user, role='admin')
        self.device = Device.objects.create(
            name='alert-api-device', device_type='router', ip_address='192.168.200.1', status='online',
        )
        self.alert = Alert.objects.create(
            device=self.device,
            alert_type='device_offline',
            severity='critical',
            message='Test alert',
            status='active',
        )

    def test_alert_list_api(self):
        """测试告警列表API"""
        self.client.login(username='alertapi', password='testpass123')
        response = self.client.get('/alerts/api/list/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

    def test_alert_detail_api(self):
        """测试告警详情API"""
        self.client.login(username='alertapi', password='testpass123')
        response = self.client.get(f'/alerts/api/{self.alert.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Test alert')

    def test_alert_acknowledge_api(self):
        """测试确认告警API"""
        self.client.login(username='alertapi', password='testpass123')
        response = self.client.post(f'/alerts/api/{self.alert.id}/acknowledge/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, 'acknowledged')

    def test_alert_ignore_api(self):
        """测试忽略告警API"""
        self.client.login(username='alertapi', password='testpass123')
        response = self.client.post(f'/alerts/api/{self.alert.id}/ignore/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, 'ignored')

    def test_alert_statistics_api(self):
        """测试告警统计API"""
        self.client.login(username='alertapi', password='testpass123')
        response = self.client.get('/alerts/api/statistics/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total', response.data)

    def test_alert_acknowledge_all_api(self):
        self.client.login(username='alertapi', password='testpass123')
        Alert.objects.create(
            device=self.device,
            alert_type='device_fault',
            severity='critical',
            message='Bulk alert',
            status='active',
        )

        response = self.client.post('/alerts/api/acknowledge-all/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['handled_count'], 2)
        self.assertEqual(Alert.objects.filter(status='acknowledged').count(), 2)

    def test_alert_detail_delete_api(self):
        self.client.login(username='alertapi', password='testpass123')

        response = self.client.delete(f'/alerts/api/{self.alert.id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Alert.objects.filter(id=self.alert.id).exists())

    def test_alert_bulk_delete_api(self):
        self.client.login(username='alertapi', password='testpass123')
        another_alert = Alert.objects.create(
            device=self.device,
            alert_type='device_fault',
            severity='critical',
            message='Bulk delete alert',
            status='active',
        )

        response = self.client.post('/alerts/api/bulk-delete/', {'alert_ids': [self.alert.id, another_alert.id]}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['deleted_count'], 2)
        self.assertEqual(Alert.objects.count(), 0)

    def test_alert_delete_all_api(self):
        self.client.login(username='alertapi', password='testpass123')
        Alert.objects.create(
            device=self.device,
            alert_type='device_fault',
            severity='critical',
            message='Delete all api 1',
            status='active',
        )
        Alert.objects.create(
            device=self.device,
            alert_type='config_failed',
            severity='important',
            message='Delete all api 2',
            status='ignored',
        )

        response = self.client.post('/alerts/api/delete-all/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['deleted_count'], 3)
        self.assertEqual(Alert.objects.count(), 0)

    def test_alert_filter_by_status(self):
        """测试按状态筛选"""
        self.client.login(username='alertapi', password='testpass123')
        response = self.client.get('/alerts/api/list/?status=active')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for alert in response.data['results']:
            self.assertEqual(alert['status'], 'active')
