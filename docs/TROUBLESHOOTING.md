# Higress EKS 部署故障排查指南

## 快速诊断

运行自动故障排查脚本：

```bash
./troubleshoot.sh
```

或使用 Makefile：

```bash
make troubleshoot
```

---

## 常见问题和解决方案

### 问题 1: Webhook 服务未就绪 ⚠️ 最常见

**症状：**
```
Error: INSTALLATION FAILED: Internal error occurred: failed calling webhook "mservice.elbv2.k8s.aws": 
failed to call webhook: Post "https://aws-load-balancer-webhook-service.kube-system.svc:443/mutate-v1-service?timeout=10s": 
no endpoints available for service "aws-load-balancer-webhook-service"
```

**原因：**
AWS Load Balancer Controller 的 webhook 服务还没有完全就绪。

**解决方案 1：使用自动修复（推荐）**

```bash
# 使用 Makefile
make fix-webhook

# 然后重新部署 Higress
make deploy
```

**解决方案 2：手动修复**

```bash
# 1. 检查 ALB Controller 状态
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller

# 2. 检查 webhook 服务
kubectl get svc aws-load-balancer-webhook-service -n kube-system
kubectl get endpoints aws-load-balancer-webhook-service -n kube-system

# 3. 如果 endpoints 为空，重启 ALB Controller
kubectl rollout restart deployment aws-load-balancer-controller -n kube-system

# 4. 等待 30-60 秒
sleep 30

# 5. 验证 endpoints 已就绪
kubectl get endpoints aws-load-balancer-webhook-service -n kube-system

# 6. 重新部署 Higress
./higress_deploy.py deploy
```

**解决方案 3：完全重装 ALB Controller**

```bash
# 1. 卸载 ALB Controller
helm uninstall aws-load-balancer-controller -n kube-system

# 2. 删除 webhook 配置
kubectl delete validatingwebhookconfiguration aws-load-balancer-webhook 2>/dev/null
kubectl delete mutatingwebhookconfiguration aws-load-balancer-webhook 2>/dev/null

# 3. 等待清理完成
sleep 10

# 4. 重新安装
./higress_deploy.py install-alb

# 5. 等待完全就绪
sleep 30

# 6. 部署 Higress
./higress_deploy.py deploy
```

---

### 问题 2: ALB Controller Pod 无法启动

**症状：**
```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller
# 显示 CrashLoopBackOff 或 Error
```

**诊断：**

```bash
# 查看 Pod 详情
kubectl describe pod -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller

# 查看日志
kubectl logs -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller
```

**常见原因和解决方案：**

**原因 1：IAM 权限不足**

```bash
# 检查 IAM 服务账户
kubectl get serviceaccount aws-load-balancer-controller -n kube-system -o yaml

# 重新创建 IAM 服务账户
eksctl delete iamserviceaccount \
  --cluster=<cluster-name> \
  --namespace=kube-system \
  --name=aws-load-balancer-controller

./higress_deploy.py install-alb
```

**原因 2：VPC ID 错误**

```bash
# 检查 Helm values
helm get values aws-load-balancer-controller -n kube-system

# 更新 VPC ID
helm upgrade aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set vpcId=<correct-vpc-id> \
  --reuse-values
```

---

### 问题 3: Higress Pod 无法启动

**症状：**
```bash
kubectl get pods -n higress-system
# 显示 Pending、CrashLoopBackOff 或 Error
```

**诊断：**

```bash
# 查看 Pod 详情
kubectl describe pod <pod-name> -n higress-system

# 查看日志
kubectl logs <pod-name> -n higress-system

# 查看事件
kubectl get events -n higress-system --sort-by='.lastTimestamp'
```

**常见原因和解决方案：**

**原因 1：资源不足**

```bash
# 检查节点资源
kubectl top nodes

# 解决方案：扩容节点
eksctl scale nodegroup \
  --cluster=<cluster-name> \
  --name=<nodegroup-name> \
  --nodes=5
```

**原因 2：镜像拉取失败**

```bash
# 检查镜像拉取状态
kubectl describe pod <pod-name> -n higress-system | grep -A 5 "Events:"

# 解决方案：检查网络和镜像仓库访问
# Higress 使用自己的镜像仓库，通常不会有问题
```

**原因 3：配置错误**

```bash
# 检查 Higress 配置
kubectl get configmap -n higress-system
kubectl describe configmap higress-config -n higress-system

# 重新部署
helm uninstall higress -n higress-system
./higress_deploy.py deploy
```

---

### 问题 4: ALB 未创建

**症状：**
```bash
kubectl get ingress -n higress-system
# ADDRESS 列为空或长时间未分配
```

**诊断：**

```bash
# 查看 Ingress 详情
kubectl describe ingress higress-alb -n higress-system

# 查看 ALB Controller 日志
kubectl logs -n kube-system deployment/aws-load-balancer-controller --tail=50
```

**常见原因和解决方案：**

**原因 1：子网标签缺失**

```bash
# 检查子网标签
aws ec2 describe-subnets --subnet-ids <subnet-id> --query 'Subnets[*].Tags'

# 添加标签
aws ec2 create-tags --resources <subnet-id> \
  --tags Key=kubernetes.io/role/elb,Value=1 \
         Key=kubernetes.io/cluster/<cluster-name>,Value=shared
```

**原因 2：Ingress 配置错误**

```bash
# 查看 Ingress YAML
kubectl get ingress higress-alb -n higress-system -o yaml

# 删除并重新创建
kubectl delete ingress higress-alb -n higress-system
./higress_deploy.py create-lb
```

**原因 3：IAM 权限不足**

```bash
# 检查 ALB Controller 日志中的权限错误
kubectl logs -n kube-system deployment/aws-load-balancer-controller | grep -i "access denied"

# 重新创建 IAM 策略和服务账户
./higress_deploy.py install-alb
```

---

### 问题 5: 健康检查失败

**症状：**
```bash
# ALB 目标组健康检查失败
aws elbv2 describe-target-health --target-group-arn <tg-arn>
# 显示 unhealthy
```

**诊断：**

```bash
# 检查 Service
kubectl get svc higress-gateway -n higress-system

# 检查 Endpoints
kubectl get endpoints higress-gateway -n higress-system

# 测试健康检查端点
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl -v http://higress-gateway.higress-system.svc.cluster.local/
```

**解决方案：**

```bash
# 1. 确认 Service 端口正确
kubectl describe svc higress-gateway -n higress-system

# 2. 确认 Pod 正在运行
kubectl get pods -n higress-system -l app=higress-gateway

# 3. 更新 Ingress 健康检查配置
kubectl edit ingress higress-alb -n higress-system
# 修改 healthcheck-path 和 healthcheck-port

# 4. 或重新创建 ALB
kubectl delete ingress higress-alb -n higress-system
./higress_deploy.py create-lb
```

---

### 问题 6: 无法访问 ALB

**症状：**
```bash
curl http://<alb-dns>
# 超时或连接被拒绝
```

**诊断：**

```bash
# 1. 检查 ALB 状态
aws elbv2 describe-load-balancers --query "LoadBalancers[?contains(LoadBalancerName, 'k8s-higresss')]"

# 2. 检查目标组
aws elbv2 describe-target-groups --query "TargetGroups[?contains(TargetGroupName, 'k8s-higresss')]"

# 3. 检查目标健康状态
aws elbv2 describe-target-health --target-group-arn <tg-arn>

# 4. 检查安全组
aws ec2 describe-security-groups --group-ids <sg-id>
```

**解决方案：**

```bash
# 1. 等待 DNS 传播（新创建的 ALB）
# 通常需要 2-5 分钟

# 2. 检查安全组规则
# 确保 ALB 安全组允许 80/443 入站
# 确保节点安全组允许来自 ALB 的流量

# 3. 检查目标注册
kubectl get ingress higress-alb -n higress-system -o yaml
# 确认 target-type 和 subnets 配置正确
```

---

### 问题 7: SSL 证书问题

**症状：**
```bash
# HTTPS 访问失败或证书错误
curl https://<alb-dns>
```

**诊断：**

```bash
# 检查证书配置
kubectl get ingress higress-alb -n higress-system -o yaml | grep certificate-arn

# 检查 ACM 证书状态
aws acm describe-certificate --certificate-arn <cert-arn>
```

**解决方案：**

```bash
# 1. 确认证书已验证
aws acm list-certificates --certificate-statuses ISSUED

# 2. 更新 Ingress 证书配置
kubectl edit ingress higress-alb -n higress-system
# 添加或更新 alb.ingress.kubernetes.io/certificate-arn

# 3. 或在 config.yaml 中配置证书后重新创建
vim config.yaml
# 添加 alb.certificate_arn
kubectl delete ingress higress-alb -n higress-system
./higress_deploy.py create-lb
```

---

## 诊断命令速查

### 检查集群状态

```bash
# 集群信息
kubectl cluster-info

# 节点状态
kubectl get nodes

# 所有命名空间的 Pods
kubectl get pods -A

# 资源使用
kubectl top nodes
kubectl top pods -A
```

### 检查 ALB Controller

```bash
# Deployment
kubectl get deployment aws-load-balancer-controller -n kube-system

# Pods
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller

# 日志
kubectl logs -n kube-system deployment/aws-load-balancer-controller --tail=100

# Webhook 服务
kubectl get svc aws-load-balancer-webhook-service -n kube-system
kubectl get endpoints aws-load-balancer-webhook-service -n kube-system

# Webhook 配置
kubectl get validatingwebhookconfiguration | grep aws-load-balancer
kubectl get mutatingwebhookconfiguration | grep aws-load-balancer
```

### 检查 Higress

```bash
# Pods
kubectl get pods -n higress-system

# Services
kubectl get svc -n higress-system

# Ingress
kubectl get ingress -n higress-system

# 日志
kubectl logs -n higress-system -l app=higress-gateway --tail=100
kubectl logs -n higress-system -l app=higress-controller --tail=100

# 事件
kubectl get events -n higress-system --sort-by='.lastTimestamp'

# ConfigMaps
kubectl get configmap -n higress-system
```

### 检查 AWS 资源

```bash
# EKS 集群
aws eks describe-cluster --name <cluster-name>

# ALB
aws elbv2 describe-load-balancers

# 目标组
aws elbv2 describe-target-groups

# 目标健康状态
aws elbv2 describe-target-health --target-group-arn <tg-arn>

# 子网
aws ec2 describe-subnets --subnet-ids <subnet-id>

# 安全组
aws ec2 describe-security-groups --group-ids <sg-id>
```

---

## 完全重置

如果所有方法都失败，可以完全重置：

```bash
# 1. 删除 Higress
helm uninstall higress -n higress-system
kubectl delete namespace higress-system

# 2. 删除 ALB Controller
helm uninstall aws-load-balancer-controller -n kube-system
kubectl delete validatingwebhookconfiguration aws-load-balancer-webhook
kubectl delete mutatingwebhookconfiguration aws-load-balancer-webhook

# 3. 等待清理
sleep 30

# 4. 重新安装
./higress_deploy.py install-alb
sleep 30
./higress_deploy.py deploy
./higress_deploy.py create-lb
```

---

## 获取帮助

如果问题仍未解决：

1. **运行故障排查脚本**
   ```bash
   ./troubleshoot.sh > troubleshoot-output.txt
   ```

2. **收集日志**
   ```bash
   kubectl logs -n kube-system deployment/aws-load-balancer-controller > alb-controller.log
   kubectl logs -n higress-system -l app=higress-gateway > higress-gateway.log
   kubectl get events -A --sort-by='.lastTimestamp' > events.log
   ```

3. **联系支持**
   - 提供 troubleshoot-output.txt
   - 提供日志文件
   - 描述具体的错误信息和操作步骤

---

## 预防措施

为避免常见问题：

1. **部署前检查**
   ```bash
   make check-tools
   ```

2. **分步部署**
   ```bash
   make create          # 创建集群
   # 等待完全就绪
   make install-alb     # 安装 ALB Controller
   sleep 30             # 等待 webhook 就绪
   make deploy          # 部署 Higress
   make create-lb       # 创建 ALB
   ```

3. **定期备份**
   ```bash
   make backup
   ```

4. **监控资源**
   ```bash
   make k8s-top
   ```

5. **保持更新**
   ```bash
   # 定期更新工具
   pip install --upgrade -r requirements.txt
   helm repo update
   ```
