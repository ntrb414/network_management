"""
自定义异常处理

统一处理Django和REST framework异常，返回JSON格式错误响应。
"""

import logging
import traceback
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    自定义异常处理器

    捕获异常，记录日志，返回统一的JSON格式错误响应
    """
    # 调用REST framework默认的异常处理器
    response = exception_handler(exc, context)

    if response is not None:
        # 使用统一的错误格式
        error_response = {
            'success': False,
            'error': {
                'code': response.status_code,
                'message': _get_error_message(response.data),
                'details': response.data if isinstance(response.data, dict) else None,
            }
        }
        response.data = error_response
    else:
        # 处理未捕获的异常
        error_traceback = traceback.format_exc()
        logger.error(f"Unhandled exception: {exc}\n{error_traceback}")

        error_response = {
            'success': False,
            'error': {
                'code': 500,
                'message': 'Internal server error',
                'details': str(exc) if __debug__ else None,
            }
        }
        response = Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return response


def _get_error_message(data):
    """提取错误消息"""
    if isinstance(data, dict):
        # 遍历字典找到第一个错误消息
        for key, value in data.items():
            if isinstance(value, list) and value:
                return f"{key}: {value[0]}"
            elif isinstance(value, str):
                return f"{key}: {value}"
        return data.get('detail', str(data))
    elif isinstance(data, list) and data:
        return str(data[0])
    elif isinstance(data, str):
        return data
    return 'Unknown error'


class APIException(Exception):
    """自定义API异常基类"""

    def __init__(self, message, code=400, details=None):
        self.message = message
        self.code = code
        self.details = details
        super().__init__(message)

    def get_response(self):
        return Response({
            'success': False,
            'error': {
                'code': self.code,
                'message': self.message,
                'details': self.details,
            }
        }, status=self.code)


class ValidationError(APIException):
    """验证错误"""

    def __init__(self, message, details=None):
        super().__init__(message, code=400, details=details)


class AuthenticationFailed(APIException):
    """认证失败"""

    def __init__(self, message="Authentication failed"):
        super().__init__(message, code=401)


class PermissionDenied(APIException):
    """权限拒绝"""

    def __init__(self, message="Permission denied"):
        super().__init__(message, code=403)


class NotFound(APIException):
    """资源不存在"""

    def __init__(self, message="Resource not found"):
        super().__init__(message, code=404)


class ServiceUnavailable(APIException):
    """服务不可用"""

    def __init__(self, message="Service unavailable"):
        super().__init__(message, code=503)
