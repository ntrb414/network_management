from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from devices.models import Device
from backups.models import ConfigBackup
from backups.services import BackupService
from accounts.models import UserProfile


class BackupPageNavigationTestCase(TestCase):
    """Test cases for backup page navigation links."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='testpass123'
        )
        
        # Create user profile with backups.view permission
        UserProfile.objects.create(
            user=self.user,
            role='user',
            permissions={'backups': ['view']}
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
        
        # Create test backup
        self.backup = ConfigBackup.objects.create(
            device=self.device,
            git_commit_hash='abc123def456',
            commit_message='Test backup',
            config_content='config content',
            backed_up_by=self.user
        )
    
    def test_backup_list_has_back_to_homepage_link(self):
        """Test that backup list page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('backups:backup_list'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.redirect_chain)
        self.assertEqual(response.redirect_chain[-1][0], reverse('configs:config_backup'))
        content = response.content.decode()
        
        # Check for back to homepage link
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_backup_list_has_user_info(self):
        """Test that backup list page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('backups:backup_list'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.redirect_chain)
        self.assertEqual(response.redirect_chain[-1][0], reverse('configs:config_backup'))
        content = response.content.decode()
        
        # Check for user info
        self.assertIn('testuser', content)
    
    def test_backup_list_has_logout_button(self):
        """Test that backup list page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('backups:backup_list'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.redirect_chain)
        self.assertEqual(response.redirect_chain[-1][0], reverse('configs:config_backup'))
        content = response.content.decode()
        
        # Check for logout button
        self.assertIn('退出', content)
        self.assertIn(reverse('homepage:logout'), content)
    
    def test_backup_detail_has_back_to_homepage_link(self):
        """Test that backup detail page has 'Back to Homepage' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('backups:backup_detail', args=[self.backup.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for back to homepage link
        self.assertIn(reverse('homepage:homepage'), content)
    
    def test_backup_detail_has_back_to_backups_link(self):
        """Test that backup detail page has 'Back to Backups' link."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('backups:backup_detail', args=[self.backup.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for back to backups link
        self.assertIn('返回列表', content)
        self.assertIn(reverse('backups:backup_list'), content)
    
    def test_backup_detail_has_user_info(self):
        """Test that backup detail page displays current user information."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('backups:backup_detail', args=[self.backup.pk]))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for user info
        self.assertIn('testuser', content)
    
    def test_backup_detail_has_logout_button(self):
        """Test that backup detail page has logout button."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('backups:backup_detail', args=[self.backup.pk]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check for logout button
        self.assertIn('退出', content)
        self.assertIn(reverse('homepage:logout'), content)


# ==================== Service Tests ====================

class BackupServiceTestCase(TestCase):
    """测试备份服务"""

    def setUp(self):
        self.service = BackupService()
        self.user = User.objects.create_user(
            username='backupuser', email='backup@test.com', password='testpass123'
        )
        self.device = Device.objects.create(
            name='backup-test-device', device_type='router', ip_address='192.168.60.1', status='online',
        )

    def test_backup_device_config(self):
        """测试设备配置备份"""
        config_content = "interface GigabitEthernet0/0\n ip address 192.168.1.1 255.255.255.0"

        result = self.service.backup_device_config(
            device=self.device,
            config_content=config_content,
            commit_message='Test backup',
            user=self.user
        )

        self.assertTrue(result['success'])
        self.assertIn('backup_id', result)
        self.assertIn('commit_hash', result)

    def test_get_device_backups(self):
        """测试获取设备备份列表"""
        # 先创建备份
        self.service.backup_device_config(
            device=self.device,
            config_content='test config',
            commit_message='Test',
            user=self.user
        )

        result = self.service.get_device_backups(device_id=self.device.id)

        self.assertIn('backups', result)
        self.assertIn('total', result)

    def test_get_all_backups(self):
        """测试获取所有备份"""
        result = self.service.get_all_backups()

        self.assertIn('backups', result)
        self.assertIn('total', result)

    def test_compare_versions(self):
        """测试版本对比"""
        # 创建两个备份
        self.service.backup_device_config(
            device=self.device,
            config_content='config version 1',
            commit_message='Version 1',
            user=self.user
        )

        backup1 = ConfigBackup.objects.first()

        self.service.backup_device_config(
            device=self.device,
            config_content='config version 2',
            commit_message='Version 2',
            user=self.user
        )

        backup2 = ConfigBackup.objects.first()

        result = self.service.compare_versions(backup1.id, backup2.id)

        self.assertTrue(result['success'])
        self.assertIn('diff', result)

    def test_cleanup_old_backups(self):
        """测试清理老旧备份"""
        # 创建备份
        self.service.backup_device_config(
            device=self.device,
            config_content='test config',
            commit_message='Test',
            user=self.user
        )

        result = self.service.cleanup_old_backups(days=0)

        self.assertIn('deleted_count', result)


# ==================== API Tests ====================

from rest_framework.test import APIClient
from rest_framework import status


class BackupAPITestCase(TestCase):
    """测试备份API"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='backup_api_user', email='backupapi@test.com', password='testpass123'
        )
        UserProfile.objects.create(user=self.user, role='admin')
        self.device = Device.objects.create(
            name='backup-api-device', device_type='router', ip_address='10.0.60.1', status='online',
        )
        self.service = BackupService()
        self.service.backup_device_config(
            device=self.device,
            config_content='test config',
            commit_message='Test',
            user=self.user
        )

    def test_backup_list_api(self):
        """测试备份列表API"""
        self.client.login(username='backup_api_user', password='testpass123')
        response = self.client.get('/backups/api/list/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('backups', response.data)

    def test_device_backup_list_api(self):
        """测试设备备份列表API"""
        self.client.login(username='backup_api_user', password='testpass123')
        response = self.client.get(f'/backups/api/devices/{self.device.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('backups', response.data)

    def test_backup_detail_api(self):
        """测试备份详情API"""
        backup = ConfigBackup.objects.first()
        self.client.login(username='backup_api_user', password='testpass123')
        response = self.client.get(f'/backups/api/{backup.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['device_name'], 'backup-api-device')

    def test_backup_create_api(self):
        """测试创建备份API"""
        self.client.login(username='backup_api_user', password='testpass123')
        response = self.client.post('/backups/api/create/', {
            'device_id': self.device.id,
            'config_content': 'new config',
            'commit_message': 'New backup',
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_backup_compare_api(self):
        """测试备份对比API"""
        backups = list(ConfigBackup.objects.all())
        if len(backups) >= 2:
            self.client.login(username='backup_api_user', password='testpass123')
            response = self.client.get(
                f'/backups/api/compare/?backup1_id={backups[1].id}&backup2_id={backups[0].id}'
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_backup_api_requires_auth(self):
        """测试备份API需要认证"""
        response = self.client.get('/backups/api/list/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
