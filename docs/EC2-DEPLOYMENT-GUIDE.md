# Higress 生产集群 AWS 部署指南

## 目录
- [快速开始（已有 VPC）](#快速开始已有-vpc)
- [环境要求](#环境要求)
- [架构概述](#架构概述)
- [前置准备](#前置准备)
- [VPC 和网络配置](#vpc-和网络配置)
- [EC2 实例部署](#ec2-实例部署)
- [Higress 集群安装](#higress-集群安装)
- [ALB 配置](#alb-配置)
- [安全加固](#安全加固)
- [监控和日志](#监控和日志)
- [故障排查](#故障排查)

---

## 快速开始（已有 VPC）

**适用场景：** 您已有标准的 AWS VPC 架构（3 公有子网 + 3 私有子网 + NAT Gateway）

**部署概览：**
1. 在 3 个私有子网中部署 3 个 EC2 实例（跨 3 个 AZ）
2. 在 EC2 上安装 K3s + Higress
3. 在 3 个公有子网中部署 ALB
4. 配置 ALB 将流量转发到 Higress

**预计部署时间：** 30-45 分钟

**快速部署步骤：**

```bash
# 1. 设置 VPC 和子网 ID（替换为您的实际值）
export VPC_ID="vpc-xxxxxxxxx"
export PUBLIC_SUBNET_1="subnet-pub-az1"
export PUBLIC_SUBNET_2="subnet-pub-az2"
export PUBLIC_SUBNET_3="subnet-pub-az3"
export PRIVATE_SUBNET_1="subnet-priv-az1"
export PRIVATE_SUBNET_2="subnet-priv-az2"
export PRIVATE_SUBNET_3="subnet-priv-az3"

# 2. 创建安全组（详见 EC2 实例部署章节）
# 3. 启动 3 个 EC2 实例（详见 EC2 实例部署章节）
# 4. 安装 K3s 和 Higress（详见 Higress 集群安装章节）
# 5. 配置 ALB（详见 ALB 配置章节）
```

**架构图：**
```
                    Internet
                       |
                       v
              [Internet Gateway]
                       |
        +--------------+--------------+
        |              |              |
   [公有子网1]     [公有子网2]     [公有子网3]
     (AZ-1)         (AZ-2)         (AZ-3)
        |              |              |
        +------[Application LB]-------+
                       |
        +--------------+--------------+
        |              |              |
   [NAT GW 1]     [NAT GW 2]     [NAT GW 3]
        |              |              |
   [私有子网1]     [私有子网2]     [私有子网3]
     (AZ-1)         (AZ-2)         (AZ-3)
        |              |              |
   [EC2+Higress]  [EC2+Higress]  [EC2+Higress]
   (独立进程)      (独立进程)      (独立进程)
```

**说明：** Higress 以独立进程方式运行在 EC2 上，无需容器或 Kubernetes。

**继续阅读详细步骤 ↓**

---

## 环境要求

### VPC 网络要求

**现有 VPC 配置验证：**

本部署方案基于您已有的标准 VPC 架构：
- 3 个公有子网（跨 3 个可用区）
- 3 个私有子网（跨 3 个可用区）
- 每个私有子网已配置 NAT Gateway 路由

**VPC 基本要求：**
- CIDR 块：任意 /16 或 /20 网段均可
- 启用 DNS 主机名和 DNS 解析
- 已配置互联网网关（IGW）
- 跨越 3 个可用区（实现更高可用性）

**子网使用规划：**

1. **公有子网（Public Subnets）**
   - 数量：3 个（已有）
   - 用途：部署 Application Load Balancer (ALB)
   - 要求：路由表包含 IGW 路由（0.0.0.0/0 -> igw-xxx）

2. **私有子网（Private Subnets）**
   - 数量：3 个（已有）
   - 用途：部署 Higress EC2 实例（推荐使用全部 3 个子网实现跨 AZ 高可用）
   - 要求：路由表包含 NAT Gateway 路由（0.0.0.0/0 -> nat-xxx）✓ 已满足

### EC2 实例要求

**最低配置（测试环境）：**
- 实例类型：t3.medium
- vCPU：2 核
- 内存：4 GB
- 存储：50 GB gp3

**生产环境推荐配置：**
- 实例类型：c5.xlarge 或 c6i.xlarge
- vCPU：4 核
- 内存：8 GB
- 存储：100 GB gp3（IOPS 3000+）
- 实例数量：3 个（每个 AZ 部署 1 个，充分利用 3 个私有子网）

**操作系统：**
- Ubuntu 22.04 LTS 或 Amazon Linux 2023
- 内核版本：5.10+

### 其他依赖

- Kubernetes：v1.24+ 或使用 K3s
- Docker：20.10+
- Helm：v3.8+
- AWS CLI：v2.x

---

## 架构概述

```
Internet
    |
    v
[Internet Gateway]
    |
    v
[Application Load Balancer] (公有子网)
    |
    v
[Higress Gateway Pods] (私有子网 EC2)
    |
    v
[后端服务] (私有子网)
```

**高可用架构：**
- ALB 部署在 3 个公有子网，跨 3 个可用区
- Higress 实例分布在 3 个私有子网，每个 AZ 一个实例
- 使用 Auto Scaling Group（可选，用于自动故障恢复）

---

## 前置准备

### 1. 安装必要工具

在本地机器上安装：

```bash
# 安装 AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# 配置 AWS 凭证
aws configure

# 安装 kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# 安装 Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

### 2. 准备 SSH 密钥对

```bash
# 在 AWS 控制台创建或导入 EC2 密钥对
aws ec2 create-key-pair \
  --key-name higress-prod-key \
  --query 'KeyMaterial' \
  --output text > higress-prod-key.pem

chmod 400 higress-prod-key.pem
```

---

## VPC 和网络配置

### 使用现有 VPC 部署

您已有标准的 3 公有子网 + 3 私有子网架构，NAT Gateway 已配置完成。以下步骤用于验证和准备环境。

**1. 获取 VPC 和子网信息**

```bash
# 设置您的 VPC ID（替换为实际值）
export VPC_ID="vpc-xxxxxxxxx"

# 查看 VPC 信息
aws ec2 describe-vpcs --vpc-ids $VPC_ID

# 列出所有子网并记录 ID
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[*].[SubnetId,AvailabilityZone,CidrBlock,Tags[?Key==`Name`].Value|[0]]' \
  --output table

# 根据输出结果，设置子网变量
# 公有子网（用于 ALB）
export PUBLIC_SUBNET_1="subnet-xxxxxxxxx"  # AZ-1
export PUBLIC_SUBNET_2="subnet-xxxxxxxxx"  # AZ-2
export PUBLIC_SUBNET_3="subnet-xxxxxxxxx"  # AZ-3

# 私有子网（用于 Higress EC2 实例）
export PRIVATE_SUBNET_1="subnet-xxxxxxxxx"  # AZ-1
export PRIVATE_SUBNET_2="subnet-xxxxxxxxx"  # AZ-2
export PRIVATE_SUBNET_3="subnet-xxxxxxxxx"  # AZ-3
```

**2. 验证 VPC 配置**

```bash
# 确认 DNS 支持已启用（如未启用则执行）
aws ec2 modify-vpc-attribute \
  --vpc-id $VPC_ID \
  --enable-dns-hostnames

aws ec2 modify-vpc-attribute \
  --vpc-id $VPC_ID \
  --enable-dns-support

# 验证 DNS 配置
aws ec2 describe-vpc-attribute \
  --vpc-id $VPC_ID \
  --attribute enableDnsHostnames

aws ec2 describe-vpc-attribute \
  --vpc-id $VPC_ID \
  --attribute enableDnsSupport
```

**3. 验证子网路由配置**

```bash
# 检查公有子网路由表（应包含 IGW 路由）
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=$PUBLIC_SUBNET_1" \
  --query 'RouteTables[*].Routes[?GatewayId!=`local`]'

# 检查私有子网路由表（应包含 NAT Gateway 路由）
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=$PRIVATE_SUBNET_1" \
  --query 'RouteTables[*].Routes[?NatGatewayId!=`null`]'

# 验证所有 3 个私有子网都有 NAT Gateway 路由
for subnet in $PRIVATE_SUBNET_1 $PRIVATE_SUBNET_2 $PRIVATE_SUBNET_3; do
  echo "Checking subnet: $subnet"
  aws ec2 describe-route-tables \
    --filters "Name=association.subnet-id,Values=$subnet" \
    --query 'RouteTables[*].Routes[?NatGatewayId!=`null`].[DestinationCidrBlock,NatGatewayId]' \
    --output table
done
```

**4. 验证 NAT Gateway 状态**

```bash
# 列出所有 NAT Gateway
aws ec2 describe-nat-gateways \
  --filter "Name=vpc-id,Values=$VPC_ID" \
  --query 'NatGateways[*].[NatGatewayId,State,SubnetId]' \
  --output table

# 确保所有 NAT Gateway 状态为 "available"
```

**5. 创建配置文件（保存环境变量）**

```bash
# 创建配置文件以便后续使用
cat > higress-vpc-config.sh <<EOF
#!/bin/bash
# Higress VPC 配置

export VPC_ID="$VPC_ID"

# 公有子网
export PUBLIC_SUBNET_1="$PUBLIC_SUBNET_1"
export PUBLIC_SUBNET_2="$PUBLIC_SUBNET_2"
export PUBLIC_SUBNET_3="$PUBLIC_SUBNET_3"

# 私有子网
export PRIVATE_SUBNET_1="$PRIVATE_SUBNET_1"
export PRIVATE_SUBNET_2="$PRIVATE_SUBNET_2"
export PRIVATE_SUBNET_3="$PRIVATE_SUBNET_3"

# AWS 区域
export AWS_REGION="us-east-1"  # 根据实际情况修改

echo "VPC 配置已加载"
echo "VPC ID: $VPC_ID"
echo "公有子网: $PUBLIC_SUBNET_1, $PUBLIC_SUBNET_2, $PUBLIC_SUBNET_3"
echo "私有子网: $PRIVATE_SUBNET_1, $PRIVATE_SUBNET_2, $PRIVATE_SUBNET_3"
EOF

chmod +x higress-vpc-config.sh

# 后续步骤可以通过 source 命令加载配置
# source ./higress-vpc-config.sh
```

---

## EC2 实例部署

### 1. 创建安全组

**Higress 节点安全组：**

```bash
# 创建安全组
SG_HIGRESS=$(aws ec2 create-security-group \
  --group-name higress-nodes-sg \
  --description "Security group for Higress nodes" \
  --vpc-id $VPC_ID \
  --query 'GroupId' \
  --output text)

# 允许 SSH（仅从堡垒机或特定 IP）
aws ec2 authorize-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol tcp \
  --port 22 \
  --cidr 10.0.0.0/16

# 允许 Kubernetes API（6443）
aws ec2 authorize-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol tcp \
  --port 6443 \
  --cidr 10.0.0.0/16

# 允许 Higress Gateway（80, 443）
aws ec2 authorize-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol tcp \
  --port 80 \
  --source-group $SG_ALB

aws ec2 authorize-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol tcp \
  --port 443 \
  --source-group $SG_ALB

# 允许节点间通信
aws ec2 authorize-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol -1 \
  --source-group $SG_HIGRESS
```

**ALB 安全组：**

```bash
SG_ALB=$(aws ec2 create-security-group \
  --group-name higress-alb-sg \
  --description "Security group for Higress ALB" \
  --vpc-id $VPC_ID \
  --query 'GroupId' \
  --output text)

# 允许 HTTP/HTTPS 流量
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ALB \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id $SG_ALB \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0
```

### 2. 创建 IAM 角色

```bash
# 创建信任策略文件
cat > ec2-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# 创建 IAM 角色
aws iam create-role \
  --role-name HigressNodeRole \
  --assume-role-policy-document file://ec2-trust-policy.json

# 附加必要的策略
aws iam attach-role-policy \
  --role-name HigressNodeRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

# 创建实例配置文件
aws iam create-instance-profile \
  --instance-profile-name HigressNodeProfile

aws iam add-role-to-instance-profile \
  --instance-profile-name HigressNodeProfile \
  --role-name HigressNodeRole
```

### 3. 启动 EC2 实例

**创建用户数据脚本（user-data.sh）：**

```bash
cat > user-data.sh <<'EOF'
#!/bin/bash
set -e

# 更新系统
apt-get update && apt-get upgrade -y

# 安装基础工具
apt-get install -y curl wget git vim htop

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker ubuntu

# 配置 Docker daemon
cat > /etc/docker/daemon.json <<DOCKER_EOF
{
  "exec-opts": ["native.cgroupdriver=systemd"],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
DOCKER_EOF

systemctl restart docker
systemctl enable docker

# 禁用 swap
swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab

# 配置内核参数
cat > /etc/sysctl.d/k8s.conf <<SYSCTL_EOF
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
SYSCTL_EOF

modprobe br_netfilter
sysctl --system

echo "EC2 instance initialization completed"
EOF
```

**提示：** 如果需要通过 SSH 访问私有子网中的实例，建议配置堡垒机（Bastion Host）或使用 AWS Systems Manager Session Manager。

**启动实例：**

```bash
# 加载 VPC 配置
source ./higress-vpc-config.sh

# 获取最新的 Ubuntu 22.04 AMI
AMI_ID=$(aws ec2 describe-images \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
  --output text)

# 启动第一个实例（Master 节点 - AZ1）
INSTANCE_1=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type c5.xlarge \
  --key-name higress-prod-key \
  --security-group-ids $SG_HIGRESS \
  --subnet-id $PRIVATE_SUBNET_1 \
  --iam-instance-profile Name=HigressNodeProfile \
  --user-data file://user-data.sh \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=100,VolumeType=gp3,Iops=3000}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=higress-master-az1},{Key=Role,Value=master},{Key=AZ,Value=az1}]' \
  --query 'Instances[0].InstanceId' \
  --output text)

# 启动 Worker 节点 - AZ2
INSTANCE_2=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type c5.xlarge \
  --key-name higress-prod-key \
  --security-group-ids $SG_HIGRESS \
  --subnet-id $PRIVATE_SUBNET_2 \
  --iam-instance-profile Name=HigressNodeProfile \
  --user-data file://user-data.sh \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=100,VolumeType=gp3,Iops=3000}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=higress-worker-az2},{Key=Role,Value=worker},{Key=AZ,Value=az2}]' \
  --query 'Instances[0].InstanceId' \
  --output text)

# 启动 Worker 节点 - AZ3
INSTANCE_3=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type c5.xlarge \
  --key-name higress-prod-key \
  --security-group-ids $SG_HIGRESS \
  --subnet-id $PRIVATE_SUBNET_3 \
  --iam-instance-profile Name=HigressNodeProfile \
  --user-data file://user-data.sh \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=100,VolumeType=gp3,Iops=3000}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=higress-worker-az3},{Key=Role,Value=worker},{Key=AZ,Value=az3}]' \
  --query 'Instances[0].InstanceId' \
  --output text)

# 等待实例启动
aws ec2 wait instance-running --instance-ids $INSTANCE_1 $INSTANCE_2 $INSTANCE_3

# 获取私有 IP
MASTER_IP=$(aws ec2 describe-instances \
  --instance-ids $INSTANCE_1 \
  --query 'Reservations[0].Instances[0].PrivateIpAddress' \
  --output text)

echo "Master node IP: $MASTER_IP"
```

---

## Higress 集群安装

### 1. 安装 K3s（轻量级 Kubernetes）

**在 Master 节点上：**

```bash
# SSH 到 Master 节点（通过堡垒机或 Session Manager）
ssh -i higress-prod-key.pem ubuntu@$MASTER_IP

# 安装 K3s Master
curl -sfL https://get.k3s.io | sh -s - server \
  --disable traefik \
  --disable servicelb \
  --write-kubeconfig-mode 644 \
  --node-taint CriticalAddonsOnly=true:NoExecute \
  --tls-san $MASTER_IP

# 获取 token
sudo cat /var/lib/rancher/k3s/server/node-token
# 保存输出的 token，后续 worker 节点加入需要使用
```

**在 Worker 节点上：**

```bash
# SSH 到每个 Worker 节点
ssh -i higress-prod-key.pem ubuntu@<WORKER_IP>

# 加入集群（替换 MASTER_IP 和 TOKEN）
curl -sfL https://get.k3s.io | K3S_URL=https://<MASTER_IP>:6443 \
  K3S_TOKEN=<TOKEN> sh -
```

**验证集群：**

```bash
# 在 Master 节点上
sudo kubectl get nodes

# 应该看到所有节点状态为 Ready
```

### 2. 安装 Helm

```bash
# 在 Master 节点上
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

### 3. 安装 Higress

```bash
# 添加 Higress Helm 仓库
helm repo add higress.io https://higress.io/helm-charts
helm repo update

# 创建命名空间
kubectl create namespace higress-system

# 创建 Higress 配置文件
cat > higress-values.yaml <<EOF
global:
  # 生产环境配置
  local: false
  
higress-core:
  gateway:
    replicas: 3
    resources:
      requests:
        cpu: 1000m
        memory: 2Gi
      limits:
        cpu: 2000m
        memory: 4Gi
    
    # 使用 NodePort 类型，后续通过 ALB 访问
    service:
      type: NodePort
      ports:
        - name: http
          port: 80
          targetPort: 80
          nodePort: 30080
        - name: https
          port: 443
          targetPort: 443
          nodePort: 30443
    
    # 高可用配置
    podDisruptionBudget:
      enabled: true
      minAvailable: 2
    
    # 反亲和性，确保 Pod 分散在不同节点
    affinity:
      podAntiAffinity:
        preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 100
          podAffinityTerm:
            labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values:
                - higress-gateway
            topologyKey: kubernetes.io/hostname

  controller:
    replicas: 2
    resources:
      requests:
        cpu: 500m
        memory: 1Gi
      limits:
        cpu: 1000m
        memory: 2Gi

higress-console:
  enabled: true
  replicas: 2
  service:
    type: NodePort
    nodePort: 30880

# 启用监控
monitoring:
  enabled: true
EOF

# 安装 Higress
helm install higress higress.io/higress \
  -n higress-system \
  -f higress-values.yaml

# 等待所有 Pod 就绪
kubectl wait --for=condition=ready pod \
  -l app=higress-gateway \
  -n higress-system \
  --timeout=300s

# 验证安装
kubectl get pods -n higress-system
kubectl get svc -n higress-system
```

**预期输出：**
```
NAME                                READY   STATUS    RESTARTS   AGE
higress-gateway-xxxxxxxxx-xxxxx     1/1     Running   0          2m
higress-gateway-xxxxxxxxx-xxxxx     1/1     Running   0          2m
higress-gateway-xxxxxxxxx-xxxxx     1/1     Running   0          2m
higress-controller-xxxxxxxxx-xxxxx  1/1     Running   0          2m
higress-controller-xxxxxxxxx-xxxxx  1/1     Running   0          2m
higress-console-xxxxxxxxx-xxxxx     1/1     Running   0          2m
```

---

## ALB 配置

### 1. 创建目标组

```bash
# 创建 HTTP 目标组
TG_HTTP=$(aws elbv2 create-target-group \
  --name higress-http-tg \
  --protocol HTTP \
  --port 30080 \
  --vpc-id $VPC_ID \
  --health-check-enabled \
  --health-check-protocol HTTP \
  --health-check-path /healthz \
  --health-check-interval-seconds 30 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

# 创建 HTTPS 目标组
TG_HTTPS=$(aws elbv2 create-target-group \
  --name higress-https-tg \
  --protocol HTTPS \
  --port 30443 \
  --vpc-id $VPC_ID \
  --health-check-enabled \
  --health-check-protocol HTTPS \
  --health-check-path /healthz \
  --health-check-interval-seconds 30 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

# 注册 EC2 实例到目标组
aws elbv2 register-targets \
  --target-group-arn $TG_HTTP \
  --targets Id=$INSTANCE_1 Id=$INSTANCE_2 Id=$INSTANCE_3

aws elbv2 register-targets \
  --target-group-arn $TG_HTTPS \
  --targets Id=$INSTANCE_1 Id=$INSTANCE_2 Id=$INSTANCE_3
```

### 2. 创建 Application Load Balancer

```bash
# 创建 ALB（跨 3 个公有子网，实现 3-AZ 高可用）
ALB_ARN=$(aws elbv2 create-load-balancer \
  --name higress-alb \
  --subnets $PUBLIC_SUBNET_1 $PUBLIC_SUBNET_2 $PUBLIC_SUBNET_3 \
  --security-groups $SG_ALB \
  --scheme internet-facing \
  --type application \
  --ip-address-type ipv4 \
  --tags Key=Name,Value=higress-alb Key=Environment,Value=production \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text)

# 获取 ALB DNS 名称
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --load-balancer-arns $ALB_ARN \
  --query 'LoadBalancers[0].DNSName' \
  --output text)

echo "ALB DNS: $ALB_DNS"
```

### 3. 配置监听器

**HTTP 监听器（重定向到 HTTPS）：**

```bash
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=redirect,RedirectConfig="{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}"
```

**HTTPS 监听器（需要 SSL 证书）：**

```bash
# 方式 1：使用 ACM 证书（推荐）
# 首先在 ACM 中申请或导入证书
CERT_ARN="arn:aws:acm:region:account-id:certificate/certificate-id"

aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=$CERT_ARN \
  --ssl-policy ELBSecurityPolicy-TLS-1-2-2017-01 \
  --default-actions Type=forward,TargetGroupArn=$TG_HTTPS

# 方式 2：如果暂时没有证书，可以先使用 HTTP
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TG_HTTP
```

### 4. 配置 SSL 证书（使用 ACM）

```bash
# 申请证书
aws acm request-certificate \
  --domain-name yourdomain.com \
  --subject-alternative-names *.yourdomain.com \
  --validation-method DNS

# 或导入现有证书
aws acm import-certificate \
  --certificate fileb://certificate.crt \
  --private-key fileb://private.key \
  --certificate-chain fileb://ca-bundle.crt
```

### 5. 配置访问日志（可选但推荐）

```bash
# 创建 S3 存储桶
aws s3 mb s3://higress-alb-logs-$(date +%s)

# 配置存储桶策略
cat > bucket-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::127311923021:root"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::higress-alb-logs-*/AWSLogs/*"
    }
  ]
}
EOF

aws s3api put-bucket-policy \
  --bucket higress-alb-logs-xxxxx \
  --policy file://bucket-policy.json

# 启用 ALB 访问日志
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn $ALB_ARN \
  --attributes Key=access_logs.s3.enabled,Value=true \
              Key=access_logs.s3.bucket,Value=higress-alb-logs-xxxxx
```

---

## 安全加固

### 1. 配置 WAF（可选）

```bash
# 创建 Web ACL
aws wafv2 create-web-acl \
  --name higress-waf \
  --scope REGIONAL \
  --default-action Allow={} \
  --rules file://waf-rules.json \
  --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=higressWAF

# 关联到 ALB
aws wafv2 associate-web-acl \
  --web-acl-arn <WAF_ACL_ARN> \
  --resource-arn $ALB_ARN
```

### 2. 配置安全组规则优化

```bash
# 限制 SSH 访问仅来自堡垒机
aws ec2 revoke-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol tcp \
  --port 22 \
  --cidr 10.0.0.0/16

aws ec2 authorize-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol tcp \
  --port 22 \
  --source-group <BASTION_SG_ID>
```

### 3. 启用 VPC Flow Logs

```bash
# 创建 CloudWatch 日志组
aws logs create-log-group --log-group-name /aws/vpc/higress

# 创建 IAM 角色
cat > vpc-flow-logs-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "vpc-flow-logs.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name VPCFlowLogsRole \
  --assume-role-policy-document file://vpc-flow-logs-trust-policy.json

# 启用 Flow Logs
aws ec2 create-flow-logs \
  --resource-type VPC \
  --resource-ids $VPC_ID \
  --traffic-type ALL \
  --log-destination-type cloud-watch-logs \
  --log-group-name /aws/vpc/higress \
  --deliver-logs-permission-arn arn:aws:iam::ACCOUNT_ID:role/VPCFlowLogsRole
```

### 4. 配置 Secrets Manager（存储敏感信息）

```bash
# 存储数据库密码等敏感信息
aws secretsmanager create-secret \
  --name higress/prod/db-password \
  --secret-string "your-secure-password"

# 在应用中引用
kubectl create secret generic db-credentials \
  --from-literal=password=$(aws secretsmanager get-secret-value \
    --secret-id higress/prod/db-password \
    --query SecretString \
    --output text)
```

---

## 监控和日志

### 1. 配置 CloudWatch 监控

```bash
# 在 EC2 实例上安装 CloudWatch Agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb

# 配置 CloudWatch Agent
cat > /opt/aws/amazon-cloudwatch-agent/etc/config.json <<EOF
{
  "metrics": {
    "namespace": "Higress/Production",
    "metrics_collected": {
      "cpu": {
        "measurement": [
          {"name": "cpu_usage_idle", "rename": "CPU_IDLE", "unit": "Percent"}
        ],
        "totalcpu": false
      },
      "disk": {
        "measurement": [
          {"name": "used_percent", "rename": "DISK_USED", "unit": "Percent"}
        ],
        "resources": ["*"]
      },
      "mem": {
        "measurement": [
          {"name": "mem_used_percent", "rename": "MEM_USED", "unit": "Percent"}
        ]
      }
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/syslog",
            "log_group_name": "/aws/ec2/higress/syslog",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  }
}
EOF

# 启动 CloudWatch Agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/config.json
```

### 2. 配置 Kubernetes 日志收集

```bash
# 安装 Fluent Bit
kubectl apply -f https://raw.githubusercontent.com/fluent/fluent-bit-kubernetes-logging/master/fluent-bit-service-account.yaml
kubectl apply -f https://raw.githubusercontent.com/fluent/fluent-bit-kubernetes-logging/master/fluent-bit-role.yaml
kubectl apply -f https://raw.githubusercontent.com/fluent/fluent-bit-kubernetes-logging/master/fluent-bit-role-binding.yaml

# 配置 Fluent Bit 发送到 CloudWatch
cat > fluent-bit-configmap.yaml <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluent-bit-config
  namespace: kube-system
data:
  fluent-bit.conf: |
    [SERVICE]
        Flush         5
        Log_Level     info
        Daemon        off

    [INPUT]
        Name              tail
        Path              /var/log/containers/higress*.log
        Parser            docker
        Tag               kube.*
        Refresh_Interval  5

    [OUTPUT]
        Name cloudwatch_logs
        Match   kube.*
        region  us-east-1
        log_group_name /aws/eks/higress
        log_stream_prefix higress-
        auto_create_group true
EOF

kubectl apply -f fluent-bit-configmap.yaml
```

### 3. 配置 Prometheus 和 Grafana（可选）

```bash
# 安装 Prometheus
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/kube-prometheus-stack \
  -n monitoring \
  --create-namespace \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false

# 访问 Grafana
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80

# 默认用户名: admin
# 获取密码:
kubectl get secret -n monitoring prometheus-grafana -o jsonpath="{.data.admin-password}" | base64 --decode
```

### 4. 配置告警

```bash
# 创建 SNS 主题
aws sns create-topic --name higress-alerts

# 订阅邮件通知
aws sns subscribe \
  --topic-arn arn:aws:sns:region:account-id:higress-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com

# 创建 CloudWatch 告警
aws cloudwatch put-metric-alarm \
  --alarm-name higress-high-cpu \
  --alarm-description "Alert when CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:region:account-id:higress-alerts
```

---

## 故障排查

### 常见问题

**1. Pod 无法启动**

```bash
# 查看 Pod 状态
kubectl get pods -n higress-system

# 查看详细信息
kubectl describe pod <pod-name> -n higress-system

# 查看日志
kubectl logs <pod-name> -n higress-system
```

**2. ALB 健康检查失败**

```bash
# 检查目标组健康状态
aws elbv2 describe-target-health --target-group-arn $TG_HTTP

# 在 EC2 实例上测试健康检查端点
curl http://localhost:30080/healthz

# 检查安全组规则
aws ec2 describe-security-groups --group-ids $SG_HIGRESS
```

**3. 无法访问服务**

```bash
# 检查 ALB 状态
aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN

# 测试从 EC2 到 Higress 的连接
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://higress-gateway.higress-system.svc.cluster.local

# 检查 DNS 解析
nslookup $ALB_DNS
```

**4. 节点间通信问题**

```bash
# 检查网络插件
kubectl get pods -n kube-system | grep -E 'flannel|calico|weave'

# 测试节点间连通性
ping <other-node-ip>

# 检查防火墙规则
sudo iptables -L -n
```

### 日志位置

- K3s 日志: `journalctl -u k3s`
- Docker 日志: `journalctl -u docker`
- Higress 日志: `kubectl logs -n higress-system -l app=higress-gateway`
- 系统日志: `/var/log/syslog`

### 性能调优

**1. 调整 Higress Gateway 资源**

```bash
kubectl edit deployment higress-gateway -n higress-system

# 增加 CPU 和内存限制
resources:
  requests:
    cpu: 2000m
    memory: 4Gi
  limits:
    cpu: 4000m
    memory: 8Gi
```

**2. 调整连接数限制**

```bash
# 编辑 Higress ConfigMap
kubectl edit configmap higress-config -n higress-system

# 添加配置
data:
  max-connections: "10000"
  max-requests-per-connection: "1000"
```

**3. 启用 HTTP/2**

```yaml
# 在 Higress values.yaml 中
gateway:
  env:
    - name: ISTIO_META_HTTP10
      value: "0"
```

---

## 备份和恢复

### 备份 etcd（K3s）

```bash
# K3s 自动备份到 /var/lib/rancher/k3s/server/db/snapshots/
sudo ls -lh /var/lib/rancher/k3s/server/db/snapshots/

# 手动创建快照
sudo k3s etcd-snapshot save --name manual-backup-$(date +%Y%m%d-%H%M%S)

# 复制到 S3
aws s3 cp /var/lib/rancher/k3s/server/db/snapshots/ \
  s3://higress-backups/etcd/ --recursive
```

### 恢复集群

```bash
# 停止 K3s
sudo systemctl stop k3s

# 恢复快照
sudo k3s server \
  --cluster-reset \
  --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/snapshot-file

# 重启 K3s
sudo systemctl start k3s
```

---

## 生产环境检查清单

### 部署前检查

- [ ] VPC 配置正确（DNS 启用、跨多 AZ）
- [ ] 子网配置正确（公有/私有子网、路由表）
- [ ] NAT Gateway 已配置
- [ ] 安全组规则最小化
- [ ] IAM 角色和策略配置正确
- [ ] SSL 证书已申请并验证
- [ ] 监控和告警已配置
- [ ] 日志收集已启用
- [ ] 备份策略已制定

### 部署后验证

- [ ] 所有 EC2 实例运行正常
- [ ] Kubernetes 集群健康
- [ ] Higress Pod 全部 Running
- [ ] ALB 健康检查通过
- [ ] 可以通过 ALB DNS 访问服务
- [ ] SSL 证书工作正常
- [ ] 监控数据正常上报
- [ ] 日志正常收集
- [ ] 告警测试通过

### 安全检查

- [ ] 最小权限原则
- [ ] 敏感信息使用 Secrets Manager
- [ ] 启用 VPC Flow Logs
- [ ] 启用 ALB 访问日志
- [ ] 配置 WAF（如需要）
- [ ] 定期更新系统和软件包
- [ ] 定期审计安全组规则

---

## 成本优化建议

1. **使用 Savings Plans 或 Reserved Instances**
   - 对于长期运行的实例，可节省 30-70% 成本

2. **使用 Spot Instances（非生产环境）**
   - Worker 节点可以考虑使用 Spot 实例

3. **优化 EBS 卷**
   - 使用 gp3 替代 gp2
   - 定期清理未使用的快照

4. **配置 Auto Scaling**
   - 根据负载自动调整实例数量

5. **使用 S3 生命周期策略**
   - 自动归档旧日志到 Glacier

---

## 附录

### A. 完整部署脚本（适用于已有 VPC）

将以下脚本保存为 `higress-deploy.sh`，用于自动化部署：

```bash
#!/bin/bash
# higress-deploy.sh - Higress 在已有 VPC 上的完整部署脚本

set -e

echo "=========================================="
echo "Higress AWS 部署脚本"
echo "=========================================="

# ============ 配置变量 ============
# 请根据您的实际环境修改以下变量

export AWS_REGION="us-east-1"
export VPC_ID="vpc-xxxxxxxxx"

# 公有子网（用于 ALB）
export PUBLIC_SUBNET_1="subnet-xxxxxxxxx"  # AZ-1
export PUBLIC_SUBNET_2="subnet-xxxxxxxxx"  # AZ-2
export PUBLIC_SUBNET_3="subnet-xxxxxxxxx"  # AZ-3

# 私有子网（用于 EC2）
export PRIVATE_SUBNET_1="subnet-xxxxxxxxx"  # AZ-1
export PRIVATE_SUBNET_2="subnet-xxxxxxxxx"  # AZ-2
export PRIVATE_SUBNET_3="subnet-xxxxxxxxx"  # AZ-3

# EC2 配置
export KEY_NAME="higress-prod-key"
export INSTANCE_TYPE="c5.xlarge"

# ============ 验证配置 ============
echo "验证 VPC 配置..."
aws ec2 describe-vpcs --vpc-ids $VPC_ID > /dev/null 2>&1 || {
  echo "错误: VPC $VPC_ID 不存在"
  exit 1
}

echo "验证子网配置..."
for subnet in $PUBLIC_SUBNET_1 $PUBLIC_SUBNET_2 $PUBLIC_SUBNET_3 \
              $PRIVATE_SUBNET_1 $PRIVATE_SUBNET_2 $PRIVATE_SUBNET_3; do
  aws ec2 describe-subnets --subnet-ids $subnet > /dev/null 2>&1 || {
    echo "错误: 子网 $subnet 不存在"
    exit 1
  }
done

echo "✓ VPC 和子网验证通过"

# ============ 创建安全组 ============
echo ""
echo "创建安全组..."

# Higress 节点安全组
SG_HIGRESS=$(aws ec2 create-security-group \
  --group-name higress-nodes-sg-$(date +%s) \
  --description "Security group for Higress nodes" \
  --vpc-id $VPC_ID \
  --query 'GroupId' \
  --output text)

echo "✓ Higress 安全组创建: $SG_HIGRESS"

# ALB 安全组
SG_ALB=$(aws ec2 create-security-group \
  --group-name higress-alb-sg-$(date +%s) \
  --description "Security group for Higress ALB" \
  --vpc-id $VPC_ID \
  --query 'GroupId' \
  --output text)

echo "✓ ALB 安全组创建: $SG_ALB"

# 配置安全组规则
echo "配置安全组规则..."

# ALB 安全组规则
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ALB \
  --protocol tcp --port 80 --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id $SG_ALB \
  --protocol tcp --port 443 --cidr 0.0.0.0/0

# Higress 节点安全组规则
aws ec2 authorize-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol tcp --port 22 --cidr 10.0.0.0/8

aws ec2 authorize-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol tcp --port 6443 --cidr 10.0.0.0/8

aws ec2 authorize-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol tcp --port 80 --source-group $SG_ALB

aws ec2 authorize-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol tcp --port 443 --source-group $SG_ALB

aws ec2 authorize-security-group-ingress \
  --group-id $SG_HIGRESS \
  --protocol -1 --source-group $SG_HIGRESS

echo "✓ 安全组规则配置完成"

# ============ 创建 IAM 角色 ============
echo ""
echo "创建 IAM 角色..."

ROLE_NAME="HigressNodeRole-$(date +%s)"
PROFILE_NAME="HigressNodeProfile-$(date +%s)"

cat > /tmp/ec2-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ec2.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name $ROLE_NAME \
  --assume-role-policy-document file:///tmp/ec2-trust-policy.json

aws iam attach-role-policy \
  --role-name $ROLE_NAME \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

aws iam create-instance-profile --instance-profile-name $PROFILE_NAME
aws iam add-role-to-instance-profile \
  --instance-profile-name $PROFILE_NAME \
  --role-name $ROLE_NAME

echo "✓ IAM 角色创建: $ROLE_NAME"
echo "等待 IAM 角色生效..."
sleep 10

# ============ 启动 EC2 实例 ============
echo ""
echo "启动 EC2 实例..."

# 获取最新 Ubuntu AMI
AMI_ID=$(aws ec2 describe-images \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
  --output text)

echo "使用 AMI: $AMI_ID"

# 创建用户数据脚本
cat > /tmp/user-data.sh <<'EOF'
#!/bin/bash
apt-get update && apt-get upgrade -y
apt-get install -y curl wget git
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu
systemctl enable docker
swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab
EOF

# 启动实例
INSTANCE_1=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type $INSTANCE_TYPE \
  --key-name $KEY_NAME \
  --security-group-ids $SG_HIGRESS \
  --subnet-id $PRIVATE_SUBNET_1 \
  --iam-instance-profile Name=$PROFILE_NAME \
  --user-data file:///tmp/user-data.sh \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=100,VolumeType=gp3}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=higress-az1}]' \
  --query 'Instances[0].InstanceId' \
  --output text)

INSTANCE_2=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type $INSTANCE_TYPE \
  --key-name $KEY_NAME \
  --security-group-ids $SG_HIGRESS \
  --subnet-id $PRIVATE_SUBNET_2 \
  --iam-instance-profile Name=$PROFILE_NAME \
  --user-data file:///tmp/user-data.sh \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=100,VolumeType=gp3}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=higress-az2}]' \
  --query 'Instances[0].InstanceId' \
  --output text)

INSTANCE_3=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type $INSTANCE_TYPE \
  --key-name $KEY_NAME \
  --security-group-ids $SG_HIGRESS \
  --subnet-id $PRIVATE_SUBNET_3 \
  --iam-instance-profile Name=$PROFILE_NAME \
  --user-data file:///tmp/user-data.sh \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=100,VolumeType=gp3}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=higress-az3}]' \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "✓ 实例已启动:"
echo "  - $INSTANCE_1 (AZ-1)"
echo "  - $INSTANCE_2 (AZ-2)"
echo "  - $INSTANCE_3 (AZ-3)"

echo "等待实例运行..."
aws ec2 wait instance-running --instance-ids $INSTANCE_1 $INSTANCE_2 $INSTANCE_3

# ============ 创建 ALB ============
echo ""
echo "创建 Application Load Balancer..."

# 创建目标组
TG_HTTP=$(aws elbv2 create-target-group \
  --name higress-http-tg-$(date +%s | tail -c 6) \
  --protocol HTTP \
  --port 30080 \
  --vpc-id $VPC_ID \
  --health-check-path /healthz \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

echo "✓ 目标组创建: $TG_HTTP"

# 注册实例
aws elbv2 register-targets \
  --target-group-arn $TG_HTTP \
  --targets Id=$INSTANCE_1 Id=$INSTANCE_2 Id=$INSTANCE_3

echo "✓ 实例已注册到目标组"

# 创建 ALB
ALB_ARN=$(aws elbv2 create-load-balancer \
  --name higress-alb-$(date +%s | tail -c 6) \
  --subnets $PUBLIC_SUBNET_1 $PUBLIC_SUBNET_2 $PUBLIC_SUBNET_3 \
  --security-groups $SG_ALB \
  --scheme internet-facing \
  --type application \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text)

echo "✓ ALB 创建: $ALB_ARN"

# 创建监听器
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TG_HTTP

echo "✓ 监听器配置完成"

# 获取 ALB DNS
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --load-balancer-arns $ALB_ARN \
  --query 'LoadBalancers[0].DNSName' \
  --output text)

# ============ 输出部署信息 ============
echo ""
echo ""
echo "资源信息："
echo "  VPC ID: $VPC_ID"
echo "  ALB 安全组: $SG_ALB"
echo "  Higress 安全组: $SG_HIGRESS"
echo "  IAM 角色: $ROLE_NAME"
echo ""
echo "EC2 实例："
echo "  实例 1: $INSTANCE_1"
echo "  实例 2: $INSTANCE_2"
echo "  实例 3: $INSTANCE_3"
echo ""
echo "负载均衡器："
echo "  ALB ARN: $ALB_ARN"
echo "  ALB DNS: $ALB_DNS"
echo "  目标组: $TG_HTTP"
echo ""
echo "下一步："
echo "  1. 等待 EC2 实例初始化完成（约 5 分钟）"
echo "  2. 通过 Session Manager 连接到实例"
echo "  3. 安装 K3s 和 Higress（参考文档）"
echo "  4. 访问 http://$ALB_DNS 测试"
echo ""
echo "保存配置到文件..."

cat > higress-deployment-info.txt <<DEPLOY_EOF
# Higress 部署信息
# 生成时间: $(date)

VPC_ID=$VPC_ID
SG_ALB=$SG_ALB
SG_HIGRESS=$SG_HIGRESS
IAM_ROLE=$ROLE_NAME
IAM_PROFILE=$PROFILE_NAME

INSTANCE_1=$INSTANCE_1
INSTANCE_2=$INSTANCE_2
INSTANCE_3=$INSTANCE_3

ALB_ARN=$ALB_ARN
ALB_DNS=$ALB_DNS
TG_HTTP=$TG_HTTP

PUBLIC_SUBNET_1=$PUBLIC_SUBNET_1
PUBLIC_SUBNET_2=$PUBLIC_SUBNET_2
PUBLIC_SUBNET_3=$PUBLIC_SUBNET_3

PRIVATE_SUBNET_1=$PRIVATE_SUBNET_1
PRIVATE_SUBNET_2=$PRIVATE_SUBNET_2
PRIVATE_SUBNET_3=$PRIVATE_SUBNET_3
DEPLOY_EOF

echo "✓ 配置已保存到 higress-deployment-info.txt"
echo ""
```

**使用方法：**

```bash
# 1. 编辑脚本，填入您的 VPC 和子网 ID
vim higress-deploy.sh

# 2. 添加执行权限
chmod +x higress-deploy.sh

# 3. 执行部署
./higress-deploy.sh

# 4. 部署完成后，查看生成的配置文件
cat higress-deployment-info.txt
```h

### B. Terraform 模板（可选）

对于基础设施即代码，可以使用 Terraform：

```hcl
# main.tf
provider "aws" {
  region = var.aws_region
}

module "vpc" {
  source = "./modules/vpc"
  # VPC 配置
}

module "ec2" {
  source = "./modules/ec2"
  # EC2 配置
}

module "alb" {
  source = "./modules/alb"
  # ALB 配置
}
```

### C. 参考链接

- Higress 官方文档: https://higress.io/
- AWS VPC 最佳实践: https://docs.aws.amazon.com/vpc/
- K3s 文档: https://docs.k3s.io/
- Kubernetes 生产最佳实践: https://kubernetes.io/docs/setup/best-practices/

---

## 总结

本文档提供了在 AWS EC2 上部署 Higress 生产集群的完整指南，包括：

- 详细的网络架构和要求
- 分步部署说明
- ALB 配置和 SSL 证书管理
- 安全加固措施
- 监控和日志方案
- 故障排查指南

按照本文档操作，您可以在 AWS 上搭建一个高可用、安全、可监控的 Higress 生产环境。

**重要提示：**
- 请根据实际情况调整配置参数
- 生产环境部署前务必在测试环境验证
- 定期备份和更新系统
- 遵循安全最佳实践

如有问题，请参考故障排查章节或联系技术支持。
