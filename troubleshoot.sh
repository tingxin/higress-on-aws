#!/bin/bash
# Higress EKS 部署故障排查脚本

echo "=========================================="
echo "Higress EKS 部署故障排查"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1"
        return 1
    fi
}

echo ""
echo "1. 检查 Kubernetes 连接"
echo "----------------------------------------"
kubectl cluster-info > /dev/null 2>&1
check_status "Kubernetes 集群连接"

echo ""
echo "2. 检查节点状态"
echo "----------------------------------------"
kubectl get nodes
NODE_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | wc -l)
if [ "$NODE_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓${NC} 发现 $NODE_COUNT 个节点"
else
    echo -e "${RED}✗${NC} 未发现节点"
fi

echo ""
echo "3. 检查 AWS Load Balancer Controller"
echo "----------------------------------------"
echo "Deployment 状态:"
kubectl get deployment aws-load-balancer-controller -n kube-system 2>/dev/null
check_status "ALB Controller Deployment 存在"

echo ""
echo "Pod 状态:"
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller
POD_STATUS=$(kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller -o jsonpath='{.items[0].status.phase}' 2>/dev/null)
if [ "$POD_STATUS" == "Running" ]; then
    echo -e "${GREEN}✓${NC} ALB Controller Pod 运行中"
else
    echo -e "${RED}✗${NC} ALB Controller Pod 状态: $POD_STATUS"
fi

echo ""
echo "4. 检查 Webhook 服务"
echo "----------------------------------------"
echo "Webhook Service:"
kubectl get svc aws-load-balancer-webhook-service -n kube-system 2>/dev/null
check_status "Webhook Service 存在"

echo ""
echo "Webhook Endpoints:"
kubectl get endpoints aws-load-balancer-webhook-service -n kube-system 2>/dev/null
ENDPOINTS=$(kubectl get endpoints aws-load-balancer-webhook-service -n kube-system -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null)
if [ -n "$ENDPOINTS" ]; then
    echo -e "${GREEN}✓${NC} Webhook Endpoints 就绪: $ENDPOINTS"
else
    echo -e "${RED}✗${NC} Webhook Endpoints 未就绪"
fi

echo ""
echo "5. 检查 ValidatingWebhookConfiguration"
echo "----------------------------------------"
kubectl get validatingwebhookconfiguration | grep aws-load-balancer
check_status "ValidatingWebhookConfiguration 存在"

echo ""
echo "6. 检查 MutatingWebhookConfiguration"
echo "----------------------------------------"
kubectl get mutatingwebhookconfiguration | grep aws-load-balancer
check_status "MutatingWebhookConfiguration 存在"

echo ""
echo "7. 检查 Higress 命名空间"
echo "----------------------------------------"
kubectl get namespace higress-system 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} higress-system 命名空间存在"
    
    echo ""
    echo "Higress Pods:"
    kubectl get pods -n higress-system
    
    echo ""
    echo "Higress Services:"
    kubectl get svc -n higress-system
else
    echo -e "${YELLOW}⚠${NC} higress-system 命名空间不存在（Higress 未部署）"
fi

echo ""
echo "8. 检查最近的事件"
echo "----------------------------------------"
echo "kube-system 命名空间事件:"
kubectl get events -n kube-system --sort-by='.lastTimestamp' | tail -10

if kubectl get namespace higress-system > /dev/null 2>&1; then
    echo ""
    echo "higress-system 命名空间事件:"
    kubectl get events -n higress-system --sort-by='.lastTimestamp' | tail -10
fi

echo ""
echo "9. ALB Controller 日志（最近 20 行）"
echo "----------------------------------------"
kubectl logs -n kube-system deployment/aws-load-balancer-controller --tail=20 2>/dev/null || echo "无法获取日志"

echo ""
echo "=========================================="
echo "故障排查完成"
echo "=========================================="

echo ""
echo "常见问题和解决方案:"
echo ""
echo "问题 1: Webhook Endpoints 未就绪"
echo "解决方案:"
echo "  kubectl rollout restart deployment aws-load-balancer-controller -n kube-system"
echo "  # 等待 30 秒后重试"
echo ""
echo "问题 2: ALB Controller Pod 未运行"
echo "解决方案:"
echo "  kubectl describe pod -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller"
echo "  # 查看详细错误信息"
echo ""
echo "问题 3: Webhook 配置错误"
echo "解决方案:"
echo "  kubectl delete validatingwebhookconfiguration aws-load-balancer-webhook"
echo "  kubectl delete mutatingwebhookconfiguration aws-load-balancer-webhook"
echo "  helm uninstall aws-load-balancer-controller -n kube-system"
echo "  # 重新安装 ALB Controller"
echo ""
echo "问题 4: Higress 安装失败"
echo "解决方案:"
echo "  # 确保 ALB Controller 完全就绪后再安装 Higress"
echo "  ./higress_deploy.py deploy"
echo ""
