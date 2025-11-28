# 资源清理指南

## 概述

Higress EKS 部署工具提供了灵活的资源清理选项，允许您选择性地删除资源。

## 清理选项

### 选项 1: 仅删除 Higress（推荐用于重新部署）

**适用场景：**
- 需要重新部署 Higress
- 需要更改 Higress 配置
- Higress 出现问题需要重装
- 保留 EKS 集群用于其他用途

**删除内容：**
- ✅ Higress Gateway、Controller 和 Console
- ✅ Higress 命名空间及所有配置
- ✅ ALB Ingress（如果存在）
- ✅ LoadBalancer/NLB（如果存在）

**保留内容：**
- ✅ EKS 集群和节点
- ✅ AWS Load Balancer Controller
- ✅ IAM 角色和策略

**命令：**

```bash
# 使用 CLI
./higress_deploy.py clean higress

# 使用 Makefile
make clean-higress

# 强制删除（不需要确认）
./higress_deploy.py clean higress --force
make clean-higress-force
```

**预计时间：** 2-3 分钟

---

### 选项 2: 删除整个 EKS 集群

**适用场景：**
- 完全清理所有资源
- 不再需要该环境
- 重新开始全新部署

**删除内容：**
- ✅ EKS 集群及所有节点
- ✅ Higress 及所有配置
- ✅ AWS Load Balancer Controller
- ✅ ALB/NLB 负载均衡器
- ✅ IAM 角色和策略
- ✅ Webhook 配置

**保留内容：**
- ✅ VPC 和子网
- ✅ NAT Gateway
- ✅ 其他 AWS 资源

**命令：**

```bash
# 使用 CLI
./higress_deploy.py clean eks

# 使用 Makefile
make clean-eks

# 强制删除（不需要确认）
./higress_deploy.py clean eks --force
make clean-eks-force
```

**预计时间：** 10-15 分钟

---

## 使用示例

### 示例 1: 重新部署 Higress

```bash
# 1. 删除现有的 Higress
./higress_deploy.py clean higress

# 2. 修改配置（如果需要）
vim config.yaml

# 3. 重新部署 Higress
./higress_deploy.py deploy

# 4. 重新创建 ALB
./higress_deploy.py create-lb
```

### 示例 2: 完全清理环境

```bash
# 删除整个 EKS 集群
./higress_deploy.py clean eks

# 或使用 Makefile
make clean-eks
```

### 示例 3: 快速重装（保留集群）

```bash
# 一行命令删除并重新部署 Higress
make clean-higress-force && make deploy && make create-lb
```

### 示例 4: 强制清理（不需要确认）

```bash
# 强制删除 Higress
./higress_deploy.py clean higress --force

# 强制删除 EKS 集群
./higress_deploy.py clean eks --force
```

---

## 详细步骤

### 删除 Higress 的详细过程

```bash
./higress_deploy.py clean higress
```

**执行步骤：**

1. **删除 ALB Ingress**
   - 删除 Kubernetes Ingress 资源
   - AWS 自动删除关联的 ALB

2. **删除 Higress Helm Release**
   - 卸载 Higress Gateway
   - 卸载 Higress Controller
   - 卸载 Higress Console

3. **等待 AWS 资源清理**
   - 等待 LoadBalancer 删除
   - 等待目标组删除

4. **删除命名空间**
   - 删除 higress-system 命名空间
   - 清理所有相关资源

5. **清理残留资源**
   - 检查并清理可能的 finalizers
   - 确保命名空间完全删除

---

### 删除 EKS 集群的详细过程

```bash
./higress_deploy.py clean eks
```

**执行步骤：**

1. **删除 Higress**
   - 删除所有 Ingress
   - 卸载 Higress Helm Release
   - 删除 higress-system 命名空间

2. **删除 ALB Controller**
   - 卸载 AWS Load Balancer Controller
   - 删除相关的 webhook 配置

3. **清理 Webhook 配置**
   - 删除 ValidatingWebhookConfiguration
   - 删除 MutatingWebhookConfiguration

4. **等待 AWS 资源清理**
   - 等待所有 LoadBalancer 删除
   - 等待所有目标组删除

5. **删除 EKS 集群**
   - 使用 eksctl 删除集群
   - 自动删除节点组
   - 自动删除相关的 IAM 角色

6. **清理 IAM 策略**
   - 删除 AWSLoadBalancerControllerIAMPolicy

---

## 确认提示

### 删除 Higress 时的确认

```
警告：即将删除 Higress 相关资源

此操作将删除：
  - Higress Gateway、Controller 和 Console
  - Higress 命名空间及所有配置
  - ALB Ingress（如果存在）
  - 相关的 LoadBalancer/NLB（如果存在）

保留：
  - EKS 集群和节点
  - AWS Load Balancer Controller

此操作不可恢复！

确认删除 Higress？ [y/N]:
```

### 删除 EKS 集群时的确认

```
警告：即将删除 EKS 集群: higress-prod

此操作将删除：
  - EKS 集群及所有节点
  - Higress 及所有配置
  - ALB/NLB 负载均衡器
  - AWS Load Balancer Controller
  - 相关的 IAM 角色和策略

此操作不可恢复！

请输入集群名称以确认删除: 
```

---

## 故障排查

### 问题 1: 命名空间卡在 Terminating 状态

**症状：**
```bash
kubectl get namespace higress-system
# 显示 Terminating 状态很长时间
```

**解决方案：**

```bash
# 方法 1: 使用工具自动清理（已内置）
./higress_deploy.py clean higress --force

# 方法 2: 手动清理 finalizers
kubectl get namespace higress-system -o json | \
  jq '.spec.finalizers=[]' | \
  kubectl replace --raw /api/v1/namespaces/higress-system/finalize -f -

# 方法 3: 强制删除资源
kubectl delete all --all -n higress-system --force --grace-period=0
kubectl patch namespace higress-system -p '{"metadata":{"finalizers":[]}}' --type=merge
```

### 问题 2: LoadBalancer 未删除

**症状：**
```bash
# ALB 或 NLB 仍然存在
aws elbv2 describe-load-balancers
```

**解决方案：**

```bash
# 1. 检查 Ingress 是否已删除
kubectl get ingress -A

# 2. 手动删除 Ingress
kubectl delete ingress --all -A

# 3. 等待 AWS 清理
sleep 30

# 4. 如果仍存在，手动删除 LoadBalancer
aws elbv2 delete-load-balancer --load-balancer-arn <alb-arn>
```

### 问题 3: IAM 策略删除失败

**症状：**
```bash
# 删除 IAM 策略时报错
An error occurred (DeleteConflict) when calling the DeletePolicy operation
```

**原因：** 策略仍被其他资源使用

**解决方案：**

```bash
# 1. 列出策略的所有附加
aws iam list-entities-for-policy \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/AWSLoadBalancerControllerIAMPolicy

# 2. 分离所有附加
aws iam detach-role-policy \
  --role-name <role-name> \
  --policy-arn <policy-arn>

# 3. 删除策略
aws iam delete-policy --policy-arn <policy-arn>
```

### 问题 4: EKS 集群删除超时

**症状：**
```bash
# eksctl delete cluster 长时间无响应
```

**解决方案：**

```bash
# 1. 检查集群状态
aws eks describe-cluster --name <cluster-name>

# 2. 检查节点组
aws eks list-nodegroups --cluster-name <cluster-name>

# 3. 手动删除节点组
aws eks delete-nodegroup \
  --cluster-name <cluster-name> \
  --nodegroup-name <nodegroup-name>

# 4. 等待节点组删除完成后再删除集群
aws eks delete-cluster --name <cluster-name>
```

---

## 验证清理

### 验证 Higress 已删除

```bash
# 检查命名空间
kubectl get namespace higress-system
# 应该返回 "NotFound"

# 检查 Helm Release
helm list -A | grep higress
# 应该没有输出

# 检查 LoadBalancer
aws elbv2 describe-load-balancers | grep higress
# 应该没有输出
```

### 验证 EKS 集群已删除

```bash
# 检查集群
aws eks list-clusters
# 不应该包含您的集群名称

# 检查节点组
aws eks list-nodegroups --cluster-name <cluster-name>
# 应该返回错误（集群不存在）

# 检查 IAM 策略
aws iam get-policy \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/AWSLoadBalancerControllerIAMPolicy
# 应该返回 NoSuchEntity 错误
```

---

## 成本节省

### 仅删除 Higress

**节省成本：**
- LoadBalancer: ~$16/月
- 无其他成本节省（EKS 集群仍在运行）

**适用场景：**
- 短期测试后暂停 Higress
- 保留集群用于其他应用

### 删除整个 EKS 集群

**节省成本：**
- EKS 控制平面: ~$73/月
- EC2 实例: ~$367/月
- EBS 卷: ~$24/月
- LoadBalancer: ~$16/月
- **总计: ~$480/月**

**适用场景：**
- 完全不再使用该环境
- 长期成本优化

---

## 最佳实践

1. **删除前备份**
   ```bash
   make backup
   ```

2. **分步删除（更安全）**
   ```bash
   # 先删除 Higress
   make clean-higress
   
   # 验证无问题后再删除集群
   make clean-eks
   ```

3. **使用强制删除（自动化场景）**
   ```bash
   # CI/CD 中使用
   ./higress_deploy.py clean eks --force
   ```

4. **定期清理测试环境**
   ```bash
   # 每天自动清理测试环境
   0 2 * * * cd /path/to/project && ./higress_deploy.py clean eks --force
   ```

---

## 快速参考

| 命令 | 说明 | 删除内容 | 保留内容 | 时间 |
|------|------|----------|----------|------|
| `clean higress` | 仅删除 Higress | Higress、ALB | EKS、ALB Controller | 2-3分钟 |
| `clean eks` | 删除整个集群 | 所有资源 | VPC、子网 | 10-15分钟 |
| `clean higress --force` | 强制删除 Higress | 同上 | 同上 | 2-3分钟 |
| `clean eks --force` | 强制删除集群 | 同上 | 同上 | 10-15分钟 |

---

## 相关文档

- [README.md](README.md) - 项目主文档
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - 故障排查指南
- [USAGE-EXAMPLES.md](USAGE-EXAMPLES.md) - 使用示例
