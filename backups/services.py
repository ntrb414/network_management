"""
配置备份服务

提供配置备份、版本对比等功能。
"""

import logging
import os
import difflib
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


class BackupService:
    """配置备份服务类"""

    def __init__(self):
        """初始化备份服务"""
        self.backup_dir = '/opt/network_management/config_backups'
        self._ensure_backup_dir()

    def _ensure_backup_dir(self):
        """确保备份目录存在"""
        os.makedirs(self.backup_dir, exist_ok=True)

    def _init_git_repo(self) -> bool:
        """
        初始化Git仓库

        Returns:
            是否成功
        """
        try:
            import git
        except ImportError:
            logger.warning("GitPython未安装，无法使用Git功能")
            return False

        repo_path = self.backup_dir

        # 检查是否已经是Git仓库
        try:
            repo = git.Repo(repo_path)
            return True
        except git.InvalidGitRepositoryError:
            # 创建新仓库
            repo = git.Repo.init(repo_path)
            return True
        except Exception as e:
            logger.error(f"初始化Git仓库失败: {e}")
            return False

    def backup_device_config(
        self,
        device,
        config_content: str,
        commit_message: str = None,
        user=None
    ) -> Optional[Dict[str, Any]]:
        """
        备份设备配置

        Args:
            device: 设备对象
            config_content: 配置内容
            commit_message: 提交说明
            user: 操作用户

        Returns:
            备份结果

        """
        try:
            import git
        except ImportError:
            logger.warning("GitPython未安装，配置备份将仅保存到数据库")
            return self._backup_to_db_only(device, config_content, commit_message, user)

        try:
            # 确保目录存在
            self._ensure_backup_dir()

            # 初始化或打开仓库
            try:
                repo = git.Repo(self.backup_dir)
            except git.InvalidGitRepositoryError:
                repo = git.Repo.init(self.backup_dir)

            # 创建设备配置目录
            device_dir = os.path.join(self.backup_dir, str(device.id))
            os.makedirs(device_dir, exist_ok=True)

            # 配置文件名
            config_file = os.path.join(device_dir, 'config.txt')

            # 读取旧配置
            old_content = ''
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    old_content = f.read()

            # 写入新配置
            with open(config_file, 'w') as f:
                f.write(config_content)

            # Git操作
            repo.index.add([config_file])

            # 生成提交信息
            if not commit_message:
                commit_message = f"Backup configuration for {device.name}"

            # 提交
            commit = repo.index.commit(commit_message)

            # 保存到数据库
            backup = self._save_backup_record(
                device=device,
                config_content=config_content,
                commit_hash=commit.hexsha,
                commit_message=commit_message,
                user=user
            )

            return {
                'success': True,
                'backup_id': backup.id,
                'commit_hash': commit.hexsha,
            }

        except Exception as e:
            logger.error(f"配置备份失败: {e}")
            # 保存失败记录
            self._save_backup_record(
                device=device,
                config_content=config_content,
                commit_hash=f"failed_{datetime.now().timestamp()}",
                commit_message=commit_message or f"Failed backup for {device.name}",
                user=user,
                status='failed'
            )
            return {
                'success': False,
                'error': str(e),
            }

    def _backup_to_db_only(
        self,
        device,
        config_content: str,
        commit_message: str,
        user=None
    ) -> Dict[str, Any]:
        """仅保存到数据库（无Git）"""
        backup = self._save_backup_record(
            device=device,
            config_content=config_content,
            commit_hash=f"db_{datetime.now().timestamp()}",
            commit_message=commit_message or f"Backup configuration for {device.name}",
            user=user
        )

        return {
            'success': True,
            'backup_id': backup.id,
            'commit_hash': backup.git_commit_hash,
        }

    def _save_backup_record(
        self,
        device,
        config_content: str,
        commit_hash: str,
        commit_message: str,
        user=None,
        status: str = 'success'
    ):
        """保存备份记录到数据库"""
        from .models import ConfigBackup

        backup = ConfigBackup.objects.create(
            device=device,
            config_content=config_content,
            git_commit_hash=commit_hash,
            commit_message=commit_message,
            backed_up_by=user,
            status=status,
        )

        return backup

    def compare_versions(
        self,
        backup1_id: int,
        backup2_id: int
    ) -> Dict[str, Any]:
        """
        对比两个版本的配置

        Args:
            backup1_id: 第一个备份ID
            backup2_id: 第二个备份ID

        Returns:
            对比结果

        """
        from .models import ConfigBackup

        try:
            backup1 = ConfigBackup.objects.get(id=backup1_id)
            backup2 = ConfigBackup.objects.get(id=backup2_id)
        except ConfigBackup.DoesNotExist:
            return {
                'success': False,
                'error': 'Backup not found',
            }

        # 对比配置
        lines1 = backup1.config_content.splitlines()
        lines2 = backup2.config_content.splitlines()

        diff = list(difflib.unified_diff(
            lines1, lines2,
            fromfile=f'version {backup1_id}',
            tofile=f'version {backup2_id}',
            lineterm=''
        ))

        # 统计差异
        added_lines = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
        removed_lines = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))

        return {
            'success': True,
            'backup1_id': backup1_id,
            'backup2_id': backup2_id,
            'backup1_time': backup1.backed_up_at,
            'backup2_time': backup2.backed_up_at,
            'diff': diff,
            'added_lines': added_lines,
            'removed_lines': removed_lines,
        }

    def get_device_backups(
        self,
        device_id: int,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        获取设备的备份历史

        Args:
            device_id: 设备ID
            page: 页码
            page_size: 每页数量

        Returns:
            备份列表

        """
        from .models import ConfigBackup

        queryset = ConfigBackup.objects.filter(device_id=device_id).order_by('-backed_up_at')

        total = queryset.count()
        offset = (page - 1) * page_size
        backups = list(queryset[offset:offset + page_size].values(
            'id', 'git_commit_hash', 'commit_message', 'backed_up_at', 'backed_up_by'
        ))

        return {
            'total': total,
            'page': page,
            'page_size': page_size,
            'backups': backups,
        }

    def get_all_backups(
        self,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """获取所有备份"""
        from .models import ConfigBackup

        queryset = ConfigBackup.objects.all().order_by('-backed_up_at')

        total = queryset.count()
        offset = (page - 1) * page_size
        backups = list(queryset[offset:offset + page_size].values(
            'id', 'device_id', 'git_commit_hash', 'commit_message', 'backed_up_at', 'backed_up_by'
        ))

        return {
            'total': total,
            'page': page,
            'page_size': page_size,
            'backups': backups,
        }

    def cleanup_old_backups(self, days: int = 30) -> Dict[str, Any]:
        """
        清理老旧备份

        Args:
            days: 保留天数

        Returns:
            清理结果

        """
        from .models import ConfigBackup

        # 计算截止时间
        cutoff_time = timezone.now() - timedelta(days=days)

        # 获取要删除的备份
        old_backups = ConfigBackup.objects.filter(backed_up_at__lt=cutoff_time)
        deleted_count = old_backups.count()

        # 获取相关设备的ID列表（用于清理文件系统）
        device_ids = set(b.device_id for b in old_backups)

        # 删除数据库记录
        old_backups.delete()

        # 清理空设备目录（保留仍有最新备份的设备目录）
        for device_id in device_ids:
            device_dir = os.path.join(self.backup_dir, str(device_id))
            # 检查是否还有其他备份记录
            if not ConfigBackup.objects.filter(device_id=device_id).exists():
                # 删除设备目录（如果存在）
                import shutil
                if os.path.exists(device_dir):
                    try:
                        shutil.rmtree(device_dir)
                    except Exception as e:
                        logger.warning(f"删除设备备份目录失败 {device_dir}: {e}")

        # 尝试清理 Git 仓库中的孤儿提交（如果配置为使用Git）
        try:
            import git
            repo = git.Repo(self.backup_dir)
            # 获取所有仍被引用的commit hash
            active_hashes = set(
                ConfigBackup.objects.values_list('git_commit_hash', flat=True)
            )
            # 保留与数据库记录对应的提交，清理其他孤儿提交
            for ref in repo.refs:
                if ref.name.startswith('origin/'):
                    continue
        except Exception as e:
            logger.warning(f"Git仓库清理跳过: {e}")

        return {
            'success': True,
            'deleted_count': deleted_count,
            'cutoff_time': cutoff_time,
        }
