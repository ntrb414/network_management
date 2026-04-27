"""
配置 GitLab 推送服务

用于将设备配置推送到 GitLab 仓库进行版本保存。
"""

import os
import logging
from typing import Dict, List

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class ConfigGitlabService:
    # 配置 GitLab 推送服务，负责将设备配置推送到远程 GitLab 仓库

    def __init__(self):
        # 初始化服务，读取 GitLab 相关配置
        self.repo_path = settings.GITLAB_CONFIG_REPO_PATH
        self.gitlab_url = settings.GITLAB_URL
        self.token = settings.GITLAB_ACCESS_TOKEN
        self.project_id = settings.GITLAB_PROJECT_ID
        self.branch = settings.GITLAB_BRANCH
        self._init_repo()

    def _resolve_project_path(self) -> str:
        # 解析 GitLab 项目路径。
        # 如果 GITLAB_PROJECT_ID 是数字，通过 API 查询获取 path_with_namespace；
        # 如果已经是 namespace/project 格式，直接使用。
        project_id = str(self.project_id).strip()
        if '/' in project_id:
            return project_id
        # 尝试通过 GitLab API 查询
        try:
            import requests
            url = f"{self.gitlab_url}/api/v4/projects/{project_id}"
            headers = {'PRIVATE-TOKEN': self.token}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                path = data.get('path_with_namespace')
                if path:
                    logger.info(f"GitLab API 解析项目路径: {project_id} -> {path}")
                    return path
        except Exception as e:
            logger.warning(f"GitLab API 查询项目路径失败: {e}")
        # 兜底：直接使用 project_id（兼容旧配置）
        return project_id

    def _init_repo(self):
        # 初始化本地仓库并关联 GitLab 远程仓库
        import git
        os.makedirs(self.repo_path, exist_ok=True)
        try:
            self.repo = git.Repo(self.repo_path)
        except git.InvalidGitRepositoryError:
            self.repo = git.Repo.init(self.repo_path)

        # 配置 remote，使用 oauth2 token 进行认证
        project_path = self._resolve_project_path()
        host = self.gitlab_url.replace('http://', '').replace('https://', '').rstrip('/')
        remote_url = f"http://oauth2:{self.token}@{host}/{project_path}.git"
        try:
            self.repo.delete_remote('origin')
        except Exception:
            # 如果 origin 不存在则忽略错误
            pass
        self.repo.create_remote('origin', remote_url)
        logger.info(f"GitLab remote 配置完成: {remote_url.replace(self.token, '***')}")

    def push_configs(self, device_configs: List[Dict], commit_message: str = None, startup_only: bool = False) -> Dict:
        # 批量推送设备配置到 GitLab
        # device_configs 参数格式示例：
        # [
        #     {'device_id': 1, 'device_name': 'SW-01', 'running_config': '...', 'startup_config': '...'},
        #     ...
        # ]
        # startup_only: 如果为 True，只推送 startup-config
        import git
        import socket

        try:
            for device_item in device_configs:
                device_dir = os.path.join(self.repo_path, f"devices/{device_item['device_id']}")
                os.makedirs(device_dir, exist_ok=True)

                # 只保存 startup-config（如果 startup_only 为 True）
                startup_config_path = os.path.join(device_dir, 'startup-config.txt')
                with open(startup_config_path, 'w') as startup_file:
                    startup_file.write(device_item.get('startup_config', ''))

                # 如果不是只推送启动配置，也保存 running-config
                if not startup_only:
                    running_config_path = os.path.join(device_dir, 'running-config.txt')
                    with open(running_config_path, 'w') as running_file:
                        running_file.write(device_item.get('running_config', ''))

            # Git 提交所有变更
            self.repo.git.add(all=True)
            if self.repo.is_dirty():
                message = commit_message
                if message is None:
                    message = f"Auto save configs at {timezone.now().isoformat()}"
                self.repo.index.commit(message)
                
                # 设置推送超时并执行
                try:
                    origin = self.repo.remote('origin')
                    # 本地分支名可能与目标分支名不一致（如本地 master，远程 main）
                    local_branch = self.repo.active_branch.name
                    refspec = f'{local_branch}:{self.branch}'
                    # 使用 repo.git.push 避免 GitPython Remote.push 不支持 timeout 参数的问题
                    self.repo.git.push('origin', refspec)
                    logger.info(f"GitLab推送成功: {message} ({refspec})")
                except socket.timeout:
                    error_msg = "GitLab推送超时：连接超时，请检查网络连接"
                    logger.error(error_msg)
                    return {'success': False, 'error': error_msg}
                except git.exc.GitCommandError as git_error:
                    error_str = str(git_error)
                    # 处理 fast-forward 拒绝：远程已有提交且历史不相关
                    if 'rejected' in error_str or 'fetch first' in error_str or 'non-fast-forward' in error_str:
                        logger.warning(f"GitLab push 被拒绝，尝试先 pull 再 push: {error_str}")
                        try:
                            # 先 fetch 远程分支
                            origin.fetch(refspec=self.branch)
                            # 配置 pull 策略为 merge，避免 Git 2.27+ 版本的警告和错误
                            self.repo.config_writer().set_value('pull', 'rebase', 'false').release()
                            # 允许合并不相关历史
                            self.repo.git.pull('origin', self.branch, '--allow-unrelated-histories')
                            # 再次推送
                            self.repo.git.push('origin', refspec)
                            logger.info(f"GitLab推送成功(先pull后push): {message} ({refspec})")
                        except Exception as pull_push_error:
                            error_msg = f"GitLab推送失败: 先pull后push仍失败: {pull_push_error}"
                            logger.error(error_msg)
                            return {'success': False, 'error': error_msg}
                    else:
                        error_msg = f"GitLab推送失败: {error_str}"
                        logger.error(error_msg)
                        return {'success': False, 'error': error_msg}

            return {'success': True, 'commit_hash': self.repo.head.commit.hexsha}
            
        except Exception as e:
            error_msg = f"GitLab推送异常: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
