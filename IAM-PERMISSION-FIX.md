# IAM 权限问题修复说明

## 问题描述

AWS 官方提供的 Load Balancer Controller IAM 策略文件缺少以下权限：
- `elasticloadbalancing:DescribeListenerAttributes`
- `elasticloadbalancing:ModifyListenerAttributes`
- `elasticloadbalancing:ModifyListenerCertificates`

这导致创建 ALB Ingress 时出现权限错误：
```
AccessDenied: User is not authorized to perform: elasticloadbalancing:DescribeListenerAttributes
```

## 修复方案

### 自动修复（已集成到代码）

程序在安装 ALB Controller 时会自动：
1. 下载 AWS 官方 IAM 策略
2. 检测缺失的权限
3. 自动添加缺失的权限到策略中
4. 使用增强后的策略创建 IAM Policy

### 修复位置

**文件：** `higress_deploy.py`

**方法：** `install_alb_controller()`

**代码逻辑：**
```python
# 下载官方策略
curl -o iam-policy.json <AWS_URL>

# 读取并增强策略
policy = json.load('iam-policy.json')

# 添加缺失的权限
additional_permissions = [
    "elasticloadbalancing:DescribeListenerAttributes",
    "elasticloadbalancing:ModifyListenerAttributes",
    "elasticloadbalancing:DescribeListenerCertificates",
    "elasticloadbalancing:ModifyListenerCertificates"
]

# 保存增强后的策略
json.dump(policy, 'iam-policy.json')

# 使用增强后的策略创建 IAM Policy
aws iam create-policy --policy-document file://iam-policy.json
```

## 验证修复

### 方法 1：运行测试脚本

```bash
./test-iam-policy-fix.sh
```

预期输出：
```
✓ 测试通过：修复逻辑正确
```

### 方法 2：检查生成的策略文件

```bash
# 运行安装命令
./higress_deploy.py install-alb

# 检查生成的策略文件
grep -E "DescribeListenerAttributes|ModifyListenerAttributes" iam-policy.json
```

应该能找到这些权限。

### 方法 3：检查 AWS IAM 策略

```bash
# 获取策略版本
aws iam get-policy \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/AWSLoadBalancerControllerIAMPolicy

# 查看策略内容
aws iam get-policy-version \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/AWSLoadBalancerControllerIAMPolicy \
  --version-id v1 \
  | grep -E "DescribeListenerAttributes|ModifyListenerAttributes"
```

## 修复现有部署

如果您已经部署了集群但遇到权限问题，可以使用以下方法修复：

### 方法 1：使用 CLI 命令

```bash
./higress_deploy.py fix-alb-permissions
```

### 方法 2：使用修复脚本

```bash
./fix-iam-permissions.sh
```

### 方法 3：使用 Makefile

```bash
make fix-alb-permissions
```

## 影响范围

### 修复前

- ❌ 创建 ALB Ingress 失败
- ❌ 无法配置 Listener 属性
- ❌ 无法管理 SSL 证书

### 修复后

- ✅ 可以正常创建 ALB Ingress
- ✅ 可以配置 Listener 属性
- ✅ 可以管理 SSL 证书
- ✅ 新部署自动包含所需权限

## 相关文件

- `higress_deploy.py` - 主程序（包含自动修复逻辑）
- `fix-iam-permissions.sh` - 独立修复脚本
- `test-iam-policy-fix.sh` - 测试脚本
- `IAM-PERMISSION-FIX.md` - 本文档

## 技术细节

### 缺失权限的原因

AWS Load Balancer Controller 的官方 IAM 策略文件（v2.7.0）中使用了通配符 `elasticloadbalancing:Describe*`，但某些特定的 API 调用需要显式声明权限。

### 添加的权限说明

| 权限 | 用途 |
|------|------|
| `DescribeListenerAttributes` | 查询 ALB Listener 的属性配置 |
| `ModifyListenerAttributes` | 修改 ALB Listener 的属性配置 |
| `DescribeListenerCertificates` | 查询 Listener 的 SSL 证书 |
| `ModifyListenerCertificates` | 修改 Listener 的 SSL 证书 |

### 安全性考虑

添加的权限都是 ALB 管理所必需的，不会增加安全风险。这些权限：
- 仅限于 ELB 资源操作
- 不涉及其他 AWS 服务
- 符合最小权限原则
- 与 AWS 官方文档一致

## 未来改进

如果 AWS 官方更新了 IAM 策略文件并包含了这些权限，我们的代码会：
1. 检测权限已存在
2. 跳过添加步骤
3. 不会重复添加权限

## 参考资料

- [AWS Load Balancer Controller 官方文档](https://kubernetes-sigs.github.io/aws-load-balancer-controller/)
- [AWS IAM 策略文件](https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.7.0/docs/install/iam_policy.json)
- [ELB API 权限参考](https://docs.aws.amazon.com/elasticloadbalancing/latest/APIReference/)

---

**最后更新：** 2024-11-28
**版本：** 1.0.0
