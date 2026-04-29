"""
设备管理功能测试

测试设备发现服务、设备管理API等功能。
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.paginator import Paginator, EmptyPage
from unittest.mock import patch
from rest_framework.test import APIClient
from rest_framework import status

from devices.models import Device
from devices.services import DeviceDiscoveryService
from accounts.models import UserProfile


class DeviceDiscoveryServiceTestCase(TestCase):
    """测试设备发现服务"""

    def setUp(self):
        """设置测试环境"""
        self.service = DeviceDiscoveryService()

    def test_scan_ip_range_returns_list(self):
        """测试IP范围扫描返回列表"""
        result = self.service.scan_ip_range('192.168.1.1', '192.168.1.10')
        self.assertIsInstance(result, list)

    def test_scan_ip_range_invalid_ip_raises_error(self):
        """测试无效IP范围应该返回空列表而不是抛出异常"""
        result = self.service.scan_ip_range('invalid_ip', '192.168.1.10')
        self.assertEqual(result, [])

    def test_discover_via_lldp_returns_list(self):
        """测试LLDP发现返回列表"""
        # 创建一个测试设备（数据库关联需要）
        device = Device.objects.create(
            name='test-lldp-device',
            device_type='switch',
            ip_address='192.168.1.100',
            status='online',
            ssh_port=22,
            ssh_username='admin',
        )
        result = self.service.discover_via_lldp(device)
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])  # LLDP需要实际网络设备

    def test_add_device_manually(self):
        """测试手动添加设备"""
        device_info = {
            'name': 'manual-router-1',
            'device_type': 'router',
            'ip_address': '10.0.0.1',
            'status': 'preparing',
            'location': 'Data Center A',
            'ssh_username': 'admin',
            'ssh_password': 'password',
        }

        device = self.service.add_device_manually(device_info)

        self.assertIsNotNone(device.id)
        self.assertEqual(device.name, 'manual-router-1')
        self.assertEqual(device.device_type, 'router')
        self.assertEqual(device.ip_address, '10.0.0.1')
        self.assertEqual(device.status, 'preparing')

    def test_get_device_details(self):
        """测试获取设备详情"""
        device = Device.objects.create(
            name='detail-test-device',
            device_type='switch',
            ip_address='192.168.1.50',
            status='online',
            location='Office Building',
            model='Cisco 2960',
        )

        details = self.service.get_device_details(device)

        self.assertEqual(details['name'], 'detail-test-device')
        self.assertEqual(details['device_type'], 'switch')
        self.assertEqual(details['ip_address'], '192.168.1.50')
        self.assertEqual(details['status'], 'online')


class DeviceModelTestCase(TestCase):
    """测试设备模型"""

    def test_create_device(self):
        """测试创建设备"""
        device = Device.objects.create(
            name='test-router',
            device_type='router',
            ip_address='192.168.1.1',
            status='online',
            ssh_port=22,
            ssh_username='admin',
        )

        self.assertIsNotNone(device.id)
        self.assertEqual(device.name, 'test-router')
        self.assertEqual(device.device_type, 'router')
        self.assertEqual(device.ip_address, '192.168.1.1')

    def test_device_str_representation(self):
        """测试设备的字符串表示"""
        device = Device.objects.create(
            name='test-switch',
            device_type='switch',
            ip_address='192.168.1.2',
            status='offline',
        )

        self.assertEqual(str(device), 'test-switch (交换机) - 192.168.1.2')

    def test_device_choices(self):
        """测试设备类型和状态选项"""
        # 测试设备类型
        router = Device(device_type='router', ip_address='1.1.1.1', name='r1')
        self.assertEqual(router.get_device_type_display(), '路由器')

        switch = Device(device_type='switch', ip_address='1.1.1.2', name='s1')
        self.assertEqual(switch.get_device_type_display(), '交换机')

        # 测试设备状态
        online = Device(ip_address='1.1.1.3', name='on1', status='online')
        self.assertEqual(online.get_status_display(), '在线')

        offline = Device(ip_address='1.1.1.4', name='off1', status='offline')
        self.assertEqual(offline.get_status_display(), '下线')


class DeviceAPITestCase(TestCase):
    """测试设备API端点"""

    def setUp(self):
        """设置测试环境"""
        self.client = APIClient()

        # 创建测试用户
        self.user = User.objects.create_user(
            username='apitest',
            email='api@test.com',
            password='testpass123'
        )
        UserProfile.objects.create(
            user=self.user,
            role='admin',
        )

        # 创建设备
        self.device = Device.objects.create(
            name='api-test-device',
            device_type='router',
            ip_address='192.168.100.1',
            status='online',
            location='Test Location',
        )

    def test_device_list_api_requires_auth(self):
        """测试设备列表API需要认证"""
        response = self.client.get('/devices/api/list/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_device_list_api_authenticated(self):
        """测试认证后的设备列表API"""
        self.client.login(username='apitest', password='testpass123')
        response = self.client.get('/devices/api/list/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'api-test-device')

    def test_device_list_api_pagination(self):
        """测试设备列表API分页"""
        # 创建更多设备
        for i in range(25):
            Device.objects.create(
                name=f'device-{i}',
                device_type='switch',
                ip_address=f'192.168.1.{i+10}',
                status='online',
            )

        self.client.login(username='apitest', password='testpass123')
        response = self.client.get('/devices/api/list/?page=1&page_size=10')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 26)
        self.assertEqual(response.data['total_pages'], 3)
        self.assertEqual(len(response.data['results']), 10)

    def test_device_list_api_filter_by_type(self):
        """测试按设备类型筛选"""
        Device.objects.create(
            name='switch-test',
            device_type='switch',
            ip_address='192.168.1.200',
            status='online',
        )

        self.client.login(username='apitest', password='testpass123')
        response = self.client.get('/devices/api/list/?device_type=router')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['device_type'], 'router')

    def test_device_list_api_filter_by_status(self):
        """测试按状态筛选"""
        Device.objects.create(
            name='offline-device',
            device_type='router',
            ip_address='192.168.1.201',
            status='offline',
        )

        self.client.login(username='apitest', password='testpass123')
        response = self.client.get('/devices/api/list/?status=online')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 所有测试设备都是online
        for device in response.data['results']:
            self.assertEqual(device['status'], 'online')

    def test_device_list_api_search(self):
        """测试搜索功能"""
        self.client.login(username='apitest', password='testpass123')
        response = self.client.get('/devices/api/list/?search=api-test')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertIn('api-test', response.data['results'][0]['name'])

    def test_device_detail_api(self):
        """测试设备详情API"""
        self.client.login(username='apitest', password='testpass123')
        response = self.client.get(f'/devices/api/{self.device.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'api-test-device')
        self.assertEqual(response.data['ip_address'], '192.168.100.1')

    def test_device_create_api(self):
        """测试创建设备API"""
        self.client.login(username='apitest', password='testpass123')

        new_device = {
            'name': 'new-api-device',
            'device_type': 'switch',
            'ip_address': '192.168.200.1',
            'status': 'preparing',
            'ssh_username': 'admin',
        }

        response = self.client.post('/devices/api/list/', new_device)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'new-api-device')

        # 验证设备已创建
        self.assertTrue(Device.objects.filter(name='new-api-device').exists())

    def test_device_update_api(self):
        """测试更新设备API"""
        self.client.login(username='apitest', password='testpass123')

        response = self.client.put(
            f'/devices/api/{self.device.id}/',
            {'name': 'updated-name', 'status': 'offline'}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 验证更新成功
        self.device.refresh_from_db()
        self.assertEqual(self.device.name, 'updated-name')
        self.assertEqual(self.device.status, 'offline')

    def test_device_delete_api(self):
        """测试删除设备API"""
        self.client.login(username='apitest', password='testpass123')

        device_id = self.device.id

        response = self.client.delete(f'/devices/api/{device_id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # 验证设备已删除
        self.assertFalse(Device.objects.filter(id=device_id).exists())

    def test_device_statistics_api(self):
        """测试设备统计API"""
        self.client.login(username='apitest', password='testpass123')
        response = self.client.get('/devices/api/statistics/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_devices', response.data)
        self.assertIn('by_device_type', response.data)
        self.assertIn('by_status', response.data)


class DeviceExportTestCase(TestCase):
    """测试设备导出功能"""

    def setUp(self):
        """设置测试环境"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='exporttest',
            email='export@test.com',
            password='testpass123'
        )
        UserProfile.objects.create(user=self.user, role='admin')

        # 创建设备
        Device.objects.create(
            name='export-device',
            device_type='router',
            ip_address='192.168.50.1',
            status='online',
            location='Export Test',
        )

    def test_device_export_json(self):
        """测试JSON导出"""
        self.client.login(username='exporttest', password='testpass123')
        response = self.client.get('/devices/api/export/?format=json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('devices', response.data)
        self.assertEqual(len(response.data['devices']), 1)


class DevicePaginationTestCase(TestCase):
    """测试设备分页功能"""

    def setUp(self):
        """创建多个设备用于分页测试"""
        for i in range(50):
            Device.objects.create(
                name=f'paginated-device-{i}',
                device_type='router',
                ip_address=f'10.0.{i//256}.{i%256}',
                status='online',
            )

    def test_paginator_first_page(self):
        """测试分页器首页"""
        queryset = Device.objects.all().order_by('name')
        paginator = Paginator(queryset, 20)

        page = paginator.page(1)
        self.assertEqual(len(page), 20)
        self.assertTrue(page.has_next())

    def test_paginator_last_page(self):
        """测试分页器末页"""
        queryset = Device.objects.all().order_by('name')
        paginator = Paginator(queryset, 20)

        page = paginator.page(3)
        self.assertEqual(len(page), 10)
        self.assertFalse(page.has_next())

    def test_paginator_out_of_range(self):
        """测试超出范围"""
        queryset = Device.objects.all().order_by('name')
        paginator = Paginator(queryset, 20)

        with self.assertRaises(EmptyPage):
            paginator.page(10)


class DeviceReadonlyPermissionTestCase(TestCase):
    """测试只读用户在设备模块中的可用功能。"""

    def setUp(self):
        self.client = Client()
        self.api_client = APIClient()

        self.user = User.objects.create_user(
            username='readonly-device',
            email='readonly-device@test.com',
            password='testpass123'
        )
        UserProfile.objects.create(user=self.user, role='readonly')

        self.device = Device.objects.create(
            name='readonly-device-1',
            device_type='router',
            ip_address='192.168.10.1',
            status='online',
            ssh_port=22,
            ssh_username='admin',
            ssh_password='secret',
        )

    def test_readonly_device_list_hides_manage_buttons(self):
        """只读用户在设备列表中只看到测试、配置和 SSH。"""
        self.client.login(username='readonly-device', password='testpass123')
        response = self.client.get(reverse('devices:device_list'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('测试', content)
        self.assertIn('配置', content)
        self.assertIn('SSH', content)
        self.assertNotIn('id="refreshStatusBtn"', content)
        self.assertNotIn('onclick="openAddModal()"', content)
        self.assertNotIn('编辑</button>', content)
        self.assertNotIn('删除</button>', content)

    @patch('devices.views.ping_host')
    def test_readonly_user_can_ping_device(self, mock_ping_host):
        """只读用户允许执行设备测试。"""
        mock_ping_host.return_value = {'reachable': True, 'latency': 12.5}

        self.api_client.login(username='readonly-device', password='testpass123')
        response = self.api_client.post(reverse('devices:device_ping_api', args=[self.device.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

    def test_readonly_user_cannot_update_device(self):
        """只读用户不允许编辑设备。"""
        self.api_client.login(username='readonly-device', password='testpass123')
        response = self.api_client.put(
            reverse('devices:device_detail_api', args=[self.device.id]),
            {'name': 'blocked-update'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
