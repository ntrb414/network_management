"""
设备管理通用工具函数
"""

import subprocess
import re


# Ping configuration constants
PING_COUNT = 4
PING_TIMEOUT = 2  # seconds per packet
PING_COMMAND_TIMEOUT = PING_TIMEOUT * PING_COUNT + 5  # total timeout for subprocess

# Device online check constants (used in scheduled tasks)
DEVICE_CHECK_MAX_WORKERS = 50  # max concurrent ping workers


def ping_host(ip_address, count=4, timeout=2):
    """
    Ping主机并返回结果

    Args:
        ip_address: 目标IP地址或主机名
        count: Ping包数量，默认4
        timeout: 超时时间（秒），默认2

    Returns:
        dict: {'reachable': bool, 'latency': float or None, 'error': str or None}
    """
    try:
        cmd = ['/usr/bin/ping', '-c', str(count), '-W', str(timeout), ip_address]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout * count + 5
        )

        if result.returncode == 0:
            output = result.stdout.decode('utf-8')

            latency_pattern = r'(\d+\.?\d*)\s*avg'
            match = re.search(latency_pattern, output)

            if match:
                latency = float(match.group(1))
            else:
                latency = None

            return {
                'reachable': True,
                'latency': latency,
                'error': None,
            }
        else:
            stderr = result.stderr.decode('utf-8', errors='replace')
            return {
                'reachable': False,
                'latency': None,
                'error': stderr if stderr else f'Ping failed with code {result.returncode}',
            }

    except subprocess.TimeoutExpired:
        return {
            'reachable': False,
            'latency': None,
            'error': 'Timeout',
        }
    except FileNotFoundError:
        return {
            'reachable': False,
            'latency': None,
            'error': 'Ping command not found',
        }
    except Exception as e:
        return {
            'reachable': False,
            'latency': None,
            'error': str(e),
        }
