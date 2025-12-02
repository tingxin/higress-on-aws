#!/usr/bin/env python3
"""
Higress EKS Deployment CLI Tool
自动化部署 Higress 到 AWS EKS 集群
"""

import click
import yaml
import subprocess
import json
import time
import sys
from pathlib import Path
from typing import Dict, Any, Optional


class HigressDeployer:
    """Higress 部署管理器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        # 每次初始化时都重新生成配置文件，确保配置同步
        self._regenerate_config_files()
        
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            click.echo(f"✓ 配置文件加载成功: {self.config_path}")
            return config
        except FileNotFoundError:
            click.echo(f"✗ 配置文件不存在: {self.config_path}", err=True)
            click.echo("请先运行: higress-deploy init 创建配置文件")
            sys.exit(1)
        except yaml.YAMLError as e:
            click.echo(f"✗ 配置文件格式错误: {e}", err=True)
            sys.exit(1)
    
    def _validate_config(self):
        """验证配置的完整性和有效性"""
        errors = []
        
        # 检查必需的配置项
        required_paths = [
            ('aws.region', ['aws', 'region']),
            ('vpc.vpc_id', ['vpc', 'vpc_id']),
            ('vpc.public_subnets', ['vpc', 'public_subnets']),
            ('vpc.private_subnets', ['vpc', 'private_subnets']),
            ('eks.cluster_name', ['eks', 'cluster_name']),
            ('eks.kubernetes_version', ['eks', 'kubernetes_version']),
            ('eks.instance_type', ['eks', 'instance_type']),
            ('eks.desired_capacity', ['eks', 'desired_capacity']),
            ('eks.min_size', ['eks', 'min_size']),
            ('eks.max_size', ['eks', 'max_size']),
            ('eks.volume_size', ['eks', 'volume_size']),
        ]
        
        for path_name, path_keys in required_paths:
            value = self.config
            for key in path_keys:
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    value = None
                    break
            
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"缺少必需配置: {path_name}")
        
        # 检查子网数量
        public_subnets = self.config.get('vpc', {}).get('public_subnets', [])
        private_subnets = self.config.get('vpc', {}).get('private_subnets', [])
        
        if len(public_subnets) != 3:
            errors.append(f"公有子网数量应为 3，当前为 {len(public_subnets)}")
        if len(private_subnets) != 3:
            errors.append(f"私有子网数量应为 3，当前为 {len(private_subnets)}")
        
        # 检查节点配置的逻辑
        min_size = self.config.get('eks', {}).get('min_size', 0)
        max_size = self.config.get('eks', {}).get('max_size', 0)
        desired_capacity = self.config.get('eks', {}).get('desired_capacity', 0)
        
        if min_size > max_size:
            errors.append(f"min_size ({min_size}) 不能大于 max_size ({max_size})")
        if desired_capacity < min_size or desired_capacity > max_size:
            errors.append(f"desired_capacity ({desired_capacity}) 应在 min_size ({min_size}) 和 max_size ({max_size}) 之间")
        
        return errors
    
    def _regenerate_config_files(self):
        """重新生成所有派生配置文件，确保与 config.yaml 同步"""
        try:
            # 验证配置
            errors = self._validate_config()
            if errors:
                click.echo("⚠ 警告：配置验证发现问题:", err=True)
                for error in errors:
                    click.echo(f"  - {error}", err=True)
                click.echo("请检查 config.yaml 并修正这些问题", err=True)
                return
            
            # 生成 EKS 集群配置
            self._generate_eks_config_file()
            # 生成 Higress values 配置
            self._generate_higress_values_file()
            # 生成 ALB Ingress 配置
            self._generate_alb_ingress_file()
        except Exception as e:
            # 配置文件生成失败不应该阻止程序启动，只记录警告
            click.echo(f"⚠ 警告：配置文件生成失败: {e}", err=True)
    
    def _generate_eks_config_file(self):
        """生成 EKS 集群配置文件"""
        config = self.config
        region = config['aws']['region']
        azs = ['a', 'b', 'c']
        
        eks_config = {
            'apiVersion': 'eksctl.io/v1alpha5',
            'kind': 'ClusterConfig',
            'metadata': {
                'name': config['eks']['cluster_name'],
                'region': region,
                'version': config['eks']['kubernetes_version']
            },
            'vpc': {
                'id': config['vpc']['vpc_id'],
                'subnets': {
                    'public': {
                        f"{region}{az}": {'id': subnet}
                        for az, subnet in zip(azs, config['vpc']['public_subnets'])
                    },
                    'private': {
                        f"{region}{az}": {'id': subnet}
                        for az, subnet in zip(azs, config['vpc']['private_subnets'])
                    }
                }
            },
            'iam': {
                'withOIDC': True
            },
            'managedNodeGroups': [{
                'name': config['eks']['node_group_name'],
                'instanceType': config['eks']['instance_type'],
                'desiredCapacity': config['eks']['desired_capacity'],
                'minSize': config['eks']['min_size'],
                'maxSize': config['eks']['max_size'],
                'volumeSize': config['eks']['volume_size'],
                'volumeType': 'gp3',
                'privateNetworking': True,
                'subnets': config['vpc']['private_subnets'],
                'labels': {
                    'role': 'higress',
                    'environment': 'production'
                },
                'tags': {
                    'Name': 'higress-node',
                    'Environment': 'production'
                },
                'iam': {
                    'withAddonPolicies': {
                        'autoScaler': True,
                        'albIngress': True,
                        'cloudWatch': True,
                        'ebs': True
                    }
                }
            }],
            'cloudWatch': {
                'clusterLogging': {
                    'enableTypes': ['api', 'audit', 'authenticator', 'controllerManager', 'scheduler']
                }
            }
        }
        
        config_file = 'eks-cluster-config.yaml'
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(eks_config, f, default_flow_style=False)
    
    def _generate_higress_values_file(self):
        """生成 Higress Helm values 文件"""
        higress_config = self.config.get('higress', {})
        use_alb = higress_config.get('use_alb', True)
        enable_monitoring = higress_config.get('enable_monitoring', False)
        
        if use_alb:
            values = {
                'global': {
                    'local': False,
                    'o11y': {
                        'enabled': enable_monitoring
                    }
                },
                'higress-core': {
                    'gateway': {
                        'replicas': higress_config.get('replicas', 3),
                        'resources': {
                            'requests': {
                                'cpu': higress_config.get('cpu_request', '1000m'),
                                'memory': higress_config.get('memory_request', '2Gi')
                            },
                            'limits': {
                                'cpu': higress_config.get('cpu_limit', '2000m'),
                                'memory': higress_config.get('memory_limit', '4Gi')
                            }
                        },
                        'service': {
                            'type': 'NodePort',
                            'ports': [
                                {'name': 'http', 'port': 80, 'targetPort': 80, 'nodePort': 30080},
                                {'name': 'https', 'port': 443, 'targetPort': 443, 'nodePort': 30443}
                            ]
                        },
                        'affinity': {
                            'podAntiAffinity': {
                                'requiredDuringSchedulingIgnoredDuringExecution': [{
                                    'labelSelector': {
                                        'matchExpressions': [{
                                            'key': 'app',
                                            'operator': 'In',
                                            'values': ['higress-gateway']
                                        }]
                                    },
                                    'topologyKey': 'kubernetes.io/hostname'
                                }]
                            }
                        },
                        'podDisruptionBudget': {
                            'enabled': True,
                            'minAvailable': 2
                        },
                        'autoscaling': {
                            'enabled': higress_config.get('enable_autoscaling', True),
                            'minReplicas': higress_config.get('min_replicas', 3),
                            'maxReplicas': higress_config.get('max_replicas', 10),
                            'targetCPUUtilizationPercentage': 70,
                            'targetMemoryUtilizationPercentage': 80
                        }
                    },
                    'controller': {
                        'replicas': 2,
                        'resources': {
                            'requests': {'cpu': '500m', 'memory': '1Gi'},
                            'limits': {'cpu': '1000m', 'memory': '2Gi'}
                        }
                    }
                },
                'higress-console': {
                    'enabled': True,
                    'replicas': 2,
                    'service': {'type': 'ClusterIP'},
                    'resources': {
                        'requests': {'cpu': '200m', 'memory': '512Mi'},
                        'limits': {'cpu': '500m', 'memory': '1Gi'}
                    },
                    'grafana': {
                        'persistence': {
                            'enabled': True,
                            'storageClassName': 'ebs-gp3',
                            'size': '10Gi'
                        }
                    },
                    'prometheus': {
                        'persistence': {
                            'enabled': True,
                            'storageClassName': 'ebs-gp3',
                            'size': '20Gi'
                        }
                    },
                    'loki': {
                        'persistence': {
                            'enabled': True,
                            'storageClassName': 'ebs-gp3',
                            'size': '20Gi'
                        }
                    }
                }
            }
        else:
            values = {
                'global': {'local': False, 'o11y': {'enabled': enable_monitoring}},
                'higress-core': {
                    'gateway': {
                        'replicas': higress_config.get('replicas', 3),
                        'resources': {
                            'requests': {'cpu': '1000m', 'memory': '2Gi'},
                            'limits': {'cpu': '2000m', 'memory': '4Gi'}
                        },
                        'service': {
                            'type': 'LoadBalancer',
                            'annotations': {
                                'service.beta.kubernetes.io/aws-load-balancer-type': 'nlb',
                                'service.beta.kubernetes.io/aws-load-balancer-scheme': 'internet-facing',
                                'service.beta.kubernetes.io/aws-load-balancer-cross-zone-load-balancing-enabled': 'true'
                            }
                        }
                    }
                },
                'higress-console': {
                    'enabled': True,
                    'grafana': {
                        'persistence': {
                            'enabled': True,
                            'storageClassName': 'ebs-gp3',
                            'size': '10Gi'
                        }
                    },
                    'prometheus': {
                        'persistence': {
                            'enabled': True,
                            'storageClassName': 'ebs-gp3',
                            'size': '20Gi'
                        }
                    },
                    'loki': {
                        'persistence': {
                            'enabled': True,
                            'storageClassName': 'ebs-gp3',
                            'size': '20Gi'
                        }
                    }
                }
            }
        
        values_file = 'higress-values.yaml'
        with open(values_file, 'w', encoding='utf-8') as f:
            yaml.dump(values, f, default_flow_style=False)
    
    def _generate_alb_ingress_file(self):
        """生成 ALB Ingress 配置文件"""
        config = self.config
        subnets = ','.join(config['vpc']['public_subnets'])
        cert_arn = config.get('alb', {}).get('certificate_arn', '').strip()
        has_certificate = bool(cert_arn)
        
        if has_certificate:
            listen_ports = '[{"HTTP": 80}, {"HTTPS": 443}]'
        else:
            listen_ports = '[{"HTTP": 80}]'
        
        ingress_config = {
            'apiVersion': 'networking.k8s.io/v1',
            'kind': 'Ingress',
            'metadata': {
                'name': 'higress-alb',
                'namespace': 'higress-system',
                'annotations': {
                    'alb.ingress.kubernetes.io/scheme': 'internet-facing',
                    'alb.ingress.kubernetes.io/target-type': 'instance',
                    'alb.ingress.kubernetes.io/subnets': subnets,
                    'alb.ingress.kubernetes.io/healthcheck-path': '/',
                    'alb.ingress.kubernetes.io/healthcheck-port': '30080',
                    'alb.ingress.kubernetes.io/healthcheck-protocol': 'HTTP',
                    'alb.ingress.kubernetes.io/healthcheck-interval-seconds': '30',
                    'alb.ingress.kubernetes.io/healthcheck-timeout-seconds': '5',
                    'alb.ingress.kubernetes.io/healthy-threshold-count': '2',
                    'alb.ingress.kubernetes.io/unhealthy-threshold-count': '3',
                    'alb.ingress.kubernetes.io/listen-ports': listen_ports,
                    'alb.ingress.kubernetes.io/tags': 'Environment=production,Application=higress'
                }
            },
            'spec': {
                'ingressClassName': 'alb',
                'rules': [{
                    'http': {
                        'paths': [{
                            'path': '/',
                            'pathType': 'Prefix',
                            'backend': {
                                'service': {
                                    'name': 'higress-gateway',
                                    'port': {'number': 80}
                                }
                            }
                        }]
                    }
                }]
            }
        }
        
        if has_certificate:
            ingress_config['metadata']['annotations']['alb.ingress.kubernetes.io/certificate-arn'] = cert_arn
            ingress_config['metadata']['annotations']['alb.ingress.kubernetes.io/ssl-redirect'] = '443'
            ingress_config['metadata']['annotations']['alb.ingress.kubernetes.io/ssl-policy'] = 'ELBSecurityPolicy-TLS-1-2-2017-01'
        
        ingress_file = 'higress-alb-ingress.yaml'
        with open(ingress_file, 'w', encoding='utf-8') as f:
            yaml.dump(ingress_config, f, default_flow_style=False)
    
    def _run_command(self, cmd: str, check: bool = True, capture: bool = False) -> Optional[str]:
        """执行 shell 命令"""
        click.echo(f"执行: {cmd}")
        try:
            if capture:
                result = subprocess.run(
                    cmd, shell=True, check=check,
                    capture_output=True, text=True
                )
                return result.stdout.strip()
            else:
                subprocess.run(cmd, shell=True, check=check)
                return None
        except subprocess.CalledProcessError as e:
            if check:
                click.echo(f"✗ 命令执行失败: {e}", err=True)
                sys.exit(1)
            return None
    
    def _check_prerequisites(self):
        """检查必要的工具是否安装"""
        tools = {
            'aws': 'AWS CLI',
            'kubectl': 'kubectl',
            'eksctl': 'eksctl',
            'helm': 'Helm'
        }
        
        click.echo("检查必要工具...")
        missing = []
        
        for cmd, name in tools.items():
            result = subprocess.run(
                f"which {cmd}", shell=True,
                capture_output=True, text=True
            )
            if result.returncode == 0:
                click.echo(f"  ✓ {name}")
            else:
                click.echo(f"  ✗ {name} 未安装")
                missing.append(name)
        
        if missing:
            click.echo(f"\n请先安装以下工具: {', '.join(missing)}")
            sys.exit(1)
    
    def _get_aws_account_id(self) -> str:
        """获取 AWS 账户 ID"""
        cmd = "aws sts get-caller-identity --query Account --output text"
        return self._run_command(cmd, capture=True)
    
    def _tag_subnets(self):
        """为子网添加 EKS 必需的标签"""
        click.echo("\n为子网添加标签...")
        cluster_name = self.config['eks']['cluster_name']
        
        # 公有子网标签
        for subnet in self.config['vpc']['public_subnets']:
            click.echo(f"  标记公有子网: {subnet}")
            cmd = f"""aws ec2 create-tags --resources {subnet} \
                --tags Key=kubernetes.io/role/elb,Value=1 \
                       Key=kubernetes.io/cluster/{cluster_name},Value=shared \
                --region {self.config['aws']['region']}"""
            self._run_command(cmd, check=False)
        
        # 私有子网标签
        for subnet in self.config['vpc']['private_subnets']:
            click.echo(f"  标记私有子网: {subnet}")
            cmd = f"""aws ec2 create-tags --resources {subnet} \
                --tags Key=kubernetes.io/role/internal-elb,Value=1 \
                       Key=kubernetes.io/cluster/{cluster_name},Value=shared \
                --region {self.config['aws']['region']}"""
            self._run_command(cmd, check=False)
        
        click.echo("✓ 子网标签添加完成")
    
    def _create_eks_config(self) -> str:
        """创建 EKS 集群配置文件"""
        click.echo("\n生成 EKS 集群配置...")
        self._generate_eks_config_file()
        config_file = 'eks-cluster-config.yaml'
        click.echo(f"✓ EKS 配置文件已生成: {config_file}")
        return config_file

    def _install_ebs_csi_driver(self):
        """安装 EBS CSI Driver addon"""
        click.echo("\n安装 EBS CSI Driver addon...")
        
        cluster_name = self.config['eks']['cluster_name']
        region = self.config['aws']['region']
        account_id = self._get_aws_account_id()
        
        # 创建 EBS CSI Driver 的 IAM 策略
        click.echo("创建 EBS CSI Driver IAM 策略...")
        policy_url = "https://raw.githubusercontent.com/kubernetes-sigs/aws-ebs-csi-driver/master/docs/example-iam-policy.json"
        self._run_command(f"curl -o ebs-csi-policy.json {policy_url}")
        
        policy_name = "AmazonEKS_EBS_CSI_Driver_Policy"
        policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"
        
        # 创建策略（如果不存在）
        cmd = f"aws iam create-policy --policy-name {policy_name} --policy-document file://ebs-csi-policy.json"
        self._run_command(cmd, check=False)
        
        # 检查并删除现有的 ServiceAccount（如果存在冲突）
        click.echo("检查现有的 ServiceAccount...")
        check_sa = self._run_command(
            "kubectl get serviceaccount ebs-csi-controller-sa -n kube-system",
            check=False, capture=True
        )
        
        if check_sa and "ebs-csi-controller-sa" in check_sa:
            click.echo("发现现有的 ServiceAccount，删除以避免冲突...")
            self._run_command("kubectl delete serviceaccount ebs-csi-controller-sa -n kube-system", check=False)
            time.sleep(5)
        
        # 创建 IAM 服务账户
        click.echo("创建 EBS CSI Driver IAM 服务账户...")
        cmd = f"""eksctl create iamserviceaccount \
            --cluster={cluster_name} \
            --namespace=kube-system \
            --name=ebs-csi-controller-sa \
            --attach-policy-arn={policy_arn} \
            --override-existing-serviceaccounts \
            --region={region} \
            --approve"""
        self._run_command(cmd)
        
        # 获取 IAM 角色 ARN
        click.echo("获取 IAM 角色 ARN...")
        role_name = f"eksctl-{cluster_name}-addon-iamserviceaccount-kube-system-ebs-csi-controller-sa"
        
        # 尝试获取角色 ARN
        get_role_cmd = f"aws iam get-role --role-name {role_name} --query 'Role.Arn' --output text"
        role_arn = self._run_command(get_role_cmd, check=False, capture=True)
        
        if not role_arn or "NoSuchEntity" in role_arn:
            # 如果找不到，尝试列出所有角色并查找
            click.echo("尝试查找 EBS CSI 相关的 IAM 角色...")
            list_roles_cmd = f"aws iam list-roles --query 'Roles[?contains(RoleName, `ebs-csi`)].RoleName' --output text"
            roles = self._run_command(list_roles_cmd, check=False, capture=True)
            
            if roles:
                # 使用找到的第一个角色
                role_name = roles.strip().split()[0]
                role_arn = self._run_command(
                    f"aws iam get-role --role-name {role_name} --query 'Role.Arn' --output text",
                    check=False, capture=True
                )
        
        # 安装 EBS CSI Driver addon
        click.echo("安装 EBS CSI Driver addon...")
        
        if role_arn and role_arn.strip() and "arn:aws:iam" in role_arn:
            # 使用找到的角色 ARN
            cmd = f"""aws eks create-addon \
                --cluster-name {cluster_name} \
                --addon-name aws-ebs-csi-driver \
                --service-account-role-arn {role_arn.strip()} \
                --resolve-conflicts OVERWRITE \
                --region {region}"""
        else:
            # 不指定角色，让 EKS 自动处理
            cmd = f"""aws eks create-addon \
                --cluster-name {cluster_name} \
                --addon-name aws-ebs-csi-driver \
                --resolve-conflicts OVERWRITE \
                --region {region}"""
        
        # 如果 addon 已存在，尝试更新
        result = self._run_command(cmd, check=False, capture=True)
        
        if result and "already exists" in result:
            click.echo("EBS CSI Driver addon 已存在，尝试更新...")
            if role_arn and role_arn.strip() and "arn:aws:iam" in role_arn:
                cmd = f"""aws eks update-addon \
                    --cluster-name {cluster_name} \
                    --addon-name aws-ebs-csi-driver \
                    --service-account-role-arn {role_arn.strip()} \
                    --resolve-conflicts OVERWRITE \
                    --region {region}"""
            else:
                cmd = f"""aws eks update-addon \
                    --cluster-name {cluster_name} \
                    --addon-name aws-ebs-csi-driver \
                    --resolve-conflicts OVERWRITE \
                    --region {region}"""
            self._run_command(cmd, check=False)
        
        # 等待 addon 就绪
        click.echo("等待 EBS CSI Driver addon 就绪...")
        for i in range(30):
            time.sleep(10)
            status_cmd = f"aws eks describe-addon --cluster-name {cluster_name} --addon-name aws-ebs-csi-driver --region {region} --query 'addon.status' --output text"
            status = self._run_command(status_cmd, check=False, capture=True)
            
            if status and "ACTIVE" in status:
                click.echo("✓ EBS CSI Driver addon 已激活")
                break
            elif status and "CREATE_FAILED" in status:
                click.echo("✗ EBS CSI Driver addon 创建失败")
                # 显示详细错误
                self._run_command(f"aws eks describe-addon --cluster-name {cluster_name} --addon-name aws-ebs-csi-driver --region {region}", check=False)
                break
            
            if (i + 1) % 3 == 0:
                click.echo(f"  等待中... 状态: {status.strip() if status else 'Unknown'}")
        
        # 验证安装
        click.echo("\n验证 EBS CSI Driver 安装...")
        self._run_command("kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-ebs-csi-driver", check=False)
        
        click.echo("✓ EBS CSI Driver addon 安装完成")
    
    def create_eks_cluster(self):
        """创建 EKS 集群"""
        click.echo("\n" + "="*60)
        click.echo("开始创建 EKS 集群")
        click.echo("="*60)
        
        # 检查工具
        self._check_prerequisites()
        
        # 标记子网
        self._tag_subnets()
        
        # 生成配置文件
        config_file = self._create_eks_config()
        
        # 创建集群
        click.echo("\n创建 EKS 集群（预计需要 15-20 分钟）...")
        cmd = f"eksctl create cluster -f {config_file}"
        self._run_command(cmd)
        
        # 验证集群
        click.echo("\n验证集群状态...")
        self._run_command("kubectl get nodes")
        
        # 安装 EBS CSI Driver
        self._install_ebs_csi_driver()
        
        click.echo("\n" + "="*60)
        click.echo("✓ EKS 集群创建完成")
        click.echo("="*60)
    
    def install_alb_controller(self):
        """安装 AWS Load Balancer Controller"""
        click.echo("\n" + "="*60)
        click.echo("安装 AWS Load Balancer Controller")
        click.echo("="*60)
        
        region = self.config['aws']['region']
        cluster_name = self.config['eks']['cluster_name']
        account_id = self._get_aws_account_id()
        
        # 下载 IAM 策略
        click.echo("\n下载 IAM 策略...")
        policy_url = "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.7.0/docs/install/iam_policy.json"
        self._run_command(f"curl -o iam-policy.json {policy_url}")
        
        # 添加缺失的权限
        click.echo("添加缺失的 ELB 权限...")
        try:
            with open('iam-policy.json', 'r') as f:
                policy = json.load(f)
            
            # 需要添加的权限
            additional_permissions = [
                "elasticloadbalancing:DescribeListenerAttributes",
                "elasticloadbalancing:ModifyListenerAttributes",
                "elasticloadbalancing:DescribeListenerCertificates",
                "elasticloadbalancing:ModifyListenerCertificates"
            ]
            
            # 只在第一个包含 elasticloadbalancing 权限的 Statement 中添加
            added = False
            for statement in policy.get('Statement', []):
                if not added and statement.get('Effect') == 'Allow':
                    actions = statement.get('Action', [])
                    if isinstance(actions, list):
                        # 检查是否包含 elasticloadbalancing 相关权限
                        has_elb = any('elasticloadbalancing' in action for action in actions)
                        if has_elb:
                            # 添加缺失的权限
                            for perm in additional_permissions:
                                if perm not in actions:
                                    actions.append(perm)
                                    click.echo(f"  添加权限: {perm}")
                            added = True
            
            # 保存更新后的策略
            with open('iam-policy.json', 'w') as f:
                json.dump(policy, f, indent=2)
            
            click.echo("✓ IAM 策略已增强")
        except Exception as e:
            click.echo(f"⚠ 增强策略失败: {e}")
            click.echo("将使用原始策略，可能需要手动添加权限")
        
        # 定义策略名称和 ARN
        policy_name = "AWSLoadBalancerControllerIAMPolicy"
        policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"
        
        # 检查策略是否已存在
        click.echo("\n检查 IAM 策略...")
        check_cmd = f"aws iam get-policy --policy-arn {policy_arn}"
        policy_exists = self._run_command(check_cmd, check=False, capture=True)
        
        if policy_exists and "Policy" in policy_exists:
            # 策略已存在，更新到最新版本
            click.echo("策略已存在，更新到最新版本...")
            
            # 获取非默认版本列表
            list_cmd = f"aws iam list-policy-versions --policy-arn {policy_arn} --query 'Versions[?IsDefaultVersion==`false`].VersionId' --output text"
            old_versions = self._run_command(list_cmd, check=False, capture=True)
            
            # AWS 限制最多 5 个版本，如果达到限制则删除最旧的
            if old_versions:
                versions = old_versions.strip().split()
                if len(versions) >= 4:
                    click.echo(f"删除旧版本以腾出空间: {versions[0]}")
                    delete_cmd = f"aws iam delete-policy-version --policy-arn {policy_arn} --version-id {versions[0]}"
                    self._run_command(delete_cmd, check=False)
            
            # 创建新版本并设为默认
            click.echo("创建新版本的策略...")
            create_version_cmd = f"aws iam create-policy-version --policy-arn {policy_arn} --policy-document file://iam-policy.json --set-as-default"
            self._run_command(create_version_cmd)
            click.echo("✓ IAM 策略已更新到最新版本")
        else:
            # 策略不存在，创建新策略
            click.echo("创建新的 IAM 策略...")
            cmd = f"aws iam create-policy --policy-name {policy_name} --policy-document file://iam-policy.json"
            self._run_command(cmd)
            click.echo("✓ IAM 策略创建成功")
        
        # 创建服务账户
        click.echo("\n创建 IAM 服务账户...")
        cmd = f"""eksctl create iamserviceaccount \
            --cluster={cluster_name} \
            --namespace=kube-system \
            --name=aws-load-balancer-controller \
            --attach-policy-arn={policy_arn} \
            --override-existing-serviceaccounts \
            --region={region} \
            --approve"""
        self._run_command(cmd)
        
        # 添加 Helm 仓库
        click.echo("\n添加 EKS Helm 仓库...")
        self._run_command("helm repo add eks https://aws.github.io/eks-charts")
        self._run_command("helm repo update")
        
        # 安装 Controller
        click.echo("\n安装 AWS Load Balancer Controller...")
        cmd = f"""helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
            -n kube-system \
            --set clusterName={cluster_name} \
            --set serviceAccount.create=false \
            --set serviceAccount.name=aws-load-balancer-controller \
            --set region={region} \
            --set vpcId={self.config['vpc']['vpc_id']}"""
        self._run_command(cmd)
        
        # 等待部署完成
        click.echo("\n等待 Controller 就绪...")
        click.echo("等待 Deployment 可用...")
        self._run_command(
            "kubectl wait --for=condition=available --timeout=300s "
            "deployment/aws-load-balancer-controller -n kube-system"
        )
        
        # 等待 webhook 服务就绪
        click.echo("等待 Webhook 服务就绪...")
        for i in range(30):
            result = self._run_command(
                "kubectl get endpoints aws-load-balancer-webhook-service -n kube-system -o jsonpath='{.subsets[*].addresses[*].ip}'",
                check=False, capture=True
            )
            if result and result.strip():
                click.echo("✓ Webhook 服务已就绪")
                break
            if (i + 1) % 5 == 0:
                click.echo(f"  等待中... ({i+1}秒)")
            time.sleep(1)
        else:
            click.echo("⚠ Webhook 服务等待超时，但将继续...")
        
        # 额外等待确保 webhook 完全就绪
        click.echo("等待 webhook 完全初始化...")
        time.sleep(10)
        
        self._run_command("kubectl get deployment -n kube-system aws-load-balancer-controller")
        
        click.echo("\n✓ AWS Load Balancer Controller 安装完成")
    
    def _create_higress_values(self) -> str:
        """创建 Higress Helm values 文件"""
        click.echo("\n生成 Higress 配置...")
        self._generate_higress_values_file()
        values_file = 'higress-values.yaml'
        click.echo(f"✓ Higress 配置文件已生成: {values_file}")
        return values_file

    def _wait_for_webhook_ready(self):
        """等待 ALB Controller webhook 就绪"""
        click.echo("检查 ALB Controller webhook 状态...")
        
        # 检查 webhook 服务是否存在
        result = self._run_command(
            "kubectl get service aws-load-balancer-webhook-service -n kube-system",
            check=False, capture=True
        )
        
        if not result or "NotFound" in result:
            click.echo("⚠ ALB Controller webhook 服务不存在")
            click.echo("请先运行: ./higress_deploy.py install-alb")
            return False
        
        # 等待 endpoints 就绪
        for i in range(60):
            result = self._run_command(
                "kubectl get endpoints aws-load-balancer-webhook-service -n kube-system -o jsonpath='{.subsets[*].addresses[*].ip}'",
                check=False, capture=True
            )
            if result and result.strip():
                click.echo("✓ ALB Controller webhook 已就绪")
                return True
            
            if i == 0:
                click.echo("等待 ALB Controller webhook 就绪...")
            elif (i + 1) % 10 == 0:
                click.echo(f"  等待中... ({i+1}秒)")
            
            time.sleep(1)
        
        click.echo("⚠ Webhook 等待超时")
        return False
    
    def deploy_higress(self):
        """部署 Higress"""
        click.echo("\n" + "="*60)
        click.echo("部署 Higress")
        click.echo("="*60)
        
        # 检查 ALB Controller webhook 是否就绪
        if not self._wait_for_webhook_ready():
            click.echo("\n尝试重启 ALB Controller...")
            self._run_command(
                "kubectl rollout restart deployment aws-load-balancer-controller -n kube-system",
                check=False
            )
            time.sleep(20)
            if not self._wait_for_webhook_ready():
                click.echo("\n✗ ALB Controller webhook 未就绪，但将继续尝试部署...")
        
        # 添加 Helm 仓库
        click.echo("\n添加 Higress Helm 仓库...")
        self._run_command("helm repo add higress.io https://higress.io/helm-charts")
        self._run_command("helm repo update")
        
        # 创建命名空间
        click.echo("\n创建命名空间...")
        self._run_command("kubectl create namespace higress-system", check=False)
        
        # 生成配置文件
        values_file = self._create_higress_values()
        
        # 安装 Higress（不使用 --wait，因为监控组件可能需要更长时间）
        click.echo("\n安装 Higress（预计需要 5-10 分钟）...")
        
        # 使用更长的超时时间，但不使用 --wait 来避免超时
        cmd = f"helm install higress higress.io/higress -n higress-system -f {values_file} --timeout 30m"
        self._run_command(cmd)
        
        # 等待核心组件就绪（Gateway 和 Controller）
        click.echo("\n等待 Higress 核心组件就绪...")
        self._run_command(
            "kubectl wait --for=condition=ready pod -l app=higress-gateway -n higress-system --timeout=300s",
            check=False
        )
        self._run_command(
            "kubectl wait --for=condition=ready pod -l app=higress-controller -n higress-system --timeout=300s",
            check=False
        )
        
        # 验证安装
        click.echo("\n验证 Higress 安装...")
        self._run_command("kubectl get pods -n higress-system")
        self._run_command("kubectl get svc -n higress-system")
        
        click.echo("\n✓ Higress 部署完成")
        click.echo("\n提示：监控组件（Grafana、Prometheus、Loki）可能需要额外时间来创建 PVC 和初始化")
        click.echo("可以使用以下命令监控进度:")
        click.echo("  kubectl get pvc -n higress-system")
        click.echo("  kubectl get pods -n higress-system")
    
    def _create_alb_ingress(self) -> str:
        """创建 ALB Ingress 配置"""
        click.echo("\n生成 ALB Ingress 配置...")
        
        cert_arn = self.config.get('alb', {}).get('certificate_arn', '').strip()
        has_certificate = bool(cert_arn)
        
        # 根据是否有证书决定监听端口
        if has_certificate:
            click.echo("✓ 检测到 SSL 证书配置，将创建 HTTP + HTTPS 监听器")
        else:
            click.echo("⚠ 未配置 SSL 证书，仅创建 HTTP 监听器")
            click.echo("  如需 HTTPS，请在 config.yaml 中配置 alb.certificate_arn")
        
        self._generate_alb_ingress_file()
        ingress_file = 'higress-alb-ingress.yaml'
        click.echo(f"✓ ALB Ingress 配置已生成: {ingress_file}")
        return ingress_file
    
    def create_alb(self):
        """创建 ALB"""
        click.echo("\n" + "="*60)
        click.echo("创建 Application Load Balancer")
        click.echo("="*60)
        
        # 检查并清理已存在的 Ingress
        click.echo("\n检查现有 Ingress...")
        existing = self._run_command(
            "kubectl get ingress higress-alb -n higress-system",
            check=False, capture=True
        )
        if existing and "higress-alb" in existing:
            click.echo("发现已存在的 Ingress，删除后重新创建...")
            self._run_command("kubectl delete ingress higress-alb -n higress-system", check=False)
            time.sleep(5)
        
        # 生成 Ingress 配置
        ingress_file = self._create_alb_ingress()
        
        # 应用配置
        click.echo("\n创建 ALB Ingress...")
        self._run_command(f"kubectl apply -f {ingress_file}")
        
        # 等待 ALB 创建
        click.echo("\n等待 ALB 创建（预计需要 3-5 分钟）...")
        click.echo("正在创建中，请稍候...")
        
        # 先等待一段时间让 ALB Controller 开始处理
        time.sleep(15)
        
        for i in range(40):
            # 检查是否有错误事件
            events = self._run_command(
                "kubectl get events -n higress-system --field-selector involvedObject.name=higress-alb --sort-by='.lastTimestamp' | tail -5",
                check=False, capture=True
            )
            
            if events and ("FailedDeployModel" in events or "error" in events.lower()):
                click.echo("\n⚠ 检测到 ALB 创建错误:")
                click.echo(events)
                click.echo("\n查看详细信息:")
                self._run_command("kubectl describe ingress higress-alb -n higress-system")
                
                # 检查是否是证书问题
                if "certificate must be specified" in events.lower():
                    click.echo("\n✗ 错误：HTTPS 监听器需要 SSL 证书")
                    click.echo("解决方案：")
                    click.echo("1. 在 config.yaml 中配置 alb.certificate_arn")
                    click.echo("2. 或者删除 HTTPS 配置，仅使用 HTTP")
                    sys.exit(1)
                
                # 检查是否是权限问题
                if "not authorized" in events.lower() or "access denied" in events.lower():
                    click.echo("\n✗ 错误：IAM 权限不足")
                    click.echo("解决方案：")
                    click.echo("1. 重新安装 ALB Controller: ./higress_deploy.py install-alb")
                    click.echo("2. 或手动添加缺失的 IAM 权限")
                    sys.exit(1)
            
            # 检查 ALB 地址
            result = self._run_command(
                "kubectl get ingress higress-alb -n higress-system -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'",
                check=False, capture=True
            )
            
            if result and result.strip():
                click.echo(f"\n✓ ALB 创建完成")
                click.echo(f"\nALB DNS 名称: {result}")
                
                # 检查是否配置了证书
                cert_arn = self.config.get('alb', {}).get('certificate_arn', '').strip()
                if cert_arn:
                    click.echo(f"\nHTTP 访问地址: http://{result}")
                    click.echo(f"HTTPS 访问地址: https://{result}")
                else:
                    click.echo(f"\nHTTP 访问地址: http://{result}")
                    click.echo("\n⚠ 提示：当前仅配置了 HTTP，如需 HTTPS 请配置 SSL 证书")
                
                # 保存到文件
                with open('alb-endpoint.txt', 'w') as f:
                    f.write(result)
                click.echo(f"\nALB 地址已保存到: alb-endpoint.txt")
                
                # 等待 ALB 完全就绪
                click.echo("\n等待 ALB 完全就绪...")
                time.sleep(30)
                
                # 测试访问
                click.echo("\n测试 ALB 连接...")
                test_result = self._run_command(f"curl -I -s -o /dev/null -w '%{{http_code}}' http://{result} --max-time 10", check=False, capture=True)
                if test_result:
                    click.echo(f"HTTP 状态码: {test_result}")
                
                return
            
            if (i + 1) % 3 == 0:
                click.echo(f"  等待中... ({(i+1)*10}秒)")
            
            time.sleep(10)
        
        click.echo("\n⚠ ALB 创建超时")
        click.echo("\n查看详细信息:")
        self._run_command("kubectl describe ingress higress-alb -n higress-system")
        click.echo("\n请检查:")
        click.echo("1. ALB Controller 日志: kubectl logs -n kube-system deployment/aws-load-balancer-controller")
        click.echo("2. Ingress 事件: kubectl get events -n higress-system")
        click.echo("3. 子网标签是否正确")
    
    def get_status(self):
        """获取部署状态"""
        click.echo("\n" + "="*60)
        click.echo("Higress 部署状态")
        click.echo("="*60)
        
        # EKS 集群状态
        click.echo("\n【EKS 集群】")
        cluster_name = self.config['eks']['cluster_name']
        region = self.config['aws']['region']
        cmd = f"eksctl get cluster --name {cluster_name} --region {region}"
        self._run_command(cmd, check=False)
        
        # 节点状态
        click.echo("\n【节点状态】")
        self._run_command("kubectl get nodes", check=False)
        
        # Higress Pods
        click.echo("\n【Higress Pods】")
        self._run_command("kubectl get pods -n higress-system", check=False)
        
        # Higress Services
        click.echo("\n【Higress Services】")
        self._run_command("kubectl get svc -n higress-system", check=False)
        
        # ALB Ingress
        click.echo("\n【ALB Ingress】")
        self._run_command("kubectl get ingress -n higress-system", check=False)
        
        # 获取 ALB 地址
        result = self._run_command(
            "kubectl get ingress higress-alb -n higress-system -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'",
            check=False, capture=True
        )
        if result:
            click.echo(f"\n【访问地址】")
            click.echo(f"ALB DNS: {result}")
            click.echo(f"HTTP: http://{result}")
            click.echo(f"HTTPS: https://{result}")
    
    def delete_higress(self, force: bool = False):
        """仅删除 Higress 相关资源"""
        if not force:
            click.echo("\n" + "="*60)
            click.echo("警告：即将删除 Higress 相关资源")
            click.echo("="*60)
            click.echo("\n此操作将删除：")
            click.echo("  - Higress Gateway、Controller 和 Console")
            click.echo("  - Higress 命名空间及所有配置")
            click.echo("  - ALB Ingress（如果存在）")
            click.echo("  - 相关的 LoadBalancer/NLB（如果存在）")
            click.echo("\n保留：")
            click.echo("  - EKS 集群和节点")
            click.echo("  - AWS Load Balancer Controller")
            click.echo("\n此操作不可恢复！")
            
            if not click.confirm("\n确认删除 Higress？"):
                click.echo("✗ 取消删除")
                return
        
        click.echo("\n开始删除 Higress...")
        
        # 1. 删除 ALB Ingress（会自动删除 ALB）
        click.echo("\n1. 删除 ALB Ingress...")
        self._run_command("kubectl delete ingress --all -n higress-system", check=False)
        
        # 2. 删除 Higress Helm Release
        click.echo("\n2. 删除 Higress...")
        self._run_command("helm uninstall higress -n higress-system", check=False)
        
        # 3. 等待 LoadBalancer 清理
        click.echo("\n3. 等待 AWS 资源清理...")
        time.sleep(20)
        
        # 4. 删除命名空间（会删除所有资源）
        click.echo("\n4. 删除 higress-system 命名空间...")
        self._run_command("kubectl delete namespace higress-system --timeout=60s", check=False)
        
        # 5. 清理可能残留的 finalizers
        click.echo("\n5. 检查并清理残留资源...")
        result = self._run_command(
            "kubectl get namespace higress-system -o json 2>/dev/null",
            check=False, capture=True
        )
        if result and "Terminating" in result:
            click.echo("命名空间处于 Terminating 状态，尝试强制清理...")
            self._run_command(
                'kubectl get namespace higress-system -o json | jq \'.spec.finalizers=[]\'| kubectl replace --raw /api/v1/namespaces/higress-system/finalize -f -',
                check=False
            )
        
        click.echo("\n" + "="*60)
        click.echo("✓ Higress 删除完成")
        click.echo("="*60)
        click.echo("\nEKS 集群仍在运行，如需删除集群请运行:")
        click.echo("  ./higress_deploy.py clean eks")
    
    def delete_cluster(self, force: bool = False):
        """删除 EKS 集群及所有资源"""
        cluster_name = self.config['eks']['cluster_name']
        region = self.config['aws']['region']
        
        if not force:
            click.echo("\n" + "="*60)
            click.echo(f"警告：即将删除 EKS 集群: {cluster_name}")
            click.echo("="*60)
            click.echo("\n此操作将删除：")
            click.echo("  - EKS 集群及所有节点")
            click.echo("  - Higress 及所有配置")
            click.echo("  - ALB/NLB 负载均衡器")
            click.echo("  - AWS Load Balancer Controller")
            click.echo("  - 相关的 IAM 角色和策略")
            click.echo("\n此操作不可恢复！")
            
            confirm = click.prompt("\n请输入集群名称以确认删除", type=str)
            if confirm != cluster_name:
                click.echo("✗ 集群名称不匹配，取消删除")
                return
        
        click.echo("\n开始删除集群...")
        
        # 1. 删除 Higress
        click.echo("\n1. 删除 Higress...")
        self._run_command("kubectl delete ingress --all -n higress-system", check=False)
        self._run_command("helm uninstall higress -n higress-system", check=False)
        self._run_command("kubectl delete namespace higress-system --timeout=60s", check=False)
        
        # 2. 删除 ALB Controller
        click.echo("\n2. 删除 AWS Load Balancer Controller...")
        self._run_command("helm uninstall aws-load-balancer-controller -n kube-system", check=False)
        
        # 3. 删除 webhook 配置
        click.echo("\n3. 清理 webhook 配置...")
        self._run_command("kubectl delete validatingwebhookconfiguration aws-load-balancer-webhook", check=False)
        self._run_command("kubectl delete mutatingwebhookconfiguration aws-load-balancer-webhook", check=False)
        
        # 4. 等待资源清理
        click.echo("\n4. 等待 AWS 资源清理...")
        time.sleep(30)
        
        # 5. 删除 EKS 集群
        click.echo("\n5. 删除 EKS 集群（预计需要 10-15 分钟）...")
        cmd = f"eksctl delete cluster --name {cluster_name} --region {region} --wait"
        self._run_command(cmd)
        
        # 6. 删除 IAM 策略
        click.echo("\n6. 清理 IAM 策略...")
        account_id = self._get_aws_account_id()
        policy_arn = f"arn:aws:iam::{account_id}:policy/AWSLoadBalancerControllerIAMPolicy"
        self._run_command(f"aws iam delete-policy --policy-arn {policy_arn}", check=False)
        
        click.echo("\n" + "="*60)
        click.echo("✓ 集群删除完成")
        click.echo("="*60)


@click.group()
@click.version_option(version='1.0.0')
def cli():
    """
    Higress EKS 部署工具
    
    自动化部署 Higress 到 AWS EKS 集群
    """
    pass


@cli.command()
@click.option('--output', '-o', default='config.yaml', help='配置文件路径')
def init(output):
    """初始化配置文件"""
    if Path(output).exists():
        if not click.confirm(f'配置文件 {output} 已存在，是否覆盖？'):
            return
    
    template = {
        'aws': {
            'region': 'us-east-1',
            'account_id': 'YOUR_AWS_ACCOUNT_ID'
        },
        'vpc': {
            'vpc_id': 'vpc-xxxxxxxxx',
            'public_subnets': [
                'subnet-public-1-xxxxxxxxx',
                'subnet-public-2-xxxxxxxxx',
                'subnet-public-3-xxxxxxxxx'
            ],
            'private_subnets': [
                'subnet-private-1-xxxxxxxxx',
                'subnet-private-2-xxxxxxxxx',
                'subnet-private-3-xxxxxxxxx'
            ]
        },
        'eks': {
            'cluster_name': 'higress-prod',
            'kubernetes_version': '1.29',
            'node_group_name': 'higress-nodes',
            'instance_type': 'c6i.xlarge',
            'desired_capacity': 3,
            'min_size': 3,
            'max_size': 6,
            'volume_size': 100
        },
        'higress': {
            'use_alb': True,
            'replicas': 3,
            'cpu_request': '1000m',
            'memory_request': '2Gi',
            'cpu_limit': '2000m',
            'memory_limit': '4Gi',
            'enable_autoscaling': True,
            'min_replicas': 3,
            'max_replicas': 10
        },
        'alb': {
            'certificate_arn': ''  # 可选：ACM 证书 ARN
        }
    }
    
    with open(output, 'w', encoding='utf-8') as f:
        yaml.dump(template, f, default_flow_style=False, allow_unicode=True)
    
    click.echo(f"✓ 配置文件已创建: {output}")
    click.echo(f"\n请编辑 {output} 填入您的 AWS 资源信息")


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
def create(config):
    """创建 EKS 集群"""
    deployer = HigressDeployer(config)
    deployer.create_eks_cluster()


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
def install_ebs_csi(config):
    """安装 EBS CSI Driver addon"""
    deployer = HigressDeployer(config)
    deployer._install_ebs_csi_driver()


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
def install_alb(config):
    """安装 AWS Load Balancer Controller"""
    deployer = HigressDeployer(config)
    deployer.install_alb_controller()


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
def fix_alb_permissions(config):
    """修复 ALB Controller IAM 权限问题"""
    deployer = HigressDeployer(config)
    
    click.echo("\n" + "="*60)
    click.echo("修复 ALB Controller IAM 权限")
    click.echo("="*60)
    
    account_id = deployer._get_aws_account_id()
    policy_arn = f"arn:aws:iam::{account_id}:policy/AWSLoadBalancerControllerIAMPolicy"
    
    # 下载最新策略
    click.echo("\n下载最新的 IAM 策略...")
    policy_url = "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.7.0/docs/install/iam_policy.json"
    deployer._run_command(f"curl -o iam-policy.json {policy_url}")
    
    # 添加缺失的权限
    click.echo("\n添加缺失的 ELB 权限...")
    try:
        with open('iam-policy.json', 'r') as f:
            policy = json.load(f)
        
        # 需要添加的权限
        additional_permissions = [
            "elasticloadbalancing:DescribeListenerAttributes",
            "elasticloadbalancing:ModifyListenerAttributes",
            "elasticloadbalancing:DescribeListenerCertificates",
            "elasticloadbalancing:ModifyListenerCertificates"
        ]
        
        # 只在第一个包含 elasticloadbalancing 权限的 Statement 中添加
        added = False
        for statement in policy.get('Statement', []):
            if not added and statement.get('Effect') == 'Allow':
                actions = statement.get('Action', [])
                if isinstance(actions, list):
                    has_elb = any('elasticloadbalancing' in action for action in actions)
                    if has_elb:
                        for perm in additional_permissions:
                            if perm not in actions:
                                actions.append(perm)
                                click.echo(f"  添加权限: {perm}")
                        added = True
        
        with open('iam-policy.json', 'w') as f:
            json.dump(policy, f, indent=2)
        
        click.echo("✓ IAM 策略已增强")
    except Exception as e:
        click.echo(f"⚠ 增强策略失败: {e}")
    
    # 获取非默认版本列表
    click.echo("\n检查现有策略版本...")
    list_cmd = f"aws iam list-policy-versions --policy-arn {policy_arn} --query 'Versions[?IsDefaultVersion==`false`].VersionId' --output text"
    old_versions = deployer._run_command(list_cmd, check=False, capture=True)
    
    # 如果达到版本限制，删除最旧的
    if old_versions:
        versions = old_versions.strip().split()
        if len(versions) >= 4:
            click.echo(f"删除旧版本: {versions[0]}")
            delete_cmd = f"aws iam delete-policy-version --policy-arn {policy_arn} --version-id {versions[0]}"
            deployer._run_command(delete_cmd, check=False)
    
    # 创建新版本
    click.echo("\n更新 IAM 策略到最新版本...")
    create_version_cmd = f"aws iam create-policy-version --policy-arn {policy_arn} --policy-document file://iam-policy.json --set-as-default"
    deployer._run_command(create_version_cmd)
    
    # 重启 ALB Controller
    click.echo("\n重启 ALB Controller 使权限生效...")
    deployer._run_command("kubectl rollout restart deployment aws-load-balancer-controller -n kube-system")
    deployer._run_command("kubectl rollout status deployment aws-load-balancer-controller -n kube-system --timeout=300s")
    
    click.echo("\n" + "="*60)
    click.echo("✓ IAM 权限修复完成")
    click.echo("="*60)
    click.echo("\n后续步骤:")
    click.echo("1. 如果之前创建 Ingress 失败，删除它:")
    click.echo("   kubectl delete ingress higress-alb -n higress-system")
    click.echo("2. 重新创建 ALB:")
    click.echo("   ./higress_deploy.py create-lb")


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
def deploy(config):
    """部署 Higress"""
    deployer = HigressDeployer(config)
    deployer.deploy_higress()


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
def create_lb(config):
    """创建 ALB"""
    deployer = HigressDeployer(config)
    deployer.create_alb()


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
def install_all(config):
    """一键安装（创建集群 + 安装 ALB Controller + 部署 Higress + 创建 ALB）"""
    deployer = HigressDeployer(config)
    
    click.echo("\n" + "="*60)
    click.echo("开始一键部署 Higress on EKS")
    click.echo("="*60)
    
    try:
        # 1. 创建 EKS 集群
        deployer.create_eks_cluster()
        
        # 2. 安装 ALB Controller
        deployer.install_alb_controller()
        
        # 3. 部署 Higress
        deployer.deploy_higress()
        
        # 4. 创建 ALB
        deployer.create_alb()
        
        # 5. 显示状态
        deployer.get_status()
        
        click.echo("\n" + "="*60)
        click.echo("✓ 所有组件部署完成！")
        click.echo("="*60)
        
    except Exception as e:
        click.echo(f"\n✗ 部署过程中出现错误: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
def status(config):
    """查看部署状态"""
    deployer = HigressDeployer(config)
    deployer.get_status()


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
def validate(config):
    """验证配置文件的完整性和一致性"""
    click.echo("\n" + "="*60)
    click.echo("验证配置文件")
    click.echo("="*60)
    
    deployer = HigressDeployer(config)
    errors = deployer._validate_config()
    
    if errors:
        click.echo("\n✗ 配置验证失败，发现以下问题:\n")
        for i, error in enumerate(errors, 1):
            click.echo(f"  {i}. {error}")
        click.echo("\n请编辑 config.yaml 修正这些问题")
        sys.exit(1)
    else:
        click.echo("\n✓ 配置验证通过")
        click.echo("\n配置摘要:")
        click.echo(f"  集群名称: {deployer.config['eks']['cluster_name']}")
        click.echo(f"  AWS 区域: {deployer.config['aws']['region']}")
        click.echo(f"  Kubernetes 版本: {deployer.config['eks']['kubernetes_version']}")
        click.echo(f"  节点类型: {deployer.config['eks']['instance_type']}")
        click.echo(f"  节点数: {deployer.config['eks']['desired_capacity']} (min: {deployer.config['eks']['min_size']}, max: {deployer.config['eks']['max_size']})")
        click.echo(f"  Higress 副本: {deployer.config['higress'].get('replicas', 3)}")
        click.echo(f"  使用 ALB: {deployer.config['higress'].get('use_alb', True)}")
        click.echo("\n✓ 所有配置文件已同步生成")


@cli.command()
@click.argument('resource', type=click.Choice(['eks', 'higress'], case_sensitive=False))
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
@click.option('--force', '-f', is_flag=True, help='强制删除，不需要确认')
def clean(resource, config, force):
    """
    清理资源
    
    RESOURCE: 要清理的资源类型
    
    \b
    - eks: 删除整个 EKS 集群及所有资源（包括 Higress、ALB Controller、IAM 策略等）
    - higress: 仅删除 Higress 相关资源（保留 EKS 集群和 ALB Controller）
    
    \b
    示例:
      ./higress_deploy.py clean higress          # 仅删除 Higress
      ./higress_deploy.py clean eks              # 删除整个 EKS 集群
      ./higress_deploy.py clean higress --force  # 强制删除 Higress（不需要确认）
    """
    deployer = HigressDeployer(config)
    
    if resource.lower() == 'higress':
        deployer.delete_higress(force)
    elif resource.lower() == 'eks':
        deployer.delete_cluster(force)


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
def fix_alb_security_group(config):
    """修复 ALB Security Group 问题"""
    deployer = HigressDeployer(config)
    
    click.echo("\n" + "="*60)
    click.echo("修复 ALB Security Group 问题")
    click.echo("="*60)
    
    region = deployer.config['aws']['region']
    cluster_name = deployer.config['eks']['cluster_name']
    vpc_id = deployer.config['vpc']['vpc_id']
    
    # 1. 获取集群 Security Group
    click.echo("\n【步骤 1】获取集群 Security Group...")
    cluster_sg_cmd = f"""aws eks describe-cluster \
        --name {cluster_name} \
        --region {region} \
        --query 'cluster.resourcesVpcConfig.securityGroupIds[0]' \
        --output text"""
    cluster_sg = deployer._run_command(cluster_sg_cmd, check=False, capture=True)
    
    if not cluster_sg or "None" in cluster_sg:
        click.echo("✗ 无法获取集群 Security Group")
        sys.exit(1)
    
    cluster_sg = cluster_sg.strip()
    click.echo(f"✓ 集群 Security Group: {cluster_sg}")
    
    # 2. 获取节点 Security Group
    click.echo("\n【步骤 2】获取节点 Security Group...")
    node_sg_cmd = f"""aws ec2 describe-security-groups \
        --filters "Name=tag:aws:cloudformation:stack-name,Values=eksctl-{cluster_name}-nodegroup-*" \
        --region {region} \
        --query 'SecurityGroups[0].GroupId' \
        --output text"""
    node_sg = deployer._run_command(node_sg_cmd, check=False, capture=True)
    
    if not node_sg or "None" in node_sg:
        click.echo("✗ 无法获取节点 Security Group")
        sys.exit(1)
    
    node_sg = node_sg.strip()
    click.echo(f"✓ 节点 Security Group: {node_sg}")
    
    # 3. 删除现有 Ingress
    click.echo("\n【步骤 3】删除现有 Ingress...")
    deployer._run_command("kubectl delete ingress higress-alb -n higress-system", check=False)
    click.echo("等待 AWS 资源清理...")
    time.sleep(30)
    
    # 4. 添加 Security Group 规则
    click.echo("\n【步骤 4】添加 Security Group 规则...")
    
    # 允许节点 SG 接收来自集群 SG 的 30080 流量
    click.echo("添加节点 SG 入站规则（30080 端口）...")
    cmd = f"""aws ec2 authorize-security-group-ingress \
        --group-id {node_sg} \
        --protocol tcp \
        --port 30080 \
        --source-group {cluster_sg} \
        --region {region}"""
    deployer._run_command(cmd, check=False)
    
    # 允许节点 SG 接收来自集群 SG 的 30443 流量
    click.echo("添加节点 SG 入站规则（30443 端口）...")
    cmd = f"""aws ec2 authorize-security-group-ingress \
        --group-id {node_sg} \
        --protocol tcp \
        --port 30443 \
        --source-group {cluster_sg} \
        --region {region}"""
    deployer._run_command(cmd, check=False)
    
    # 5. 重新创建 Ingress
    click.echo("\n【步骤 5】重新创建 Ingress...")
    ingress_file = deployer._create_alb_ingress()
    deployer._run_command(f"kubectl apply -f {ingress_file}")
    
    # 6. 等待 ALB 创建
    click.echo("\n【步骤 6】等待 ALB 创建（最多 5 分钟）...")
    for i in range(30):
        result = deployer._run_command(
            "kubectl get ingress higress-alb -n higress-system -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'",
            check=False, capture=True
        )
        
        if result and result.strip():
            click.echo(f"\n✓ ALB 创建成功！")
            click.echo(f"ALB DNS: {result}")
            with open('alb-endpoint.txt', 'w') as f:
                f.write(result)
            break
        
        if (i + 1) % 3 == 0:
            click.echo(f"等待中... ({(i+1)*10}秒)")
        time.sleep(10)
    else:
        click.echo("\n⚠ ALB 创建超时，请检查 Ingress 状态:")
        deployer._run_command("kubectl describe ingress higress-alb -n higress-system")
        sys.exit(1)
    
    click.echo("\n" + "="*60)
    click.echo("✓ ALB Security Group 修复完成")
    click.echo("="*60)


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
@click.option('--force', '-f', is_flag=True, help='强制删除，不需要确认')
def delete(config, force):
    """删除 EKS 集群（已弃用，请使用 clean eks）"""
    click.echo("⚠ 警告: 'delete' 命令已弃用，请使用 'clean eks' 代替")
    click.echo("正在执行: clean eks\n")
    deployer = HigressDeployer(config)
    deployer.delete_cluster(force)


if __name__ == '__main__':
    cli()
