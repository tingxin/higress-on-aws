# 架构设计文档

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         Internet                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
                  ┌────────────────┐
                  │ Internet Gateway│
                  └────────┬────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
   │公有子网1│       │公有子网2│       │公有子网3│
   │ (AZ-1) │       │ (AZ-2) │       │ (AZ-3) │
   └────┬────┘       └────┬────┘       └────┬────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                  ┌────────▼────────┐
                  │      ALB        │
                  │ (Application    │
                  │ Load Balancer)  │
                  └────────┬────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
   │NAT GW 1 │       │NAT GW 2 │       │NAT GW 3 │
   └────┬────┘       └────┬────┘       └────┬────┘
        │                  │                  │
   ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
   │私有子网1│       │私有子网2│       │私有子网3│
   │ (AZ-1) │       │ (AZ-2) │       │ (AZ-3) │
   └────┬────┘       └────┬────┘       └────┬────┘
        │                  │                  │
   ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
   │EKS Node │       │EKS Node │       │EKS Node │
   │         │       │         │       │         │
   │Higress  │       │Higress  │       │Higress  │
   │Gateway  │       │Gateway  │       │Gateway  │
   └─────────┘       └─────────┘       └─────────┘
```

## 组件说明

### 1. 网络层

#### Internet Gateway (IGW)
- 提供 VPC 与互联网的连接
- 公有子网通过 IGW 访问互联网

#### NAT Gateway
- 每个可用区一个 NAT Gateway
- 私有子网通过 NAT Gateway 访问互联网
- 高可用设计

#### 子网设计
- **公有子网**：部署 ALB
- **私有子网**：部署 EKS 节点和 Higress

### 2. 负载均衡层

#### Application Load Balancer (ALB)
- 部署在公有子网
- 跨 3 个可用区
- 支持 HTTP/HTTPS
- 自动健康检查
- SSL/TLS 终止

**特性：**
- 基于路径的路由
- 基于主机的路由
- WebSocket 支持
- HTTP/2 支持

### 3. 计算层

#### EKS 集群
- 托管的 Kubernetes 控制平面
- 自动升级和补丁
- 高可用设计

#### EKS 节点组
- 部署在私有子网
- 跨 3 个可用区
- 使用 Auto Scaling Group
- 支持自动扩缩容

### 4. 应用层

#### Higress Gateway
- 云原生 API 网关
- 基于 Envoy 和 Istio
- 支持多种协议
- 插件化架构

**组件：**
- **Gateway**：处理流量
- **Controller**：管理配置
- **Console**：Web 管理界面

## 高可用设计

### 1. 多可用区部署

```
AZ-1          AZ-2          AZ-3
┌────┐        ┌────┐        ┌────┐
│ALB │        │ALB │        │ALB │
└─┬──┘        └─┬──┘        └─┬──┘
  │             │             │
┌─▼──┐        ┌─▼──┐        ┌─▼──┐
│Node│        │Node│        │Node│
└────┘        └────┘        └────┘
```

- 每个 AZ 至少一个节点
- ALB 跨所有 AZ
- 自动故障转移

### 2. Pod 反亲和性

```yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
    - labelSelector:
        matchExpressions:
        - key: app
          operator: In
          values:
          - higress-gateway
      topologyKey: kubernetes.io/hostname
```

确保 Pod 分散在不同节点。

### 3. Pod 中断预算

```yaml
podDisruptionBudget:
  enabled: true
  minAvailable: 2
```

确保滚动更新时至少 2 个 Pod 可用。

## 自动扩缩容

### 1. Horizontal Pod Autoscaler (HPA)

```yaml
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

**触发条件：**
- CPU 使用率 > 70%
- 内存使用率 > 80%

### 2. Cluster Autoscaler

自动调整节点数量：
- 当 Pod 无法调度时增加节点
- 当节点利用率低时减少节点

## 安全架构

### 1. 网络安全

```
Internet
   │
   ▼
[Security Group: ALB]
   │ 允许: 80, 443 from 0.0.0.0/0
   ▼
  ALB
   │
   ▼
[Security Group: Nodes]
   │ 允许: 30080, 30443 from ALB SG
   │ 允许: All from Nodes SG
   ▼
EKS Nodes
```

### 2. IAM 权限

```
EKS Cluster Role
├── AmazonEKSClusterPolicy
└── AmazonEKSVPCResourceController

Node Group Role
├── AmazonEKSWorkerNodePolicy
├── AmazonEKS_CNI_Policy
├── AmazonEC2ContainerRegistryReadOnly
└── Custom Policies

ALB Controller Role
└── AWSLoadBalancerControllerIAMPolicy
```

### 3. 数据加密

- **传输加密**：HTTPS/TLS
- **静态加密**：EBS 卷加密
- **Secrets 加密**：KMS 加密

## 流量路径

### HTTP 请求流程

```
1. 用户请求
   │
   ▼
2. DNS 解析 → ALB DNS
   │
   ▼
3. ALB 接收请求
   │
   ▼
4. ALB 健康检查
   │
   ▼
5. 转发到 Higress Gateway (NodePort)
   │
   ▼
6. Higress Gateway 处理
   │
   ▼
7. 路由到后端服务
   │
   ▼
8. 返回响应
```

### 详细流程

```
Client
  │
  │ 1. HTTPS Request
  ▼
ALB (Public Subnet)
  │
  │ 2. SSL Termination
  │ 3. Health Check
  │ 4. Target Selection
  ▼
Higress Gateway Pod (Private Subnet)
  │
  │ 5. Request Processing
  │ 6. Plugin Execution
  │ 7. Route Matching
  ▼
Backend Service
  │
  │ 8. Business Logic
  ▼
Response
```

## 监控架构

### 1. 监控组件

```
┌─────────────────────────────────────┐
│         CloudWatch                   │
│  ┌──────────┐      ┌──────────┐    │
│  │ Metrics  │      │  Logs    │    │
│  └──────────┘      └──────────┘    │
└──────────▲──────────────▲───────────┘
           │              │
           │              │
┌──────────┴──────────────┴───────────┐
│         EKS Cluster                  │
│  ┌──────────┐      ┌──────────┐    │
│  │Prometheus│      │Fluent Bit│    │
│  └──────────┘      └──────────┘    │
└──────────────────────────────────────┘
```

### 2. 监控指标

**集群级别：**
- CPU 使用率
- 内存使用率
- 网络流量
- 磁盘 I/O

**应用级别：**
- 请求数
- 响应时间
- 错误率
- 并发连接数

## 成本架构

### 月度成本分解

```
总成本: ~$480/月
├── EKS 控制平面: $73 (15%)
├── EC2 实例: $367 (76%)
├── EBS 卷: $24 (5%)
├── ALB: $16 (3%)
└── 数据传输: ~$20 (4%)
```

### 成本优化策略

1. **使用 Savings Plans**
   - 节省 30-70%
   - 1 年或 3 年承诺

2. **使用 Spot 实例**
   - 节省 70-90%
   - 适用于非生产环境

3. **右侧调整实例大小**
   - 根据实际负载选择
   - 定期审查使用情况

4. **使用 gp3 卷**
   - 比 gp2 更便宜
   - 性能更好

## 扩展性

### 1. 水平扩展

- **Pod 扩展**：3-10 个副本
- **节点扩展**：3-6 个节点
- **集群扩展**：多集群部署

### 2. 垂直扩展

- **实例类型升级**：t3 → c6i → c7i
- **资源限制调整**：增加 CPU/内存

### 3. 性能优化

- **连接池**：复用连接
- **缓存**：减少后端请求
- **压缩**：减少传输数据

## 灾难恢复

### 1. 备份策略

- **配置备份**：每日自动备份
- **数据备份**：持久化数据备份
- **快照备份**：EBS 快照

### 2. 恢复流程

```
1. 创建新集群
   │
   ▼
2. 恢复配置
   │
   ▼
3. 恢复数据
   │
   ▼
4. 验证功能
   │
   ▼
5. 切换流量
```

### 3. RTO/RPO

- **RTO**（恢复时间目标）：< 1 小时
- **RPO**（恢复点目标）：< 24 小时

## 最佳实践

### 1. 部署最佳实践

- 使用 Infrastructure as Code
- 版本控制配置文件
- 自动化部署流程
- 蓝绿部署或金丝雀发布

### 2. 运维最佳实践

- 定期备份
- 监控告警
- 日志收集
- 定期演练

### 3. 安全最佳实践

- 最小权限原则
- 定期更新
- 安全扫描
- 审计日志

## 相关文档

- [用户指南](USER-GUIDE.md)
- [配置参考](CONFIG-REFERENCE.md)
- [故障排查](TROUBLESHOOTING.md)
