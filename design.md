# 设计文档

## 概述

网络管理工具是一个基于Django的Web应用系统，为网络工程师提供统一的网络设备管理平台。系统采用前后端分离架构，支持400台网络设备的管理和4个并发用户的访问。

### 核心功能模块

- **设备发现与管理**：自动发现网络设备，维护设备资产清单
- **配置管理**：基于模板的配置生成和批量下发
- **性能监控**：实时采集和展示设备性能指标
- **告警系统**：多级别告警生成和通知机制
- **拓扑可视化**：分层网络拓扑图展示和交互
- **日志分析**：日志收集、查询和统计分析
- **配置备份**：基于Git的配置版本控制
- **权限管理**：基于角色的访问控制（RBAC）

### 技术栈

- **后端框架**：Django 4.2+ (Python 3.10+)
- **数据库**：PostgreSQL 14+ (持久化存储)
- **缓存**：Redis 7+ (会话、缓存、任务队列)
- **任务队列**：Celery + Redis (异步任务处理)
- **前端**：HTML5 + JavaScript + Bootstrap 5 (简单直观的UI)
- **图形库**：Cytoscape.js (拓扑可视化)
- **版本控制**：GitPython (配置备份)
- **网络协议库**：Netmiko (SSH)、PySNMP (SNMP)、scapy (LLDP)

## 架构

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        用户浏览器                              │
│                    (HTML/JS/Bootstrap)                       │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/HTTPS
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                      Django Web Server                       │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │  设备管理  │  配置管理  │  监控模块  │  告警模块  │  拓扑模块  │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘  │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │  日志模块  │  备份模块  │  权限模块  │  审计模块  │  API层   │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘  │
└────────────┬────────────────────────────────────┬──────────┘
             │                                     │
             ▼                                     ▼
┌─────────────────────┐              ┌─────────────────────┐
│    PostgreSQL       │              │       Redis         │
│  (持久化数据存储)     │              │  (缓存/会话/队列)    │
└─────────────────────┘              └──────────┬──────────┘
                                                 │
                                                 ▼
                                     ┌─────────────────────┐
                                     │   Celery Workers    │
                                     │  (异步任务处理)      │
                                     └──────────┬──────────┘
                                                │
                                                ▼
                                     ┌─────────────────────┐
                                     │    网络设备层        │
                                     │ (SSH/SNMP/LLDP)     │
                                     └─────────────────────┘
```

### 分层架构

#### 1. 表现层 (Presentation Layer)
- 基于Bootstrap 5的响应式Web界面
- 使用Cytoscape.js实现拓扑图可视化
- 使用Chart.js或ECharts实现监控数据图表
- 通过AJAX与后端API交互

#### 2. 应用层 (Application Layer)
- Django Views处理HTTP请求
- Django REST Framework提供RESTful API
- 业务逻辑封装在Service层
- 使用Django ORM进行数据访问

#### 3. 任务层 (Task Layer)
- Celery异步任务处理设备发现、配置下发、监控采集
- Celery Beat定时任务调度器
- Redis作为消息代理和结果后端

#### 4. 数据层 (Data Layer)
- PostgreSQL存储设备信息、配置、日志、用户数据
- Redis缓存热点数据和会话信息
- Git仓库存储配置备份

#### 5. 网络层 (Network Layer)
- Netmiko库通过SSH连接设备
- PySNMP库通过SNMP协议采集监控数据
- scapy库实现LLDP协议发现

## 组件和接口

### Django应用模块划分

```
network_management/
├── devices/              # 设备管理应用
│   ├── models.py        # Device, DeviceType, Port等模型
│   ├── views.py         # 设备CRUD视图
│   ├── services.py      # 设备发现、状态检查服务
│   └── tasks.py         # Celery异步任务
├── configs/             # 配置管理应用
│   ├── models.py        # ConfigTemplate, ConfigTask等模型
│   ├── views.py         # 配置管理视图
│   ├── services.py      # 模板渲染、配置下发服务
│   └── tasks.py         # 配置下发异步任务
├── monitoring/          # 性能监控应用
│   ├── models.py        # MetricData模型
│   ├── views.py         # 监控数据展示视图
│   ├── services.py      # 数据采集服务
│   └── tasks.py         # 监控采集异步任务
├── alerts/              # 告警应用
│   ├── models.py        # Alert模型
│   ├── views.py         # 告警管理视图
│   ├── services.py      # 告警生成和通知服务
│   └── tasks.py         # 告警检查异步任务
├── topology/            # 拓扑应用
│   ├── models.py        # TopologyLink模型
│   ├── views.py         # 拓扑展示视图
│   ├── services.py      # 拓扑计算服务
│   └── tasks.py         # 拓扑发现异步任务
├── logs/                # 日志应用
│   ├── models.py        # SystemLog, OperationLog等模型
│   ├── views.py         # 日志查询视图
│   └── services.py      # 日志收集和分析服务
├── backups/             # 备份应用
│   ├── models.py        # ConfigBackup模型
│   ├── views.py         # 备份管理视图
│   ├── services.py      # Git操作服务
│   └── tasks.py         # 备份异步任务
└── accounts/            # 用户权限应用
    ├── models.py        # User, Role, Permission模型
    ├── views.py         # 用户管理视图
    └── middleware.py    # 权限检查中间件
```

### 核心组件接口

#### 1. 设备发现服务 (DeviceDiscoveryService)

```python
class DeviceDiscoveryService:
    def scan_ip_range(self, start_ip: str, end_ip: str) -> List[Device]:
        """扫描IP地址范围发现设备"""
        
    def discover_via_lldp(self, seed_device: Device) -> List[Device]:
        """通过LLDP协议发现相邻设备"""
        
    def add_device_manually(self, device_info: dict) -> Device:
        """手动添加设备"""
        
    def get_device_details(self, device: Device) -> dict:
        """获取设备详细信息（型号、端口、状态等）"""
```

#### 2. 配置管理服务 (ConfigManagementService)

```python
class ConfigManagementService:
    def render_template(self, template: ConfigTemplate, variables: dict) -> str:
        """使用Jinja2渲染配置模板"""
        
    def create_batch_task(self, devices: List[Device], template: ConfigTemplate, 
                         variables: dict) -> ConfigTask:
        """创建批量配置任务"""
        
    def deploy_config(self, device: Device, config: str) -> bool:
        """通过SSH下发配置到设备"""
        
    def get_current_config(self, device: Device) -> str:
        """获取设备当前配置"""
```

#### 3. 监控服务 (MonitoringService)

```python
class MonitoringService:
    def collect_metrics(self, device: Device) -> dict:
        """采集设备性能指标"""
        
    def store_metrics(self, device: Device, metrics: dict) -> None:
        """存储监控数据"""
        
    def get_metrics_history(self, device: Device, metric_name: str, 
                           duration: timedelta) -> List[MetricData]:
        """获取历史监控数据"""
        
    def check_thresholds(self, device: Device, metrics: dict) -> List[Alert]:
        """检查指标是否超过阈值"""
```

#### 4. 告警服务 (AlertService)

```python
class AlertService:
    def create_alert(self, device: Device, alert_type: str, 
                    severity: str, message: str) -> Alert:
        """创建告警"""
        
    def notify_users(self, alert: Alert) -> None:
        """通知用户（系统内弹窗）"""
        
    def acknowledge_alert(self, alert: Alert, user: User) -> None:
        """确认处理告警"""
        
    def ignore_alert(self, alert: Alert, user: User) -> None:
        """忽略告警"""
```

#### 5. 拓扑服务 (TopologyService)

```python
class TopologyService:
    def build_topology(self) -> dict:
        """构建网络拓扑数据结构"""
        
    def calculate_layout(self, topology: dict) -> dict:
        """计算分层布局（接入层、汇聚层、核心层）"""
        
    def export_topology_image(self, topology: dict, filename: str, 
                             format: str) -> str:
        """导出拓扑图为图片"""
        
    def detect_topology_changes(self) -> List[dict]:
        """检测拓扑变更"""
```

#### 6. 备份服务 (BackupService)

```python
class BackupService:
    def backup_device_config(self, device: Device, commit_message: str) -> bool:
        """备份设备配置到Git仓库"""
        
    def compare_versions(self, device: Device, version1: str, 
                        version2: str) -> dict:
        """对比两个版本的配置差异"""
        
    def get_backup_history(self, device: Device) -> List[dict]:
        """获取备份历史"""
```

### API接口设计

#### RESTful API端点

```
# 设备管理
GET    /api/devices/                    # 获取设备列表
POST   /api/devices/                    # 添加设备
GET    /api/devices/{id}/               # 获取设备详情
PUT    /api/devices/{id}/               # 更新设备信息
DELETE /api/devices/{id}/               # 删除设备
POST   /api/devices/discover/           # 触发设备发现
GET    /api/devices/export/             # 导出设备清单

# 配置管理
GET    /api/configs/templates/          # 获取配置模板列表
POST   /api/configs/templates/          # 创建配置模板
GET    /api/configs/templates/{id}/     # 获取模板详情
PUT    /api/configs/templates/{id}/     # 更新模板
DELETE /api/configs/templates/{id}/     # 删除模板
POST   /api/configs/tasks/              # 创建配置任务
POST   /api/configs/tasks/{id}/approve/ # 审批配置任务
POST   /api/configs/tasks/{id}/execute/ # 执行配置任务

# 监控
GET    /api/monitoring/devices/{id}/metrics/  # 获取设备监控数据
GET    /api/monitoring/devices/{id}/realtime/ # 获取实时监控数据

# 告警
GET    /api/alerts/                     # 获取告警列表
POST   /api/alerts/{id}/acknowledge/    # 确认告警
POST   /api/alerts/{id}/ignore/         # 忽略告警
GET    /api/alerts/statistics/          # 获取告警统计

# 拓扑
GET    /api/topology/                   # 获取拓扑数据
POST   /api/topology/export/            # 导出拓扑图

# 日志
GET    /api/logs/                       # 查询日志
GET    /api/logs/statistics/            # 日志统计

# 备份
GET    /api/backups/devices/{id}/       # 获取设备备份历史
POST   /api/backups/devices/{id}/       # 手动触发备份
GET    /api/backups/compare/            # 对比配置版本

# 用户权限
GET    /api/users/                      # 获取用户列表
POST   /api/users/                      # 创建用户
PUT    /api/users/{id}/permissions/     # 设置用户权限
GET    /api/audit/logs/                 # 获取审计日志
```

## 数据模型

### 核心数据模型

#### Device (设备)

```python
class Device(models.Model):
    DEVICE_TYPES = [
        ('router', '路由器'),
        ('switch', '交换机'),
        ('ap', 'AP'),
        ('ac', 'AC'),
    ]
    
    STATUS_CHOICES = [
        ('online', '在线'),
        ('offline', '下线'),
        ('fault', '故障'),
        ('preparing', '预备上线'),
    ]
    
    LAYER_CHOICES = [
        ('access', '接入层'),
        ('aggregation', '汇聚层'),
        ('core', '核心层'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES)
    model = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    layer = models.CharField(max_length=20, choices=LAYER_CHOICES, null=True)
    location = models.CharField(max_length=200, blank=True)
    ssh_port = models.IntegerField(default=22)
    ssh_username = models.CharField(max_length=50)
    ssh_password = models.CharField(max_length=200)  # 加密存储
    snmp_community = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(null=True)
```

#### Port (端口)

```python
class Port(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='ports')
    name = models.CharField(max_length=50)
    port_type = models.CharField(max_length=20)
    status = models.CharField(max_length=20)
    speed = models.CharField(max_length=20, blank=True)
    mac_address = models.CharField(max_length=17, blank=True)
```

#### ConfigTemplate (配置模板)

```python
class ConfigTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    device_types = models.JSONField()  # 适用的设备类型列表
    template_content = models.TextField()  # Jinja2模板内容
    variables_schema = models.JSONField()  # 变量定义
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

#### ConfigTask (配置任务)

```python
class ConfigTask(models.Model):
    STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已审批'),
        ('executing', '执行中'),
        ('completed', '已完成'),
        ('failed', '失败'),
    ]
    
    name = models.CharField(max_length=100)
    template = models.ForeignKey(ConfigTemplate, on_delete=models.CASCADE)
    devices = models.ManyToManyField(Device)
    variables = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_tasks')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True)
```

#### ConfigTaskResult (配置任务结果)

```python
class ConfigTaskResult(models.Model):
    task = models.ForeignKey(ConfigTask, on_delete=models.CASCADE, related_name='results')
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    success = models.BooleanField()
    config_content = models.TextField()
    error_message = models.TextField(blank=True)
    executed_at = models.DateTimeField(auto_now_add=True)
```

#### MetricData (监控数据)

```python
class MetricData(models.Model):
    METRIC_TYPES = [
        ('cpu', 'CPU使用率'),
        ('memory', '内存使用率'),
        ('traffic', '端口流量'),
        ('packet_loss', '丢包率'),
        ('connections', '连接数'),
    ]
    
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    metric_type = models.CharField(max_length=20, choices=METRIC_TYPES)
    metric_name = models.CharField(max_length=50)  # 如 "port_eth0_traffic"
    value = models.FloatField()
    unit = models.CharField(max_length=20)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['device', 'metric_type', 'timestamp']),
        ]
```

#### Alert (告警)

```python
class Alert(models.Model):
    SEVERITY_CHOICES = [
        ('critical', '紧急'),
        ('important', '重要'),
        ('normal', '一般'),
    ]
    
    ALERT_TYPES = [
        ('device_offline', '设备离线'),
        ('config_failed', '配置失败'),
        ('metric_abnormal', '指标异常'),
        ('topology_changed', '拓扑变更'),
    ]
    
    STATUS_CHOICES = [
        ('active', '活动'),
        ('acknowledged', '已确认'),
        ('ignored', '已忽略'),
    ]
    
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    handled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    handled_at = models.DateTimeField(null=True)
```

#### TopologyLink (拓扑链路)

```python
class TopologyLink(models.Model):
    source_device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='outgoing_links')
    source_port = models.ForeignKey(Port, on_delete=models.CASCADE, related_name='outgoing_links')
    target_device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='incoming_links')
    target_port = models.ForeignKey(Port, on_delete=models.CASCADE, related_name='incoming_links')
    link_status = models.CharField(max_length=20)
    discovered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

#### SystemLog (系统日志)

```python
class SystemLog(models.Model):
    LOG_TYPES = [
        ('alert', '告警日志'),
        ('system', '系统日志'),
        ('operation', '操作日志'),
    ]
    
    log_type = models.CharField(max_length=20, choices=LOG_TYPES)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    message = models.TextField()
    details = models.JSONField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['log_type', 'timestamp']),
        ]
```

#### ConfigBackup (配置备份)

```python
class ConfigBackup(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    config_content = models.TextField()
    git_commit_hash = models.CharField(max_length=40)
    commit_message = models.TextField()
    backed_up_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    backed_up_at = models.DateTimeField(auto_now_add=True)
```

#### User (用户) - 扩展Django User

```python
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', '管理员'),
        ('user', '普通用户'),
        ('readonly', '只读用户'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    permissions = models.JSONField(default=dict)  # 普通用户的细粒度权限
```

### 数据关系图

```
User ──┬─── ConfigTask (创建者)
       ├─── ConfigTask (审批者)
       ├─── Alert (处理者)
       ├─── SystemLog
       └─── ConfigBackup

Device ──┬─── Port
         ├─── MetricData
         ├─── Alert
         ├─── TopologyLink (源/目标)
         ├─── SystemLog
         ├─── ConfigBackup
         └─── ConfigTask (多对多)

ConfigTemplate ─── ConfigTask

ConfigTask ─── ConfigTaskResult ─── Device

TopologyLink ──┬─── Device (源/目标)
               └─── Port (源/目标)
```


## 错误处理

### 错误分类

#### 1. 网络连接错误
- **SSH连接失败**：设备不可达、认证失败、超时
- **SNMP查询失败**：社区字符串错误、设备不支持SNMP
- **处理策略**：重试3次（间隔5秒），失败后生成告警，记录日志

#### 2. 配置下发错误
- **配置语法错误**：模板渲染错误、变量缺失
- **设备拒绝配置**：配置冲突、权限不足
- **处理策略**：
  - 模板渲染阶段验证语法
  - 配置下发失败时跳过该设备，继续处理下一台
  - 生成告警并记录详细错误信息
  - 不自动回滚（需人工介入）

#### 3. 数据采集错误
- **监控数据采集失败**：设备无响应、指标不存在
- **处理策略**：记录空值或上次有效值，不中断采集流程

#### 4. 系统资源错误
- **数据库连接失败**：连接池耗尽、数据库宕机
- **Redis连接失败**：缓存服务不可用
- **处理策略**：
  - 数据库：使用连接池，配置重连机制
  - Redis：降级处理，直接访问数据库
  - 返回友好错误提示给用户

#### 5. 用户输入错误
- **无效的IP地址范围**：格式错误、范围过大
- **模板语法错误**：Jinja2语法不正确
- **处理策略**：前端和后端双重验证，返回具体错误信息

### 错误响应格式

```python
{
    "success": false,
    "error": {
        "code": "CONFIG_DEPLOY_FAILED",
        "message": "配置下发失败",
        "details": {
            "device": "switch-01",
            "reason": "SSH连接超时",
            "timestamp": "2024-01-15T10:30:00Z"
        }
    }
}
```

### 日志记录策略

- **ERROR级别**：系统错误、配置下发失败、设备连接失败
- **WARNING级别**：监控数据异常、告警生成
- **INFO级别**：用户操作、任务执行、设备状态变更
- **DEBUG级别**：详细的调试信息（仅开发环境）

### 异常恢复机制

1. **Celery任务失败重试**：自动重试机制，最多3次
2. **数据库事务回滚**：确保数据一致性
3. **配置备份**：每次配置变更前自动备份
4. **健康检查**：定期检查关键服务状态

## 测试策略

### 测试方法

本系统采用双重测试方法：

1. **单元测试**：验证具体示例、边缘情况和错误条件
   - 专注于特定示例和集成点
   - 测试边缘情况和错误处理
   - 避免过多单元测试，让属性测试覆盖大量输入

2. **属性测试**：验证跨所有输入的通用属性
   - 通过随机化实现全面的输入覆盖
   - 每个属性测试最少100次迭代
   - 每个测试必须引用设计文档中的属性
   - 标签格式：**Feature: network-management-tool, Property {number}: {property_text}**

### 测试框架

- **单元测试**：pytest + Django TestCase
- **属性测试**：Hypothesis (Python属性测试库)
- **集成测试**：pytest + Django Client
- **前端测试**：Jest (如需要)
- **性能测试**：Locust (负载测试)

### 测试覆盖范围

#### 单元测试重点
- 设备发现逻辑（IP扫描、LLDP解析）
- 配置模板渲染（Jinja2）
- 监控数据采集和存储
- 告警生成规则
- 拓扑计算算法
- 权限验证逻辑
- Git操作（备份、对比）

#### 属性测试重点
- 配置模板渲染的正确性
- 数据序列化/反序列化
- 权限检查的一致性
- 拓扑计算的不变性
- 日志查询的完整性

#### 集成测试重点
- API端点完整流程
- 用户认证和授权
- Celery任务执行
- 数据库事务
- 缓存一致性

### 测试数据

- **Mock设备**：使用模拟的网络设备进行测试
- **测试数据库**：独立的PostgreSQL测试数据库
- **测试Redis**：独立的Redis实例
- **测试Git仓库**：临时Git仓库

### 性能测试目标

- **并发用户**：支持4个并发用户，响应时间<2秒
- **设备规模**：支持400台设备，设备列表加载<3秒
- **监控数据**：实时监控数据延迟<5秒
- **配置下发**：批量下发100台设备配置<10分钟

### CI/CD集成

- 每次提交自动运行单元测试和属性测试
- 代码覆盖率目标：>80%
- 集成测试在合并前执行
- 性能测试定期执行（每周）


## 正确性属性

属性是系统所有有效执行中应该保持为真的特征或行为——本质上是关于系统应该做什么的形式化陈述。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。

### 属性1：IP范围扫描完整性

对于任意有效的IP地址范围，扫描发现的所有设备的IP地址都应当在指定的范围内。

**验证需求：1.1**

### 属性2：LLDP发现数据解析

对于任意LLDP响应数据，系统应当能够正确解析并提取设备信息（类型、型号、端口信息）。

**验证需求：1.2**

### 属性3：设备添加持久化

对于任意有效的设备信息，手动添加后，设备清单中应当包含该设备且信息完整。

**验证需求：1.3**

### 属性4：设备发现数据完整性

对于任意发现的设备，返回的数据应当包含设备类型、型号、IP地址、端口信息和运行状态这些必需字段。

**验证需求：1.4**

### 属性5：设备列表渲染完整性

对于任意设备列表，列表视图渲染结果应当包含每个设备的名称、状态和位置描述。

**验证需求：2.1**

### 属性6：设备统计计算正确性

对于任意设备数据集，计算出的统计数字、比例和百分比应当与实际数据一致（如在线设备数/总设备数 = 在线百分比）。

**验证需求：2.5**

### 属性7：设备筛选正确性

对于任意设备列表和筛选条件（类型或状态），筛选结果中的所有设备都应当满足筛选条件。

**验证需求：2.7, 2.8**

### 属性8：设备搜索匹配性

对于任意设备列表和搜索关键字，搜索结果中的所有设备的名称、IP地址或位置描述应当包含该关键字。

**验证需求：2.10**

### 属性9：设备导出往返一致性

对于任意设备列表，导出为JSON后再导入，应当得到等价的设备数据（序列化往返测试）。

**验证需求：2.12**

### 属性10：Excel导出格式正确性

对于任意设备列表，导出为Excel文件后，文件应当是有效的Excel格式且包含所有设备数据。

**验证需求：2.11**

### 属性11：设备配置获取非空性

对于任意在线设备，获取当前配置应当返回非空的配置内容。

**验证需求：3.1**

### 属性12：配置模板创建持久化

对于任意有效的配置模板数据，创建后，模板列表中应当包含该模板且内容完整。

**验证需求：3.4**

### 属性13：配置模板修改持久化

对于任意现有配置模板和修改内容，修改后，模板应当反映最新的修改内容。

**验证需求：3.5**

### 属性14：Jinja2模板渲染正确性

对于任意配置模板和变量字典，渲染后的配置内容应当包含所有变量的值且不包含未替换的模板标记。

**验证需求：3.6**

### 属性15：批量配置任务设备完整性

对于任意设备列表和配置模板，创建的批量配置任务应当包含所有选定的设备。

**验证需求：3.7**

### 属性16：配置任务初始状态

对于任意新创建的配置任务，其初始状态应当为"待审批"。

**验证需求：3.8**

### 属性17：配置下发执行

对于任意已审批的配置任务，执行后应当尝试连接所有目标设备并下发配置。

**验证需求：3.9**

### 属性18：配置失败告警生成

对于任意配置下发失败的设备，系统应当生成对应的告警记录。

**验证需求：3.10**

### 属性19：配置失败日志完整性

对于任意配置下发失败的情况，系统日志应当包含发生时间、设备名称和失败原因。

**验证需求：3.11**

### 属性20：批量配置容错性

对于任意包含多台设备的配置任务，即使某台设备配置失败，系统也应当继续处理剩余设备。

**验证需求：3.12**

### 属性21：监控数据类型完整性

对于任意设备的监控数据采集，应当包含端口流量、丢包率、连接数、内存使用率和CPU使用率这些指标类型。

**验证需求：4.1**

### 属性22：监控数据保留期限

对于任意监控数据，超过24小时的数据应当被清理，24小时内的数据应当保留。

**验证需求：4.6**

### 属性23：设备离线告警生成

对于任意设备状态从在线变为离线，系统应当生成设备离线告警。

**验证需求：5.1**

### 属性24：配置失败告警生成

对于任意配置下发失败事件，系统应当生成配置失败告警。

**验证需求：5.2**

### 属性25：指标异常告警生成

对于任意监控指标超过预设阈值，系统应当生成指标异常告警。

**验证需求：5.3**

### 属性26：拓扑变更告警生成

对于任意拓扑结构变化（设备或链路增删），系统应当生成拓扑变更告警。

**验证需求：5.4**

### 属性27：告警优先级有效性

对于任意生成的告警，其优先级应当是"紧急"、"重要"或"一般"之一。

**验证需求：5.5**

### 属性28：告警状态转换正确性

对于任意活动状态的告警，当用户确认或忽略后，告警状态应当相应变更为"已确认"或"已忽略"，且不再触发新通知。

**验证需求：5.7, 5.8**

### 属性29：告警统计准确性

对于任意告警数据集和统计维度（按类型、优先级、时间段），统计结果应当与实际数据一致。

**验证需求：5.10**

### 属性30：拓扑数据结构完整性

对于任意网络拓扑，拓扑数据应当包含所有设备节点、设备间的连接关系、链路状态和设备IP地址。

**验证需求：6.1**

### 属性31：拓扑分层布局正确性

对于任意网络拓扑，分层布局算法应当将所有设备分配到接入层、汇聚层或核心层之一。

**验证需求：6.3, 6.4**

### 属性32：拓扑融合层级减少

对于任意分层拓扑，执行融合操作后，汇聚层和核心层应当合并为一层，总层级数应当减少。

**验证需求：6.5**

### 属性33：设备状态颜色映射

对于任意设备节点，其显示颜色应当与设备状态一致：离线为灰色，在线为绿色，有告警为红色。

**验证需求：6.6, 6.7, 6.8**

### 属性34：拓扑图导出文件有效性

对于任意拓扑图和文件名，导出的文件应当是有效的PNG或JPG格式且保存在指定路径。

**验证需求：6.12**

### 属性35：日志收集类型完整性

对于任意时间段的日志收集，应当包含告警日志、系统日志和操作日志这三种类型。

**验证需求：7.1**

### 属性36：日志关键字搜索准确性

对于任意日志集合和搜索关键字，搜索结果中的所有日志记录都应当包含该关键字。

**验证需求：7.2**

### 属性37：日志时间范围筛选准确性

对于任意日志集合和时间范围，筛选结果中的所有日志记录的时间戳都应当在指定范围内。

**验证需求：7.3**

### 属性38：日志保留期限

对于任意日志记录，超过7天的日志应当被清理，7天内的日志应当保留。

**验证需求：7.6**

### 属性39：配置备份Git存储

对于任意设备配置备份操作，应当在Git仓库中创建新的commit，且commit包含该设备的配置文件。

**验证需求：8.2, 8.3**

### 属性40：配置版本对比差异显示

对于任意设备的两个不同配置版本，对比结果应当显示两个版本之间的具体差异（增加、删除、修改的行）。

**验证需求：8.5, 8.6**

### 属性41：配置备份保留期限

对于任意配置备份记录，超过30天的备份应当被清理，30天内的备份应当保留。

**验证需求：8.7**

### 属性42：用户角色有效性

对于任意用户，其角色应当是"管理员"、"普通用户"或"只读用户"之一。

**验证需求：9.1**

### 属性43：管理员权限完整性

对于任意管理员用户和任意系统操作，权限检查应当返回允许。

**验证需求：9.2**

### 属性44：只读用户权限限制

对于任意只读用户和任意修改操作（创建、更新、删除），权限检查应当返回拒绝。

**验证需求：9.3**

### 属性45：权限授予持久化

对于任意普通用户和授予的权限，权限设置后，该用户的权限记录应当包含新授予的权限。

**验证需求：9.4**

### 属性46：权限检查一致性

对于任意普通用户和操作，如果用户拥有该操作权限则允许执行，否则拒绝并提示权限不足。

**验证需求：9.5, 9.6**

### 属性47：操作审计日志完整性

对于任意用户操作，审计日志应当包含操作时间、操作内容和执行用户的身份信息。

**验证需求：10.1, 10.2**

