# 配置参考文档

## 配置文件结构

配置文件 `config.yaml` 包含所有部署参数。

## 完整配置示例

```yaml
# AWS 配置
aws:
  region: us-east-1
  account_id: YOUR_AWS_ACCOUNT_ID  # 可选，会自动获取

# VPC 网络配置
vpc:
  vpc_id: vpc-xxxxxxxxx
  public_subnets:
    - subnet-public-1-xxxxxxxxx
    - subnet-public-2-xxxxxxxxx
    - subnet-public-3-xxxxxxxxx
  private_subnets:
    - subnet-private-1-xxxxxxxxx
    - subnet-private-2-xxxxxxxxx
    - subnet-private-3-xxxxxxxxx

# EKS 集群配置
eks:
  cluster_name: higress-prod
  kubernetes_version: '1.29'
  node_group_name: higress-nodes
  instance_type: c6i.xlarge
  desired_capacity: 3
  min_size: 3
  max_size: 6
  volume_size: 100

# Higress 配置
higress:
  use_alb: true
  replicas: 3
  cpu_request: 1000m
  memory_request: 2Gi
  cpu_limit: 2000m
  memory_limit: 4Gi
  enable_autoscaling: true
  min_replicas: 3
  max_replicas: 10

# ALB 配置
alb:
  certificate_arn: ''
```

## 配置项详解

### AWS 配置

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `region` | string | 是 | - | AWS 区域，如 us-east-1 |
| `account_id` | string | 否 | 自动获取 | AWS 账户 ID |

**示例：**
```yaml
aws:
  region: us-east-1
```

### VPC 配置

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `vpc_id` | string | 是 | VPC ID |
| `public_subnets` | array | 是 | 公有子网列表（3个，跨3个AZ） |
| `private_subnets` | array | 是 | 私有子网列表（3个，跨3个AZ） |

**要求：**
- 公有子网必须有 Internet Gateway 路由
- 私有子网必须有 NAT Gateway 路由
- 子网必须跨 3 个不同的可用区

**示例：**
```yaml
vpc:
  vpc_id: vpc-0a1b2c3d4e5f6g7h8
  public_subnets:
    - subnet-0a1b2c3d  # us-east-1a
    - subnet-1a2b3c4d  # us-east-1b
    - subnet-2a3b4c5d  # us-east-1c
  private_subnets:
    - subnet-3a4b5c6d  # us-east-1a
    - subnet-4a5b6c7d  # us-east-1b
    - subnet-5a6b7c8d  # us-east-1c
```

### EKS 配置

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `cluster_name` | string | 是 | - | EKS 集群名称 |
| `kubernetes_version` | string | 是 | - | Kubernetes 版本（1.28, 1.29, 1.30） |
| `node_group_name` | string | 是 | - | 节点组名称 |
| `instance_type` | string | 是 | - | EC2 实例类型 |
| `desired_capacity` | integer | 是 | - | 期望节点数 |
| `min_size` | integer | 是 | - | 最小节点数 |
| `max_size` | integer | 是 | - | 最大节点数 |
| `volume_size` | integer | 是 | - | 每个节点的磁盘大小（GB） |

**实例类型建议：**

| 环境 | 实例类型 | vCPU | 内存 | 价格/小时 |
|------|----------|------|------|----------|
| 测试 | t3.medium | 2 | 4GB | $0.0416 |
| 开发 | t3.large | 2 | 8GB | $0.0832 |
| 生产 | c6i.xlarge | 4 | 8GB | $0.17 |
| 高性能 | c6i.2xlarge | 8 | 16GB | $0.34 |

**示例：**
```yaml
eks:
  cluster_name: higress-prod
  kubernetes_version: '1.29'
  node_group_name: higress-nodes
  instance_type: c6i.xlarge
  desired_capacity: 3
  min_size: 3
  max_size: 6
  volume_size: 100
```

### Higress 配置

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `use_alb` | boolean | 是 | - | 是否使用 ALB（true）或 NLB（false） |
| `replicas` | integer | 是 | - | Higress Gateway 副本数 |
| `cpu_request` | string | 是 | - | CPU 请求（如 1000m = 1核） |
| `memory_request` | string | 是 | - | 内存请求（如 2Gi） |
| `cpu_limit` | string | 是 | - | CPU 限制 |
| `memory_limit` | string | 是 | - | 内存限制 |
| `enable_autoscaling` | boolean | 是 | - | 是否启用自动扩缩容 |
| `min_replicas` | integer | 否 | 3 | 最小副本数（启用自动扩缩容时） |
| `max_replicas` | integer | 否 | 10 | 最大副本数（启用自动扩缩容时） |

**资源配置建议：**

| 场景 | CPU Request | Memory Request | CPU Limit | Memory Limit |
|------|-------------|----------------|-----------|--------------|
| 小型 | 500m | 1Gi | 1000m | 2Gi |
| 中型 | 1000m | 2Gi | 2000m | 4Gi |
| 大型 | 2000m | 4Gi | 4000m | 8Gi |

**示例：**
```yaml
higress:
  use_alb: true
  replicas: 3
  cpu_request: 1000m
  memory_request: 2Gi
  cpu_limit: 2000m
  memory_limit: 4Gi
  enable_autoscaling: true
  min_replicas: 3
  max_replicas: 10
```

### ALB 配置

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `certificate_arn` | string | 否 | '' | ACM 证书 ARN（用于 HTTPS） |

**示例：**
```yaml
alb:
  certificate_arn: 'arn:aws:acm:us-east-1:123456789012:certificate/xxxxx'
```

## 配置模板

### 最小配置（测试环境）

```yaml
aws:
  region: us-east-1

vpc:
  vpc_id: vpc-xxxxx
  public_subnets: [subnet-pub-1, subnet-pub-2, subnet-pub-3]
  private_subnets: [subnet-priv-1, subnet-priv-2, subnet-priv-3]

eks:
  cluster_name: higress-test
  kubernetes_version: '1.29'
  node_group_name: test-nodes
  instance_type: t3.medium
  desired_capacity: 2
  min_size: 2
  max_size: 4
  volume_size: 50

higress:
  use_alb: true
  replicas: 2
  cpu_request: 500m
  memory_request: 1Gi
  cpu_limit: 1000m
  memory_limit: 2Gi
  enable_autoscaling: false

alb:
  certificate_arn: ''
```

### 生产配置（推荐）

```yaml
aws:
  region: us-east-1

vpc:
  vpc_id: vpc-xxxxx
  public_subnets: [subnet-pub-1, subnet-pub-2, subnet-pub-3]
  private_subnets: [subnet-priv-1, subnet-priv-2, subnet-priv-3]

eks:
  cluster_name: higress-prod
  kubernetes_version: '1.29'
  node_group_name: prod-nodes
  instance_type: c6i.xlarge
  desired_capacity: 3
  min_size: 3
  max_size: 6
  volume_size: 100

higress:
  use_alb: true
  replicas: 3
  cpu_request: 1000m
  memory_request: 2Gi
  cpu_limit: 2000m
  memory_limit: 4Gi
  enable_autoscaling: true
  min_replicas: 3
  max_replicas: 10

alb:
  certificate_arn: 'arn:aws:acm:us-east-1:123456789012:certificate/xxxxx'
```

### 高性能配置

```yaml
aws:
  region: us-east-1

vpc:
  vpc_id: vpc-xxxxx
  public_subnets: [subnet-pub-1, subnet-pub-2, subnet-pub-3]
  private_subnets: [subnet-priv-1, subnet-priv-2, subnet-priv-3]

eks:
  cluster_name: higress-high-perf
  kubernetes_version: '1.29'
  node_group_name: high-perf-nodes
  instance_type: c6i.2xlarge
  desired_capacity: 5
  min_size: 3
  max_size: 10
  volume_size: 200

higress:
  use_alb: true
  replicas: 5
  cpu_request: 2000m
  memory_request: 4Gi
  cpu_limit: 4000m
  memory_limit: 8Gi
  enable_autoscaling: true
  min_replicas: 5
  max_replicas: 20

alb:
  certificate_arn: 'arn:aws:acm:us-east-1:123456789012:certificate/xxxxx'
```

## 配置验证

### 验证配置文件

```bash
# 检查 YAML 语法
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"

# 验证必需字段
./higress_deploy.py init --validate
```

### 验证 AWS 资源

```bash
# 验证 VPC
aws ec2 describe-vpcs --vpc-ids <vpc-id>

# 验证子网
aws ec2 describe-subnets --subnet-ids <subnet-id>

# 验证子网标签
aws ec2 describe-subnets --subnet-ids <subnet-id> --query 'Subnets[*].Tags'
```

## 常见配置问题

### 问题 1: 子网数量不足

**错误：** 需要 3 个公有子网和 3 个私有子网

**解决：** 确保配置文件中有 6 个子网（3 公有 + 3 私有）

### 问题 2: 子网未跨可用区

**错误：** 子网必须分布在不同的可用区

**解决：** 确保子网分布在 3 个不同的 AZ

### 问题 3: 实例类型不支持

**错误：** 实例类型在该区域不可用

**解决：** 选择该区域支持的实例类型

### 问题 4: Kubernetes 版本不支持

**错误：** Kubernetes 版本不支持

**解决：** 使用支持的版本（1.28, 1.29, 1.30）

## 相关文档

- [用户指南](USER-GUIDE.md)
- [快速开始](QUICK-START.md)
- [架构设计](ARCHITECTURE.md)
