# 设备配置查看功能重构规格文档

## 1. 概述

### 1.1 背景
当前设备配置查看功能存在以下问题：
- **完全黑屏**：页面加载后显示完全黑屏，无法查看配置内容
- **缓存过期**：显示的配置内容与设备实际配置不一致，Redis缓存未及时更新
- **获取缓慢**：从设备获取配置需要5-15秒，用户体验差
- **定时任务固定**：后台预加载任务间隔固定，无法根据需求灵活调整

### 1.2 目标
重构配置查看功能，解决现有问题，提升用户体验，扩展设备厂商支持，**将配置获取时间优化至5秒以内**，**支持用户自定义定时任务配置**。

---

## 2. 功能需求

### 2.1 核心功能

| 功能 | 描述 |
|------|------|
| 配置显示 | 左右双栏布局，左侧显示运行配置，右侧显示启动配置 |
| 缓存读取 | 默认从Redis读取缓存的配置内容 |
| 刷新缓存 | 提供"刷新"按钮，从Redis重新读取配置 |
| 实时读取 | 提供"实时读取"按钮，直接通过SSH从设备获取最新配置 |
| 搜索功能 | 支持关键字搜索并高亮匹配内容 |
| 配置导出 | 支持下载配置为文本文件 |
| 定时任务配置 | 用户可自定义后台配置获取任务的执行间隔和时间 |

### 2.2 设备厂商支持

| 厂商 | 配置命令 |
|------|----------|
| 华为 | `display current-configuration` / `display saved-configuration` |
| 华三(H3C) | `display current-configuration` / `display saved-configuration` |

**厂商识别规则**：根据`device_type`字段推断厂商（无需新增数据库字段）

### 2.3 操作流程

```
┌─────────────────────────────────────────────────────────────┐
│                      配置查看页面                            │
├─────────────────────────────────────────────────────────────┤
│  [设备选择下拉框]           [刷新] [实时读取]               │
├──────────────────────┬──────────────────────────────────────┤
│     运行配置         │           启动配置                   │
│  ┌────────────────┐  │  ┌────────────────────────────────┐  │
│  │                │  │  │                                │  │
│  │  配置内容      │  │  │    配置内容                    │  │
│  │  (搜索高亮)    │  │  │    (搜索高亮)                  │  │
│  │                │  │  │                                │  │
│  └────────────────┘  │  └────────────────────────────────┘  │
│  [下载]              │  [下载]                              │
└──────────────────────┴──────────────────────────────────────┘
```

---

## 3. 定时任务配置功能

### 3.1 功能概述

用户可在管理界面配置后台配置获取任务的执行计划，包括：
- **执行间隔**：每隔多长时间执行一次
- **执行时间**：每天固定时间执行
- **任务开关**：启用/禁用任务
- **目标设备**：可选择全部设备或指定设备

### 3.2 配置选项

| 配置项 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| 任务名称 | 文本 | 定时任务名称 | "设备配置预加载" |
| 执行模式 | 选择 | 间隔执行 / 定时执行 | 间隔执行 |
| 执行间隔 | 数字+单位 | 间隔执行的频率 | 每30分钟 |
| 执行时间 | 时间选择 | 定时执行的时间点 | 每天 02:00 |
| 启用状态 | 开关 | 任务是否启用 | 启用 |
| 目标设备 | 多选 | 全部设备 / 指定设备 | 全部在线设备 |
| 任务队列 | 选择 | 执行队列优先级 | low / normal / high |

### 3.3 执行模式说明

#### 模式一：间隔执行
```
┌─────────────────────────────────────────┐
│  执行模式: [间隔执行 ▼]                  │
│                                         │
│  执行间隔: [30] [分钟 ▼]                 │
│  (可选值: 5分钟/10分钟/30分钟/1小时/6小时)│
│                                         │
│  首次执行: [立即] / [指定时间: ____]     │
└─────────────────────────────────────────┘

执行时间线:
|--|----|----|----|----|----|----|
   0   30   60   90  120  150  180 (分钟)
   ↑    ↑    ↑    ↑    ↑    ↑
  执行 执行 执行 执行 执行 执行
```

#### 模式二：定时执行
```
┌─────────────────────────────────────────┐
│  执行模式: [定时执行 ▼]                  │
│                                         │
│  执行时间: [02:00]                       │
│  执行日期: [每天 ▼]                      │
│  (可选: 每天/工作日/周末/指定星期)        │
│                                         │
│  下次执行: 2026-03-22 02:00:00          │
└─────────────────────────────────────────┘

执行时间线:
|--|----|----|----|----|----|----|
  Day1 Day2 Day3 Day4 Day5 Day6 Day7
   ↑         ↑         ↑
  02:00    02:00    02:00
  执行      执行      执行
```

### 3.4 数据模型

```python
# configs/models.py

class ConfigFetchSchedule(models.Model):
    """配置获取定时任务配置"""
    
    EXEC_MODE_CHOICES = [
        ('interval', '间隔执行'),
        ('cron', '定时执行'),
    ]
    
    INTERVAL_CHOICES = [
        (300, '每5分钟'),
        (600, '每10分钟'),
        (1800, '每30分钟'),
        (3600, '每1小时'),
        (21600, '每6小时'),
        (43200, '每12小时'),
        (86400, '每24小时'),
    ]
    
    DAY_CHOICES = [
        ('*', '每天'),
        ('1-5', '工作日'),
        ('0,6', '周末'),
        ('0', '周日'),
        ('1', '周一'),
        ('2', '周二'),
        ('3', '周三'),
        ('4', '周四'),
        ('5', '周五'),
        ('6', '周六'),
    ]
    
    QUEUE_CHOICES = [
        ('low', '低优先级'),
        ('normal', '普通优先级'),
        ('high', '高优先级'),
    ]
    
    # 基本信息
    name = models.CharField('任务名称', max_length=100, default='设备配置预加载')
    enabled = models.BooleanField('是否启用', default=True)
    
    # 执行模式
    exec_mode = models.CharField('执行模式', max_length=20, choices=EXEC_MODE_CHOICES, default='interval')
    
    # 间隔执行配置
    interval_seconds = models.IntegerField('执行间隔(秒)', choices=INTERVAL_CHOICES, default=1800)
    
    # 定时执行配置
    exec_time = models.TimeField('执行时间', default=time(2, 0))
    exec_days = models.CharField('执行日期', max_length=20, default='*')
    
    # 目标配置
    target_devices = models.ManyToManyField('devices.Device', blank=True, verbose_name='目标设备')
    target_all_devices = models.BooleanField('全部设备', default=True)
    only_online_devices = models.BooleanField('仅在线设备', default=True)
    
    # 任务配置
    queue = models.CharField('任务队列', max_length=20, choices=QUEUE_CHOICES, default='low')
    max_concurrent = models.IntegerField('最大并发数', default=5)
    
    # 元数据
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, verbose_name='创建者')
    
    # 执行统计
    last_run_time = models.DateTimeField('上次执行时间', null=True, blank=True)
    last_run_status = models.CharField('上次执行状态', max_length=20, blank=True)
    total_run_count = models.IntegerField('总执行次数', default=0)
    
    class Meta:
        db_table = 'config_fetch_schedule'
        verbose_name = '配置获取定时任务'
        verbose_name_plural = '配置获取定时任务'
    
    def __str__(self):
        return self.name
    
    def get_celery_schedule(self):
        """生成Celery Beat调度配置"""
        if self.exec_mode == 'interval':
            return self._get_interval_schedule()
        else:
            return self._get_cron_schedule()
    
    def _get_interval_schedule(self):
        """生成间隔调度"""
        from celery.schedules import schedule
        return schedule(run_every=self.interval_seconds)
    
    def _get_cron_schedule(self):
        """生成Cron调度"""
        from celery.schedules import crontab
        hour = self.exec_time.hour
        minute = self.exec_time.minute
        day_of_week = self.exec_days
        return crontab(hour=hour, minute=minute, day_of_week=day_of_week)


class ConfigFetchLog(models.Model):
    """配置获取执行日志"""
    
    STATUS_CHOICES = [
        ('running', '执行中'),
        ('success', '成功'),
        ('partial', '部分成功'),
        ('failed', '失败'),
    ]
    
    schedule = models.ForeignKey(ConfigFetchSchedule, on_delete=models.CASCADE, related_name='logs', verbose_name='定时任务')
    start_time = models.DateTimeField('开始时间', auto_now_add=True)
    end_time = models.DateTimeField('结束时间', null=True, blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='running')
    
    # 执行结果
    total_devices = models.IntegerField('设备总数', default=0)
    success_count = models.IntegerField('成功数', default=0)
    failed_count = models.IntegerField('失败数', default=0)
    
    # 详细信息
    error_message = models.TextField('错误信息', blank=True)
    result_detail = models.JSONField('执行详情', default=dict, blank=True)
    
    class Meta:
        db_table = 'config_fetch_log'
        verbose_name = '配置获取日志'
        verbose_name_plural = '配置获取日志'
        ordering = ['-start_time']
```

### 3.5 动态调度实现

```python
# configs/scheduler.py

from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
import json

class DynamicScheduler:
    """动态调度管理器"""
    
    @staticmethod
    def sync_schedule(schedule_config: ConfigFetchSchedule):
        """同步定时任务配置到Celery Beat"""
        task_name = f'config_fetch_{schedule_config.id}'
        
        # 删除旧任务
        PeriodicTask.objects.filter(name=task_name).delete()
        
        if not schedule_config.enabled:
            return
        
        # 创建新任务
        if schedule_config.exec_mode == 'interval':
            # 间隔执行
            interval, _ = IntervalSchedule.objects.get_or_create(
                every=schedule_config.interval_seconds,
                period=IntervalSchedule.SECONDS,
            )
            PeriodicTask.objects.create(
                name=task_name,
                task='configs.tasks.preload_device_configs',
                interval=interval,
                enabled=True,
                kwargs=json.dumps({
                    'schedule_id': schedule_config.id,
                }),
                queue=schedule_config.queue,
            )
        else:
            # 定时执行
            cron, _ = CrontabSchedule.objects.get_or_create(
                minute=schedule_config.exec_time.minute,
                hour=schedule_config.exec_time.hour,
                day_of_week=schedule_config.exec_days,
                day_of_month='*',
                month_of_year='*',
            )
            PeriodicTask.objects.create(
                name=task_name,
                task='configs.tasks.preload_device_configs',
                crontab=cron,
                enabled=True,
                kwargs=json.dumps({
                    'schedule_id': schedule_config.id,
                }),
                queue=schedule_config.queue,
            )
    
    @staticmethod
    def remove_schedule(schedule_id: int):
        """移除定时任务"""
        task_name = f'config_fetch_{schedule_id}'
        PeriodicTask.objects.filter(name=task_name).delete()
```

### 3.6 前端UI设计

#### 定时任务配置列表页
```
┌─────────────────────────────────────────────────────────────────────┐
│  定时任务配置                                    [+ 新建任务]        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 任务名称          │ 执行计划      │ 状态  │ 上次执行 │ 操作  │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │ 设备配置预加载    │ 每30分钟      │ 🟢 启用│ 10:30   │ 编辑 删除│ │
│  │ 每日配置备份      │ 每天 02:00    │ 🟢 启用│ 昨天    │ 编辑 删除│ │
│  │ 高优先级设备刷新  │ 每10分钟      │ 🔴 禁用│ -       │ 编辑 删除│ │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### 定时任务编辑页
```
┌─────────────────────────────────────────────────────────────────────┐
│  编辑定时任务                                                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  基本信息                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 任务名称:  [设备配置预加载                          ]        │   │
│  │ 启用状态:  [🟢 启用]                                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  执行计划                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 执行模式:  ○ 间隔执行  ○ 定时执行                            │   │
│  │                                                               │   │
│  │ [间隔执行模式]                                                │   │
│  │ 执行间隔:  [每30分钟 ▼]                                       │   │
│  │                                                               │   │
│  │ [定时执行模式]                                                │   │
│  │ 执行时间:  [02:00]                                            │   │
│  │ 执行日期:  [每天 ▼]                                           │   │
│  │ 下次执行:  2026-03-22 02:00:00                                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  目标设备                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 目标范围:  ○ 全部设备  ○ 指定设备                             │   │
│  │ 仅在线设备: [✓]                                               │   │
│  │                                                               │   │
│  │ [指定设备时显示设备列表]                                       │   │
│  │ ☑ SW-01 (192.168.1.1)                                        │   │
│  │ ☑ SW-02 (192.168.1.2)                                        │   │
│  │ ☐ RT-01 (192.168.1.254)                                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  任务配置                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 任务队列:  [低优先级 ▼]                                       │   │
│  │ 最大并发:  [5] 个设备同时执行                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  执行历史                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 时间              │ 状态   │ 成功/总数 │ 耗时    │ 详情      │   │
│  │ 2026-03-21 10:30  │ 🟢 成功│ 15/15    │ 45秒    │ [查看]    │   │
│  │ 2026-03-21 10:00  │ 🟢 成功│ 14/15    │ 42秒    │ [查看]    │   │
│  │ 2026-03-21 09:30  │ 🟡 部分│ 12/15    │ 38秒    │ [查看]    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│                              [取消]  [保存]                         │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.7 API设计

#### 获取定时任务列表
```
GET /configs/api/schedules/

Response:
{
    "schedules": [
        {
            "id": 1,
            "name": "设备配置预加载",
            "enabled": true,
            "exec_mode": "interval",
            "exec_plan": "每30分钟",
            "last_run_time": "2026-03-21T10:30:00Z",
            "last_run_status": "success",
            "next_run_time": "2026-03-21T11:00:00Z"
        }
    ]
}
```

#### 创建/更新定时任务
```
POST /configs/api/schedules/
PUT /configs/api/schedules/{id}/

Request:
{
    "name": "设备配置预加载",
    "enabled": true,
    "exec_mode": "interval",
    "interval_seconds": 1800,
    "exec_time": null,
    "exec_days": "*",
    "target_all_devices": true,
    "only_online_devices": true,
    "queue": "low",
    "max_concurrent": 5
}

Response:
{
    "success": true,
    "id": 1,
    "message": "定时任务已保存"
}
```

#### 立即执行任务
```
POST /configs/api/schedules/{id}/run/

Response:
{
    "success": true,
    "task_id": "abc123",
    "message": "任务已触发"
}
```

#### 获取执行日志
```
GET /configs/api/schedules/{id}/logs/

Response:
{
    "logs": [
        {
            "id": 1,
            "start_time": "2026-03-21T10:30:00Z",
            "end_time": "2026-03-21T10:30:45Z",
            "status": "success",
            "total_devices": 15,
            "success_count": 15,
            "failed_count": 0,
            "elapsed_seconds": 45
        }
    ]
}
```

---

## 4. 性能优化方案

### 4.1 目标指标

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| SSH获取配置时间 | 5-15秒 | <5秒 |
| 页面加载时间 | 黑屏 | <1秒 |
| 缓存读取时间 | <100ms | <100ms |

### 4.2 SSH连接优化

#### 4.2.1 连接复用
使用SSH连接池，复用已建立的连接：

```
┌─────────────────────────────────────────────────────┐
│                  SSH连接池                           │
├─────────────────────────────────────────────────────┤
│  Device-1 ──► [Connection-1] ──► 保持活跃           │
│  Device-2 ──► [Connection-2] ──► 保持活跃           │
│  Device-3 ──► [Connection-3] ──► 保持活跃           │
│  ...                                                │
│                                                     │
│  最大连接数: 10                                     │
│  空闲超时: 5分钟                                    │
│  连接复用: 同设备后续请求直接使用已有连接            │
└─────────────────────────────────────────────────────┘
```

**优化效果**：省去每次请求的TCP三次握手 + SSH握手（约1-3秒）

#### 4.2.2 命令执行优化

| 优化项 | 说明 | 预期收益 |
|--------|------|----------|
| 减少超时等待 | 将read_timeout从30s调整为10s | 减少异常情况等待时间 |
| 禁用分页 | 发送命令前设置 `screen-length 0 temporary` | 避免分页等待 |
| 批量命令 | 一次连接执行多个命令 | 减少连接次数 |

#### 4.2.3 Netmiko参数优化

```python
device_params = {
    'device_type': 'huawei',
    'host': device.ip_address,
    'port': device.ssh_port,
    'username': device.ssh_username,
    'password': device.ssh_password,
    'timeout': 10,              # 降低：30 → 10
    'session_timeout': 30,      # 降低：60 → 30
    'conn_timeout': 8,          # 新增：连接超时
    'fast_cli': True,           # 新增：快速CLI模式
    'global_delay_factor': 0.5, # 新增：减少延迟因子
}
```

### 4.3 后台预加载机制

#### 4.3.1 定时预热任务

```
┌────────────────────────────────────────────────────────────┐
│                    后台预加载流程                           │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Celery Beat定时任务（用户可配置间隔/时间）                  │
│         │                                                  │
│         ▼                                                  │
│  ┌─────────────────┐                                       │
│  │ 获取目标设备列表 │◄── 根据任务配置筛选                    │
│  └────────┬────────┘                                       │
│           │                                                │
│           ▼                                                │
│  ┌─────────────────┐                                       │
│  │ 批量SSH获取配置  │◄── 并行执行（最大并发数可配置）         │
│  └────────┬────────┘                                       │
│           │                                                │
│           ▼                                                │
│  ┌─────────────────┐                                       │
│  │ 更新Redis缓存    │                                       │
│  │ 记录执行日志     │                                       │
│  └─────────────────┘                                       │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 4.4 性能优化效果预估

| 场景 | 优化前 | 优化后 | 说明 |
|------|--------|--------|------|
| 首次获取（无缓存） | 5-15秒 | 3-5秒 | SSH优化 + 命令优化 |
| 缓存命中 | <1秒 | <0.5秒 | Redis读取无变化 |
| 后台预加载后获取 | 5-15秒 | <1秒 | 直接读缓存 |
| 连接复用获取 | 5-15秒 | 2-4秒 | 省去连接建立时间 |

---

## 5. 技术方案

### 5.1 前端技术栈

| 技术 | 选择 | 说明 |
|------|------|------|
| 框架 | 原生JavaScript | 与项目保持一致 |
| 样式 | global.css | 保持现有UI风格 |
| 布局 | 左右双栏Flexbox | 固定高度，内容滚动 |
| 响应式 | 仅桌面端 | 不支持移动端 |

### 5.2 后端技术栈

| 技术 | 说明 |
|------|------|
| Django View | DeviceConfigView, ScheduleConfigView |
| Django REST Framework | 配置API端点 |
| Redis | 配置缓存存储 |
| Netmiko | SSH连接库 |
| Celery | 异步任务执行 |
| django-celery-beat | 动态定时任务调度 |
| SSH连接池 | 自定义实现 |

### 5.3 依赖新增

```python
# requirements.txt 新增
django-celery-beat>=2.5.0  # 动态定时任务调度
```

---

## 6. API设计汇总

### 6.1 配置查看API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/devices/api/{id}/config/` | GET | 获取缓存配置 |
| `/devices/api/{id}/config/realtime/` | POST | 实时读取配置 |
| `/devices/api/{id}/config/cancel/` | POST | 取消实时读取 |
| `/devices/api/{id}/config/download/` | GET | 下载配置文件 |

### 6.2 定时任务API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/configs/api/schedules/` | GET | 获取定时任务列表 |
| `/configs/api/schedules/` | POST | 创建定时任务 |
| `/configs/api/schedules/{id}/` | GET | 获取任务详情 |
| `/configs/api/schedules/{id}/` | PUT | 更新定时任务 |
| `/configs/api/schedules/{id}/` | DELETE | 删除定时任务 |
| `/configs/api/schedules/{id}/run/` | POST | 立即执行任务 |
| `/configs/api/schedules/{id}/logs/` | GET | 获取执行日志 |
| `/configs/api/schedules/{id}/logs/{log_id}/` | GET | 获取日志详情 |

---

## 7. 数据模型汇总

### 7.1 新增模型

| 模型 | 说明 |
|------|------|
| ConfigFetchSchedule | 定时任务配置 |
| ConfigFetchLog | 执行日志记录 |

### 7.2 配置缓存结构（Redis）
```
Key: device_config:{device_id}:{config_type}
Value: {
    "config": "配置内容",
    "timestamp": "2026-03-21T10:30:00Z",
    "vendor": "huawei",
    "config_hash": "md5hash",
    "size_bytes": 12345
}
TTL: 30天
```

---

## 8. 前端UI设计汇总

### 8.1 配置查看页面
- 左右双栏布局
- 设备选择下拉框
- 搜索功能
- 刷新缓存/实时读取按钮
- 下载按钮
- 缓存状态指示
- 加载动画与进度提示
- 可取消操作

### 8.2 定时任务管理页面
- 任务列表（增删改查）
- 任务配置表单
- 执行历史查看

---

## 9. 错误处理

| 错误类型 | 用户提示 | 系统处理 |
|----------|----------|----------|
| SSH连接超时 | "连接设备超时，请检查网络连通性" | 记录日志 + 告警 |
| 认证失败 | "SSH认证失败，请检查用户名密码" | 记录日志 |
| 设备离线 | "设备当前离线，无法获取配置" | 记录日志 |
| 命令执行失败 | "配置获取命令执行失败" | 记录日志 + 告警 |
| Redis异常 | "缓存服务异常" | 降级为直接SSH获取 |

---

## 10. 文件结构

```
/opt/network_management/
├── devices/
│   ├── views.py                    # 修改: DeviceConfigView
│   ├── urls.py                     # 修改: 新增API路由
│   └── templates/devices/
│       └── device_config_view.html # 重写: 新UI模板
│
├── configs/
│   ├── models.py                   # 修改: 新增ConfigFetchSchedule, ConfigFetchLog
│   ├── views.py                    # 修改: 新增ScheduleConfigView
│   ├── urls.py                     # 修改: 新增API路由
│   ├── services.py                 # 修改: ConfigManagementService
│   ├── scheduler.py                # 新增: 动态调度管理器
│   ├── ssh_pool.py                 # 新增: SSH连接池
│   ├── tasks.py                    # 修改: 预加载任务
│   └── templates/configs/
│       ├── schedule_list.html      # 新增: 定时任务列表页
│       └── schedule_form.html      # 新增: 定时任务编辑页
│
└── static/
    └── css/
        └── global.css              # 无需修改
```

---

## 11. 测试要点

### 11.1 功能测试

| 测试项 | 预期结果 |
|--------|----------|
| 页面加载 | 正常显示配置内容，无黑屏，<1秒 |
| 刷新缓存 | 从Redis重新读取，更新显示 |
| 实时读取 | SSH获取最新配置，耗时<5秒 |
| 取消操作 | 中断SSH，显示已取消提示 |
| 搜索功能 | 高亮显示匹配内容 |
| 下载功能 | 正确下载配置文件 |
| 创建定时任务 | 任务创建成功，Celery Beat生效 |
| 修改定时任务 | 任务更新成功，调度同步更新 |
| 立即执行任务 | 任务触发成功，执行日志记录 |

### 11.2 性能测试

| 测试项 | 预期结果 |
|--------|----------|
| 首次SSH获取 | <5秒 |
| 连接复用获取 | <3秒 |
| 缓存命中读取 | <0.5秒 |
| 后台预加载执行 | 不影响前台响应 |
| 并发5设备获取 | 全部<10秒完成 |

### 11.3 异常测试

| 测试项 | 预期结果 |
|--------|----------|
| 设备离线 | 显示友好错误提示 + 重试按钮 |
| SSH超时 | 显示超时提示 + 告警 |
| 认证失败 | 显示认证错误提示 |
| Redis异常 | 降级为SSH获取 |
| 连接池满 | 等待或新建临时连接 |

---

## 12. 实施优先级

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | 修复黑屏问题 | 排查前端渲染问题 |
| P0 | 缓存刷新功能 | 添加刷新按钮 |
| P1 | SSH连接优化 | 参数调优 + 连接复用 |
| P1 | 实时读取功能 | SSH直接获取 |
| P1 | 华三设备支持 | 扩展厂商命令 |
| P1 | 定时任务模型 | ConfigFetchSchedule, ConfigFetchLog |
| P1 | 动态调度实现 | django-celery-beat集成 |
| P2 | 定时任务管理UI | 列表页、编辑页 |
| P2 | 搜索功能 | 关键字搜索高亮 |
| P2 | 下载功能 | 配置导出 |
| P2 | 取消功能 | 中断SSH操作 |
| P3 | 错误告警 | 失败告警通知 |
| P3 | 执行日志详情 | 日志查看页面 |

---

## 13. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| SSH长时间阻塞 | 用户体验差 | 设置超时时间，提供取消功能 |
| 大配置文件 | 前端渲染慢 | 分段加载或虚拟滚动 |
| 并发请求过多 | 资源耗尽 | 连接池限制 + 队列排队 |
| 连接池泄漏 | 连接无法释放 | 空闲超时自动清理 |
| 定时任务冲突 | 重复执行 | 任务锁 + 状态检查 |
| 调度配置错误 | 任务无法执行 | 配置校验 + 错误提示 |

---

**文档版本**: v1.2  
**创建日期**: 2026-03-21  
**状态**: 已确认
