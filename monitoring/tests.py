from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import UserProfile
from devices.models import Device
from monitoring.models import MetricData
from monitoring.services import MonitoringService


class MonitoringPageNavigationTestCase(TestCase):
    """Test cases for monitoring page navigation links."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='testpass123'
        )
        
        # Create user profile with monitoring.view permission
        UserProfile.objects.create(
            user=self.user,
            role='user',
            permissions={'monitoring': ['view']}
        )
    
    def test_monitoring_list_has_back_to_homepage_link(self):
        """Test that monitoring list page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for back to homepage link
        self.assertIn('Back to Homepage', content)
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_monitoring_list_has_user_info(self):
        """Test that monitoring list page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for user info
        self.assertIn('User:', content)
        self.assertIn('testuser', content)
    
    def test_monitoring_list_has_logout_button(self):
        """Test that monitoring list page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for logout button
        self.assertIn('Logout', content)
        self.assertIn(reverse('homepage:logout'), content)
    
    def test_monitoring_dashboard_has_back_to_homepage_link(self):
        """Test that monitoring dashboard page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for back to homepage link
        self.assertIn('Back to Homepage', content)
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_monitoring_dashboard_has_user_info(self):
        """Test that monitoring dashboard page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for user info
        self.assertIn('User:', content)
        self.assertIn('testuser', content)
    
    def test_monitoring_dashboard_has_logout_button(self):
        """Test that monitoring dashboard page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_dashboard'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check for logout button
        self.assertIn('Logout', content)
        self.assertIn(reverse('homepage:logout'), content)


# ==================== 功能测试 ====================

class MonitoringServiceTestCase(TestCase):
    """测试监控服务"""

    def setUp(self):
        self.service = MonitoringService()
        self.device = Device.objects.create(
            name='monitoring-device-svc',
            device_type='router',
            ip_address='192.168.40.1',
            status='online',
        )

    def test_collect_metrics_returns_dict(self):
        result = self.service.collect_metrics(self.device)
        self.assertIsInstance(result, dict)

    def test_store_metrics_creates_records(self):
        metrics = {'cpu': 50.0, 'memory': 60.0, 'traffic': [], 'packet_loss': 0.5}
        count = self.service.store_metrics(self.device, metrics)
        self.assertGreater(count, 0)


class MetricDataModelTestCase(TestCase):
    """测试监控数据模型"""

    def setUp(self):
        self.device = Device.objects.create(
            name='metric-test-device', device_type='router', ip_address='192.168.50.1', status='online',
        )

    def test_create_metric_data(self):
        metric = MetricData.objects.create(
            device=self.device, metric_type='cpu', metric_name='cpu_usage', value=75.5, unit='%',
        )
        self.assertIsNotNone(metric.id)
        self.assertEqual(metric.value, 75.5)


class MonitoringAPITestCase(TestCase):
    """测试监控API"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='monitorapi', email='monitorapi@test.com', password='testpass123')
        UserProfile.objects.create(user=self.user, role='admin')
        self.device = Device.objects.create(
            name='monitoring-api-device', device_type='router', ip_address='192.168.60.1', status='online',
        )
        MetricData.objects.create(
            device=self.device, metric_type='cpu', metric_name='cpu_usage', value=50.0, unit='%',
        )

    def test_realtime_api_requires_auth(self):
        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/realtime/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_realtime_api(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/realtime/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('device', response.data)

    def test_metrics_api(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/metrics/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_interface_status_metrics_api_only_returns_up_ports(self):
        self.client.force_authenticate(user=self.user)
        MetricData.objects.create(
            device=self.device, metric_type='interface_status', metric_name='GigabitEthernet1/0/1_status', value=1, unit=''
        )
        MetricData.objects.create(
            device=self.device, metric_type='interface_status', metric_name='GigabitEthernet1/0/2_status', value=2, unit=''
        )

        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/metrics/?metric_type=interface_status')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['metrics']), 1)
        self.assertEqual(response.data['metrics'][0]['display_metric_name'], 'GigabitEthernet1/0/1')

    def test_realtime_api_only_returns_up_interfaces(self):
        self.client.force_authenticate(user=self.user)
        MetricData.objects.create(
            device=self.device, metric_type='interface_status', metric_name='Vlan-interface1_status', value=1, unit=''
        )
        MetricData.objects.create(
            device=self.device, metric_type='interface_status', metric_name='Vlan-interface2_status', value=2, unit=''
        )

        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/realtime/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['metrics']['interfaces']), 1)
        self.assertEqual(response.data['metrics']['interfaces'][0]['name'], 'Vlan-interface1')

    def test_metrics_api_formats_ospf_display_name(self):
        self.client.force_authenticate(user=self.user)
        MetricData.objects.create(
            device=self.device, metric_type='ospf_neighbor', metric_name='ospf_nbr_10.20.2.2', value=8, unit=''
        )

        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/metrics/?metric_type=ospf_neighbor')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['metrics'][0]['display_metric_name'], 'OSPF邻居 10.20.2.2')


class MonitoringDeviceDetailViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='detailuser',
            email='detailuser@test.com',
            password='testpass123'
        )
        UserProfile.objects.create(
            user=self.user,
            role='user',
            permissions={'monitoring': ['view']}
        )
        self.device = Device.objects.create(
            name='detail-device', device_type='router', ip_address='192.168.70.1', status='online',
        )

    def test_device_detail_shows_specific_ospf_neighbors_in_latest_metrics(self):
        self.client.login(username='detailuser', password='testpass123')
        MetricData.objects.create(
            device=self.device, metric_type='ospf_neighbor', metric_name='ospf_nbr_10.20.2.2', value=8, unit=''
        )
        MetricData.objects.create(
            device=self.device, metric_type='ospf_neighbor', metric_name='ospf_nbr_10.20.2.3', value=4, unit=''
        )

        response = self.client.get(reverse('monitoring:device_detail', args=[self.device.id]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
    self.assertIn('10.20.2.2', content)
    self.assertIn('10.20.2.3', content)
    self.assertNotIn('10.20.2.2 (Full)', content)
