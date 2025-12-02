#!/bin/bash
# 修复 ALB Security Group 问题

set -e

CLUSTER_NAME="higress-prod"
REGION="us-east-2"
VPC_ID="vpc-0c9a0d81e8f5ca012"

echo "=========================================="
echo "修复 ALB Security Group 问题"
echo "=========================================="

# 1. 获取集群信息
echo -e "\n【步骤 1】获取集群信息..."
CLUSTER_SG=$(aws eks describe-cluster \
  --name $CLUSTER_NAME \
  --region $REGION \
  --query 'cluster.resourcesVpcConfig.securityGroupIds[0]' \
  --output text)

echo "集群 Security Group: $CLUSTER_SG"

# 2. 获取节点 Security Group
echo -e "\n【步骤 2】获取节点 Security Group..."
NODE_SG=$(aws ec2 describe-security-groups \
  --filters "Name=tag:aws:cloudformation:stack-name,Values=eksctl-${CLUSTER_NAME}-nodegroup-*" \
  --region $REGION \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

echo "节点 Security Group: $NODE_SG"

# 3. 删除现有 Ingress
echo -e "\n【步骤 3】删除现有 Ingress..."
kubectl delete ingress higress-alb -n higress-system --ignore-not-found=true
echo "等待 AWS 资源清理..."
sleep 30

# 4. 验证 Security Group
echo -e "\n【步骤 4】验证 Security Group..."
aws ec2 describe-security-groups \
  --group-ids $CLUSTER_SG $NODE_SG \
  --region $REGION \
  --query 'SecurityGroups[*].[GroupId,GroupName,VpcId]' \
  --output table

# 5. 检查 Security Group 规则
echo -e "\n【步骤 5】检查 Security Group 规则..."
echo "集群 SG 入站规则:"
aws ec2 describe-security-groups \
  --group-ids $CLUSTER_SG \
  --region $REGION \
  --query 'SecurityGroups[0].IpPermissions[*].[IpProtocol,FromPort,ToPort]' \
  --output table

echo -e "\n节点 SG 入站规则:"
aws ec2 describe-security-groups \
  --group-ids $NODE_SG \
  --region $REGION \
  --query 'SecurityGroups[0].IpPermissions[*].[IpProtocol,FromPort,ToPort]' \
  --output table

# 6. 添加必要的规则
echo -e "\n【步骤 6】添加必要的 Security Group 规则..."

# 允许节点 SG 接收来自集群 SG 的流量
echo "添加节点 SG 入站规则（来自集群 SG）..."
aws ec2 authorize-security-group-ingress \
  --group-id $NODE_SG \
  --protocol tcp \
  --port 30080 \
  --source-group $CLUSTER_SG \
  --region $REGION \
  --output text 2>/dev/null || echo "规则已存在或添加失败"

aws ec2 authorize-security-group-ingress \
  --group-id $NODE_SG \
  --protocol tcp \
  --port 30443 \
  --source-group $CLUSTER_SG \
  --region $REGION \
  --output text 2>/dev/null || echo "规则已存在或添加失败"

# 7. 重新创建 Ingress
echo -e "\n【步骤 7】重新创建 Ingress..."
kubectl apply -f higress-alb-ingress.yaml

# 8. 等待 ALB 创建
echo -e "\n【步骤 8】等待 ALB 创建（最多 5 分钟）..."
for i in {1..30}; do
  ALB_DNS=$(kubectl get ingress higress-alb -n higress-system \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
  
  if [ -n "$ALB_DNS" ]; then
    echo "✓ ALB 创建成功！"
    echo "ALB DNS: $ALB_DNS"
    echo $ALB_DNS > alb-endpoint.txt
    break
  fi
  
  echo "等待中... ($((i*10))秒)"
  sleep 10
done

# 9. 验证
echo -e "\n【步骤 9】验证 Ingress 状态..."
kubectl describe ingress higress-alb -n higress-system

echo -e "\n=========================================="
echo "✓ 修复完成"
echo "=========================================="
