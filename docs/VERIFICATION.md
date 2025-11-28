# Higress 集群验证指南

本文档提供完整的 Higress 集群验证步骤，确保部署成功且功能正常。

## 目录

- [基础验证](#基础验证)
- [部署测试应用](#部署测试应用)
- [功能验证](#功能验证)
- [高级功能测试](#高级功能测试)
- [性能测试](#性能测试)
- [自动化验证脚本](#自动化验证脚本)

---

## 基础验证

### 1. 获取 ALB 地址

```bash
# 获取 ALB DNS 名称
ALB_DNS=$(kubectl get ingress higress-alb -n higress-system -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "ALB DNS: $ALB_DNS"

# 保存到文件
echo $ALB_DNS > alb-endpoint.txt
```

### 2. 测试 ALB 连通性

```bash
# 测试 HTTP 访问
curl -I http://$ALB_DNS

# 预期输出：
# HTTP/1.1 404 Not Found
# （404 是正常的，说明 ALB -> Higress 通了，只是还没配置路由）
```

### 3. 检查 Higress 组件状态

```bash
# 检查所有 Higress Pods
kubectl get pods -n higress-system

# 预期输出：所有 Pods 状态为 Running
# NAME                                  READY   STATUS    RESTARTS   AGE
# higress-gateway-xxxxxxxxx-xxxxx       1/1     Running   0          10m
# higress-gateway-xxxxxxxxx-xxxxx       1/1     Running   0          10m
# higress-gateway-xxxxxxxxx-xxxxx       1/1     Running   0          10m
# higress-controller-xxxxxxxxx-xxxxx    1/1     Running   0          10m
# higress-console-xxxxxxxxx-xxxxx       1/1     Running   0          10m

# 检查 Services
kubectl get svc -n higress-system

# 检查 Ingress
kubectl get ingress -n higress-system
```

---

## 部署测试应用

### 1. 创建测试应用

```bash
# 创建 httpbin 测试应用
cat > test-httpbin.yaml <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: demo
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: httpbin
  namespace: demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: httpbin
  template:
    metadata:
      labels:
        app: httpbin
    spec:
      containers:
      - name: httpbin
        image: kennethreitz/httpbin
        ports:
        - containerPort: 80
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 200m
            memory: 256Mi
---
apiVersion: v1
kind: Service
metadata:
  name: httpbin
  namespace: demo
spec:
  selector:
    app: httpbin
  ports:
  - port: 80
    targetPort: 80
EOF

# 部署应用
kubectl apply -f test-httpbin.yaml
```

### 2. 等待应用就绪

```bash
# 等待 Pod 就绪
kubectl wait --for=condition=ready pod -l app=httpbin -n demo --timeout=120s

# 查看状态
kubectl get pods -n demo

# 预期输出：
# NAME                       READY   STATUS    RESTARTS   AGE
# httpbin-xxxxxxxxxx-xxxxx   1/1     Running   0          1m
# httpbin-xxxxxxxxxx-xxxxx   1/1     Running   0          1m
```

### 3. 配置 Higress 路由

```bash
# 创建 Ingress 路由
cat > httpbin-ingress.yaml <<'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: httpbin
  namespace: demo
spec:
  ingressClassName: higress
  rules:
  - http:
      paths:
      - path: /httpbin
        pathType: Prefix
        backend:
          service:
            name: httpbin
            port:
              number: 80
EOF

# 应用路由
kubectl apply -f httpbin-ingress.yaml

# 查看 Ingress
kubectl get ingress -n demo
```

---

## 功能验证

### 1. 基本路由测试

```bash
# 获取 ALB 地址
ALB_DNS=$(cat alb-endpoint.txt)

# 测试 GET 请求
curl http://$ALB_DNS/httpbin/get

# 预期输出：JSON 格式的响应
# {
#   "args": {},
#   "headers": {
#     "Accept": "*/*",
#     "Host": "...",
#     ...
#   },
#   "origin": "...",
#   "url": "http://.../httpbin/get"
# }
```

### 2. 测试不同 HTTP 方法

```bash
# POST 请求
curl -X POST http://$ALB_DNS/httpbin/post -d "test=data"

# PUT 请求
curl -X PUT http://$ALB_DNS/httpbin/put -d '{"key":"value"}'

# DELETE 请求
curl -X DELETE http://$ALB_DNS/httpbin/delete

# 查看请求头
curl http://$ALB_DNS/httpbin/headers

# 测试状态码
curl -I http://$ALB_DNS/httpbin/status/200
curl -I http://$ALB_DNS/httpbin/status/404
```

### 3. 测试请求参数

```bash
# 带查询参数
curl "http://$ALB_DNS/httpbin/get?param1=value1&param2=value2"

# 带自定义 Header
curl -H "X-Custom-Header: test-value" http://$ALB_DNS/httpbin/headers

# 测试 User-Agent
curl -A "MyApp/1.0" http://$ALB_DNS/httpbin/user-agent
```

### 4. 测试响应格式

```bash
# JSON 响应
curl http://$ALB_DNS/httpbin/json

# HTML 响应
curl http://$ALB_DNS/httpbin/html

# XML 响应
curl http://$ALB_DNS/httpbin/xml

# 图片响应
curl -I http://$ALB_DNS/httpbin/image/png
```

---

## 高级功能测试

### 1. 路径重写

```bash
# 创建路径重写规则
cat > httpbin-rewrite.yaml <<'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: httpbin-rewrite
  namespace: demo
  annotations:
    higress.io/rewrite-target: /get
spec:
  ingressClassName: higress
  rules:
  - http:
      paths:
      - path: /test
        pathType: Prefix
        backend:
          service:
            name: httpbin
            port:
              number: 80
EOF

kubectl apply -f httpbin-rewrite.yaml

# 测试（访问 /test 会被重写为 /get）
curl http://$ALB_DNS/test
```

### 2. 基于域名的路由

```bash
# 创建基于域名的路由
cat > httpbin-host.yaml <<'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: httpbin-host
  namespace: demo
spec:
  ingressClassName: higress
  rules:
  - host: test.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: httpbin
            port:
              number: 80
EOF

kubectl apply -f httpbin-host.yaml

# 测试（使用 Host header）
curl -H "Host: test.example.com" http://$ALB_DNS/get
```

### 3. 超时和重试配置

```bash
# 创建带超时配置的路由
cat > httpbin-timeout.yaml <<'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: httpbin-timeout
  namespace: demo
  annotations:
    higress.io/timeout: "30s"
    higress.io/retry-on: "5xx"
spec:
  ingressClassName: higress
  rules:
  - http:
      paths:
      - path: /delay
        pathType: Prefix
        backend:
          service:
            name: httpbin
            port:
              number: 80
EOF

kubectl apply -f httpbin-timeout.yaml

# 测试延迟响应
curl http://$ALB_DNS/delay/5
```

---

## 性能测试

### 1. 使用 hey 进行压力测试

```bash
# 安装 hey（如果未安装）
# macOS: brew install hey
# Linux: go install github.com/rakyll/hey@latest

# 简单压测（30秒，50并发）
hey -z 30s -c 50 http://$ALB_DNS/httpbin/get

# 查看结果
# Summary:
#   Total:        30.0xxx secs
#   Slowest:      x.xxxx secs
#   Fastest:      x.xxxx secs
#   Average:      x.xxxx secs
#   Requests/sec: xxxx.xx
```

### 2. 观察自动扩缩容

```bash
# 在另一个终端观察 Pod 数量变化
watch kubectl get pods -n higress-system -l app=higress-gateway

# 查看 HPA 状态
kubectl get hpa -n higress-system

# 查看资源使用
kubectl top pods -n higress-system
```

### 3. 查看 Higress 日志

```bash
# 查看 Gateway 日志
kubectl logs -n higress-system -l app=higress-gateway --tail=100 -f

# 查看 Controller 日志
kubectl logs -n higress-system -l app=higress-controller --tail=100 -f
```

---

## 访问 Higress Console

### 方法 1：端口转发（临时访问）

```bash
# 启动端口转发
kubectl port-forward -n higress-system svc/higress-console 8080:8080

# 在浏览器访问
# http://localhost:8080

# 首次访问需要设置管理员账号密码
```

### 方法 2：通过 Ingress 暴露（生产环境）

```bash
# 创建 Console Ingress
cat > higress-console-ingress.yaml <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: higress-console
  namespace: higress-system
  annotations:
    # 建议添加 IP 白名单
    # alb.ingress.kubernetes.io/inbound-cidrs: "YOUR_OFFICE_IP/32"
spec:
  ingressClassName: alb
  rules:
  - host: console.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: higress-console
            port:
              number: 8080
EOF

kubectl apply -f higress-console-ingress.yaml

# 获取 Console 地址
kubectl get ingress higress-console -n higress-system
```

---

## 自动化验证脚本

### 完整验证脚本

```bash
#!/bin/bash
# verify-higress.sh - Higress 集群完整验证脚本

set -e

echo "=========================================="
echo "Higress 集群验证"
echo "=========================================="

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查函数
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1"
        return 1
    fi
}

# 1. 获取 ALB 地址
echo ""
echo "1. 获取 ALB 地址..."
ALB_DNS=$(kubectl get ingress higress-alb -n higress-system -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null)
if [ -n "$ALB_DNS" ]; then
    echo -e "${GREEN}✓${NC} ALB DNS: $ALB_DNS"
    echo $ALB_DNS > alb-endpoint.txt
else
    echo -e "${RED}✗${NC} 无法获取 ALB 地址"
    exit 1
fi

# 2. 测试 ALB 连通性
echo ""
echo "2. 测试 ALB 连通性..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://$ALB_DNS 2>/dev/null)
if [ "$HTTP_CODE" == "404" ] || [ "$HTTP_CODE" == "200" ]; then
    echo -e "${GREEN}✓${NC} ALB 连通正常（HTTP $HTTP_CODE）"
else
    echo -e "${YELLOW}⚠${NC} ALB 响应异常: HTTP $HTTP_CODE"
fi

# 3. 检查 Higress 组件
echo ""
echo "3. 检查 Higress 组件状态..."

GATEWAY_PODS=$(kubectl get pods -n higress-system -l app=higress-gateway --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
CONTROLLER_PODS=$(kubectl get pods -n higress-system -l app=higress-controller --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
CONSOLE_PODS=$(kubectl get pods -n higress-system -l app=higress-console --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)

echo "  Gateway Pods: $GATEWAY_PODS"
echo "  Controller Pods: $CONTROLLER_PODS"
echo "  Console Pods: $CONSOLE_PODS"

if [ "$GATEWAY_PODS" -ge 3 ] && [ "$CONTROLLER_PODS" -ge 1 ]; then
    echo -e "${GREEN}✓${NC} Higress 组件状态正常"
else
    echo -e "${RED}✗${NC} Higress 组件状态异常"
fi

# 4. 检查测试应用
echo ""
echo "4. 检查测试应用..."
if kubectl get deployment httpbin -n demo &>/dev/null; then
    POD_COUNT=$(kubectl get pods -n demo -l app=httpbin --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
    echo -e "${GREEN}✓${NC} 测试应用已部署，运行中的 Pod: $POD_COUNT"
    
    # 测试路由
    echo ""
    echo "5. 测试路由功能..."
    RESPONSE=$(curl -s http://$ALB_DNS/httpbin/get 2>/dev/null)
    if echo "$RESPONSE" | grep -q "headers"; then
        echo -e "${GREEN}✓${NC} 路由功能正常"
        echo ""
        echo "响应示例（前 15 行）："
        echo "$RESPONSE" | head -15
    else
        echo -e "${RED}✗${NC} 路由功能异常"
    fi
else
    echo -e "${YELLOW}⚠${NC} 测试应用未部署"
    echo ""
    echo "部署测试应用："
    echo "  kubectl apply -f test-httpbin.yaml"
    echo "  kubectl apply -f httpbin-ingress.yaml"
fi

# 6. 检查资源使用
echo ""
echo "6. 检查资源使用..."
echo "节点资源："
kubectl top nodes 2>/dev/null || echo "  无法获取节点资源（需要 metrics-server）"
echo ""
echo "Higress Pods 资源："
kubectl top pods -n higress-system 2>/dev/null || echo "  无法获取 Pod 资源（需要 metrics-server）"

# 7. 总结
echo ""
echo "=========================================="
echo "验证完成"
echo "=========================================="
echo ""
echo "访问信息："
echo "  ALB 地址: http://$ALB_DNS"
echo "  测试端点: http://$ALB_DNS/httpbin/get"
echo "  Console: kubectl port-forward -n higress-system svc/higress-console 8080:8080"
echo ""
echo "后续步骤："
echo "  1. 配置域名 DNS 指向 ALB"
echo "  2. 配置 SSL 证书"
echo "  3. 部署您的应用"
echo "  4. 配置路由规则"
echo ""
```

### 保存并运行脚本

```bash
# 保存脚本
cat > verify-higress.sh << 'EOF'
[上面的脚本内容]
EOF

# 添加执行权限
chmod +x verify-higress.sh

# 运行验证
./verify-higress.sh
```

---

## 常见验证问题

### 问题 1：ALB 返回 503

**原因：** 目标组健康检查失败

**解决方案：**
```bash
# 检查目标组健康状态
aws elbv2 describe-target-health --target-group-arn <tg-arn>

# 检查 Higress Gateway Service
kubectl get svc higress-gateway -n higress-system

# 检查 Endpoints
kubectl get endpoints higress-gateway -n higress-system
```

### 问题 2：路由不生效

**原因：** Ingress 配置错误或 ingressClassName 不匹配

**解决方案：**
```bash
# 检查 Ingress 配置
kubectl describe ingress <ingress-name> -n <namespace>

# 确认 ingressClassName 为 higress
kubectl get ingress <ingress-name> -n <namespace> -o yaml | grep ingressClassName

# 查看 Higress Controller 日志
kubectl logs -n higress-system -l app=higress-controller --tail=50
```

### 问题 3：测试应用无法访问

**原因：** Service 或 Pod 问题

**解决方案：**
```bash
# 检查 Service
kubectl get svc -n demo

# 检查 Endpoints
kubectl get endpoints httpbin -n demo

# 检查 Pod 日志
kubectl logs -n demo -l app=httpbin

# 测试 Service 内部访问
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://httpbin.demo.svc.cluster.local/get
```

---

## 验证检查清单

部署完成后，请确认以下项目：

### 基础检查
- [ ] ALB 已创建并可访问
- [ ] 所有 Higress Pods 状态为 Running
- [ ] Higress Gateway Service 正常
- [ ] Ingress 已创建并分配了地址

### 功能检查
- [ ] 可以通过 ALB 访问测试应用
- [ ] 路由规则生效
- [ ] HTTP 方法测试通过
- [ ] 请求参数正确传递

### 高级功能检查
- [ ] 路径重写功能正常
- [ ] 基于域名的路由正常
- [ ] 超时配置生效
- [ ] 自动扩缩容工作正常

### 性能检查
- [ ] 压力测试通过
- [ ] 响应时间在可接受范围
- [ ] 资源使用正常
- [ ] 无错误日志

### 安全检查
- [ ] 仅必要的端口对外开放
- [ ] Console 访问受限
- [ ] SSL 证书配置正确（如果使用）
- [ ] 日志记录正常

---

## 下一步

验证完成后，您可以：

1. **配置生产应用**
   - 部署您的应用到 Kubernetes
   - 创建 Ingress 路由
   - 配置域名和 SSL

2. **配置监控**
   - 安装 Prometheus 和 Grafana
   - 配置告警规则
   - 启用日志收集

3. **优化配置**
   - 调整资源限制
   - 配置自动扩缩容参数
   - 优化路由规则

4. **安全加固**
   - 配置 WAF
   - 启用访问日志
   - 配置 IP 白名单

参考文档：
- [用户指南](USER-GUIDE.md)
- [配置参考](CONFIG-REFERENCE.md)
- [故障排查](TROUBLESHOOTING.md)
