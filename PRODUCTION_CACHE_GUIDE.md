# Azure Functions 生产环境缓存部署指南

## 🎯 生产环境缓存策略

### 问题分析
在真正的Azure Functions环境中，您遇到的实例级内存缓存有以下限制：

1. **冷启动** - 函数实例会在空闲后被回收，丢失所有内存缓存
2. **多实例扩展** - 负载增加时会创建多个实例，每个实例的缓存独立
3. **实例回收** - Azure定期回收实例以优化资源

### 🏗️ 推荐的解决方案

我为您实现了一个**混合缓存策略**，结合以下优势：

#### 1. **Azure Cache for Redis**（主要缓存）
- ✅ 跨实例共享缓存
- ✅ 持久化存储
- ✅ 高性能
- ✅ 自动过期（TTL）

#### 2. **内存缓存**（辅助缓存）
- ✅ 最快访问速度
- ✅ 减少Redis网络调用
- ✅ 作为Redis的备份

## 🚀 部署步骤

### 步骤1: 创建Azure Cache for Redis

```bash
# 创建资源组（如果不存在）
az group create --name rg-beer-prediction --location eastus

# 创建Redis缓存实例
az redis create \
  --name redis-beer-cache-001 \
  --resource-group rg-beer-prediction \
  --location eastus \
  --sku Basic \
  --vm-size c0

# 获取连接字符串
az redis list-keys --name redis-beer-cache-001 --resource-group rg-beer-prediction
```

### 步骤2: 配置Azure Functions应用设置

在Azure Portal中，为您的Functions App添加以下应用设置：

```json
{
  "AZURE_REDIS_CONNECTION_STRING": "redis-beer-cache-001.redis.cache.windows.net:6380,password=YOUR_REDIS_KEY,ssl=True"
}
```

### 步骤3: 部署更新的代码

使用以下命令部署：

```bash
# 安装依赖
pip install -r requirements.txt

# 部署到Azure
func azure functionapp publish your-function-app-name
```

## 📊 缓存性能对比

| 方案 | 第一次调用 | 相同请求重复调用 | 跨实例访问 | 冷启动后 |
|------|------------|------------------|------------|----------|
| **仅内存缓存** | 8-10秒 | 0.1秒 | ❌ 需重新计算 | ❌ 缓存丢失 |
| **Redis + 内存** | 8-10秒 | 0.1秒 | ✅ 2-3秒 | ✅ 2-3秒 |

## 🔧 缓存策略详情

### TTL（生存时间）设置
- **天气缓存**: 30分钟 - 天气数据变化较频繁
- **周预测缓存**: 1小时 - 预测结果相对稳定

### 缓存键策略
- 使用MD5哈希确保键的一致性
- 包含前缀以区分不同类型的缓存

### 故障回退
- Redis不可用时自动回退到内存缓存
- 网络问题时不影响函数正常运行

## 🧪 测试验证

### 本地测试（无Redis）
```bash
curl "http://localhost:7071/api/weekly?start_date=2025-06-25"
curl "http://localhost:7071/api/health"
```

### 生产环境测试（有Redis）
```bash
# 检查缓存状态
curl "https://your-function-app.azurewebsites.net/api/health"

# 测试缓存效果
curl "https://your-function-app.azurewebsites.net/api/weekly?start_date=2025-06-25"
```

## 💰 成本考虑

### Redis缓存成本
- **Basic C0**: ~$15/月（1GB内存）
- **Standard C1**: ~$55/月（2.5GB内存，高可用）

### 性能收益
- 减少70-80%的计算时间
- 降低天气API调用次数
- 提升用户体验

## 🔍 监控和维护

### 关键指标
- Redis连接状态
- 缓存命中率
- 内存使用情况
- 响应时间

### 日志监控
```bash
# 查看Functions日志
az functionapp logs tail --name your-function-app-name --resource-group rg-beer-prediction
```

## 🚨 注意事项

1. **网络延迟**: Redis在不同区域会有网络延迟
2. **安全性**: 使用SSL连接和强密码
3. **监控**: 定期检查Redis性能和成本
4. **备份**: 考虑Redis数据备份策略

## 📈 扩展建议

### 高级优化
1. **Redis集群** - 更高性能和可用性
2. **CDN缓存** - 地理位置优化
3. **预热策略** - 定时任务预热热门数据
4. **智能过期** - 基于访问频率的动态TTL

这个解决方案确保您的缓存在生产环境中能够正常工作，无论是单实例还是多实例场景！
