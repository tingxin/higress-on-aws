#!/bin/bash
# Higress EKS 部署工具安装脚本

set -e

echo "=========================================="
echo "Higress EKS 部署工具安装"
echo "=========================================="

# 检查 Python 版本
echo ""
echo "检查 Python 版本..."
if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 未安装"
    echo "请先安装 Python 3.8 或更高版本"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✓ Python 版本: $(python3 --version)"

# 检查 pip
echo ""
echo "检查 pip..."
if ! command -v pip3 &> /dev/null; then
    echo "✗ pip3 未安装"
    echo "请先安装 pip3"
    exit 1
fi
echo "✓ pip3 已安装"

# 安装 Python 依赖
echo ""
echo "安装 Python 依赖..."
pip3 install -r requirements.txt

# 添加执行权限
echo ""
echo "添加执行权限..."
chmod +x higress_deploy.py

# 创建符号链接（可选）
echo ""
read -p "是否创建全局命令 'higress-deploy'？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo ln -sf $(pwd)/higress_deploy.py /usr/local/bin/higress-deploy
    echo "✓ 已创建全局命令: higress-deploy"
fi

# 检查必要工具
echo ""
echo "=========================================="
echo "检查必要工具"
echo "=========================================="

check_tool() {
    if command -v $1 &> /dev/null; then
        echo "✓ $2"
        return 0
    else
        echo "✗ $2 未安装"
        return 1
    fi
}

MISSING_TOOLS=0

check_tool aws "AWS CLI" || MISSING_TOOLS=$((MISSING_TOOLS+1))
check_tool kubectl "kubectl" || MISSING_TOOLS=$((MISSING_TOOLS+1))
check_tool eksctl "eksctl" || MISSING_TOOLS=$((MISSING_TOOLS+1))
check_tool helm "Helm" || MISSING_TOOLS=$((MISSING_TOOLS+1))

if [ $MISSING_TOOLS -gt 0 ]; then
    echo ""
    echo "⚠ 缺少 $MISSING_TOOLS 个必要工具"
    echo ""
    echo "安装指南："
    echo ""
    echo "AWS CLI:"
    echo "  curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o 'awscliv2.zip'"
    echo "  unzip awscliv2.zip"
    echo "  sudo ./aws/install"
    echo ""
    echo "kubectl:"
    echo "  curl -LO 'https://dl.k8s.io/release/\$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl'"
    echo "  sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl"
    echo ""
    echo "eksctl:"
    echo "  curl --silent --location 'https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_\$(uname -s)_amd64.tar.gz' | tar xz -C /tmp"
    echo "  sudo mv /tmp/eksctl /usr/local/bin"
    echo ""
    echo "Helm:"
    echo "  curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"
    echo ""
fi

# 完成
echo ""
echo "=========================================="
echo "✓ 安装完成"
echo "=========================================="
echo ""
echo "后续步骤："
echo ""
echo "1. 配置 AWS 凭证（如果还未配置）："
echo "   aws configure"
echo ""
echo "2. 初始化配置文件："
echo "   ./higress_deploy.py init"
echo "   # 或者"
echo "   higress-deploy init"
echo ""
echo "3. 编辑配置文件："
echo "   vim config.yaml"
echo ""
echo "4. 一键部署："
echo "   ./higress_deploy.py install-all"
echo "   # 或者"
echo "   higress-deploy install-all"
echo ""
echo "5. 查看帮助："
echo "   ./higress_deploy.py --help"
echo "   # 或者"
echo "   higress-deploy --help"
echo ""
