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
