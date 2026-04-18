from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch

from configs.models import ConfigTemplate, ConfigTask, ConfigTaskResult, ConfigFetchSchedule, ConfigFetchLog
from configs.services import ConfigManagementService
from configs.tasks import backup_all_devices_configs
from devices.models import Device
from accounts.models import UserProfile


class ConfigPageNavigationTestCase(TestCase):
    """Test cases for config page navigation links."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='testpass123'
        )
        
        # Create user profile with configs.view permission
        UserProfile.objects.create(
            user=self.user,
            role='user',
            permissions={'configs': ['view']}
        )
        
        # Create test config
        self.config = ConfigTemplate.objects.create(
            name='Test Config',
            description='Test configuration template',
            device_types=['router'],
            template_content='config content',
            created_by=self.user
        )
    
    def test_config_list_has_back_to_homepage_link(self):
        """Test that config list page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('configs:config_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for back to homepage link
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_config_list_has_user_info(self):
        """Test that config list page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('configs:config_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for user info
        self.assertIn('testuser', content)
    
    def test_config_list_has_logout_button(self):
        """Test that config list page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('configs:config_list'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for logout button
        self.assertIn('退出', content)
        self.assertIn(reverse('homepage:logout'), content)
    
    def test_config_detail_has_back_to_homepage_link(self):
        """Test that config detail page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('configs:config_detail', args=[self.config.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for back to homepage link
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_config_detail_has_back_to_configs_link(self):
        """Test that config detail page has 'Back to Configs' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('configs:config_detail', args=[self.config.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for back to configs link
        self.assertIn('返回列表', content)
        self.assertIn(reverse('configs:config_list'), content)
    
    def test_config_detail_has_user_info(self):
        """Test that config detail page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('configs:config_detail', args=[self.config.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for user info
        self.assertIn('testuser', content)
    
    def test_config_detail_has_logout_button(self):
        """Test that config detail page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('configs:config_detail', args=[self.config.pk]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check for logout button
        self.assertIn('退出', content)
        self.assertIn(reverse('homepage:logout'), content)


# ==================== 功能测试 ====================

class ConfigTemplateModelTestCase(TestCase):
    """测试配置模板模型"""

    def setUp(self):
        """设置测试环境"""
        self.user = User.objects.create_user(
            username='configuser2',
            email='config2@test.com',
            password='testpass123'
        )

    def test_create_config_template(self):
        """测试创建配置模板"""
        template = ConfigTemplate.objects.create(
            name='test-template-func',
            description='Test configuration template',
            device_types=['router', 'switch'],
            template_content='hostname {{ hostname }}',
            created_by=self.user,
        )

        self.assertIsNotNone(template.id)
        self.assertEqual(template.name, 'test-template-func')


class ConfigManagementServiceTestCase(TestCase):
    """测试配置管理服务"""

    def setUp(self):
        """设置测试环境"""
        self.service = ConfigManagementService()
        self.template = ConfigTemplate.objects.create(
            name='service-test-template-func',
            template_content='hostname {{ hostname }}',
            device_types=['router'],
            variables_schema={'required': ['hostname']},
        )
        self.device = Device.objects.create(
            name='config-device-func',
            device_type='router',
            ip_address='192.168.10.1',
            status='online',
        )

    def test_render_template(self):
        """测试模板渲染"""
        variables = {'hostname': 'test-router-01'}
        result = self.service.render_template(self.template, variables)
        self.assertEqual(result, 'hostname test-router-01')

    def test_validate_template_valid(self):
        """测试有效模板验证"""
        variables = {'hostname': 'valid-router'}
        result = self.service.validate_template(self.template, variables)
        self.assertTrue(result['valid'])

    @patch.object(ConfigManagementService, '_get_config_via_netmiko', return_value='sysname router1')
    def test_get_current_config_prefers_netmiko(self, mock_netmiko):
        result = self.service.get_current_config(self.device, use_cache=False)

        self.assertEqual(result, 'sysname router1')
        mock_netmiko.assert_called_once_with(self.device, 'running')

    @patch.object(ConfigManagementService, '_get_config_via_paramiko', return_value='fallback-config')
    @patch.object(ConfigManagementService, '_get_config_via_netmiko', side_effect=Exception('netmiko failed'))
    def test_get_startup_config_falls_back_to_paramiko(self, mock_netmiko, mock_paramiko):
        result = self.service.get_startup_config(self.device, use_cache=False)

        self.assertEqual(result, 'fallback-config')
        mock_netmiko.assert_called_once_with(self.device, 'startup')
        mock_paramiko.assert_called_once_with(self.device, 'startup')

    def test_clean_config_output_removes_null_bytes_and_prompt(self):
        output = '\x00display current-configuration\n<router1>\nsysname router1\ninterface Vlan1\n ip address 10.0.0.1 255.255.255.0\n'

        cleaned = self.service._clean_config_output(output, 'display current-configuration')

        self.assertEqual(cleaned, 'sysname router1\ninterface Vlan1\n ip address 10.0.0.1 255.255.255.0')


class ConfigAPITestCase(TestCase):
    """测试配置管理API"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='configapi2', email='configapi2@test.com', password='testpass123'
        )
        UserProfile.objects.create(user=self.user, role='admin')
        self.template = ConfigTemplate.objects.create(
            name='api-template-func', template_content='hostname {{ hostname }}', device_types=['router'],
        )
        self.device = Device.objects.create(
            name='api-device-func',
            device_type='router',
            ip_address='192.168.10.2',
            status='online',
        )

    def test_template_list_api_requires_auth(self):
        response = self.client.get('/configs/api/templates/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_template_list_api(self):
        self.client.login(username='configapi2', password='testpass123')
        response = self.client.get('/configs/api/templates/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_task_from_device_commands_template_sets_config_content(self):
        self.client.login(username='configapi2', password='testpass123')
        response = self.client.post(
            '/configs/api/tasks/',
            {
                'template_id': self.template.id,
                'device_ids': [self.device.id],
                'name': 'api-task-device-commands',
            },
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        task = ConfigTask.objects.get(pk=response.data['id'])
        self.assertEqual(task.config_content, self.template.template_content)


class ConfigTaskExecutionTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='taskuser',
            email='taskuser@test.com',
            password='testpass123'
        )
        self.template = ConfigTemplate.objects.create(
            name='task-template-device-commands',
            template_content='sysname branch-router',
            device_types=['router'],
            created_by=self.user,
        )
        self.device = Device.objects.create(
            name='task-device',
            device_type='router',
            ip_address='192.168.10.3',
            status='online',
        )

    def test_execute_task_uses_template_content_for_device_commands(self):
        task = ConfigTask.objects.create(
            name='execute-device-commands-task',
            template=self.template,
            config_content='',
            created_by=self.user,
        )
        task.devices.set([self.device])

        with patch.object(ConfigManagementService, 'deploy_config_batch', return_value={
            'success': True,
            'total': 1,
            'success_count': 1,
            'failure_count': 0,
            'results': [{
                'device_id': self.device.id,
                'device_ip': self.device.ip_address,
                'device_name': self.device.name,
                'success': True,
                'output': 'ok',
            }]
        }):
            service = ConfigManagementService()
            result = service.execute_task(task)

        task.refresh_from_db()

        self.assertTrue(result['success'])
        self.assertEqual(task.status, 'completed')
        self.assertEqual(task.results.count(), 1)
        self.assertEqual(task.results.first().config_content, 'sysname branch-router')

    def test_execute_task_replaces_previous_results_for_same_task(self):
        task = ConfigTask.objects.create(
            name='repeat-execute-task',
            template=self.template,
            config_content='',
            created_by=self.user,
        )
        task.devices.set([self.device])

        ConfigTaskResult.objects.create(
            task=task,
            device=self.device,
            success=False,
            config_content='old config',
            error_message='old error',
        )

        with patch.object(ConfigManagementService, 'deploy_config_batch', return_value={
            'success': True,
            'total': 1,
            'success_count': 1,
            'failure_count': 0,
            'results': [{
                'device_id': self.device.id,
                'device_ip': self.device.ip_address,
                'device_name': self.device.name,
                'success': True,
                'output': 'ok',
            }]
        }):
            service = ConfigManagementService()
            service.execute_task(task)

        task.refresh_from_db()

        self.assertEqual(task.results.count(), 1)
        self.assertTrue(task.results.first().success)
        self.assertEqual(task.results.first().config_content, 'sysname branch-router')

    def test_execute_task_with_batch_results_persists_correctly(self):
        """验证 execute_task 按批量结果正确落库。"""
        device2 = Device.objects.create(
            name='task-device-2',
            device_type='router',
            ip_address='192.168.10.4',
            status='online',
        )

        task = ConfigTask.objects.create(
            name='batch-task',
            template=self.template,
            config_content='',
            created_by=self.user,
        )
        task.devices.set([self.device, device2])

        with patch.object(ConfigManagementService, 'deploy_config_batch', return_value={
            'success': True,
            'total': 2,
            'success_count': 2,
            'failure_count': 0,
            'results': [
                {
                    'device_id': self.device.id,
                    'device_ip': self.device.ip_address,
                    'device_name': self.device.name,
                    'success': True,
                    'output': 'ok1',
                },
                {
                    'device_id': device2.id,
                    'device_ip': device2.ip_address,
                    'device_name': device2.name,
                    'success': True,
                    'output': 'ok2',
                },
            ]
        }):
            service = ConfigManagementService()
            result = service.execute_task(task)

        task.refresh_from_db()

        self.assertTrue(result['success'])
        self.assertEqual(result['success_count'], 2)
        self.assertEqual(result['failure_count'], 0)
        self.assertEqual(task.results.count(), 2)

    def test_execute_task_partial_failure_sets_correct_status(self):
        """验证批量部分失败时 success_count/failure_count 与任务状态一致。"""
        device2 = Device.objects.create(
            name='task-device-3',
            device_type='router',
            ip_address='192.168.10.5',
            status='online',
        )

        task = ConfigTask.objects.create(
            name='partial-failure-task',
            template=self.template,
            config_content='',
            created_by=self.user,
        )
        task.devices.set([self.device, device2])

        with patch.object(ConfigManagementService, 'deploy_config_batch', return_value={
            'success': False,
            'total': 2,
            'success_count': 1,
            'failure_count': 1,
            'results': [
                {
                    'device_id': self.device.id,
                    'device_ip': self.device.ip_address,
                    'device_name': self.device.name,
                    'success': True,
                    'output': 'ok',
                },
                {
                    'device_id': device2.id,
                    'device_ip': device2.ip_address,
                    'device_name': device2.name,
                    'success': False,
                    'error': 'Connection failed',
                },
            ]
        }):
            service = ConfigManagementService()
            result = service.execute_task(task)

        task.refresh_from_db()

        # 部分成功时任务状态应为 completed
        self.assertEqual(task.status, 'completed')
        self.assertEqual(result['success_count'], 1)
        self.assertEqual(result['failure_count'], 1)
        self.assertEqual(task.results.count(), 2)

        # 验证结果记录正确
        success_result = task.results.filter(device=self.device).first()
        failure_result = task.results.filter(device=device2).first()
        self.assertTrue(success_result.success)
        self.assertFalse(failure_result.success)
        self.assertEqual(failure_result.error_message, 'Connection failed')


class ConfigBackupTaskVisibilityAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='backupapi',
            email='backupapi@test.com',
            password='testpass123'
        )
        UserProfile.objects.create(user=self.user, role='admin')
        self.device1 = Device.objects.create(
            name='backup-device-1',
            device_type='router',
            ip_address='192.168.20.1',
            status='online',
        )
        self.device2 = Device.objects.create(
            name='backup-device-2',
            device_type='switch',
            ip_address='192.168.20.2',
            status='online',
        )

    def _login(self):
        self.client.login(username='backupapi', password='testpass123')

    def test_backup_schedule_api_returns_schedule_id(self):
        self._login()
        response = self.client.get('/configs/api/backup/schedule/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('id', response.data)
        self.assertTrue(ConfigFetchSchedule.objects.filter(id=response.data['id']).exists())

    def test_config_task_detail_api_returns_latest_result_per_device(self):
        self._login()
        template = ConfigTemplate.objects.create(
            name='detail-template',
            template_content='display current-configuration',
            device_types=['router'],
            created_by=self.user,
        )
        task = ConfigTask.objects.create(
            name='detail-task',
            template=template,
            config_content='display current-configuration',
            created_by=self.user,
            status='completed',
        )
        task.devices.set([self.device1])

        ConfigTaskResult.objects.create(
            task=task,
            device=self.device1,
            success=False,
            config_content='old',
            error_message='old error',
        )
        ConfigTaskResult.objects.create(
            task=task,
            device=self.device1,
            success=True,
            config_content='new',
            error_message='',
        )

        response = self.client.get(f'/configs/api/tasks/{task.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertTrue(response.data['results'][0]['success'])
        self.assertEqual(response.data['results'][0]['device_id'], self.device1.id)

    def test_schedule_logs_api_returns_result_detail(self):
        self._login()
        schedule = ConfigFetchSchedule.objects.create(
            name='配置备份任务',
            task_type='backup',
            enabled=True,
            exec_mode='cron',
            exec_days='*',
            created_by=self.user,
        )
        ConfigFetchLog.objects.create(
            schedule=schedule,
            status='partial',
            total_devices=2,
            success_count=1,
            failed_count=1,
            result_detail={
                'results': [
                    {'device_id': 1, 'device_name': 'router1', 'success': True},
                    {'device_id': 2, 'device_name': 'router2', 'success': False, 'error': 'SSH failed'},
                ]
            }
        )

        response = self.client.get(f'/configs/api/schedules/{schedule.id}/logs/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['logs']), 1)
        self.assertIn('result_detail', response.data['logs'][0])
        self.assertEqual(response.data['logs'][0]['result_detail']['results'][1]['error'], 'SSH failed')

    def test_create_backup_schedule_persists_selected_devices(self):
        self._login()
        response = self.client.post(
            '/configs/api/schedules/',
            {
                'name': '核心设备定时备份',
                'task_type': 'backup',
                'enabled': True,
                'exec_mode': 'interval',
                'interval_seconds': 1800,
                'exec_time': '02:00',
                'exec_days': '*',
                'target_all_devices': False,
                'device_selection_mode': 'single',
                'target_devices': [self.device1.id, self.device2.id],
                'only_online_devices': True,
            },
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        schedule = ConfigFetchSchedule.objects.get(pk=response.data['id'])
        self.assertEqual(schedule.task_type, 'backup')
        self.assertFalse(schedule.target_all_devices)
        self.assertEqual(schedule.device_selection_mode, 'single')
        self.assertEqual(list(schedule.target_devices.values_list('id', flat=True)), [self.device1.id])

    def test_schedule_list_api_can_filter_backup_tasks(self):
        self._login()
        ConfigFetchSchedule.objects.create(
            name='设备配置预加载',
            task_type='preload',
            created_by=self.user,
        )
        ConfigFetchSchedule.objects.create(
            name='夜间备份',
            task_type='backup',
            created_by=self.user,
        )

        response = self.client.get('/configs/api/schedules/?task_type=backup')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['schedules']), 1)
        self.assertEqual(response.data['schedules'][0]['task_type'], 'backup')

    @patch('configs.tasks.backup_all_devices_configs.delay')
    def test_schedule_run_api_dispatches_backup_task(self, mock_delay):
        self._login()
        mock_delay.return_value.id = 'job-123'
        schedule = ConfigFetchSchedule.objects.create(
            name='夜间备份',
            task_type='backup',
            created_by=self.user,
        )

        response = self.client.post(f'/configs/api/schedules/{schedule.id}/run/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_delay.assert_called_once_with(schedule.id)
        self.assertEqual(response.data['task_type'], 'backup')


class ConfigBackupTaskExecutionScopeTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='scopeuser',
            email='scopeuser@test.com',
            password='testpass123'
        )
        self.device1 = Device.objects.create(
            name='scope-device-1',
            device_type='router',
            ip_address='192.168.21.1',
            status='online',
        )
        self.device2 = Device.objects.create(
            name='scope-device-2',
            device_type='switch',
            ip_address='192.168.21.2',
            status='online',
        )

    def test_backup_task_respects_selected_devices(self):
        schedule = ConfigFetchSchedule.objects.create(
            name='指定设备备份',
            task_type='backup',
            enabled=True,
            target_all_devices=False,
            only_online_devices=False,
            created_by=self.user,
        )
        schedule.target_devices.set([self.device2])

        with patch.object(ConfigManagementService, 'backup_device_configs', side_effect=lambda device: {
            'device_id': device.id,
            'device_name': device.name,
            'success': True,
        }) as mock_backup:
            result = backup_all_devices_configs.run(schedule_id=schedule.id)

        self.assertTrue(result['success'])
        self.assertEqual(result['total_devices'], 1)
        self.assertEqual(result['success_count'], 1)
        self.assertEqual(mock_backup.call_count, 1)
        self.assertEqual(mock_backup.call_args[0][0].id, self.device2.id)
