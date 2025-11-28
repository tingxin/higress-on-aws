# Higress EKS 部署工具文档

## 📚 文档导航

### 快速开始

- **[快速开始指南](QUICK-START.md)** - 5 分钟快速部署
  - 安装工具
  - 配置环境
  - 一键部署
  - 验证部署

### 完整指南

- **[用户指南](USER-GUIDE.md)** - 完整使用文档
  - 前置准备
  - 安装配置
  - 部署流程
  - 管理操作
  - 清理资源

- **[验证指南](VERIFICATION.md)** - 集群验证和功能测试 ⭐ 新增
  - 基础验证
  - 部署测试应用
  - 功能验证
  - 高级功能测试
  - 性能测试
  - 自动化验证脚本

- **[配置参考](CONFIG-REFERENCE.md)** - 配置文件详细说明
  - 配置项详解
  - 配置模板
  - 配置验证
  - 常见问题

- **[架构设计](ARCHITECTURE.md)** - 架构和设计文档
  - 系统架构
  - 组件说明
  - 高可用设计
  - 安全架构
  - 监控架构

### 运维指南

- **[清理指南](CLEANUP-GUIDE.md)** - 资源清理详细说明
  - 清理选项
  - 使用示例
  - 故障排查
  - 验证清理

- **[故障排查](TROUBLESHOOTING.md)** - 常见问题和解决方案
  - 快速诊断
  - 常见问题
  - 诊断命令
  - 完全重置

### 参考文档

- **[更新日志](CHANGELOG.md)** - 版本更新历史
  - 功能变更
  - 问题修复
  - 迁移指南

- **[EKS 手动部署指南](EKS-MANUAL-DEPLOYMENT.md)** - 手动部署参考
  - 详细步骤
  - 命令说明
  - 最佳实践

- **[EC2 部署指南](EC2-DEPLOYMENT-GUIDE.md)** - EC2 + K3s 方案（备选）
  - 适用场景
  - 部署步骤
  - 配置说明

## 📖 文档使用指南

### 新用户

1. 阅读 [快速开始指南](QUICK-START.md)
2. 参考 [配置参考](CONFIG-REFERENCE.md) 配置环境
3. 遇到问题查看 [故障排查](TROUBLESHOOTING.md)

### 运维人员

1. 阅读 [用户指南](USER-GUIDE.md) 了解完整功能
2. 参考 [架构设计](ARCHITECTURE.md) 了解系统架构
3. 使用 [清理指南](CLEANUP-GUIDE.md) 管理资源

### 开发人员

1. 阅读 [架构设计](ARCHITECTURE.md) 了解技术细节
2. 参考 [EKS 手动部署指南](EKS-MANUAL-DEPLOYMENT.md) 了解底层实现
3. 查看 [更新日志](CHANGELOG.md) 了解版本变化

## 🔍 快速查找

### 按任务查找

| 任务 | 文档 |
|------|------|
| 首次部署 | [快速开始](QUICK-START.md) |
| 验证集群 | [验证指南](VERIFICATION.md) ⭐ |
| 配置集群 | [配置参考](CONFIG-REFERENCE.md) |
| 重新部署 Higress | [清理指南](CLEANUP-GUIDE.md) |
| 解决问题 | [故障排查](TROUBLESHOOTING.md) |
| 了解架构 | [架构设计](ARCHITECTURE.md) |
| 查看更新 | [更新日志](CHANGELOG.md) |

### 按角色查找

| 角色 | 推荐文档 |
|------|----------|
| 新用户 | 快速开始 → 配置参考 → 故障排查 |
| 运维人员 | 用户指南 → 架构设计 → 清理指南 |
| 开发人员 | 架构设计 → 手动部署指南 → 更新日志 |
| 管理员 | 用户指南 → 配置参考 → 架构设计 |

## 📝 文档贡献

欢迎改进文档！

### 报告问题

- 文档错误
- 内容过时
- 缺少信息

### 贡献内容

- 添加示例
- 改进说明
- 翻译文档

## 🔗 外部资源

- [Higress 官方文档](https://higress.io/)
- [AWS EKS 文档](https://docs.aws.amazon.com/eks/)
- [Kubernetes 文档](https://kubernetes.io/docs/)
- [AWS Load Balancer Controller](https://kubernetes-sigs.github.io/aws-load-balancer-controller/)

## 📞 获取帮助

1. 查看 [故障排查文档](TROUBLESHOOTING.md)
2. 运行故障排查脚本：`./troubleshoot.sh`
3. 查看日志：`kubectl logs -n higress-system -l app=higress-gateway`
4. 提交 Issue

---

**返回 [主页](../README.md)**
