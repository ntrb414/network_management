"""
网络连接工具

提供网络连接重试机制和错误处理。
"""

import logging
import time
from functools import wraps
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


class NetworkError(Exception):
    """网络连接错误"""

    def __init__(self, message, device=None, retry_count=0):
        self.message = message
        self.device = device
        self.retry_count = retry_count
        super().__init__(message)


def retry_on_network_error(
    max_retries: int = 3,
    delay: float = 5.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    网络连接重试装饰器

    Args:
        max_retries: 最大重试次数
        delay: 初始延迟（秒）
        backoff: 延迟倍数
        exceptions: 需要重试的异常类型

    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retrying in {current_delay}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )

            raise last_exception

        return wrapper
    return decorator


def validate_ip_address(ip: str) -> bool:
    """
    验证IP地址格式

    Args:
        ip: IP地址字符串

    Returns:
        是否有效
    """
    import ipaddress
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def validate_port(port: int) -> bool:
    """
    验证端口号

    Args:
        port: 端口号

    Returns:
        是否有效
    """
    return 1 <= port <= 65535


def validate_hostname(hostname: str) -> bool:
    """
    验证主机名格式

    Args:
        hostname: 主机名字符串

    Returns:
        是否有效
    """
    import re
    # 简单的主机名验证
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
    return bool(re.match(pattern, hostname))


class ConnectionPool:
    """连接池管理器"""

    def __init__(self, max_connections: int = 10):
        self.max_connections = max_connections
        self.connections = {}
        self.locks = {}

    def get_connection(self, key: str):
        """获取连接"""
        if key not in self.connections:
            self.connections[key] = None
        return self.connections.get(key)

    def set_connection(self, key: str, connection: Any):
        """设置连接"""
        self.connections[key] = connection

    def close_connection(self, key: str):
        """关闭连接"""
        if key in self.connections:
            conn = self.connections.pop(key)
            if conn:
                try:
                    conn.close()
                except (OSError, IOError, Exception) as e:
                    logger.debug(f"关闭连接时发生错误: {e}")

    def close_all(self):
        """关闭所有连接"""
        for key in list(self.connections.keys()):
            self.close_connection(key)
