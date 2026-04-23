from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch
from types import ModuleType
import sys
from accounts.models import UserProfile
from devices.models import Device
from monitoring.models import MetricData
from monitoring.services import MonitoringService


class InMemoryRedis:
    """用于测试的最小 Redis List 行为模拟。"""

    def __init__(self):
        self._data = {}

    def lpush(self, key, value):
        if isinstance(value, str):
            value = value.encode('utf-8')
        self._data.setdefault(key, [])
        self._data[key].insert(0, value)

    def ltrim(self, key, start, end):
        values = self._data.get(key, [])
        if end == -1:
            end = len(values) - 1
        self._data[key] = values[start:end + 1]

    def expire(self, key, ttl):
        return True

    def lindex(self, key, index):
        values = self._data.get(key, [])
        if index < 0:
            index = len(values) + index
        if 0 <= index < len(values):
            return values[index]
        return None

    def lrange(self, key, start, end):
        values = self._data.get(key, [])
        if not values:
            return []
        if end == -1:
            end = len(values) - 1
        return values[start:end + 1]


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
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_monitoring_list_has_user_info(self):
        """Test that monitoring list page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for user info
        self.assertIn('testuser', content)
    
    def test_monitoring_list_has_logout_button(self):
        """Test that monitoring list page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for logout button
        self.assertIn('退出', content)
        self.assertIn(reverse('homepage:logout'), content)
    
    def test_monitoring_dashboard_has_back_to_homepage_link(self):
        """Test that monitoring dashboard page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for back to homepage link
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_monitoring_dashboard_has_user_info(self):
        """Test that monitoring dashboard page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for user info
        self.assertIn('testuser', content)
    
    def test_monitoring_dashboard_has_logout_button(self):
        """Test that monitoring dashboard page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_dashboard'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check for logout button
        self.assertIn('退出', content)
        self.assertIn(reverse('homepage:logout'), content)

    def test_monitoring_dashboard_hides_monitored_devices_count(self):
        """Test that monitoring dashboard no longer shows monitored devices count card."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:monitoring_dashboard'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertNotIn('监控设备数', content)
        self.assertIn('监控项目', content)
        self.assertNotIn('当前监控指标', content)

    def test_metric_types_page_accessible(self):
        """Test that metric types page is accessible from monitoring module."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('monitoring:metric_types'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertIn('目前监控到的指标类别', content)
        self.assertIn('返回监控仪表盘', content)


# ==================== 功能测试 ====================

class MonitoringServiceTestCase(TestCase):
    """测试监控服务"""

    def setUp(self):
        self.redis_mock = InMemoryRedis()
        self.redis_patcher = patch(
            'monitoring.services.MonitoringService._get_redis_connection_safe',
            return_value=self.redis_mock,
        )
        self.redis_patcher.start()
        self.addCleanup(self.redis_patcher.stop)

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

    def test_store_metrics_merges_partial_snapshots(self):
        self.service.store_metrics(
            self.device,
            {
                'traffic': [],
                'packet_loss': None,
                'connections': None,
                'interfaces': [{'name': 'GigabitEthernet1/0', 'status': 1}],
                'ospf_neighbors': [],
                '_partial_update': True,
            },
        )

        self.service.store_metrics(
            self.device,
            {
                'traffic': [{'interface': 'GigabitEthernet1/0', 'in_octets': 100, 'out_octets': 80}],
                'packet_loss': None,
                'connections': None,
                'interfaces': [{'name': 'GigabitEthernet1/0', 'in_octets': 100, 'out_octets': 80}],
                'ospf_neighbors': [],
                '_partial_update': True,
            },
        )

        latest = self.service.get_latest_metrics_from_redis(self.device.id)
        self.assertIsNotNone(latest)

        interfaces = latest['metrics']['interfaces']
        self.assertEqual(len(interfaces), 1)
        self.assertEqual(interfaces[0]['name'], 'GigabitEthernet1/0')
        self.assertEqual(interfaces[0]['status'], 1)
        self.assertEqual(interfaces[0]['in_octets'], 100)


class H3CDialoutParserTestCase(TestCase):
    @staticmethod
    def _extract_metrics(sensor_path, payload):
        if 'grpc' not in sys.modules:
            grpc_stub = ModuleType('grpc')
            grpc_stub.GenericRpcHandler = object
            grpc_stub.stream_stream_rpc_method_handler = lambda *args, **kwargs: None
            grpc_stub.server = lambda *args, **kwargs: None
            sys.modules['grpc'] = grpc_stub

        from monitoring.management.commands.run_gnmi_receiver import _extract_h3c_metrics

        return _extract_h3c_metrics(sensor_path, payload)

    def test_extract_ifmgr_statistics_metrics(self):
        payload = {
            'Notification': {
                'Ifmgr': {
                    'Statistics': {
                        'Interface': [
                            {
                                'Name': 'GigabitEthernet1/0',
                                'IfIndex': 17,
                                'InOctets': 17950301,
                                'OutOctets': 5201673,
                                'InRate': 2883,
                                'OutRate': 570,
                                'InDiscards': 0,
                                'OutDiscards': 0,
                            }
                        ]
                    }
                }
            }
        }

        metrics = self._extract_metrics('Ifmgr/Statistics', payload)

        self.assertEqual(len(metrics['interfaces']), 1)
        self.assertEqual(metrics['interfaces'][0]['name'], 'GigabitEthernet1/0')
        self.assertEqual(metrics['traffic'][0]['in_octets'], 17950301)
        self.assertEqual(metrics['traffic'][0]['out_octets'], 5201673)

    def test_extract_ospf_cpu_memory_metrics(self):
        payload = {
            'Notification': {
                'OSPF': {
                    'Neighbours': {
                        'Nbr': [
                            {
                                'IfIndex': 33,
                                'NbrAddress': '10.20.2.2',
                                'NbrRouterId': '2.2.2.2',
                                'State': 7,
                            }
                        ]
                    }
                },
                'Device': {
                    'CPUs': {
                        'CPU': [
                            {'CPUUsage': 3}
                        ]
                    }
                },
                'Diagnostic': {
                    'Memories': {
                        'Memory': [
                            {'Total': 2000, 'Used': 800}
                        ]
                    }
                },
            }
        }

        metrics = self._extract_metrics('OSPF/Neighbours', payload)

        self.assertEqual(len(metrics['ospf_neighbors']), 1)
        self.assertEqual(metrics['ospf_neighbors'][0]['neighbor_ip'], '10.20.2.2')
        self.assertEqual(metrics['ospf_neighbors'][0]['raw_state'], 7)
        self.assertEqual(metrics['ospf_neighbors'][0]['state'], 8)
        self.assertEqual(metrics['ospf_neighbors'][0]['state_name'], 'Full')
        self.assertTrue(metrics['ospf_neighbors'][0]['is_full'])
        self.assertEqual(metrics['cpu_usage'], 3.0)
        self.assertEqual(metrics['memory_usage'], 40.0)


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
        self.redis_mock = InMemoryRedis()
        self.redis_patcher = patch(
            'monitoring.services.MonitoringService._get_redis_connection_safe',
            return_value=self.redis_mock,
        )
        self.redis_patcher.start()
        self.addCleanup(self.redis_patcher.stop)

        self.client = APIClient()
        self.user = User.objects.create_user(username='monitorapi', email='monitorapi@test.com', password='testpass123')
        UserProfile.objects.create(user=self.user, role='admin')
        self.device = Device.objects.create(
            name='monitoring-api-device', device_type='router', ip_address='192.168.60.1', status='online',
        )

        self.service = MonitoringService()
        self.service.store_metrics(
            self.device,
            {
                'traffic': [{'interface': 'GigabitEthernet1/0/1', 'in_octets': 120, 'out_octets': 80}],
                'packet_loss': None,
                'connections': None,
                'interfaces': [{'name': 'GigabitEthernet1/0/1', 'status': 1, 'in_drop_rate': 2, 'out_drop_rate': 1}],
                'ospf_neighbors': [{'neighbor_ip': '10.20.2.2', 'state': 8, 'state_name': 'full', 'is_full': True}],
            }
        )

        MetricData.objects.create(
            device=self.device, metric_type='cpu', metric_name='cpu_usage', value=50.0, unit='%',
        )

    def test_realtime_api_requires_auth(self):
        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/realtime/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_realtime_api(self):
        self.client.login(username='monitorapi', password='testpass123')
        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/realtime/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('device', response.data)

    def test_metrics_api(self):
        self.client.login(username='monitorapi', password='testpass123')
        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/metrics/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data['count'], 1)

    def test_interface_status_metrics_api_only_returns_up_ports(self):
        self.client.login(username='monitorapi', password='testpass123')
        self.service.store_metrics(
            self.device,
            {
                'traffic': [],
                'packet_loss': None,
                'connections': None,
                'interfaces': [
                    {'name': 'GigabitEthernet1/0/1', 'status': 1, 'in_drop_rate': 0, 'out_drop_rate': 0},
                    {'name': 'GigabitEthernet1/0/2', 'status': 2, 'in_drop_rate': 0, 'out_drop_rate': 0},
                ],
                'ospf_neighbors': [],
            }
        )

        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/metrics/?metric_type=interface_status')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        display_names = [item['display_metric_name'] for item in response.data['metrics']]
        self.assertIn('GigabitEthernet1/0/1', display_names)
        self.assertNotIn('GigabitEthernet1/0/2', display_names)

    def test_realtime_api_only_returns_up_interfaces(self):
        self.client.login(username='monitorapi', password='testpass123')
        self.service.store_metrics(
            self.device,
            {
                'traffic': [],
                'packet_loss': None,
                'connections': None,
                'interfaces': [
                    {'name': 'Vlan-interface1', 'status': 1, 'in_drop_rate': 0, 'out_drop_rate': 0},
                    {'name': 'Vlan-interface2', 'status': 2, 'in_drop_rate': 0, 'out_drop_rate': 0},
                ],
                'ospf_neighbors': [],
            }
        )

        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/realtime/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['metrics']['interfaces']), 1)
        self.assertEqual(response.data['metrics']['interfaces'][0]['name'], 'Vlan-interface1')

    def test_metrics_api_formats_ospf_display_name(self):
        self.client.login(username='monitorapi', password='testpass123')
        self.service.store_metrics(
            self.device,
            {
                'traffic': [],
                'packet_loss': None,
                'connections': None,
                'interfaces': [],
                'ospf_neighbors': [{'neighbor_ip': '10.20.2.2', 'state': 8, 'state_name': 'full', 'is_full': True}],
            }
        )

        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/metrics/?metric_type=ospf_neighbor')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['metrics'][0]['display_metric_name'], 'OSPF邻居 10.20.2.2')


class MonitoringRedisRealtimeAPITestCase(TestCase):
    """测试 Redis 实时监控 API。"""

    def setUp(self):
        self.redis_mock = InMemoryRedis()
        self.redis_patcher = patch(
            'monitoring.services.MonitoringService._get_redis_connection_safe',
            return_value=self.redis_mock,
        )
        self.redis_patcher.start()
        self.addCleanup(self.redis_patcher.stop)

        self.client = APIClient()
        self.user = User.objects.create_user(username='redisapi', email='redisapi@test.com', password='testpass123')
        UserProfile.objects.create(user=self.user, role='admin')
        self.client.login(username='redisapi', password='testpass123')

        self.device = Device.objects.create(
            name='redis-api-device',
            device_type='router',
            ip_address='192.168.61.1',
            status='online',
        )

    def test_realtime_redis_api_returns_reload_time(self):
        service = MonitoringService()
        service.store_metrics(
            self.device,
            {
                'traffic': [{'interface': 'Gi0/1', 'in_octets': 100, 'out_octets': 50}],
                'packet_loss': None,
                'connections': None,
                'interfaces': [{'name': 'Gi0/1', 'status': 1, 'in_drop_rate': 0, 'out_drop_rate': 0}],
                'ospf_neighbors': [],
            },
        )

        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/realtime-redis/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('reload_time', response.data)
        self.assertIn('metrics', response.data)

    def test_realtime_redis_api_returns_empty_metrics_when_no_data(self):
        response = self.client.get(f'/monitoring/api/devices/{self.device.id}/realtime-redis/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['metrics'], {})

    def test_realtime_redis_api_returns_404_for_missing_device(self):
        response = self.client.get('/monitoring/api/devices/999999/realtime-redis/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MonitoringDeviceDetailViewTestCase(TestCase):
    def setUp(self):
        self.redis_mock = InMemoryRedis()
        self.redis_patcher = patch(
            'monitoring.services.MonitoringService._get_redis_connection_safe',
            return_value=self.redis_mock,
        )
        self.redis_patcher.start()
        self.addCleanup(self.redis_patcher.stop)

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
        service = MonitoringService()
        service.store_metrics(
            self.device,
            {
                'traffic': [],
                'packet_loss': None,
                'connections': None,
                'interfaces': [],
                'ospf_neighbors': [
                    {'neighbor_ip': '10.20.2.2', 'state': 8, 'state_name': 'full', 'is_full': True},
                    {'neighbor_ip': '10.20.2.3', 'state': 4, 'state_name': 'twoWay', 'is_full': False},
                ],
            },
        )

        response = self.client.get(reverse('monitoring:device_detail', args=[self.device.id]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('10.20.2.2', content)
        self.assertIn('10.20.2.3', content)
        self.assertNotIn('10.20.2.2 (Full)', content)


class MonitoringMetricTypesViewTestCase(TestCase):
    def setUp(self):
        self.redis_mock = InMemoryRedis()
        self.redis_patcher = patch(
            'monitoring.services.MonitoringService._get_redis_connection_safe',
            return_value=self.redis_mock,
        )
        self.redis_patcher.start()
        self.addCleanup(self.redis_patcher.stop)

        self.client = Client()
        self.user = User.objects.create_user(
            username='metrictypes',
            email='metrictypes@test.com',
            password='testpass123'
        )
        UserProfile.objects.create(
            user=self.user,
            role='user',
            permissions={'monitoring': ['view']}
        )

        self.device = Device.objects.create(
            name='metric-types-device',
            device_type='router',
            ip_address='192.168.80.1',
            status='online',
        )

        service = MonitoringService()
        service.store_metrics(
            self.device,
            {
                'traffic': [{'interface': 'GigabitEthernet1/0/1', 'in_octets': 300, 'out_octets': 220}],
                'packet_loss': 0.1,
                'connections': 8,
                'interfaces': [{
                    'name': 'GigabitEthernet1/0/1',
                    'status': 1,
                    'in_mbps': 5.2,
                    'out_mbps': 4.8,
                    'in_drop_rate': 0,
                    'out_drop_rate': 0,
                }],
                'ospf_neighbors': [
                    {'neighbor_ip': '10.20.2.2', 'state': 8, 'state_name': 'full', 'is_full': True}
                ],
            },
        )

    def test_metric_types_view_shows_monitored_categories(self):
        self.client.login(username='metrictypes', password='testpass123')
        response = self.client.get(reverse('monitoring:metric_types'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertIn('端口流量', content)
        self.assertIn('接口状态', content)
        self.assertIn('OSPF邻居状态', content)
        self.assertIn('metric-type-card', content)
