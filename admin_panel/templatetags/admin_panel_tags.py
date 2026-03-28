"""
admin_panel 自定义模板标签。

目前仅为定时任务页面提供任务展示元数据。
"""

from django import template

register = template.Library()


# 任务展示元数据映射
TASK_DESCRIPTIONS = {
    # 设备管理任务
    'devices.tasks.check_device_online': {
        'name': '设备在线状态检测',
        'description': '对所有设备进行 ping 检测，更新在线状态并触发离线告警',
        'devices': 'all',
        'category': '设备管理',
    },
    'devices.tasks.scheduled_device_discovery': {
        'name': '定时设备发现',
        'description': '基于 LLDP 协议发现网络中的新设备',
        'devices': 'online',
        'category': '设备管理',
    },
    'devices.tasks.scan_ip_range_task': {
        'name': 'IP 范围扫描',
        'description': '扫描指定 IP 范围内的设备',
        'devices': 'range',
        'category': '设备管理',
    },
    'devices.tasks.scan_lldp_task': {
        'name': 'LLDP 设备发现',
        'description': '通过 LLDP 协议发现相邻设备',
        'devices': 'seed',
        'category': '设备管理',
    },
    'devices.tasks.discover_device_details': {
        'name': '设备详情发现',
        'description': '获取设备的详细信息和端口状态',
        'devices': 'single',
        'category': '设备管理',
    },
    # 配置管理任务
    'configs.tasks.backup_all_devices_configs': {
        'name': '配置定时备份',
        'description': '备份所有设备的运行配置和启动配置',
        'devices': 'all',
        'category': '配置管理',
    },
    'configs.tasks.backup_single_device_config': {
        'name': '单设备配置备份',
        'description': '备份指定设备的配置',
        'devices': 'single',
        'category': '配置管理',
    },
    'configs.tasks.execute_config_task': {
        'name': '执行配置任务',
        'description': '执行配置下发任务',
        'devices': 'task',
        'category': '配置管理',
    },
    'configs.tasks.deploy_single_device_config': {
        'name': '单设备配置下发',
        'description': '向指定设备下发配置',
        'devices': 'single',
        'category': '配置管理',
    },
    'configs.tasks.deploy_batch_device_config': {
        'name': '批量配置下发',
        'description': '向多台设备批量下发配置',
        'devices': 'batch',
        'category': '配置管理',
    },
    'configs.tasks.execute_scheduled_backup': {
        'name': '执行定时配置备份',
        'description': '按备份计划触发配置预加载与备份流程',
        'devices': 'scheduled',
        'category': '配置管理',
    },
    'configs.tasks.preload_device_configs_task': {
        'name': '预加载设备配置',
        'description': '根据定时任务配置批量获取设备配置',
        'devices': 'scheduled',
        'category': '配置管理',
    },
    'configs.tasks.cleanup_old_config_results': {
        'name': '清理配置历史',
        'description': '清理 30 天前的配置任务结果',
        'devices': 'none',
        'category': '配置管理',
    },
    # 监控任务
    'monitoring.tasks.collect_device_metrics': {
        'name': '采集设备指标',
        'description': '采集指定设备的性能指标数据',
        'devices': 'single',
        'category': '性能监控',
    },
    'monitoring.tasks.collect_all_online_devices_metrics': {
        'name': '批量指标采集',
        'description': '采集所有在线设备的性能指标',
        'devices': 'online',
        'category': '性能监控',
    },
    'monitoring.tasks.collect_ap_devices_metrics': {
        'name': 'AP 设备指标采集',
        'description': '实时采集 AP 设备的性能指标',
        'devices': 'ap',
        'category': '性能监控',
    },
    'monitoring.tasks.cleanup_old_metrics': {
        'name': '清理监控数据',
        'description': '清理超过保留期限的监控数据',
        'devices': 'none',
        'category': '性能监控',
    },
    # 告警任务
    'alerts.tasks.check_device_status': {
        'name': '设备状态检查',
        'description': '检查设备状态并生成告警',
        'devices': 'all',
        'category': '告警管理',
    },
    'alerts.tasks.cleanup_old_alerts': {
        'name': '清理告警历史',
        'description': '清理 30 天前的已处理告警',
        'devices': 'none',
        'category': '告警管理',
    },
    'alerts.tasks.generate_alert_report': {
        'name': '生成告警报告',
        'description': '生成告警统计报告',
        'devices': 'none',
        'category': '告警管理',
    },
    # 日志任务
    'logs.tasks.collect_device_logs': {
        'name': '采集设备日志',
        'description': '采集单台设备的运行日志并写入系统',
        'devices': 'single',
        'category': '系统日志',
    },
    'logs.tasks.collect_all_online_devices_logs': {
        'name': '批量采集设备日志',
        'description': '采集所有在线设备的运行日志',
        'devices': 'online',
        'category': '系统日志',
    },
    'logs.tasks.generate_log_report': {
        'name': '生成日志报告',
        'description': '汇总指定时间范围内的日志统计信息',
        'devices': 'none',
        'category': '系统日志',
    },
    # 日志任务
    'logs.tasks.cleanup_old_logs': {
        'name': '清理系统日志',
        'description': '清理超过保留期限的系统日志',
        'devices': 'none',
        'category': '系统日志',
    },
    # 备份任务
    'backups.tasks.backup_all_devices': {
        'name': '备份全部设备配置',
        'description': '遍历全部设备并执行配置备份',
        'devices': 'all',
        'category': '配置备份',
    },
    'backups.tasks.backup_single_device': {
        'name': '备份单台设备配置',
        'description': '对指定设备执行配置备份',
        'devices': 'single',
        'category': '配置备份',
    },
    'backups.tasks.cleanup_old_backups': {
        'name': '清理历史备份',
        'description': '清理超过保留期限的配置备份文件',
        'devices': 'none',
        'category': '配置备份',
    },
    # IP 管理任务
    'ipmanagement.tasks.scan_subnet_task': {
        'name': '扫描网段任务',
        'description': '扫描指定网段中的存活主机并更新结果',
        'devices': 'subnet_task',
        'category': 'IP 管理',
    },
    'ipmanagement.tasks.enqueue_scan_task': {
        'name': '创建扫描任务',
        'description': '创建网段扫描记录并发起后台扫描',
        'devices': 'subnet',
        'category': 'IP 管理',
    },
    'ipmanagement.tasks.discover_subnets': {
        'name': '自动发现网段',
        'description': '扫描网络环境并自动发现新的网段配置',
        'devices': 'all_subnets',
        'category': 'IP 管理',
    },
    'ipmanagement.tasks.scan_all_subnets': {
        'name': '扫描全部网段',
        'description': '遍历所有启用网段并为其创建扫描任务',
        'devices': 'all_subnets',
        'category': 'IP 管理',
    },
    'ipmanagement.tasks.sync_scan_results_to_ipam': {
        'name': '同步扫描结果',
        'description': '将网段扫描结果同步到 IP 地址管理表',
        'devices': 'subnet_task',
        'category': 'IP 管理',
    },
    'ipmanagement.tasks.auto_discover_unmanaged_ips': {
        'name': '发现未纳管 IP',
        'description': '在指定网段中识别未纳入管理的 IP 地址',
        'devices': 'subnet',
        'category': 'IP 管理',
    },
    # 系统任务
    'network_management.celery.debug_task': {
        'name': '调试任务',
        'description': '用于验证 Celery 连通性和任务调度是否正常',
        'devices': 'none',
        'category': '系统任务',
    },
}


def get_task_metadata(func_name):
    """根据任务名返回统一的展示元数据"""
    if not func_name:
        return {
            'name': '未知任务',
            'description': '',
            'devices': 'unknown',
            'category': '其他任务',
            'queue_label': '其他任务 / 未知任务',
        }

    for key, info in TASK_DESCRIPTIONS.items():
        if key in func_name:
            category = info.get('category', '其他任务')
            return {
                'name': info['name'],
                'description': info.get('description', ''),
                'devices': info.get('devices', 'unknown'),
                'category': category,
                'queue_label': f"{category} / {info['name']}",
            }

    if '.' in func_name:
        default_name = func_name.split('.')[-1].replace('_', ' ').title()
    else:
        default_name = func_name.replace('_', ' ').title()

    return {
        'name': default_name,
        'description': '未配置任务说明',
        'devices': 'unknown',
        'category': '其他任务',
        'queue_label': f'其他任务 / {default_name}',
    }


# 默认的 crontab 任务列表（用于 stats.html）
DEFAULT_CRON_TASKS = [
    {
        'name': '设备在线检测',
        'func': 'devices.tasks.check_device_online',
        'description': '每60秒对所有设备进行ping检测',
        'schedule': '* * * * *',
        'interval_desc': '每分钟',
        'devices': 'all',
    },
    {
        'name': '定时设备发现',
        'func': 'devices.tasks.scheduled_device_discovery',
        'description': '每2小时基于LLDP发现新设备',
        'schedule': '0 */2 * * *',
        'interval_desc': '每2小时',
        'devices': 'online',
    },
    {
        'name': '配置定时备份',
        'func': 'configs.tasks.backup_all_devices_configs',
        'description': '每天凌晨2点备份所有设备配置',
        'schedule': '0 2 * * *',
        'interval_desc': '每天',
        'devices': 'all',
    },
    {
        'name': '告警状态检查',
        'func': 'alerts.tasks.check_device_status',
        'description': '每5分钟检查设备状态并生成告警',
        'schedule': '*/5 * * * *',
        'interval_desc': '每5分钟',
        'devices': 'all',
    },
    {
        'name': '告警历史清理',
        'func': 'alerts.tasks.cleanup_old_alerts',
        'description': '每天凌晨3点清理30天前的已处理告警',
        'schedule': '0 3 * * *',
        'interval_desc': '每天',
        'devices': 'none',
    },
    {
        'name': '监控数据采集',
        'func': 'monitoring.tasks.collect_all_online_devices_metrics',
        'description': '每5分钟采集所有在线设备的性能指标',
        'schedule': '*/5 * * * *',
        'interval_desc': '每5分钟',
        'devices': 'online',
    },
    {
        'name': '监控数据清理',
        'func': 'monitoring.tasks.cleanup_old_metrics',
        'description': '每天凌晨4点清理过期监控数据',
        'schedule': '0 4 * * *',
        'interval_desc': '每天',
        'devices': 'none',
    },
    {
        'name': '系统日志清理',
        'func': 'logs.tasks.cleanup_old_logs',
        'description': '每天凌晨5点清理过期日志',
        'schedule': '0 5 * * *',
        'interval_desc': '每天',
        'devices': 'none',
    },
]


@register.simple_tag
def get_default_cron_tasks():
    """获取默认的 crontab 任务列表"""
    return DEFAULT_CRON_TASKS


@register.filter
def get_status_badge_class(status):
    """根据状态获取徽章样式类"""
    if not status:
        return ''
    
    status_val = status.value if hasattr(status, 'value') else str(status).lower()
    
    mapping = {
        'queued': 'queued',
        'started': 'started',
        'finished': 'finished',
        'failed': 'failed',
        'scheduled': 'scheduled',
        'deferred': 'deferred',
    }
    
    return mapping.get(status_val, '')
