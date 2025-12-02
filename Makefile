.PHONY: help install init create deploy status delete clean test

# 默认目标
.DEFAULT_GOAL := help

# 配置文件
CONFIG ?= config.yaml

# Python 解释器
PYTHON := python3

# CLI 工具
CLI := ./higress_deploy.py

help: ## 显示帮助信息
	@echo "Higress EKS 部署工具 - Makefile"
	@echo ""
	@echo "使用方法: make [target]"
	@echo ""
	@echo "可用目标:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## 安装依赖和工具
	@echo "安装 Python 依赖..."
	$(PYTHON) -m pip install -r requirements.txt
	@echo "添加执行权限..."
	chmod +x $(CLI) setup.sh
	@echo "✓ 安装完成"

init: ## 初始化配置文件
	$(CLI) init -o $(CONFIG)
	@echo ""
	@echo "请编辑 $(CONFIG) 填入您的 AWS 资源信息"

create: ## 创建 EKS 集群
	$(CLI) create -c $(CONFIG)

install-ebs-csi: ## 安装 EBS CSI Driver addon
	$(CLI) install-ebs-csi -c $(CONFIG)

install-alb: ## 安装 ALB Controller
	$(CLI) install-alb -c $(CONFIG)

deploy: ## 部署 Higress
	$(CLI) deploy -c $(CONFIG)

create-lb: ## 创建 ALB
	$(CLI) create-lb -c $(CONFIG)

install-all: ## 一键安装所有组件
	$(CLI) install-all -c $(CONFIG)

status: ## 查看部署状态
	$(CLI) status -c $(CONFIG)

verify: ## 运行完整验证脚本
	./verify-higress.sh

clean-higress: ## 仅删除 Higress（保留 EKS 集群）
	$(CLI) clean higress -c $(CONFIG)

clean-higress-force: ## 强制删除 Higress（不需要确认）
	$(CLI) clean higress -c $(CONFIG) --force

clean-eks: ## 删除整个 EKS 集群
	$(CLI) clean eks -c $(CONFIG)

clean-eks-force: ## 强制删除 EKS 集群（不需要确认）
	$(CLI) clean eks -c $(CONFIG) --force

delete: ## 删除集群（已弃用，请使用 clean-eks）
	@echo "⚠ 警告: 'delete' 已弃用，请使用 'clean-eks'"
	$(CLI) clean eks -c $(CONFIG)

delete-force: ## 强制删除集群（已弃用，请使用 clean-eks-force）
	@echo "⚠ 警告: 'delete-force' 已弃用，请使用 'clean-eks-force'"
	$(CLI) clean eks -c $(CONFIG) --force

clean: ## 清理生成的文件
	@echo "清理生成的文件..."
	rm -f eks-cluster-config.yaml
	rm -f higress-values.yaml
	rm -f higress-alb-ingress.yaml
	rm -f alb-endpoint.txt
	rm -f iam-policy.json
	rm -f test-app.yaml
	rm -f httpbin-ingress.yaml
	rm -f higress-console-ingress.yaml
	rm -f *.backup
	@echo "✓ 清理完成"

check-tools: ## 检查必要工具是否安装
	@echo "检查必要工具..."
	@command -v aws >/dev/null 2>&1 || { echo "✗ AWS CLI 未安装"; exit 1; }
	@echo "✓ AWS CLI"
	@command -v kubectl >/dev/null 2>&1 || { echo "✗ kubectl 未安装"; exit 1; }
	@echo "✓ kubectl"
	@command -v eksctl >/dev/null 2>&1 || { echo "✗ eksctl 未安装"; exit 1; }
	@echo "✓ eksctl"
	@command -v helm >/dev/null 2>&1 || { echo "✗ Helm 未安装"; exit 1; }
	@echo "✓ Helm"
	@echo "✓ 所有工具已安装"

test: ## 运行测试
	@echo "运行测试..."
	$(PYTHON) -m pytest tests/ -v

# Kubernetes 相关命令
k8s-nodes: ## 查看 Kubernetes 节点
	kubectl get nodes

k8s-pods: ## 查看 Higress Pods
	kubectl get pods -n higress-system

k8s-svc: ## 查看 Higress Services
	kubectl get svc -n higress-system

k8s-ingress: ## 查看所有 Ingress
	kubectl get ingress -A

k8s-logs: ## 查看 Higress Gateway 日志
	kubectl logs -n higress-system -l app=higress-gateway --tail=100

k8s-top: ## 查看资源使用情况
	@echo "节点资源使用:"
	kubectl top nodes
	@echo ""
	@echo "Pod 资源使用:"
	kubectl top pods -n higress-system

k8s-console: ## 端口转发 Higress Console
	@echo "访问 http://localhost:8080"
	kubectl port-forward -n higress-system svc/higress-console 8080:8080

# AWS 相关命令
aws-clusters: ## 列出所有 EKS 集群
	aws eks list-clusters --region $(shell grep region $(CONFIG) | awk '{print $$2}')

aws-alb: ## 列出所有 ALB
	aws elbv2 describe-load-balancers --region $(shell grep region $(CONFIG) | awk '{print $$2}')

aws-subnets: ## 查看子网信息
	aws ec2 describe-subnets --subnet-ids $(shell grep -A 3 public_subnets $(CONFIG) | grep subnet | awk '{print $$2}' | tr -d '-' | tr '\n' ' ')

# 备份和恢复
backup: ## 备份 Higress 配置
	@echo "备份 Higress 配置..."
	@mkdir -p backups/$(shell date +%Y%m%d)
	kubectl get all -n higress-system -o yaml > backups/$(shell date +%Y%m%d)/higress-all.yaml
	kubectl get configmap -n higress-system -o yaml > backups/$(shell date +%Y%m%d)/higress-configmaps.yaml
	kubectl get ingress -A -o yaml > backups/$(shell date +%Y%m%d)/all-ingress.yaml
	cp $(CONFIG) backups/$(shell date +%Y%m%d)/config.yaml
	@echo "✓ 备份完成: backups/$(shell date +%Y%m%d)/"

restore: ## 恢复 Higress 配置（需要指定 DATE=YYYYMMDD）
	@if [ -z "$(DATE)" ]; then echo "请指定日期: make restore DATE=20240101"; exit 1; fi
	@echo "恢复配置: backups/$(DATE)/"
	kubectl apply -f backups/$(DATE)/higress-all.yaml
	kubectl apply -f backups/$(DATE)/all-ingress.yaml
	@echo "✓ 恢复完成"

# 开发相关
dev-setup: ## 开发环境设置
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install pytest black flake8
	chmod +x $(CLI) setup.sh

lint: ## 代码检查
	@echo "运行代码检查..."
	flake8 $(CLI) --max-line-length=120
	@echo "✓ 代码检查通过"

format: ## 代码格式化
	@echo "格式化代码..."
	black $(CLI) --line-length=120
	@echo "✓ 代码格式化完成"

# 文档相关
docs: ## 生成文档
	@echo "文档已存在:"
	@ls -1 *.md

docs-serve: ## 启动文档服务器（需要安装 mkdocs）
	@command -v mkdocs >/dev/null 2>&1 || { echo "请先安装 mkdocs: pip install mkdocs"; exit 1; }
	mkdocs serve

# 快捷命令
quick-start: install init ## 快速开始（安装 + 初始化）
	@echo ""
	@echo "后续步骤:"
	@echo "1. 编辑配置文件: vim $(CONFIG)"
	@echo "2. 一键部署: make install-all"

full-deploy: check-tools install-all status ## 完整部署流程
	@echo ""
	@echo "✓ 部署完成！"
	@echo ""
	@echo "访问地址:"
	@cat alb-endpoint.txt 2>/dev/null || echo "ALB 地址文件不存在"

# 故障排查
troubleshoot: ## 运行故障排查脚本
	./troubleshoot.sh

fix-webhook: ## 修复 ALB Controller webhook 问题
	@echo "重启 ALB Controller..."
	kubectl rollout restart deployment aws-load-balancer-controller -n kube-system
	@echo "等待 30 秒..."
	@sleep 30
	@echo "检查状态..."
	kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller
	kubectl get endpoints aws-load-balancer-webhook-service -n kube-system

fix-alb-permissions: ## 修复 ALB Controller IAM 权限问题
	$(CLI) fix-alb-permissions -c $(CONFIG)
	@echo ""
	@echo "权限已修复，现在可以重新创建 ALB:"
	@echo "  make create-lb"

fix-ebs-csi: ## 修复 EBS CSI Driver 安装冲突
	./fix-ebs-csi.sh

fix-iam: ## 修复 IAM 策略权限
	./fix-iam-policy.sh

test: ## 测试部署
	./test-deployment.sh

# 版本信息
version: ## 显示版本信息
	@echo "Higress EKS 部署工具 v1.0.0"
	@echo ""
	@echo "工具版本:"
	@$(PYTHON) --version
	@aws --version
	@kubectl version --client --short 2>/dev/null || kubectl version --client
	@eksctl version
	@helm version --short
