# 部署顺序指南

## 问题说明

之前的部署过程中，`./higress_deploy.py deploy` 命令会因为 Helm 超时而失败。这是因为：

1. **监控组件需要 PVC** - Grafana、Prometheus、Loki 需要持久化存储
2. **PVC 需要 StorageClass** - 但 StorageClass 可能未创建或未正确配置
3. **Helm 等待超时** - 默认超时时间不足以等待 PVC 绑定和 Pod 就绪

## 正确的部署顺序

### 方式 1: 使用一键部署脚本（推荐）

```bash
./deploy-complete.sh
```

这个脚本会按正确顺序执行所有步骤。

### 方式 2: 手动执行各个步骤

#### 步骤 1: 初始化配置

```bash
./higress_deploy.py init
# 编辑 config.yaml，填入您的 AWS 资源信息
vim config.yaml
```

#### 步骤 2: 创建 EKS 集群

```bash
./higress_deploy.py create
```

**这一步会自动：**
- 创建 EKS 集群
- 安装 EBS CSI Driver addon
- 创建 ebs-gp3 StorageClass

**预计时间**: 15-20 分钟

#### 步骤 3: 安装 ALB Controller

```bash
./higress_deploy.py install-alb
```

**这一步会：**
- 创建 IAM 服务账户
- 安装 AWS Load Balancer Controller
- 等待 webhook 就绪

**预计时间**: 5-10 分钟

#### 步骤 4: 部署 Higress

```bash
./higress_deploy.py deploy
```

**这一步会：**
- 添加 Higress Helm 仓库
- 创建 higress-system 命名空间
- 安装 Higress（包括监控组件）
- 等待核心组件就绪

**预计时间**: 5-10 分钟

**注意**: 监控组件（Grafana、Prometheus、Loki）可能需要额外时间来创建 PVC 和初始化。

#### 步骤 5: 创建 ALB

```bash
./higress_deploy.py create-lb
```

**这一步会：**
- 创建 ALB Ingress 配置
- 等待 ALB 创建完成
- 保存 ALB DNS 地址到 alb-endpoint.txt

**预计时间**: 3-5 分钟

#### 步骤 6: 验证部署

```bash
./higress_deploy.py status
```

## 监控部署进度

### 监控 Pod 状态

```bash
# 实时监控 Pod 状态
kubectl get pods -n higress-system -w

# 查看 Pod 详情
kubectl describe pod <pod-name> -n higress-system

# 查看 Pod 日志
kubectl logs <pod-name> -n higress-system
```

### 监控 PVC 状态

```bash
# 查看 PVC 状态
kubectl get pvc -n higress-system

# 查看 PVC 详情
kubectl describe pvc <pvc-name> -n higress-system

# 查看 PV 状态
kubectl get pv
```

### 监控 ALB 创建

```bash
# 查看 Ingress 状态
kubectl get ingress -n higress-system

# 查看 Ingress 详情
kubectl describe ingress higress-alb -n higress-system

# 查看 Ingress 事件
kubectl get events -n higress-system --field-selector involvedObject.name=higress-alb
```

## 常见问题

### Q: 为什么 Helm 安装超时？

**A**: 因为监控组件需要时间来创建 PVC 和初始化。新版本已修复这个问题，不再使用 `--wait` 标志。

### Q: 为什么 Pod 处于 Pending 状态？

**A**: 通常是因为 PVC 无法绑定。检查：

```bash
kubectl describe pvc <pvc-name> -n higress-system
```

如果显示 "no persistent volumes available"，说明 StorageClass 未创建。运行：

```bash
./create-storage-class.sh
```

### Q: 为什么 ALB 未创建？

**A**: 可能是因为 ALB Controller 未就绪或 IAM 权限不足。检查：

```bash
# 检查 ALB Controller 状态
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller

# 查看 ALB Controller 日志
kubectl logs -n kube-system deployment/aws-load-balancer-controller

# 查看 Ingress 事件
kubectl describe ingress higress-alb -n higress-system
```

### Q: 如何重新部署？

**A**: 如果需要重新部署，先清理旧的资源：

```bash
# 仅删除 Higress
./higress_deploy.py clean higress

# 然后重新部署
./higress_deploy.py deploy
./higress_deploy.py create-lb
```

### Q: 如何完全清理？

**A**: 删除整个 EKS 集群：

```bash
./higress_deploy.py clean eks
```

## 总结

| 步骤 | 命令 | 预计时间 | 说明 |
|------|------|---------|------|
| 1 | `init` | 1 分钟 | 初始化配置 |
| 2 | `create` | 15-20 分钟 | 创建 EKS 集群 + EBS CSI + StorageClass |
| 3 | `install-alb` | 5-10 分钟 | 安装 ALB Controller |
| 4 | `deploy` | 5-10 分钟 | 部署 Higress |
| 5 | `create-lb` | 3-5 分钟 | 创建 ALB |
| 6 | `status` | 1 分钟 | 验证部署 |
| **总计** | | **30-50 分钟** | |

## 相关文档

- [快速开始](docs/QUICK-START.md)
- [用户指南](docs/USER-GUIDE.md)
- [StorageClass 配置](docs/STORAGE-CLASS.md)
- [故障排查](docs/TROUBLESHOOTING.md)
