#!/bin/bash
# 创建 EBS StorageClass 脚本

set -e

echo "创建 EBS StorageClass..."

# 创建 ebs-gp3 StorageClass
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ebs-gp3
  namespace: kube-system
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  iops: "3000"
  throughput: "125"
  encrypted: "true"
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
---
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ebs-gp3-default
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  iops: "3000"
  throughput: "125"
  encrypted: "true"
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
EOF

echo "✓ StorageClass 创建完成"

# 验证
echo ""
echo "验证 StorageClass..."
kubectl get storageclass | grep ebs-gp3

echo ""
echo "✓ 所有 StorageClass 已创建"
