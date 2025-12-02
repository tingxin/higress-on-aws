# Higress EKS 自动化部署工具

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

一个强大的命令行工具，用于在 AWS EKS 上自动化部署 Higress 云原生网关。

## ✨ 特性

- 🚀 **一键部署** - 单个命令完成 EKS 集群创建和 Higress 部署
- 🔧 **灵活配置** - 通过 YAML 文件管理所有配置参数
- 🏗️ **高可用架构** - 跨 3 个可用区部署，自动扩缩容
- 🔒 **安全加固** - 集成 AWS 最佳实践和安全配置
- 🌐 **ALB 集成** - 自动创建和配置 Application Load Balancer
- 🧹 **灵活清理** - 支持选择性删除资源（仅 Higress 或整个集群）

## 📋 前置要求

### 必需工具

- Python 3.8+
- AWS CLI v2.x
- kubectl v1.28+
- eksctl v0.170.0+
- Helm v3.10+

### AWS 资源

- 1 个 VPC
- 3 个公有子网（跨 3 个可用区）
- 3 个私有子网（跨 3 个可用区）
- NAT Gateway 已配置

## 🚀 快速开始
### 1. 安装必要工具

```bash
#尝试使用setup.sh
bash setup.sh
```
如果报错，分步骤
#### 安装 AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

#### 配置 AWS 凭证
```
aws configure
# 输入 Access Key ID、Secret Access Key、Region 等信息
```

#### 安装 kubectl
```
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
kubectl version --client
```

#### 安装 eksctl
```
curl --silent --location "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin
eksctl version
```

#### 安装 Helm
```
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

### 2. 安装

```bash
# 运行安装脚本
./setup.sh

# 或手动安装
pip3 install -r requirements.txt
chmod +x higress_deploy.py
```

### 3. 初始化配置

```bash
# 创建配置文件
./higress_deploy.py init

# 编辑配置文件，填入您的 AWS 资源信息
vim config.yaml
```

### 4. 按顺序部署

**或手动执行各步骤**（详见 [部署顺序指南](DEPLOYMENT-ORDER.md)）：

```bash
./higress_deploy.py create        # 创建 EKS 集群
./higress_deploy.py install-alb   # 安装 ALB Controller
./higress_deploy.py deploy        # 部署 Higress
./higress_deploy.py create-lb     # 创建 ALB
./higress_deploy.py status        # 查看状态
# 获取访问地址
cat alb-endpoint.txt
```

## 📖 命令参考

### 基础命令

```bash
./higress_deploy.py init              # 初始化配置文件
./higress_deploy.py validate          # 验证配置文件完整性
./higress_deploy.py create            # 创建 EKS 集群（自动安装 EBS CSI Driver）
./higress_deploy.py install-ebs-csi   # 安装 EBS CSI Driver（可选，create 已包含）
./higress_deploy.py install-alb       # 安装 ALB Controller
./higress_deploy.py deploy            # 部署 Higress
./higress_deploy.py create-lb         # 创建 ALB
./higress_deploy.py install-all       # 一键安装所有组件
./higress_deploy.py status            # 查看部署状态
```

### 故障修复命令

```bash
./higress_deploy.py fix-alb-security-group  # 修复 ALB Security Group 问题
./higress_deploy.py fix-alb-permissions     # 修复 ALB IAM 权限问题
```

### 清理命令

```bash
# 仅删除 Higress（保留 EKS 集群）
./higress_deploy.py clean higress

# 删除整个 EKS 集群
./higress_deploy.py clean eks

# 强制删除（不需要确认）
./higress_deploy.py clean higress --force
./higress_deploy.py clean eks --force
```

### Makefile 快捷命令

```bash
make install-all      # 一键部署
make status           # 查看状态
make clean-higress    # 仅删除 Higress
make clean-eks        # 删除整个集群
make troubleshoot     # 运行故障排查
make fix-webhook      # 修复 webhook 问题
```

## 📚 文档

| 文档 | 说明 |
|------|------|
| [部署顺序指南](DEPLOYMENT-ORDER.md) | ⭐ 正确的部署步骤和顺序 |
| [快速开始](docs/QUICK-START.md) | 5 分钟快速入门指南 |
| [完整指南](docs/USER-GUIDE.md) | 详细使用文档 |
| [StorageClass 配置](docs/STORAGE-CLASS.md) | ⭐ 新增 - 持久化存储配置 |
| [验证指南](docs/VERIFICATION.md) | 集群验证和功能测试 |
| [清理指南](docs/CLEANUP-GUIDE.md) | 资源清理详细说明 |
| [故障排查](docs/TROUBLESHOOTING.md) | 常见问题和解决方案 |
| [配置说明](docs/CONFIG-REFERENCE.md) | 配置文件详细说明 |
| [架构设计](docs/ARCHITECTURE.md) | 架构和设计文档 |
| [更新日志](docs/CHANGELOG.md) | 版本更新历史 |

## 🎯 使用场景

### 场景 1: 首次部署

```bash
./setup.sh                    # 安装工具
./higress_deploy.py init      # 初始化配置
vim config.yaml               # 编辑配置
./higress_deploy.py install-all  # 一键部署
```

### 场景 2: 重新部署 Higress

```bash
./higress_deploy.py clean higress  # 删除 Higress
./higress_deploy.py deploy         # 重新部署
./higress_deploy.py create-lb      # 创建 ALB
```

### 场景 3: 完全清理

```bash
./higress_deploy.py clean eks  # 删除整个集群
```

## 🔍 故障排查

### 快速诊断

```bash
# 运行自动故障排查脚本
./troubleshoot.sh

# 修复 webhook 问题
make fix-webhook

# 验证配置
./higress_deploy.py validate
```

### 常见问题

**问题 1: ALB 创建失败 - Security Group 无效**

```bash
# 症状：InvalidConfigurationRequest: One or more security groups are invalid
# 解决方案：
./higress_deploy.py fix-alb-security-group

# 或手动修复
bash fix-alb-security-group.sh
```

**问题 2: IAM 权限不足（创建 ALB 失败）**

```bash
# 症状：elasticloadbalancing:DescribeListenerAttributes 权限错误
# 解决方案：
./higress_deploy.py fix-alb-permissions
# 或
make fix-alb-permissions

# 然后重新创建 ALB
kubectl delete ingress higress-alb -n higress-system
./higress_deploy.py create-lb
```

**问题 3: Webhook 服务未就绪**

```bash
# 解决方案
kubectl rollout restart deployment aws-load-balancer-controller -n kube-system
sleep 30
./higress_deploy.py deploy
```

**问题 4: ALB 未创建**

```bash
# 检查子网标签
aws ec2 describe-subnets --subnet-ids <subnet-id> --query 'Subnets[*].Tags'

# 检查 Ingress 状态
kubectl describe ingress higress-alb -n higress-system

# 查看 ALB Controller 日志
kubectl logs -n kube-system deployment/aws-load-balancer-controller | tail -50
```

更多问题请参考 [故障排查文档](docs/TROUBLESHOOTING.md)。

