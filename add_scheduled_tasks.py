#!/usr/bin/env python3
"""
在所有模板中添加定时任务链接
"""

import re
import os

# 需要处理的文件列表
files_to_process = [
    'accounts/templates/accounts/account_list.html',
    'accounts/templates/accounts/account_detail.html',
    'devices/templates/devices/device_detail.html',
    'devices/templates/devices/device_list.html',
    'devices/templates/devices/device_config_view.html',
    'ipmanagement/templates/ipmanagement/base_ipmanagement.html',
    'monitoring/templates/monitoring/monitoring_metric_types.html',
    'monitoring/templates/monitoring/monitoring_list.html',
    'monitoring/templates/monitoring/monitoring_device_detail.html',
    'monitoring/templates/monitoring/monitoring_dashboard.html',
    'logs/templates/logs/log_list.html',
    'logs/templates/logs/runtime_log_list.html',
    'alerts/templates/alerts/alert_detail.html',
    'alerts/templates/alerts/alert_list.html',
    'configs/templates/configs/config_detail.html',
    'configs/templates/configs/config_list.html',
    'backups/templates/backups/backup_detail.html',
    'backups/templates/backups/backup_list.html',
    'admin_panel/templates/admin_panel/scheduled_tasks.html',
    'admin_panel/templates/admin_panel/dashboard.html',
]

# 定时任务链接的HTML
scheduled_tasks_html = '''        <div class="nb-sidebar-divider"></div>
        <div class="nb-sidebar-section">系统</div>
        <a href="{% url 'admin_panel:scheduled_tasks' %}" class="nb-sidebar-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            定时任务
        </a>
'''

# 匹配模式：账户管理链接后面直接是</aside>
pattern = r'(<a href="{% url \'accounts:account_list\' %}" class="nb-sidebar-item[^"]*">\s*<svg[^>]*>.*?</svg>\s*账户管理\s*</a>)(\s*</aside>)'

def add_scheduled_tasks(file_path):
    """添加定时任务链接"""
    full_path = os.path.join('/opt/network_management', file_path)

    if not os.path.exists(full_path):
        print(f"文件不存在: {file_path}")
        return

    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # 在账户管理链接和</aside>之间插入定时任务链接
    def replace_func(match):
        return match.group(1) + '\n' + scheduled_tasks_html + match.group(2)

    content = re.sub(pattern, replace_func, content, flags=re.DOTALL)

    if content != original_content:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"已更新: {file_path}")
    else:
        print(f"无需修改: {file_path}")

if __name__ == '__main__':
    for file_path in files_to_process:
        add_scheduled_tasks(file_path)
    print("\n处理完成!")
