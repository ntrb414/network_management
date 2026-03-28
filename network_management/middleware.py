"""
自定义中间件
"""
import json
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


class APIDisallowRedirectMiddleware(MiddlewareMixin):
    """
    API请求禁止重定向中间件
    
    对于API请求，如果用户未认证，返回JSON错误响应而不是重定向到登录页面
    """
    
    def process_request(self, request):
        # 检查是否是API请求
        if request.path.startswith('/api/') or request.path.startswith('/ipmanagement/api/'):
            # 检查用户是否已认证
            if not request.user.is_authenticated:
                # 返回JSON格式的认证错误
                return JsonResponse({
                    'success': False,
                    'error': {
                        'code': 401,
                        'message': 'Authentication required',
                        'details': 'Please login to access this API'
                    }
                }, status=401)
        
        return None
    
    def process_response(self, request, response):
        # 对于API请求，确保返回JSON格式
        if (request.path.startswith('/api/') or request.path.startswith('/ipmanagement/api/')) and \
           hasattr(response, 'status_code') and response.status_code == 302:
            # 将302重定向转换为401 JSON响应
            return JsonResponse({
                'success': False,
                'error': {
                    'code': 401,
                    'message': 'Authentication required',
                    'details': 'Please login to access this API'
                }
            }, status=401)
        
        return response
