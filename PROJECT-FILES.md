# 项目文件说明

## 核心文件

```
.
├── higress_deploy.py          # 主程序（CLI 工具）
├── requirements.txt           # Python 依赖
├── setup.sh                   # 安装脚本
├── troubleshoot.sh            # 故障排查脚本
├── Makefile                   # Make 命令集合
├── .gitignore                 # Git 忽略文件
├── config.example.yaml        # 配置文件示例
└── config.yaml                # 运行时配置（由 init 生成）
```

## 文档目录

```
docs/
├── README.md                  # 文档索引
├── QUICK-START.md             # 快速开始指南
├── USER-GUIDE.md              # 完整用户指南
├── CONFIG-REFERENCE.md        # 配置参考
├── ARCHITECTURE.md            # 架构设计
├── CLEANUP-GUIDE.md           # 清理指南
├── TROUBLESHOOTING.md         # 故障排查
├── CHANGELOG.md               # 更新日志
├── EKS-MANUAL-DEPLOYMENT.md   # EKS 手动部署指南
└── EC2-DEPLOYMENT-GUIDE.md    # EC2 部署指南（备选）
```

## 运行时生成的文件

```
# 部署过程中生成
├── eks-cluster-config.yaml    # EKS 集群配置
├── higress-values.yaml         # Higress Helm values
├── higress-alb-ingress.yaml    # ALB Ingress 配置
├── alb-endpoint.txt            # ALB DNS 地址
└── iam-policy.json             # IAM 策略文件
```

## 文件说明

### 核心程序

- **higress_deploy.py** - Python CLI 工具，包含所有部署逻辑
- **requirements.txt** - Python 依赖包（click, PyYAML）
- **setup.sh** - 自动安装脚本，检查环境并安装依赖
- **troubleshoot.sh** - 自动故障排查脚本
- **Makefile** - 提供便捷的 make 命令

### 配置文件

- **config.example.yaml** - 配置文件示例，包含详细注释
- **config.yaml** - 实际使用的配置文件（不提交到 Git）

### 文档文件

所有文档都在 `docs/` 目录下，详见 [docs/README.md](docs/README.md)

## 快速开始

```bash
# 1. 安装
./setup.sh

# 2. 初始化配置
./higress_deploy.py init

# 3. 编辑配置
vim config.yaml

# 4. 部署
./higress_deploy.py install-all
```

## 更多信息

- [README.md](README.md) - 项目主页
- [docs/README.md](docs/README.md) - 文档索引
