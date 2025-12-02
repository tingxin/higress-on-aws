#!/bin/bash
# 修复 EBS CSI Driver 安装冲突

set -e

echo "=========================================="
echo "修复 EBS CSI Driver 安装冲突"
echo "=========================================="

# 从 config.yaml 读取配置
CLUSTER_NAME=$(grep "cluster_name:" config.yaml | awk '{print $2}')
REGION=$(grep "region:" config.yaml | head -1 | awk '{print $2}')
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo ""
echo "集群名称: $CLUSTER_NAME"
echo "区域: $REGION"
echo "账户 ID: $ACCOUNT_ID"

# 1. 删除现有的 addon（如果存在）
echo ""
echo "1. 检查并删除现有的 EBS CSI Driver addon..."
if aws eks describe-addon --cluster-name $CLUSTER_NAME --addon-name aws-ebs-csi-driver --region $REGION &>/dev/null; then
    echo "发现现有 addon，删除中..."
    aws eks delete-addon \
        --cluster-name $CLUSTER_NAME \
        --addon-name aws-ebs-csi-driver \
        --region $REGION
    
    echo "等待 addon 删除完成..."
    sleep 30
else
    echo "未发现现有 addon"
fi

# 2. 删除冲突的 ServiceAccount
echo ""
echo "2. 删除冲突的 ServiceAccount..."
kubectl delete serviceaccount ebs-csi-controller-sa -n kube-system 2>/dev/null || echo "ServiceAccount 不存在或已删除"

# 3. 等待清理
echo ""
echo "3. 等待资源清理..."
sleep 10

# 4. 重新创建 IAM 策略（如果不存在）
echo ""
echo "4. 创建 IAM 策略..."
POLICY_NAME="AmazonEKS_EBS_CSI_Driver_Policy"
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}"

if ! aws iam get-policy --policy-arn $POLICY_ARN &>/dev/null; then
    echo "下载 IAM 策略..."
    curl -o ebs-csi-policy.json https://raw.githubusercontent.com/kubernetes-sigs/aws-ebs-csi-driver/master/docs/example-iam-policy.json
    
    echo "创建 IAM 策略..."
    aws iam create-policy \
        --policy-name $POLICY_NAME \
        --policy-document file://ebs-csi-policy.json
else
    echo "IAM 策略已存在"
fi

# 5. 创建 IAM 服务账户
echo ""
echo "5. 创建 IAM 服务账户..."
eksctl create iamserviceaccount \
    --cluster=$CLUSTER_NAME \
    --namespace=kube-system \
    --name=ebs-csi-controller-sa \
    --attach-policy-arn=$POLICY_ARN \
    --override-existing-serviceaccounts \
    --region=$REGION \
    --approve

# 6. 获取 IAM 角色 ARN
echo ""
echo "6. 获取 IAM 角色 ARN..."
ROLE_NAME="eksctl-${CLUSTER_NAME}-addon-iamserviceaccount-kube-system-ebs-csi-controller-sa"
ROLE_ARN=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text 2>/dev/null || echo "")

if [ -z "$ROLE_ARN" ]; then
    echo "尝试查找 EBS CSI 相关的角色..."
    ROLE_NAME=$(aws iam list-roles --query 'Roles[?contains(RoleName, `ebs-csi`)].RoleName' --output text | awk '{print $1}')
    if [ -n "$ROLE_NAME" ]; then
        ROLE_ARN=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text)
    fi
fi

echo "IAM 角色 ARN: $ROLE_ARN"

# 7. 安装 EBS CSI Driver addon
echo ""
echo "7. 安装 EBS CSI Driver addon..."
if [ -n "$ROLE_ARN" ]; then
    aws eks create-addon \
        --cluster-name $CLUSTER_NAME \
        --addon-name aws-ebs-csi-driver \
        --service-account-role-arn $ROLE_ARN \
        --resolve-conflicts OVERWRITE \
        --region $REGION
else
    echo "未找到 IAM 角色，使用默认配置安装..."
    aws eks create-addon \
        --cluster-name $CLUSTER_NAME \
        --addon-name aws-ebs-csi-driver \
        --resolve-conflicts OVERWRITE \
        --region $REGION
fi

# 8. 等待 addon 就绪
echo ""
echo "8. 等待 addon 就绪..."
for i in {1..30}; do
    STATUS=$(aws eks describe-addon \
        --cluster-name $CLUSTER_NAME \
        --addon-name aws-ebs-csi-driver \
        --region $REGION \
        --query 'addon.status' \
        --output text 2>/dev/null || echo "UNKNOWN")
    
    echo "  状态: $STATUS"
    
    if [ "$STATUS" == "ACTIVE" ]; then
        echo "✓ EBS CSI Driver addon 已激活"
        break
    elif [ "$STATUS" == "CREATE_FAILED" ]; then
        echo "✗ 创建失败，查看详细信息："
        aws eks describe-addon \
            --cluster-name $CLUSTER_NAME \
            --addon-name aws-ebs-csi-driver \
            --region $REGION
        exit 1
    fi
    
    sleep 10
done

# 9. 验证安装
echo ""
echo "9. 验证安装..."
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-ebs-csi-driver

echo ""
echo "=========================================="
echo "✓ 修复完成"
echo "=========================================="
echo ""
echo "验证 StorageClass:"
echo "  kubectl get storageclass"
echo ""
