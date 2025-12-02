#!/bin/bash
# Higress EKS 部署工具 - 安装脚本
# 检查并安装必要的工具和依赖

set -e

echo "=========================================="
echo "Higress EKS 部署工具 - 环境检查和安装"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查工具函数
check_tool() {
    local tool=$1
    local name=$2
    
    if command -v $tool &> /dev/null; then
        version=$($tool --version 2>&1 | head -1)
        echo -e "${GREEN}✓${NC} $name 已安装: $version"
        return 0
    else
        echo -e "${RED}✗${NC} $name 未安装"
        return 1
    fi
}

# 检查必要工具
echo "【检查必要工具】"
echo ""

missing_tools=()

# 检查 Python
if ! check_tool "python3" "Python 3"; then
    missing_tools+=("python3")
fi

# 检查 pip
if ! check_tool "pip3" "pip3"; then
    missing_tools+=("pip3")
fi

# 检查 AWS CLI
if ! check_tool "aws" "AWS CLI"; then
    missing_tools+=("aws-cli")
fi

# 检查 kubectl
if ! check_tool "kubectl" "kubectl"; then
    missing_tools+=("kubectl")
fi

# 检查 eksctl
if ! check_tool "eksctl" "eksctl"; then
    missing_tools+=("eksctl")
fi

# 检查 helm
if ! check_tool "helm" "Helm"; then
    missing_tools+=("helm")
fi

echo ""

# 如果有缺失的工具，提示安装
if [ ${#missing_tools[@]} -gt 0 ]; then
    echo -e "${YELLOW}⚠ 检测到缺失的工具:${NC}"
    for tool in "${missing_tools[@]}"; do
        echo "  - $tool"
    done
    echo ""
    echo "请根据您的操作系统安装这些工具:"
    echo ""
    echo "【macOS (使用 Homebrew)】"
    echo "  brew install python3 awscli kubectl eksctl helm"
    echo ""
    echo "【Ubuntu/Debian】"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install -y python3 python3-pip"
    echo "  # 然后按照官方文档安装 AWS CLI, kubectl, eksctl, helm"
    echo ""
    echo "【Amazon Linux 2】"
    echo "  sudo yum install -y python3 python3-pip"
    echo "  # 然后按照官方文档安装 AWS CLI, kubectl, eksctl, helm"
    echo ""
    echo "官方文档:"
    echo "  - AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    echo "  - kubectl: https://kubernetes.io/docs/tasks/tools/"
    echo "  - eksctl: https://eksctl.io/installation/"
    echo "  - Helm: https://helm.sh/docs/intro/install/"
    echo ""
    exit 1
fi

echo "✓ 所有必要工具已安装"
echo ""

# 安装 Python 依赖
echo "【安装 Python 依赖】"
echo ""

if [ -f "requirements.txt" ]; then
    echo "从 requirements.txt 安装依赖..."
    pip3 install -r requirements.txt
    echo -e "${GREEN}✓${NC} Python 依赖安装完成"
else
    echo -e "${YELLOW}⚠${NC} requirements.txt 不存在，跳过 Python 依赖安装"
fi

echo ""

# 设置执行权限
echo "【设置执行权限】"
echo ""

chmod +x higress_deploy.py
echo -e "${GREEN}✓${NC} higress_deploy.py 已设置为可执行"

chmod +x troubleshoot.sh
echo -e "${GREEN}✓${NC} troubleshoot.sh 已设置为可执行"

chmod +x verify-higress.sh
echo -e "${GREEN}✓${NC} verify-higress.sh 已设置为可执行"

chmod +x create-storage-class.sh
echo -e "${GREEN}✓${NC} create-storage-class.sh 已设置为可执行"

chmod +x deploy-complete.sh
echo -e "${GREEN}✓${NC} deploy-complete.sh 已设置为可执行"

echo ""

# 检查 AWS 凭证
echo "【检查 AWS 凭证】"
echo ""

if aws sts get-caller-identity &> /dev/null; then
    account_id=$(aws sts get-caller-identity --query Account --output text)
    user_arn=$(aws sts get-caller-identity --query Arn --output text)
    echo -e "${GREEN}✓${NC} AWS 凭证有效"
    echo "  账户 ID: $account_id"
    echo "  用户 ARN: $user_arn"
else
    echo -e "${YELLOW}⚠${NC} AWS 凭证未配置或无效"
    echo "请运行: aws configure"
    echo "或设置环境变量: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
fi

echo ""

# 检查配置文件
echo "【检查配置文件】"
echo ""

if [ -f "config.yaml" ]; then
    echo -e "${GREEN}✓${NC} config.yaml 已存在"
else
    echo -e "${YELLOW}⚠${NC} config.yaml 不存在"
    echo "请运行: ./higress_deploy.py init"
fi

echo ""

# 完成
echo "=========================================="
echo -e "${GREEN}✓ 环境检查和安装完成！${NC}"
echo "=========================================="
echo ""
echo "后续步骤:"
echo "1. 初始化配置:"
echo "   ./higress_deploy.py init"
echo ""
echo "2. 编辑配置文件:"
echo "   vim config.yaml"
echo ""
echo "3. 执行部署:"
echo "   ./deploy-complete.sh"
echo ""
echo "或查看详细文档:"
echo "   cat DEPLOYMENT-ORDER.md"
echo ""
