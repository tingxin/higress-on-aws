# EBS CSI Driver 说明

## 概述

EBS CSI (Container Storage Interface) Driver 是 AWS 提供的存储插件，允许 Kubernetes 使用 Amazon EBS 卷作为持久化存储。

## 为什么需要 EBS CSI Driver

1. **持久化存储**：为 StatefulSet 和需要持久化数据的应用提供存储
2. **动态卷供应**：自动创建和管理 EBS 卷
3. **卷快照**：支持创建和恢复卷快照
4. **卷扩容**：支持在线扩容 EBS 卷

## 自动安装

本工具在创建 EKS 集群时会自动安装 EBS CSI Driver。

```bash
# 创建集群时自动安装
./higress_deploy.py create
```

## 手动安装

如果集群已创建但未安装 EBS CSI Driver：

```bash
# 使用 CLI 工具
./higress_deploy.py install-ebs-csi

# 或使用 Makefile
make install-ebs-csi
```

## 验证安装

```bash
# 检查 EBS CSI Driver Pods
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-ebs-csi-driver

# 预期输出：
# NAME                                  READY   STATUS    RESTARTS   AGE
# ebs-csi-controller-xxxxxxxxxx-xxxxx   6/6     Running   0          5m
# ebs-csi-controller-xxxxxxxxxx-xxxxx   6/6     Running   0          5m
# ebs-csi-node-xxxxx                    3/3     Running   0          5m
# ebs-csi-node-xxxxx                    3/3     Running   0          5m
# ebs-csi-node-xxxxx                    3/3     Running   0          5m

# 检查 StorageClass
kubectl get storageclass

# 预期输出应包含：
# NAME            PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
# gp2 (default)   kubernetes.io/aws-ebs   Delete          WaitForFirstConsumer   false                  10m
# gp3             ebs.csi.aws.com         Delete          WaitForFirstConsumer   true                   5m
```

## 使用示例

### 1. 创建 PersistentVolumeClaim

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ebs-claim
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: gp3
  resources:
    requests:
      storage: 10Gi
```

### 2. 在 Pod 中使用

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: app
spec:
  containers:
  - name: app
    image: nginx
    volumeMounts:
    - name: persistent-storage
      mountPath: /data
  volumes:
  - name: persistent-storage
    persistentVolumeClaim:
      claimName: ebs-claim
```

### 3. 在 StatefulSet 中使用

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: web
spec:
  serviceName: "nginx"
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx
        volumeMounts:
        - name: www
          mountPath: /usr/share/nginx/html
  volumeClaimTemplates:
  - metadata:
      name: www
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: "gp3"
      resources:
        requests:
          storage: 10Gi
```

## StorageClass 配置

### 默认 gp2 StorageClass

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp2
provisioner: kubernetes.io/aws-ebs
parameters:
  type: gp2
  fsType: ext4
volumeBindingMode: WaitForFirstConsumer
```

### 推荐的 gp3 StorageClass

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  fsType: ext4
  iops: "3000"
  throughput: "125"
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
```

### 创建自定义 StorageClass

```bash
cat > custom-storageclass.yaml <<'EOF'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: ebs.csi.aws.com
parameters:
  type: io2
  iops: "10000"
  fsType: ext4
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
EOF

kubectl apply -f custom-storageclass.yaml
```

## 卷快照

### 1. 创建 VolumeSnapshotClass

```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: ebs-snapshot-class
driver: ebs.csi.aws.com
deletionPolicy: Delete
```

### 2. 创建快照

```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: ebs-volume-snapshot
spec:
  volumeSnapshotClassName: ebs-snapshot-class
  source:
    persistentVolumeClaimName: ebs-claim
```

### 3. 从快照恢复

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ebs-claim-restored
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: gp3
  dataSource:
    name: ebs-volume-snapshot
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
  resources:
    requests:
      storage: 10Gi
```

## 卷扩容

### 1. 确保 StorageClass 允许扩容

```bash
kubectl get storageclass gp3 -o yaml | grep allowVolumeExpansion
# 应该显示: allowVolumeExpansion: true
```

### 2. 扩容 PVC

```bash
# 编辑 PVC
kubectl edit pvc ebs-claim

# 修改 storage 大小
spec:
  resources:
    requests:
      storage: 20Gi  # 从 10Gi 扩容到 20Gi
```

### 3. 验证扩容

```bash
# 查看 PVC 状态
kubectl get pvc ebs-claim

# 查看事件
kubectl describe pvc ebs-claim
```

## 性能优化

### gp3 vs gp2

| 特性 | gp2 | gp3 |
|------|-----|-----|
| 基准性能 | 3 IOPS/GB | 3000 IOPS |
| 最大 IOPS | 16000 | 16000 |
| 吞吐量 | 250 MB/s | 125-1000 MB/s |
| 成本 | 较高 | 较低（约便宜 20%） |

**推荐使用 gp3**，性能更好且成本更低。

### 高性能场景

对于数据库等高性能需求：

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: high-performance
provisioner: ebs.csi.aws.com
parameters:
  type: io2
  iops: "64000"
  throughput: "1000"
allowVolumeExpansion: true
```

## 故障排查

### 问题 1：PVC 一直处于 Pending 状态

```bash
# 检查 PVC 事件
kubectl describe pvc <pvc-name>

# 常见原因：
# 1. EBS CSI Driver 未安装
# 2. IAM 权限不足
# 3. 可用区不匹配
```

### 问题 2：EBS CSI Driver Pods 未运行

```bash
# 检查 Pods
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-ebs-csi-driver

# 查看日志
kubectl logs -n kube-system -l app=ebs-csi-controller

# 检查 IAM 角色
aws iam get-role --role-name AmazonEKS_EBS_CSI_DriverRole
```

### 问题 3：卷挂载失败

```bash
# 检查节点上的 CSI driver
kubectl get csinode

# 查看 Pod 事件
kubectl describe pod <pod-name>

# 检查 EBS 卷状态
aws ec2 describe-volumes --filters "Name=tag:kubernetes.io/created-for/pvc/name,Values=<pvc-name>"
```

## 最佳实践

1. **使用 gp3 而不是 gp2**
   - 性能更好
   - 成本更低
   - 支持独立配置 IOPS 和吞吐量

2. **启用卷扩容**
   ```yaml
   allowVolumeExpansion: true
   ```

3. **使用 WaitForFirstConsumer**
   ```yaml
   volumeBindingMode: WaitForFirstConsumer
   ```
   确保卷在正确的可用区创建

4. **设置合理的回收策略**
   - `Delete`：删除 PVC 时自动删除 EBS 卷（默认）
   - `Retain`：保留 EBS 卷，需要手动清理

5. **定期创建快照**
   - 用于备份
   - 用于灾难恢复
   - 用于跨区域复制

6. **监控卷使用情况**
   ```bash
   # 查看 PVC 使用情况
   kubectl get pvc -A
   
   # 查看 PV 状态
   kubectl get pv
   ```

## 成本优化

1. **删除未使用的卷**
   ```bash
   # 查找未绑定的 PV
   kubectl get pv | grep Released
   
   # 删除未使用的 PV
   kubectl delete pv <pv-name>
   ```

2. **使用 gp3 替代 gp2**
   - 可节省约 20% 成本

3. **定期清理快照**
   ```bash
   # 列出所有快照
   aws ec2 describe-snapshots --owner-ids self
   
   # 删除旧快照
   aws ec2 delete-snapshot --snapshot-id <snapshot-id>
   ```

4. **设置卷大小限制**
   ```yaml
   apiVersion: v1
   kind: ResourceQuota
   metadata:
     name: storage-quota
   spec:
     hard:
       requests.storage: "100Gi"
   ```

## 参考文档

- [AWS EBS CSI Driver GitHub](https://github.com/kubernetes-sigs/aws-ebs-csi-driver)
- [AWS EBS CSI Driver 文档](https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html)
- [Kubernetes 持久化卷](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [EBS 卷类型](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ebs-volume-types.html)

---

**返回 [文档首页](README.md)**
