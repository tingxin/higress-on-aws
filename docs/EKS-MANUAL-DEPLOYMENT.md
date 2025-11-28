# Higress 生产集群 AWS EKS 部署指南

## 目录
- [快速开始](#快速开始)
- [环境要求](#环境要求)
- [架构概述](#架构概述)
- [前置准备](#前置准备)
- [创建 EKS 集群](#创建-eks-集群)
- [配置 ALB Ingress Controller](#配置-alb-ingress-controller)
- [部署 Higress](#部署-higress)
- [配置 ALB](#配置-alb)
- [安全加固](#安全加固)
- [监控和日志](#监控和日志)
- [故障排查](#故障排查)
- [成本优化](#成本优化)

---

## 快速开始

**适用场景：** 在现有 VPC（3 公有子网 + 3 私有子网）中部署 Higress 生产集群

**部署概览：**
1. 在现有 VPC 中创建 EKS 集群
2. 配置 EKS 节点组（在私有子网中）
3. 安装 AWS Load Balancer Controller
4. 部署 Higress
5. 通过 ALB 暴露服务

**预计部署时间：** 40-60 分钟

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
   [EKS Node]     [EKS Node]     [EKS Node]
   [Higress Pod]  [Higress Pod]  [Higress Pod]
```

---

## 环境要求

### VPC 网络要求

**现有 VPC 配置验证：**
- ✅ 3 个公有子网（跨 3 个可用区）
- ✅ 3 个私有子网（跨 3 个可用区）
- ✅ 每个私有子网已配置 NAT Gateway
- ✅ DNS 主机名和 DNS 解析已启用

**子网标签要求（EKS 必需）：**

公有子网需要添加：
```
kubernetes.io/role/elb = 1
kubernetes.io/cluster/<cluster-name> = shared
```

私有子网需要添加：
```
kubernetes.io/role/internal-elb = 1
kubernetes.io/cluster/<cluster-name> = shared
```

### EKS 集群要求

**最低配置（测试环境）：**
- Kubernetes 版本：1.28+
- 节点数量：2 个
- 节点类型：t3.medium
- vCPU：2 核/节点
- 内存：4 GB/节点

**生产环境推荐配置：**
- Kubernetes 版本：1.28+ 或 1.29+
- 节点数量：3 个（每个 AZ 一个）
- 节点类型：c6i.xlarge 或 c7i.xlarge
- vCPU：4 核/节点
- 内存：8 GB/节点
- 存储：100 GB gp3

### 本地工具要求

- AWS CLI：v2.x
- kubectl：v1.28+
- eksctl：v0.170.0+
- Helm：v3.10+

---

## 前置准备

### 1. 安装必要工具

```bash
# 安装 AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# 配置 AWS 凭证
aws configure
# 输入 Access Key ID、Secret Access Key、Region 等信息

# 安装 kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
kubectl version --client

# 安装 eksctl
curl --silent --location "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin
eksctl version

# 安装 Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

### 2. 设置环境变量

```bash
# 创建配置文件
cat > higress-eks-config.sh <<'EOF'
#!/bin/bash

# AWS 配置
export AWS_REGION="us-east-1"  # 根据实际情况修改
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# VPC 配置（替换为您的实际值）
export VPC_ID="vpc-xxxxxxxxx"
export PUBLIC_SUBNET_1="subnet-xxxxxxxxx"  # AZ-1
export PUBLIC_SUBNET_2="subnet-xxxxxxxxx"  # AZ-2
export PUBLIC_SUBNET_3="subnet-xxxxxxxxx"  # AZ-3
export PRIVATE_SUBNET_1="subnet-xxxxxxxxx"  # AZ-1
export PRIVATE_SUBNET_2="subnet-xxxxxxxxx"  # AZ-2
export PRIVATE_SUBNET_3="subnet-xxxxxxxxx"  # AZ-3

# EKS 集群配置
export CLUSTER_NAME="higress-prod"
export K8S_VERSION="1.29"

echo "配置已加载"
echo "AWS Region: $AWS_REGION"
echo "AWS Account: $AWS_ACCOUNT_ID"
echo "VPC ID: $VPC_ID"
echo "Cluster Name: $CLUSTER_NAME"
EOF

chmod +x higress-eks-config.sh
source ./higress-eks-config.sh
```

### 3. 验证 VPC 配置

```bash
# 验证 VPC 存在
aws ec2 describe-vpcs --vpc-ids $VPC_ID

# 验证子网
aws ec2 describe-subnets \
  --subnet-ids $PUBLIC_SUBNET_1 $PUBLIC_SUBNET_2 $PUBLIC_SUBNET_3 \
               $PRIVATE_SUBNET_1 $PRIVATE_SUBNET_2 $PRIVATE_SUBNET_3 \
  --query 'Subnets[*].[SubnetId,AvailabilityZone,CidrBlock,MapPublicIpOnLaunch]' \
  --output table
```

---

## 创建 EKS 集群

### 方案 A：使用 eksctl（推荐）

**1. 为子网添加必要标签**

```bash
# 为公有子网添加标签
for subnet in $PUBLIC_SUBNET_1 $PUBLIC_SUBNET_2 $PUBLIC_SUBNET_3; do
  aws ec2 create-tags --resources $subnet \
    --tags Key=kubernetes.io/role/elb,Value=1 \
           Key=kubernetes.io/cluster/$CLUSTER_NAME,Value=shared
done

# 为私有子网添加标签
for subnet in $PRIVATE_SUBNET_1 $PRIVATE_SUBNET_2 $PRIVATE_SUBNET_3; do
  aws ec2 create-tags --resources $subnet \
    --tags Key=kubernetes.io/role/internal-elb,Value=1 \
           Key=kubernetes.io/cluster/$CLUSTER_NAME,Value=shared
done

# 验证标签
aws ec2 describe-subnets \
  --subnet-ids $PUBLIC_SUBNET_1 $PRIVATE_SUBNET_1 \
  --query 'Subnets[*].[SubnetId,Tags]' \
  --output json
```

**2. 创建 EKS 集群配置文件**

```bash
cat > eks-cluster-config.yaml <<EOF
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig

metadata:
  name: ${CLUSTER_NAME}
  region: ${AWS_REGION}
  version: "${K8S_VERSION}"

# 使用现有 VPC
vpc:
  id: "${VPC_ID}"
  subnets:
    public:
      ${AWS_REGION}a: { id: ${PUBLIC_SUBNET_1} }
      ${AWS_REGION}b: { id: ${PUBLIC_SUBNET_2} }
      ${AWS_REGION}c: { id: ${PUBLIC_SUBNET_3} }
    private:
      ${AWS_REGION}a: { id: ${PRIVATE_SUBNET_1} }
      ${AWS_REGION}b: { id: ${PRIVATE_SUBNET_2} }
      ${AWS_REGION}c: { id: ${PRIVATE_SUBNET_3} }

# IAM OIDC Provider（ALB Controller 需要）
iam:
  withOIDC: true

# 托管节点组
managedNodeGroups:
  - name: higress-nodes
    instanceType: c6i.xlarge
    desiredCapacity: 3
    minSize: 3
    maxSize: 6
    volumeSize: 100
    volumeType: gp3
    privateNetworking: true
    # 将节点分布在所有私有子网
    subnets:
      - ${PRIVATE_SUBNET_1}
      - ${PRIVATE_SUBNET_2}
      - ${PRIVATE_SUBNET_3}
    labels:
      role: higress
      environment: production
    tags:
      Name: higress-node
      Environment: production
    iam:
      withAddonPolicies:
        autoScaler: true
        albIngress: true
        cloudWatch: true
        ebs: true

# 启用日志
cloudWatch:
  clusterLogging:
    enableTypes: ["api", "audit", "authenticator", "controllerManager", "scheduler"]
EOF
```

**3. 创建 EKS 集群**

```bash
# 创建集群（大约需要 15-20 分钟）
eksctl create cluster -f eks-cluster-config.yaml

# 验证集群创建成功
kubectl get nodes
kubectl get pods -A

# 查看集群信息
eksctl get cluster --name $CLUSTER_NAME --region $AWS_REGION
```

### 方案 B：使用 AWS 控制台（可选）

如果您更喜欢使用 AWS 控制台，可以按照以下步骤操作：

1. 进入 EKS 控制台
2. 点击"创建集群"
3. 选择现有 VPC 和子网
4. 配置节点组
5. 启用 OIDC Provider

详细步骤请参考 [AWS EKS 官方文档](https://docs.aws.amazon.com/eks/latest/userguide/create-cluster.html)。

---

## 配置 ALB Ingress Controller

AWS Load Balancer Controller 用于自动创建和管理 ALB。

### 1. 创建 IAM 策略

```bash
# 下载 IAM 策略文档
curl -o iam-policy.json https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.7.0/docs/install/iam_policy.json

# 创建 IAM 策略
aws iam create-policy \
  --policy-name AWSLoadBalancerControllerIAMPolicy \
  --policy-document file://iam-policy.json

# 记录策略 ARN
export LBC_POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy"
echo $LBC_POLICY_ARN
```

### 2. 创建 IAM 服务账户

```bash
# 使用 eksctl 创建服务账户
eksctl create iamserviceaccount \
  --cluster=$CLUSTER_NAME \
  --namespace=kube-system \
  --name=aws-load-balancer-controller \
  --attach-policy-arn=$LBC_POLICY_ARN \
  --override-existing-serviceaccounts \
  --region=$AWS_REGION \
  --approve

# 验证服务账户
kubectl get serviceaccount aws-load-balancer-controller -n kube-system
```

### 3. 安装 AWS Load Balancer Controller

```bash
# 添加 EKS Helm 仓库
helm repo add eks https://aws.github.io/eks-charts
helm repo update

# 安装 AWS Load Balancer Controller
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=$CLUSTER_NAME \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set region=$AWS_REGION \
  --set vpcId=$VPC_ID

# 验证安装
kubectl get deployment -n kube-system aws-load-balancer-controller
kubectl logs -n kube-system deployment/aws-load-balancer-controller
```

---

## 部署 Higress

### 1. 添加 Higress Helm 仓库

```bash
helm repo add higress.io https://higress.io/helm-charts
helm repo update
```

### 2. 创建 Higress 配置文件

```bash
cat > higress-values.yaml <<'EOF'
global:
  # 生产环境配置
  local: false
  
higress-core:
  gateway:
    # 副本数（跨 3 个 AZ）
    replicas: 3
    
    # 资源配置
    resources:
      requests:
        cpu: 1000m
        memory: 2Gi
      limits:
        cpu: 2000m
        memory: 4Gi
    
    # 使用 LoadBalancer 类型（将自动创建 NLB）
    # 或使用 NodePort 配合 Ingress（将创建 ALB）
    service:
      type: LoadBalancer
      annotations:
        # 使用 NLB（网络负载均衡器）
        service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
        service.beta.kubernetes.io/aws-load-balancer-scheme: "internet-facing"
        service.beta.kubernetes.io/aws-load-balancer-cross-zone-load-balancing-enabled: "true"
      ports:
        - name: http
          port: 80
          targetPort: 80
        - name: https
          port: 443
          targetPort: 443
    
    # Pod 反亲和性（确保分散在不同节点）
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
        preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 100
          podAffinityTerm:
            labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values:
                - higress-gateway
            topologyKey: topology.kubernetes.io/zone
    
    # Pod 中断预算（确保高可用）
    podDisruptionBudget:
      enabled: true
      minAvailable: 2
    
    # 自动扩缩容
    autoscaling:
      enabled: true
      minReplicas: 3
      maxReplicas: 10
      targetCPUUtilizationPercentage: 70
      targetMemoryUtilizationPercentage: 80

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
    type: ClusterIP
  resources:
    requests:
      cpu: 200m
      memory: 512Mi
    limits:
      cpu: 500m
      memory: 1Gi

# 启用可观测性
global:
  o11y:
    enabled: true
EOF
```

### 3. 安装 Higress

```bash
# 创建命名空间
kubectl create namespace higress-system

# 安装 Higress
helm install higress higress.io/higress \
  -n higress-system \
  -f higress-values.yaml \
  --wait

# 等待所有 Pod 就绪
kubectl wait --for=condition=ready pod \
  -l app=higress-gateway \
  -n higress-system \
  --timeout=300s

# 验证安装
kubectl get pods -n higress-system
kubectl get svc -n higress-system
```

### 4. 获取 Load Balancer 地址

```bash
# 获取 Higress Gateway 的 LoadBalancer 地址
kubectl get svc higress-gateway -n higress-system -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'

# 保存 NLB 地址
export NLB_HOSTNAME=$(kubectl get svc higress-gateway -n higress-system -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "NLB Hostname: $NLB_HOSTNAME"

# 测试访问（可能需要等待几分钟 DNS 生效）
curl -I http://$NLB_HOSTNAME
```

---

## 配置 ALB

如果您希望使用 ALB 而不是 NLB，可以通过 Ingress 资源创建 ALB。

### 方案 A：使用 ALB（推荐用于 HTTP/HTTPS 流量）

**1. 修改 Higress Service 为 NodePort**

```bash
# 更新 higress-values.yaml
cat > higress-values-alb.yaml <<'EOF'
global:
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
    
    # 使用 NodePort
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
    
    podDisruptionBudget:
      enabled: true
      minAvailable: 2
    
    autoscaling:
      enabled: true
      minReplicas: 3
      maxReplicas: 10
      targetCPUUtilizationPercentage: 70

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
    type: ClusterIP

global:
  o11y:
    enabled: true
EOF

# 升级 Higress
helm upgrade higress higress.io/higress \
  -n higress-system \
  -f higress-values-alb.yaml \
  --wait
```

**2. 创建 ALB Ingress**

```bash
cat > higress-alb-ingress.yaml <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: higress-alb
  namespace: higress-system
  annotations:
    # ALB 配置
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: instance
    alb.ingress.kubernetes.io/subnets: ${PUBLIC_SUBNET_1},${PUBLIC_SUBNET_2},${PUBLIC_SUBNET_3}
    
    # 健康检查
    alb.ingress.kubernetes.io/healthcheck-path: /
    alb.ingress.kubernetes.io/healthcheck-port: "30080"
    alb.ingress.kubernetes.io/healthcheck-protocol: HTTP
    alb.ingress.kubernetes.io/healthcheck-interval-seconds: "30"
    alb.ingress.kubernetes.io/healthcheck-timeout-seconds: "5"
    alb.ingress.kubernetes.io/healthy-threshold-count: "2"
    alb.ingress.kubernetes.io/unhealthy-threshold-count: "3"
    
    # 监听器配置
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
    
    # SSL 配置（需要先在 ACM 中创建证书）
    # alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:region:account:certificate/xxxxx
    
    # HTTP 到 HTTPS 重定向（可选）
    # alb.ingress.kubernetes.io/ssl-redirect: "443"
    
    # 访问日志（可选）
    # alb.ingress.kubernetes.io/load-balancer-attributes: access_logs.s3.enabled=true,access_logs.s3.bucket=my-bucket
    
    # 标签
    alb.ingress.kubernetes.io/tags: Environment=production,Application=higress
spec:
  ingressClassName: alb
  rules:
  - http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: higress-gateway
            port:
              number: 80
EOF

# 应用 Ingress
kubectl apply -f higress-alb-ingress.yaml

# 等待 ALB 创建（大约需要 3-5 分钟）
kubectl get ingress -n higress-system -w
```

**3. 获取 ALB 地址**

```bash
# 获取 ALB DNS 名称
export ALB_HOSTNAME=$(kubectl get ingress higress-alb -n higress-system -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "ALB Hostname: $ALB_HOSTNAME"

# 测试访问
curl -I http://$ALB_HOSTNAME

# 在 AWS 控制台查看 ALB
aws elbv2 describe-load-balancers \
  --query "LoadBalancers[?contains(LoadBalancerName, 'k8s-higresss')].{Name:LoadBalancerName,DNS:DNSName,State:State.Code}" \
  --output table
```

### 方案 B：配置 SSL 证书

**1. 在 ACM 中申请证书**

```bash
# 申请证书
aws acm request-certificate \
  --domain-name yourdomain.com \
  --subject-alternative-names *.yourdomain.com \
  --validation-method DNS \
  --region $AWS_REGION

# 获取证书 ARN
export CERT_ARN=$(aws acm list-certificates \
  --query "CertificateSummaryList[?DomainName=='yourdomain.com'].CertificateArn" \
  --output text)

echo "Certificate ARN: $CERT_ARN"

# 验证证书（需要在 DNS 中添加验证记录）
aws acm describe-certificate --certificate-arn $CERT_ARN
```

**2. 更新 Ingress 使用 SSL**

```bash
cat > higress-alb-ingress-ssl.yaml <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: higress-alb
  namespace: higress-system
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: instance
    alb.ingress.kubernetes.io/subnets: ${PUBLIC_SUBNET_1},${PUBLIC_SUBNET_2},${PUBLIC_SUBNET_3}
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
    alb.ingress.kubernetes.io/certificate-arn: ${CERT_ARN}
    alb.ingress.kubernetes.io/ssl-redirect: "443"
    alb.ingress.kubernetes.io/ssl-policy: ELBSecurityPolicy-TLS-1-2-2017-01
    alb.ingress.kubernetes.io/healthcheck-path: /
    alb.ingress.kubernetes.io/healthcheck-port: "30080"
    alb.ingress.kubernetes.io/tags: Environment=production,Application=higress
spec:
  ingressClassName: alb
  rules:
  - host: yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: higress-gateway
            port:
              number: 80
  - host: "*.yourdomain.com"
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: higress-gateway
            port:
              number: 80
EOF

# 应用更新
kubectl apply -f higress-alb-ingress-ssl.yaml
```

---

## 配置 Higress Console 访问

### 1. 通过 Port Forward 访问（临时）

```bash
# 端口转发
kubectl port-forward -n higress-system svc/higress-console 8080:8080

# 在浏览器访问 http://localhost:8080
```

### 2. 通过 Ingress 暴露（生产环境）

```bash
cat > higress-console-ingress.yaml <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: higress-console
  namespace: higress-system
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/subnets: ${PUBLIC_SUBNET_1},${PUBLIC_SUBNET_2},${PUBLIC_SUBNET_3}
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS": 443}]'
    alb.ingress.kubernetes.io/certificate-arn: ${CERT_ARN}
    # 建议添加 IP 白名单限制访问
    alb.ingress.kubernetes.io/inbound-cidrs: "YOUR_OFFICE_IP/32"
spec:
  ingressClassName: alb
  rules:
  - host: console.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: higress-console
            port:
              number: 8080
EOF

kubectl apply -f higress-console-ingress.yaml
```

---

## 安全加固

### 1. 配置 Security Groups

```bash
# 获取 EKS 节点的安全组
export NODE_SG=$(aws ec2 describe-security-groups \
  --filters "Name=tag:aws:eks:cluster-name,Values=$CLUSTER_NAME" \
  --query "SecurityGroups[?contains(GroupName, 'node')].GroupId" \
  --output text)

echo "Node Security Group: $NODE_SG"

# 限制 SSH 访问（仅允许堡垒机）
# aws ec2 authorize-security-group-ingress \
#   --group-id $NODE_SG \
#   --protocol tcp \
#   --port 22 \
#   --source-group <BASTION_SG_ID>
```

### 2. 启用 Pod Security Standards

```bash
# 创建 Pod Security Policy
cat > pod-security-policy.yaml <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: higress-system
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
EOF

kubectl apply -f pod-security-policy.yaml
```

### 3. 配置 Network Policies

```bash
cat > higress-network-policy.yaml <<'EOF'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: higress-gateway-policy
  namespace: higress-system
spec:
  podSelector:
    matchLabels:
      app: higress-gateway
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 80
    - protocol: TCP
      port: 443
  egress:
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 443
    - protocol: TCP
      port: 80
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - protocol: TCP
      port: 53
    - protocol: UDP
      port: 53
EOF

kubectl apply -f higress-network-policy.yaml
```

### 4. 启用 Secrets 加密

```bash
# 创建 KMS 密钥
aws kms create-key \
  --description "EKS Secrets Encryption Key for $CLUSTER_NAME" \
  --region $AWS_REGION

# 获取密钥 ARN
export KMS_KEY_ARN=$(aws kms list-keys --region $AWS_REGION --query "Keys[0].KeyArn" --output text)

# 为 EKS 集群启用 secrets 加密
aws eks associate-encryption-config \
  --cluster-name $CLUSTER_NAME \
  --encryption-config '[{"resources":["secrets"],"provider":{"keyArn":"'$KMS_KEY_ARN'"}}]' \
  --region $AWS_REGION
```

---

## 监控和日志

### 1. 安装 Prometheus 和 Grafana

```bash
# 添加 Prometheus 社区 Helm 仓库
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# 安装 kube-prometheus-stack
helm install prometheus prometheus-community/kube-prometheus-stack \
  -n monitoring \
  --create-namespace \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set grafana.adminPassword=admin123

# 访问 Grafana
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80

# 浏览器访问 http://localhost:3000
# 用户名: admin
# 密码: admin123
```

### 2. 配置 CloudWatch Container Insights

```bash
# 安装 CloudWatch Agent
curl https://raw.githubusercontent.com/aws-samples/amazon-cloudwatch-container-insights/latest/k8s-deployment-manifest-templates/deployment-mode/daemonset/container-insights-monitoring/quickstart/cwagent-fluentd-quickstart.yaml | \
sed "s/{{cluster_name}}/$CLUSTER_NAME/;s/{{region_name}}/$AWS_REGION/" | \
kubectl apply -f -

# 验证安装
kubectl get pods -n amazon-cloudwatch
```

### 3. 配置日志收集到 CloudWatch

```bash
# 创建 CloudWatch 日志组
aws logs create-log-group \
  --log-group-name /aws/eks/$CLUSTER_NAME/higress \
  --region $AWS_REGION

# Higress 日志会自动通过 Fluent Bit 发送到 CloudWatch
```

### 4. 配置告警

```bash
# 创建 SNS 主题
aws sns create-topic \
  --name higress-eks-alerts \
  --region $AWS_REGION

export SNS_TOPIC_ARN=$(aws sns list-topics --query "Topics[?contains(TopicArn, 'higress-eks-alerts')].TopicArn" --output text)

# 订阅邮件通知
aws sns subscribe \
  --topic-arn $SNS_TOPIC_ARN \
  --protocol email \
  --notification-endpoint your-email@example.com \
  --region $AWS_REGION

# 创建 CloudWatch 告警
aws cloudwatch put-metric-alarm \
  --alarm-name higress-pod-cpu-high \
  --alarm-description "Higress Pod CPU usage is high" \
  --metric-name pod_cpu_utilization \
  --namespace ContainerInsights \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --dimensions Name=ClusterName,Value=$CLUSTER_NAME Name=Namespace,Value=higress-system \
  --alarm-actions $SNS_TOPIC_ARN \
  --region $AWS_REGION
```

---

## 部署示例应用

### 1. 部署测试服务

```bash
cat > test-app.yaml <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: demo
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: httpbin
  namespace: demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: httpbin
  template:
    metadata:
      labels:
        app: httpbin
    spec:
      containers:
      - name: httpbin
        image: kennethreitz/httpbin
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: httpbin
  namespace: demo
spec:
  selector:
    app: httpbin
  ports:
  - port: 80
    targetPort: 80
EOF

kubectl apply -f test-app.yaml
```

### 2. 配置 Higress 路由

```bash
cat > httpbin-ingress.yaml <<'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: httpbin
  namespace: demo
  annotations:
    higress.io/destination: httpbin.demo.svc.cluster.local:80
spec:
  ingressClassName: higress
  rules:
  - host: httpbin.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: httpbin
            port:
              number: 80
EOF

kubectl apply -f httpbin-ingress.yaml
```

### 3. 测试访问

```bash
# 通过 ALB 访问
curl -H "Host: httpbin.example.com" http://$ALB_HOSTNAME/get

# 或配置本地 hosts 文件
# echo "$ALB_HOSTNAME httpbin.example.com" | sudo tee -a /etc/hosts
# curl http://httpbin.example.com/get
```

---

## 故障排查

### 常见问题

**1. ALB 未创建**

```bash
# 检查 AWS Load Balancer Controller 日志
kubectl logs -n kube-system deployment/aws-load-balancer-controller

# 检查 Ingress 事件
kubectl describe ingress higress-alb -n higress-system

# 验证 IAM 权限
aws iam get-policy --policy-arn $LBC_POLICY_ARN
```

**2. Pod 无法启动**

```bash
# 查看 Pod 状态
kubectl get pods -n higress-system

# 查看详细信息
kubectl describe pod <pod-name> -n higress-system

# 查看日志
kubectl logs <pod-name> -n higress-system

# 查看事件
kubectl get events -n higress-system --sort-by='.lastTimestamp'
```

**3. 健康检查失败**

```bash
# 检查目标组健康状态
aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn> \
  --region $AWS_REGION

# 在节点上测试健康检查端点
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://higress-gateway.higress-system.svc.cluster.local/

# 检查 Service
kubectl get svc -n higress-system
kubectl describe svc higress-gateway -n higress-system
```

**4. 无法访问服务**

```bash
# 检查 DNS 解析
nslookup $ALB_HOSTNAME

# 检查安全组
aws ec2 describe-security-groups \
  --group-ids $NODE_SG \
  --region $AWS_REGION

# 测试从 Pod 内部访问
kubectl run -it --rm debug --image=nicolaka/netshoot --restart=Never -- bash
# 在 Pod 内执行: curl http://higress-gateway.higress-system.svc.cluster.local
```

**5. 节点无法加入集群**

```bash
# 查看节点状态
kubectl get nodes

# 检查节点日志
aws ec2 get-console-output --instance-id <instance-id> --region $AWS_REGION

# 检查 IAM 角色
aws iam get-role --role-name <node-role-name>
```

### 日志位置

- EKS 控制平面日志: CloudWatch Logs `/aws/eks/$CLUSTER_NAME/cluster`
- Higress Gateway 日志: `kubectl logs -n higress-system -l app=higress-gateway`
- Higress Controller 日志: `kubectl logs -n higress-system -l app=higress-controller`
- ALB Controller 日志: `kubectl logs -n kube-system deployment/aws-load-balancer-controller`

---

## 成本优化

### 1. 使用 Spot 实例（非生产环境）

```bash
# 在 eks-cluster-config.yaml 中添加 Spot 节点组
cat >> eks-cluster-config.yaml <<'EOF'
  - name: higress-spot-nodes
    instanceTypes: ["c6i.xlarge", "c5.xlarge", "c5a.xlarge"]
    spot: true
    desiredCapacity: 2
    minSize: 0
    maxSize: 5
    privateNetworking: true
    subnets:
      - ${PRIVATE_SUBNET_1}
      - ${PRIVATE_SUBNET_2}
      - ${PRIVATE_SUBNET_3}
    labels:
      role: higress-spot
      lifecycle: spot
    taints:
      - key: spot
        value: "true"
        effect: NoSchedule
EOF
```

### 2. 使用 Savings Plans

```bash
# 在 AWS Cost Explorer 中购买 Compute Savings Plans
# 可节省 30-70% 的成本
```

### 3. 配置 Cluster Autoscaler

```bash
# 安装 Cluster Autoscaler
kubectl apply -f https://raw.githubusercontent.com/kubernetes/autoscaler/master/cluster-autoscaler/cloudprovider/aws/examples/cluster-autoscaler-autodiscover.yaml

# 配置 Cluster Autoscaler
kubectl -n kube-system annotate deployment.apps/cluster-autoscaler \
  cluster-autoscaler.kubernetes.io/safe-to-evict="false"

kubectl -n kube-system set image deployment.apps/cluster-autoscaler \
  cluster-autoscaler=registry.k8s.io/autoscaling/cluster-autoscaler:v1.28.0
```

### 4. 优化 EBS 卷

```bash
# 使用 gp3 替代 gp2（更便宜且性能更好）
# 在节点组配置中已设置 volumeType: gp3

# 定期清理未使用的 EBS 卷
aws ec2 describe-volumes \
  --filters Name=status,Values=available \
  --query "Volumes[*].{ID:VolumeId,Size:Size}" \
  --region $AWS_REGION
```

### 5. 配置 S3 生命周期策略

```bash
# 为日志存储桶配置生命周期策略
aws s3api put-bucket-lifecycle-configuration \
  --bucket your-log-bucket \
  --lifecycle-configuration file://lifecycle.json

# lifecycle.json 示例
cat > lifecycle.json <<'EOF'
{
  "Rules": [
    {
      "Id": "archive-old-logs",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ],
      "Expiration": {
        "Days": 365
      }
    }
  ]
}
EOF
```

---

## 备份和恢复

### 1. 备份 EKS 配置

```bash
# 导出所有 Higress 资源
kubectl get all -n higress-system -o yaml > higress-backup.yaml

# 备份 ConfigMaps 和 Secrets
kubectl get configmap -n higress-system -o yaml > higress-configmaps.yaml
kubectl get secret -n higress-system -o yaml > higress-secrets.yaml

# 上传到 S3
aws s3 cp higress-backup.yaml s3://your-backup-bucket/eks-backups/$(date +%Y%m%d)/
aws s3 cp higress-configmaps.yaml s3://your-backup-bucket/eks-backups/$(date +%Y%m%d)/
aws s3 cp higress-secrets.yaml s3://your-backup-bucket/eks-backups/$(date +%Y%m%d)/
```

### 2. 使用 Velero 进行备份

```bash
# 安装 Velero
wget https://github.com/vmware-tanzu/velero/releases/download/v1.12.0/velero-v1.12.0-linux-amd64.tar.gz
tar -xvf velero-v1.12.0-linux-amd64.tar.gz
sudo mv velero-v1.12.0-linux-amd64/velero /usr/local/bin/

# 创建 S3 存储桶
aws s3 mb s3://higress-velero-backup-$AWS_ACCOUNT_ID --region $AWS_REGION

# 安装 Velero 到集群
velero install \
  --provider aws \
  --plugins velero/velero-plugin-for-aws:v1.8.0 \
  --bucket higress-velero-backup-$AWS_ACCOUNT_ID \
  --backup-location-config region=$AWS_REGION \
  --snapshot-location-config region=$AWS_REGION \
  --use-node-agent

# 创建备份
velero backup create higress-backup --include-namespaces higress-system

# 查看备份
velero backup get

# 恢复备份
velero restore create --from-backup higress-backup
```

---

## 生产环境检查清单

### 部署前检查

- [ ] VPC 和子网配置正确
- [ ] 子网已添加 EKS 必需标签
- [ ] NAT Gateway 已配置
- [ ] IAM 权限配置正确
- [ ] SSL 证书已申请并验证
- [ ] 域名 DNS 已配置
- [ ] 监控和告警已配置
- [ ] 备份策略已制定

### 部署后验证

- [ ] EKS 集群健康
- [ ] 所有节点状态为 Ready
- [ ] Higress Pod 全部 Running
- [ ] ALB/NLB 创建成功
- [ ] 健康检查通过
- [ ] 可以通过负载均衡器访问服务
- [ ] SSL 证书工作正常
- [ ] 监控数据正常上报
- [ ] 日志正常收集
- [ ] 告警测试通过
- [ ] 自动扩缩容测试通过

### 安全检查

- [ ] 最小权限原则
- [ ] Pod Security Standards 已启用
- [ ] Network Policies 已配置
- [ ] Secrets 加密已启用
- [ ] 安全组规则最小化
- [ ] VPC Flow Logs 已启用
- [ ] ALB 访问日志已启用
- [ ] 定期更新 EKS 版本
- [ ] 定期审计 IAM 权限

### 性能检查

- [ ] 资源限制配置合理
- [ ] HPA 配置正确
- [ ] Cluster Autoscaler 工作正常
- [ ] 负载测试通过
- [ ] 响应时间符合预期

---

## 升级和维护

### 1. 升级 EKS 集群

```bash
# 查看当前版本
kubectl version --short

# 升级控制平面
eksctl upgrade cluster --name $CLUSTER_NAME --region $AWS_REGION --approve

# 升级节点组
eksctl upgrade nodegroup \
  --cluster=$CLUSTER_NAME \
  --name=higress-nodes \
  --region=$AWS_REGION \
  --kubernetes-version=1.29
```

### 2. 升级 Higress

```bash
# 更新 Helm 仓库
helm repo update

# 查看可用版本
helm search repo higress.io/higress --versions

# 升级 Higress
helm upgrade higress higress.io/higress \
  -n higress-system \
  -f higress-values.yaml \
  --version <new-version>

# 验证升级
kubectl rollout status deployment -n higress-system
```

### 3. 定期维护任务

```bash
# 清理未使用的镜像
kubectl get pods -A -o jsonpath='{range .items[*]}{.spec.containers[*].image}{"\n"}{end}' | sort -u

# 清理已完成的 Job
kubectl delete jobs --field-selector status.successful=1 -A

# 清理 Evicted Pods
kubectl get pods -A --field-selector status.phase=Failed -o json | \
  kubectl delete -f -

# 检查资源使用情况
kubectl top nodes
kubectl top pods -n higress-system
```

---

## 附录

### A. 完整部署脚本

```bash
#!/bin/bash
# higress-eks-deploy.sh - 完整部署脚本

set -e

# 加载配置
source ./higress-eks-config.sh

echo "开始部署 Higress on EKS..."

# 1. 为子网添加标签
echo "步骤 1: 添加子网标签..."
for subnet in $PUBLIC_SUBNET_1 $PUBLIC_SUBNET_2 $PUBLIC_SUBNET_3; do
  aws ec2 create-tags --resources $subnet \
    --tags Key=kubernetes.io/role/elb,Value=1 \
           Key=kubernetes.io/cluster/$CLUSTER_NAME,Value=shared
done

for subnet in $PRIVATE_SUBNET_1 $PRIVATE_SUBNET_2 $PRIVATE_SUBNET_3; do
  aws ec2 create-tags --resources $subnet \
    --tags Key=kubernetes.io/role/internal-elb,Value=1 \
           Key=kubernetes.io/cluster/$CLUSTER_NAME,Value=shared
done

# 2. 创建 EKS 集群
echo "步骤 2: 创建 EKS 集群（约需 15-20 分钟）..."
eksctl create cluster -f eks-cluster-config.yaml

# 3. 安装 AWS Load Balancer Controller
echo "步骤 3: 安装 AWS Load Balancer Controller..."
curl -o iam-policy.json https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.7.0/docs/install/iam_policy.json
aws iam create-policy \
  --policy-name AWSLoadBalancerControllerIAMPolicy \
  --policy-document file://iam-policy.json || true

export LBC_POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy"

eksctl create iamserviceaccount \
  --cluster=$CLUSTER_NAME \
  --namespace=kube-system \
  --name=aws-load-balancer-controller \
  --attach-policy-arn=$LBC_POLICY_ARN \
  --override-existing-serviceaccounts \
  --region=$AWS_REGION \
  --approve

helm repo add eks https://aws.github.io/eks-charts
helm repo update

helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=$CLUSTER_NAME \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set region=$AWS_REGION \
  --set vpcId=$VPC_ID

# 4. 部署 Higress
echo "步骤 4: 部署 Higress..."
helm repo add higress.io https://higress.io/helm-charts
helm repo update

kubectl create namespace higress-system

helm install higress higress.io/higress \
  -n higress-system \
  -f higress-values-alb.yaml \
  --wait

# 5. 创建 ALB Ingress
echo "步骤 5: 创建 ALB..."
kubectl apply -f higress-alb-ingress.yaml

# 等待 ALB 创建
echo "等待 ALB 创建完成..."
sleep 60

# 获取 ALB 地址
export ALB_HOSTNAME=$(kubectl get ingress higress-alb -n higress-system -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

echo "=========================================="
echo "部署完成！"
echo "ALB Hostname: $ALB_HOSTNAME"
echo "=========================================="
echo ""
echo "后续步骤："
echo "1. 配置 DNS 记录指向 ALB"
echo "2. 在 ACM 中申请 SSL 证书"
echo "3. 更新 Ingress 配置使用 SSL"
echo "4. 配置 Higress Console 访问"
echo "5. 部署您的应用"
echo ""
echo "测试访问："
echo "curl -I http://$ALB_HOSTNAME"
```

### B. 清理资源

```bash
#!/bin/bash
# cleanup.sh - 清理所有资源

set -e

source ./higress-eks-config.sh

echo "警告：此操作将删除所有资源！"
read -p "确认删除？(yes/no): " confirm

if [ "$confirm" != "yes" ]; then
  echo "取消操作"
  exit 0
fi

# 删除 Higress
helm uninstall higress -n higress-system || true
kubectl delete namespace higress-system || true

# 删除 AWS Load Balancer Controller
helm uninstall aws-load-balancer-controller -n kube-system || true

# 删除 EKS 集群
eksctl delete cluster --name $CLUSTER_NAME --region $AWS_REGION

# 删除 IAM 策略
aws iam delete-policy --policy-arn $LBC_POLICY_ARN || true

echo "清理完成"
```

### C. 参考链接

- [Higress 官方文档](https://higress.io/)
- [AWS EKS 用户指南](https://docs.aws.amazon.com/eks/latest/userguide/)
- [AWS Load Balancer Controller](https://kubernetes-sigs.github.io/aws-load-balancer-controller/)
- [eksctl 文档](https://eksctl.io/)
- [Kubernetes 最佳实践](https://kubernetes.io/docs/setup/best-practices/)

---

## 总结

本文档提供了在 AWS EKS 上部署 Higress 生产集群的完整指南，相比 EC2 + K3s 方案，EKS 方案具有以下优势：

**优势：**
- ✅ 托管的 Kubernetes 控制平面，无需维护
- ✅ 自动升级和补丁管理
- ✅ 与 AWS 服务深度集成（ALB、CloudWatch、IAM 等）
- ✅ 更好的可扩展性和可靠性
- ✅ 企业级支持

**适用场景：**
- 生产环境部署
- 需要高可用和自动扩缩容
- 团队熟悉 Kubernetes
- 预算充足

按照本文档操作，您可以在 30-60 分钟内完成 Higress 在 EKS 上的部署，并获得一个高可用、安全、可监控的生产环境。

**重要提示：**
- 请根据实际情况调整配置参数
- 生产环境部署前务必在测试环境验证
- 定期备份和更新系统
- 遵循安全最佳实践
- 监控成本使用情况

如有问题，请参考故障排查章节或查阅官方文档。
