#!/bin/bash
# 快速修复 ALB Controller IAM 权限问题

set -e

echo "=========================================="
echo "修复 ALB Controller IAM 权限"
echo "=========================================="

# 获取 AWS 账户 ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy"

echo ""
echo "AWS 账户 ID: $ACCOUNT_ID"
echo "策略 ARN: $POLICY_ARN"

# 下载最新的 IAM 策略
echo ""
echo "1. 下载最新的 IAM 策略..."
curl -o iam-policy-latest.json https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.7.0/docs/install/iam_policy.json

# 添加缺失的权限
echo ""
echo "2. 添加缺失的 ELB 权限..."
python3 << 'PYTHON_SCRIPT'
import json

# 读取策略
with open('iam-policy-latest.json', 'r') as f:
    policy = json.load(f)

# 需要添加的权限
additional_permissions = [
    "elasticloadbalancing:DescribeListenerAttributes",
    "elasticloadbalancing:ModifyListenerAttributes",
    "elasticloadbalancing:DescribeListenerCertificates",
    "elasticloadbalancing:ModifyListenerCertificates"
]

# 添加权限
for statement in policy.get('Statement', []):
    if statement.get('Effect') == 'Allow':
        actions = statement.get('Action', [])
        if isinstance(actions, list):
            has_elb = any('elasticloadbalancing' in action for action in actions)
            if has_elb:
                for perm in additional_permissions:
                    if perm not in actions:
                        actions.append(perm)
                        print(f"  添加权限: {perm}")

# 保存
with open('iam-policy-latest.json', 'w') as f:
    json.dump(policy, f, indent=2)

print("✓ IAM 策略已增强")
PYTHON_SCRIPT

# 检查是否有旧版本需要删除
echo ""
echo "3. 检查现有策略版本..."
OLD_VERSIONS=$(aws iam list-policy-versions --policy-arn $POLICY_ARN --query 'Versions[?IsDefaultVersion==`false`].VersionId' --output text)

if [ -n "$OLD_VERSIONS" ]; then
    VERSION_COUNT=$(echo $OLD_VERSIONS | wc -w)
    echo "发现 $VERSION_COUNT 个非默认版本"
    
    if [ $VERSION_COUNT -ge 4 ]; then
        OLDEST_VERSION=$(echo $OLD_VERSIONS | awk '{print $1}')
        echo "删除最旧的版本: $OLDEST_VERSION"
        aws iam delete-policy-version --policy-arn $POLICY_ARN --version-id $OLDEST_VERSION
    fi
fi

# 创建新版本
echo ""
echo "4. 创建新版本的策略..."
aws iam create-policy-version \
  --policy-arn $POLICY_ARN \
  --policy-document file://iam-policy-latest.json \
  --set-as-default

echo "✓ IAM 策略已更新到最新版本"

# 重启 ALB Controller
echo ""
echo "5. 重启 ALB Controller..."
kubectl rollout restart deployment aws-load-balancer-controller -n kube-system

echo ""
echo "6. 等待 ALB Controller 就绪..."
kubectl rollout status deployment aws-load-balancer-controller -n kube-system --timeout=300s

echo ""
echo "=========================================="
echo "✓ 修复完成"
echo "=========================================="

echo ""
echo "后续步骤:"
echo "1. 删除失败的 Ingress:"
echo "   kubectl delete ingress higress-alb -n higress-system"
echo ""
echo "2. 重新创建 ALB:"
echo "   ./higress_deploy.py create-lb"
echo "   或"
echo "   make create-lb"
echo ""
