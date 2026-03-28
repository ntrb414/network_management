"""
IP Management Celery 异步任务
"""
import json
import logging

from celery import shared_task
from django.utils import timezone

from .models import IPScanTask, Subnet
from .services import IPScanService, IPAMService, NetworkDiscoveryService

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=2)
def scan_subnet_task(self, task_id: int):
    """异步扫描网段任务"""
    try:
        task = IPScanTask.objects.get(id=task_id)
    except IPScanTask.DoesNotExist:
        return

    task.status = 'running'
    task.scanned_ips = 0
    task.alive_ips = 0
    task.save()

    scanner = IPScanService()

    try:
        all_results = scanner.scan_subnet(task.cidr, return_all=True)
        alive_hosts = [result for result in all_results if result.get('alive')]

        if task.subnet:
            service = IPAMService()
            service.sync_scan_results(task.subnet_id, all_results)

        task.message = json.dumps(alive_hosts)
        task.status = 'completed'
        task.scanned_ips = task.total_ips
        task.alive_ips = len(alive_hosts)
        task.completed_at = timezone.now()
        task.save()

        return {
            'task_id': task_id,
            'cidr': task.cidr,
            'alive_count': len(alive_hosts),
            'alive_hosts': alive_hosts,
        }

    except Exception as e:
        task.status = 'failed'
        task.message = str(e)
        task.completed_at = timezone.now()
        task.save()
        raise


@shared_task(bind=True, max_retries=3)
def enqueue_scan_task(self, cidr: str, subnet_id: int = None) -> int:
    """将扫描任务加入队列"""
    import ipaddress

    network = ipaddress.ip_network(cidr, strict=False)
    total_ips = len(list(network.hosts()))

    task = IPScanTask.objects.create(
        subnet_id=subnet_id,
        cidr=cidr,
        status='pending',
        total_ips=total_ips,
        scanned_ips=0,
        alive_ips=0,
    )

    scan_subnet_task.delay(task.id)
    return task.id


@shared_task(bind=True, max_retries=3)
def discover_subnets(self):
    """自动发现网段任务"""
    discovery_service = NetworkDiscoveryService()
    discovered_subnets = discovery_service.discover_network_subnets()
    
    created_count = 0
    updated_count = 0
    
    for cidr in discovered_subnets:
        try:
            subnet, created = Subnet.objects.get_or_create(
                cidr=cidr,
                defaults={
                    'name': f'自动发现-{cidr}',
                    'source': 'auto',
                    'is_active': True,
                }
            )
            
            if created:
                created_count += 1
                logger.info(f"Auto-discovered new subnet: {cidr}")
            else:
                # 更新已存在的网段，确保启用
                if not subnet.is_active:
                    subnet.is_active = True
                    subnet.save()
                    updated_count += 1
                    logger.info(f"Activated existing subnet: {cidr}")
                    
        except Exception as e:
            logger.error(f"Failed to process subnet {cidr}: {e}")
    
    logger.info(f"Subnet discovery completed: {created_count} created, {updated_count} updated")
    return {
        'discovered_count': len(discovered_subnets),
        'created_count': created_count,
        'updated_count': updated_count,
    }


@shared_task(bind=True)
def scan_all_subnets(self):
    """定时扫描所有启用的网段"""
    subnets = Subnet.objects.filter(is_active=True)
    scanner = IPScanService()
    
    total_tasks = 0
    for subnet in subnets:
        try:
            task_id = enqueue_scan_task(subnet.cidr, subnet.id)
            total_tasks += 1
            logger.info(f"Queued scan for subnet {subnet.cidr}, task_id: {task_id}")
        except Exception as e:
            logger.error(f"Failed to queue scan for {subnet.cidr}: {e}")
    
    logger.info(f"Queued {total_tasks} subnet scans")
    return {
        'total_subnets': subnets.count(),
        'queued_tasks': total_tasks,
    }


@shared_task(bind=True)
def sync_scan_results_to_ipam(self, task_id: int):
    """将扫描结果同步到IPAM注册表"""
    try:
        task = IPScanTask.objects.get(id=task_id)
    except IPScanTask.DoesNotExist:
        return {'success': False, 'error': 'Task not found'}

    if not task.subnet:
        return {'success': False, 'error': 'Task not associated with subnet'}

    if not task.message:
        return {'success': False, 'error': 'No scan results found'}

    try:
        alive_hosts = json.loads(task.message)
    except json.JSONDecodeError:
        return {'success': False, 'error': 'Invalid scan results format'}

    service = IPAMService()
    result = service.sync_scan_results(task.subnet_id, alive_hosts)

    return result


@shared_task(bind=True)
def auto_discover_unmanaged_ips(self, subnet_id: int):
    """自动发现未管理的IP"""
    from .models import Subnet

    try:
        subnet = Subnet.objects.get(id=subnet_id)
    except Subnet.DoesNotExist:
        return {'success': False, 'error': 'Subnet not found'}

    scanner = IPScanService()
    all_results = scanner.scan_subnet(subnet.cidr, return_all=True)

    service = IPAMService()
    result = service.sync_scan_results(subnet_id, all_results)

    return result
