# StorageClass 配置指南

## 概述

Higress 部署包含监控组件（Grafana、Prometheus、Loki），这些组件需要持久化存储来保存数据。本文档说明如何配置和使用 EBS-backed StorageClass。

## 自动配置

从最新版本开始，部署工具会自动：

1. **安装 EBS CSI Driver** - 在创建 EKS 集群时自动安装
2. **创建 StorageClass** - 自动创建 `ebs-gp3` StorageClass
3. **配置持久化存储** - 为监控组件自动配置 PVC

## StorageClass 详情

### ebs-gp3

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ebs-gp3
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  iops: "3000"
  throughput: "125"
  encrypted: "true"
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
```

**特性：**
- **类型**: GP3（通用 SSD）
- **IOPS**: 3000（可根据需要调整）
- **吞吐量**: 125 MB/s（可根据需要调整）
- **加密**: 启用（使用 AWS KMS）
- **卷扩展**: 支持在线扩展
- **绑定模式**: WaitForFirstConsumer（延迟绑定，优化成本）

## 监控组件存储配置

### Grafana

- **大小**: 10 GB
- **用途**: 存储 Grafana 配置、仪表板和数据库
- **PVC 名称**: `higress-console-grafana`

### Prometheus

- **大小**: 20 GB
- **用途**: 存储时间序列数据（metrics）
- **PVC 名称**: `higress-console-prometheus`
- **保留期**: 默认 15 天（可配置）

### Loki

- **大小**: 20 GB
- **用途**: 存储日志数据
- **PVC 名称**: `higress-console-loki`
- **保留期**: 默认 24 小时（可配置）

## 手动创建 StorageClass

如果自动创建失败，可以手动创建：

```bash
./create-storage-class.sh
```

或使用 kubectl：

```bash
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ebs-gp3
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  iops: "3000"
  throughput: "125"
  encrypted: "true"
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
EOF
```

## 验证 StorageClass

```bash
# 查看所有 StorageClass
kubectl get storageclass

# 查看 ebs-gp3 详情
kubectl describe storageclass ebs-gp3

# 查看 PVC 状态
kubectl get pvc -n higress-system

# 查看 PV 状态
kubectl get pv
```

## 监控存储使用

```bash
# 查看 PVC 使用情况
kubectl get pvc -n higress-system -o wide

# 查看 Pod 挂载的卷
kubectl get pods -n higress-system -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.volumes[*].persistentVolumeClaim.claimName}{"\n"}{end}'

# 查看 EBS 卷信息
aws ec2 describe-volumes --filters "Name=tag:kubernetes.io/cluster/higress-prod,Values=owned" --region us-east-2
```

## 扩展存储

### 在线扩展 PVC

```bash
# 扩展 Prometheus PVC 到 30 GB
kubectl patch pvc higress-console-prometheus -n higress-system -p '{"spec":{"resources":{"requests":{"storage":"30Gi"}}}}'

# 验证扩展
kubectl get pvc higress-console-prometheus -n higress-system
```

### 修改 StorageClass 参数

如需修改 IOPS 或吞吐量，可以创建新的 StorageClass：

```bash
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ebs-gp3-high-performance
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  iops: "6000"
  throughput: "250"
  encrypted: "true"
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
EOF
```

然后更新 Higress values 配置以使用新的 StorageClass。

## 成本优化

### 1. 使用 gp3 而不是 gp2

- **gp3**: 更便宜，性能更好
- **gp2**: 旧版本，成本更高

### 2. 调整 IOPS 和吞吐量

根据实际需求调整参数：

```yaml
parameters:
  type: gp3
  iops: "1000"      # 最低 3000，可降低到 1000
  throughput: "125" # 最低 125，可降低
```

### 3. 使用 WaitForFirstConsumer 绑定模式

- 延迟绑定，直到 Pod 调度
- 优化成本，避免创建未使用的卷

## 故障排查

### PVC 处于 Pending 状态

**症状**: PVC 无法绑定到 PV

**原因**:
1. StorageClass 不存在
2. EBS CSI Driver 未安装
3. 节点没有可用的 EBS 卷

**解决方案**:

```bash
# 1. 检查 StorageClass
kubectl get storageclass

# 2. 检查 EBS CSI Driver
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-ebs-csi-driver

# 3. 检查 PVC 事件
kubectl describe pvc <pvc-name> -n higress-system

# 4. 检查节点
kubectl describe nodes
```

### Pod 无法挂载卷

**症状**: Pod 处于 Pending 或 CrashLoopBackOff 状态

**原因**:
1. PVC 未绑定
2. 卷挂载路径权限问题
3. 节点磁盘空间不足

**解决方案**:

```bash
# 1. 检查 PVC 状态
kubectl get pvc -n higress-system

# 2. 检查 Pod 事件
kubectl describe pod <pod-name> -n higress-system

# 3. 检查节点磁盘
kubectl top nodes
df -h
```

## 备份和恢复

### 备份 EBS 卷

```bash
# 创建快照
aws ec2 create-snapshot \
  --volume-id vol-xxxxxxxxx \
  --description "Higress Prometheus backup" \
  --region us-east-2

# 查看快照
aws ec2 describe-snapshots --owner-ids self --region us-east-2
```

### 从快照恢复

```bash
# 从快照创建新卷
aws ec2 create-volume \
  --snapshot-id snap-xxxxxxxxx \
  --availability-zone us-east-2a \
  --region us-east-2

# 将卷附加到节点并挂载
```

## 相关文档

- [EBS CSI Driver](EBS-CSI-DRIVER.md)
- [架构设计](ARCHITECTURE.md)
- [故障排查](TROUBLESHOOTING.md)
