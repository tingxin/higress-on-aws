# 快速开始指南

## 5 分钟快速部署

### 步骤 1: 安装工具 (1 分钟)

```bash
./setup.sh
```

### 步骤 2: 配置 (2 分钟)

```bash
# 初始化配置文件
./higress_deploy.py init

# 编辑配置文件
vim config.yaml
```

**最小配置示例：**

```yaml
aws:
  region: us-east-1

vpc:
  vpc_id: vpc-xxxxx
  public_subnets:
    - subnet-pub-1
    - subnet-pub-2
    - subnet-pub-3
  private_subnets:
    - subnet-priv-1
    - subnet-priv-2
    - subnet-priv-3

eks:
  cluster_name: higress-prod
  kubernetes_version: '1.29'
  instance_type: c6i.xlarge
  desired_capacity: 3

higress:
  use_alb: true
  replicas: 3
```

### 步骤 3: 部署 (30-40 分钟)

```bash
# 一键部署
./higress_deploy.py install-all

# 或使用 Makefile
make install-all
```

### 步骤 4: 验证

```bash
# 查看状态
./higress_deploy.py status

# 获取访问地址
cat alb-endpoint.txt

# 测试访问
curl -I http://$(cat alb-endpoint.txt)
```

## 常用命令

```bash
# 查看帮助
./higress_deploy.py --help

# 查看状态
make status

# 查看日志
make k8s-logs

# 故障排查
./troubleshoot.sh
```

## 下一步

- [完整使用指南](USER-GUIDE.md)
- [配置参考](CONFIG-REFERENCE.md)
- [故障排查](TROUBLESHOOTING.md)
