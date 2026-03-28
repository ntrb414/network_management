# 首页与功能页面分离 - 实现任务列表

## 任务概览

本任务列表包含实现首页与功能页面分离所需的所有任务，共分为5个阶段：
1. 基础设施准备（任务1-3）
2. 首页实现（任务4-6）
3. 功能页面路由分离（任务7-10）
4. 权限控制实现（任务11-13）
5. 测试与优化（任务14-15）

---

## 第一阶段：基础设施准备

### 任务1：创建homepage应用
- [x] 1.1 使用 `python manage.py startapp homepage` 创建新应用
- [x] 1.2 在 `settings.py` 的 `INSTALLED_APPS` 中添加 `'homepage.apps.HomepageConfig'`
- [x] 1.3 创建 `homepage/templates/` 目录结构
- [x] 1.4 创建 `homepage/static/` 目录结构
- [x] 1.5 验证应用已正确注册

### 任务2：创建基础模板和静态文件
- [x] 2.1 创建 `templates/base.html` 基础模板，包含导航栏、用户信息、登出按钮
- [x] 2.2 创建 `templates/homepage/homepage.html` 首页模板，展示功能模块按钮网格
- [x] 2.3 创建 `static/css/homepage.css` 首页样式文件
- [x] 2.4 创建 `static/css/base.css` 基础样式文件
- [x] 2.5 创建 `static/js/homepage.js` 首页交互脚本
- [x] 2.6 验证静态文件能正确加载

### 任务3：修改主URL配置
- [x] 3.1 修改 `network_management/urls.py`，添加首页路由 `path('', include('homepage.urls'))`
- [x] 3.2 修改 `network_management/urls.py`，添加功能页面路由（devices, configs等）
- [x] 3.3 确保API路由保持在 `/api/` 下
- [x] 3.4 确保admin路由保持在 `/admin/` 下
- [x] 3.5 验证URL配置无冲突

---

## 第二阶段：首页实现

### 任务4：实现首页视图
- [x] 4.1 在 `homepage/views.py` 中创建 `HomepageView` 类视图
- [x] 4.2 实现 `get_context_data()` 方法，返回功能模块列表
- [x] 4.3 实现 `get_available_modules()` 方法，根据用户权限过滤模块
- [x] 4.4 添加登录检查装饰器，未登录用户重定向到登录页
- [x] 4.5 测试首页视图能正确渲染

### 任务5：实现登录和登出视图
- [x] 5.1 在 `homepage/views.py` 中创建 `LoginView` 类视图
- [x] 5.2 在 `homepage/views.py` 中创建 `LogoutView` 类视图
- [x] 5.3 创建 `templates/homepage/login.html` 登录模板
- [x] 5.4 实现登录表单验证和用户认证
- [x] 5.5 实现登出功能，清除会话

### 任务6：创建首页URL配置
- [x] 6.1 创建 `homepage/urls.py` 文件
- [x] 6.2 添加首页路由 `path('', HomepageView.as_view(), name='homepage')`
- [x] 6.3 添加登录路由 `path('login/', LoginView.as_view(), name='login')`
- [x] 6.4 添加登出路由 `path('logout/', LogoutView.as_view(), name='logout')`
- [x] 6.5 验证所有路由能正确工作

---

## 第三阶段：功能页面路由分离

### 任务7：分离设备管理页面
- [x] 7.1 在 `devices/views.py` 中创建 `DeviceListView` 页面视图
- [x] 7.2 在 `devices/views.py` 中创建 `DeviceDetailView` 页面视图
- [x] 7.3 创建 `devices/templates/devices/device_list.html` 模板
- [x] 7.4 创建 `devices/templates/devices/device_detail.html` 模板
- [x] 7.5 创建 `devices/urls.py` 定义功能页面路由
- [x] 7.6 验证设备管理页面能从首页访问

### 任务8：分离其他功能页面（配置、监控、告警、拓扑、日志、备份）
- [x] 8.1 为 `configs` 应用创建页面视图和模板
- [x] 8.2 为 `monitoring` 应用创建页面视图和模板
- [x] 8.3 为 `alerts` 应用创建页面视图和模板
- [x] 8.4 为 `topology` 应用创建页面视图和模板
- [x] 8.5 为 `logs` 应用创建页面视图和模板
- [x] 8.6 为 `backups` 应用创建页面视图和模板
- [x] 8.7 为 `accounts` 应用创建页面视图和模板

### 任务9：从Django admin中移除功能页面注册
- [x] 9.1 检查 `devices/admin.py`，移除功能模型的admin注册
- [x] 9.2 检查 `configs/admin.py`，移除功能模型的admin注册
- [x] 9.3 检查 `monitoring/admin.py`，移除功能模型的admin注册
- [x] 9.4 检查 `alerts/admin.py`，移除功能模型的admin注册
- [x] 9.5 检查 `topology/admin.py`，移除功能模型的admin注册
- [x] 9.6 检查 `logs/admin.py`，移除功能模型的admin注册
- [x] 9.7 检查 `backups/admin.py`，移除功能模型的admin注册
- [x] 9.8 验证admin后台不再显示功能页面

### 任务10：创建功能页面返回首页链接
- [x] 10.1 在所有功能页面模板中添加"返回首页"链接
- [x] 10.2 在所有功能页面模板中添加导航栏，显示当前用户和权限
- [x] 10.3 在所有功能页面模板中添加登出按钮
- [-] 10.4 验证用户能从功能页面返回首页

---

## 第四阶段：权限控制实现

### 任务11：创建权限检查装饰器
- [x] 11.1 在 `accounts/decorators.py` 中创建 `permission_required` 装饰器
- [x] 11.2 实现权限检查逻辑，检查用户是否有权限访问页面
- [x] 11.3 如果无权限，返回403错误或弹窗提示
- [x] 11.4 支持多个权限的检查（AND/OR逻辑）
- [ ] 11.5 测试装饰器能正确工作

### 任务12：为功能页面添加权限检查
- [x] 12.1 为 `DeviceListView` 添加 `@permission_required('devices.view')` 装饰器
- [x] 12.2 为 `ConfigListView` 添加 `@permission_required('configs.view')` 装饰器
- [x] 12.3 为 `MonitoringView` 添加 `@permission_required('monitoring.view')` 装饰器
- [x] 12.4 为 `AlertListView` 添加 `@permission_required('alerts.view')` 装饰器
- [x] 12.5 为 `TopologyView` 添加 `@permission_required('topology.view')` 装饰器
- [x] 12.6 为 `LogListView` 添加 `@permission_required('logs.view')` 装饰器
- [x] 12.7 为 `BackupListView` 添加 `@permission_required('backups.view')` 装饰器
- [x] 12.8 为 `AccountListView` 添加 `@permission_required('accounts.view')` 装饰器

### 任务13：创建权限不足错误页面
- [x] 13.1 创建 `templates/errors/permission_denied.html` 模板
- [x] 13.2 创建 `templates/errors/404.html` 模板
- [x] 13.3 在 `network_management/urls.py` 中配置错误处理视图
- [x] 13.4 实现权限不足时的弹窗提示和返回首页功能
- [ ] 13.5 测试权限不足错误页面能正确显示

---

## 第五阶段：测试与优化

### 任务14：单元测试
- [ ] 14.1 为 `HomepageView` 编写单元测试
- [ ] 14.2 为登录/登出视图编写单元测试
- [ ] 14.3 为权限检查装饰器编写单元测试
- [ ] 14.4 为功能页面视图编写单元测试
- [ ] 14.5 运行所有单元测试，确保通过

### 任务15：集成测试和性能优化
- [ ] 15.1 编写集成测试，验证首页到功能页面的完整流程
- [ ] 15.2 编写集成测试，验证权限检查的正确性
- [ ] 15.3 优化首页模块列表查询，使用缓存减少数据库查询
- [ ] 15.4 优化权限检查，使用缓存避免重复查询
- [ ] 15.5 运行性能测试，确保支持4个并发用户
- [ ] 15.6 验证所有功能正常工作，无回归问题

---

## 验收标准

### 功能验收标准
- ✓ 用户访问 `/` 时显示首页，展示所有8个功能模块按钮
- ✓ 用户点击功能按钮时导航到对应功能页面（如 `/devices/`）
- ✓ 功能页面不在Django admin中显示
- ✓ 用户无权限时显示权限不足提示，可返回首页
- ✓ 用户有权限时能正常访问功能页面
- ✓ 管理员仍能访问Django admin后台

### 性能验收标准
- ✓ 首页加载时间 < 1秒
- ✓ 功能页面加载时间 < 2秒
- ✓ 支持4个并发用户同时访问
- ✓ 支持400台设备的数据处理

### 测试覆盖率
- ✓ 单元测试覆盖率 > 80%
- ✓ 集成测试覆盖所有主要流程
- ✓ 无回归问题
