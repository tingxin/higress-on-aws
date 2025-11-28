#!/bin/bash
# 测试 IAM 策略修复是否正确添加了缺失的权限

echo "=========================================="
echo "测试 IAM 策略修复"
echo "=========================================="

# 下载原始策略
echo ""
echo "1. 下载原始 AWS 策略..."
curl -s -o test-original-policy.json https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.7.0/docs/install/iam_policy.json

# 检查原始策略是否包含所需权限
echo ""
echo "2. 检查原始策略..."
MISSING_PERMS=()

if ! grep -q "DescribeListenerAttributes" test-original-policy.json; then
    echo "  ✗ 缺少: DescribeListenerAttributes"
    MISSING_PERMS+=("DescribeListenerAttributes")
else
    echo "  ✓ 包含: DescribeListenerAttributes"
fi

if ! grep -q "ModifyListenerAttributes" test-original-policy.json; then
    echo "  ✗ 缺少: ModifyListenerAttributes"
    MISSING_PERMS+=("ModifyListenerAttributes")
else
    echo "  ✓ 包含: ModifyListenerAttributes"
fi

if ! grep -q "DescribeListenerCertificates" test-original-policy.json; then
    echo "  ✗ 缺少: DescribeListenerCertificates"
    MISSING_PERMS+=("DescribeListenerCertificates")
else
    echo "  ✓ 包含: DescribeListenerCertificates"
fi

if ! grep -q "ModifyListenerCertificates" test-original-policy.json; then
    echo "  ✗ 缺少: ModifyListenerCertificates"
    MISSING_PERMS+=("ModifyListenerCertificates")
else
    echo "  ✓ 包含: ModifyListenerCertificates"
fi

# 应用修复
if [ ${#MISSING_PERMS[@]} -gt 0 ]; then
    echo ""
    echo "3. 应用修复..."
    
    python3 << 'PYTHON_SCRIPT'
import json

# 读取策略
with open('test-original-policy.json', 'r') as f:
    policy = json.load(f)

# 需要添加的权限
additional_permissions = [
    "elasticloadbalancing:DescribeListenerAttributes",
    "elasticloadbalancing:ModifyListenerAttributes",
    "elasticloadbalancing:DescribeListenerCertificates",
    "elasticloadbalancing:ModifyListenerCertificates"
]

# 添加权限
added = []
for statement in policy.get('Statement', []):
    if statement.get('Effect') == 'Allow':
        actions = statement.get('Action', [])
        if isinstance(actions, list):
            has_elb = any('elasticloadbalancing' in action for action in actions)
            if has_elb:
                for perm in additional_permissions:
                    if perm not in actions:
                        actions.append(perm)
                        added.append(perm)

# 保存
with open('test-fixed-policy.json', 'w') as f:
    json.dump(policy, f, indent=2)

if added:
    print(f"  添加了 {len(added)} 个权限")
    for perm in added:
        print(f"    - {perm}")
else:
    print("  无需添加权限")
PYTHON_SCRIPT
    
    # 验证修复后的策略
    echo ""
    echo "4. 验证修复后的策略..."
    
    ALL_PRESENT=true
    for perm in "DescribeListenerAttributes" "ModifyListenerAttributes" "DescribeListenerCertificates" "ModifyListenerCertificates"; do
        if grep -q "$perm" test-fixed-policy.json; then
            echo "  ✓ 包含: $perm"
        else
            echo "  ✗ 缺少: $perm"
            ALL_PRESENT=false
        fi
    done
    
    # 清理
    rm -f test-original-policy.json test-fixed-policy.json
    
    echo ""
    echo "=========================================="
    if [ "$ALL_PRESENT" = true ]; then
        echo "✓ 测试通过：修复逻辑正确"
    else
        echo "✗ 测试失败：修复逻辑有问题"
    fi
    echo "=========================================="
else
    echo ""
    echo "=========================================="
    echo "✓ 原始策略已包含所有必需权限"
    echo "=========================================="
    rm -f test-original-policy.json
fi
