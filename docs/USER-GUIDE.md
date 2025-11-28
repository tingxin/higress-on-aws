# Higress EKS 部署完整指南

## 目录

- [前置准备](#前置准备)
- [安装工具](#安装工具)
- [配置说明](#配置说明)
- [部署流程](#部署流程)
- [管理操作](#管理操作)
- [清理资源](#清理资源)

## 前置准备

### 1. 安装必要工具

```bash
# AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# eksctl
curl --silent --location "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin

# Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

### 2. 配置 AWS 凭证

```bash
aws configure
# 输入 Access Key ID、Secret Access Key、Region
```

### 3. 准备 VPC 环境

确保您已有：
- 1 个 VPC
- 3 个公有子网（跨 3 个可用区）
- 3 个私有子网（跨 3 个可用区）
- NAT Gateway 已配置

## 安装工具

### 方法 1: 使用安装脚本（推荐）

```bash
./setup.sh
```

### 方法 2: 手动安装

```bash
pip3 install -r requirements.txt
chmod +x higress_deploy.py
```

### 方法 3: 全局安装

```bash
pip3 install -r requirements.txt
sudo ln -s $(pwd)/higress_deploy.py /usr/local/bin/higress-deploy
```

## 配置说明

### 初始化配置文件

```bash
./higress_deploy.py init
```

### 配置文件结构

```yaml
# AWS 配置
aws:
  region: us-east-1                    # AWS 区域

# VPC 配置
vpc:
  vpc_id: vpc-xxxxx                    # VPC ID
  public_subnets:                      # 公有子网（3个）
    - subnet-pub-1
    - subnet-pub-2
    - subnet-pub-3
  private_subnets:                     # 私有子网（3个）
    - subnet-priv-1
    - subnet-priv-2
    - subnet-priv-3

# EKS 配置
eks:
  cluster_name: higress-prod           # 集群名称
  kubernetes_version: '1.29'           # K8s 版本
  node_group_name: higress-nodes       # 节点组名称
  instance_type: c6i.xlarge            # 实例类型
  desired_capacity: 3                  # 期望节点数
  min_size: 3                          # 最小节点数
  max_size: 6                          # 最大节点数
  volume_size: 100                     # 磁盘大小（GB）

# Higress 配置
higress:
  use_alb: true                        # 使用 ALB
  replicas: 3                          # 副本数
  cpu_request: 1000m                   # CPU 请求
  memory_request: 2Gi                  # 内存请求
  cpu_limit: 2000m                     # CPU 限制
  memory_limit: 4Gi                    # 内存限制
  enable_autoscaling: true             # 启用自动扩缩容
  min_replicas: 3                      # 最小副本数
  max_replicas: 10                     # 最大副本数

# ALB 配置
alb:
  certificate_arn: ''                  # ACM 证书 ARN（可选）
```

详细配置说明请参考 [配置参考文档](CONFIG-REFERENCE.md)。

## 部署流程

### 方案 A: 一键部署（推荐）

```bash
./higress_deploy.py install-all
```

### 方案 B: 分步部署

```bash
# 1. 创建 EKS 集群（15-20 分钟）
./higress_deploy.py create

# 2. 安装 ALB Controller（2-3 分钟）
./higress_deploy.py install-alb

# 3. 部署 Higress（3-5 分钟）
./higress_deploy.py deploy

# 4. 创建 ALB（3-5 分钟）
./higress_deploy.py create-lb

# 5. 查看状态
./higress_deploy.py status
```

### 使用 Makefile

```bash
# 一键部署
make install-all

# 或分步部署
make create
make install-alb
make deploy
make create-lb
make status
```

## 管理操作

### 查看状态

```bash
# 查看所有资源状态
./higress_deploy.py status

# 查看 Pods
kubectl get pods -n higress-system

# 查看 Services
kubectl get svc -n higress-system

# 查看 Ingress
kubectl get ingress -n higress-system

# 查看资源使用
kubectl top nodes
kubectl top pods -n higress-system
```

### 查看日志

```bash
# Higress Gateway 日志
kubectl logs -n higress-system -l app=higress-gateway --tail=100

# Higress Controller 日志
kubectl logs -n higress-system -l app=higress-controller --tail=100

# ALB Controller 日志
kubectl logs -n kube-system deployment/aws-load-balancer-controller --tail=100
```

### 访问 Higress Console

```bash
# 方法 1: Port Forward
kubectl port-forward -n higress-system svc/higress-console 8080:8080
# 访问 http://localhost:8080

# 方法 2: 通过 Ingress 暴露（生产环境）
# 参考配置文档
```

### 配置 SSL 证书

```bash
# 1. 在 ACM 中申请证书
aws acm request-certificate \
  --domain-name yourdomain.com \
  --subject-alternative-names *.yourdomain.com \
  --validation-method DNS

# 2. 获取证书 ARN
aws acm list-certificates

# 3. 在 config.yaml 中配置
# alb:
#   certificate_arn: arn:aws:acm:...

# 4. 重新创建 ALB
kubectl delete ingress higress-alb -n higress-system
./higress_deploy.py create-lb
```

### 扩缩容

```bash
# 手动扩容 Higress
kubectl scale deployment higress-gateway -n higress-system --replicas=5

# 扩容 EKS 节点
eksctl scale nodegroup \
  --cluster=higress-prod \
  --name=higress-nodes \
  --nodes=5

# 查看 HPA 状态
kubectl get hpa -n higress-system
```

### 更新配置

```bash
# 1. 修改配置文件
vim config.yaml

# 2. 重新部署 Higress
helm upgrade higress higress.io/higress \
  -n higress-system \
  -f higress-values.yaml
```

### 备份

```bash
# 使用 Makefile
make backup

# 手动备份
kubectl get all -n higress-system -o yaml > backup.yaml
kubectl get configmap -n higress-system -o yaml > configmaps.yaml
kubectl get ingress -A -o yaml > ingress.yaml
```

## 清理资源

### 仅删除 Higress（保留 EKS 集群）

```bash
# 交互式删除
./higress_deploy.py clean higress

# 强制删除
./higress_deploy.py clean higress --force

# 使用 Makefile
make clean-higress
```

**删除内容：**
- Higress Gateway、Controller、Console
- Higress 命名空间
- ALB Ingress
- LoadBalancer/NLB

**保留内容：**
- EKS 集群和节点
- ALB Controller

**预计时间：** 2-3 分钟

### 删除整个 EKS 集群

```bash
# 交互式删除
./higress_deploy.py clean eks

# 强制删除
./higress_deploy.py clean eks --force

# 使用 Makefile
make clean-eks
```

**删除内容：**
- EKS 集群及所有节点
- Higress 及所有配置
- ALB Controller
- ALB/NLB
- IAM 角色和策略

**保留内容：**
- VPC 和子网
- NAT Gateway

**预计时间：** 10-15 分钟

详细清理说明请参考 [清理指南](CLEANUP-GUIDE.md)。

## 故障排查

### 快速诊断

```bash
# 运行自动故障排查脚本
./troubleshoot.sh

# 使用 Makefile
make troubleshoot
```

### 常见问题

**问题 1: Webhook 服务未就绪**

```bash
# 修复方法
make fix-webhook
# 或
kubectl rollout restart deployment aws-load-balancer-controller -n kube-system
sleep 30
./higress_deploy.py deploy
```

**问题 2: ALB 未创建**

```bash
# 检查子网标签
aws ec2 describe-subnets --subnet-ids <subnet-id> --query 'Subnets[*].Tags'

# 检查 ALB Controller 日志
kubectl logs -n kube-system deployment/aws-load-balancer-controller
```

**问题 3: Pod 无法启动**

```bash
# 查看详情
kubectl describe pod <pod-name> -n higress-system

# 查看日志
kubectl logs <pod-name> -n higress-system

# 查看事件
kubectl get events -n higress-system --sort-by='.lastTimestamp'
```

更多问题请参考 [故障排查文档](TROUBLESHOOTING.md)。

## 最佳实践

1. **生产环境建议**
   - 使用至少 3 个节点跨 3 个可用区
   - 启用自动扩缩容
   - 配置 SSL 证书
   - 启用监控和日志

2. **安全建议**
   - 使用 IAM 角色而非访问密钥
   - 定期更新 EKS 版本
   - 配置安全组最小权限
   - 启用 VPC Flow Logs

3. **成本优化**
   - 使用 Savings Plans
   - 测试环境使用 Spot 实例
   - 配置 Cluster Autoscaler
   - 定期清理未使用资源

4. **运维建议**
   - 定期备份配置
   - 监控资源使用情况
   - 设置告警
   - 保持文档更新

## 下一步

- [配置参考](CONFIG-REFERENCE.md) - 详细配置说明
- [架构设计](ARCHITECTURE.md) - 架构和设计文档
- [故障排查](TROUBLESHOOTING.md) - 常见问题解决
- [清理指南](CLEANUP-GUIDE.md) - 资源清理说明
