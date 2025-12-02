#!/usr/bin/env python3
"""测试 AWS 可用区容量"""
import boto3
import yaml

# 读取配置
with open('config.yaml') as f:
    config = yaml.safe_load(f)

region = config['aws']['region']
vpc_id = config['vpc']['vpc_id']

ec2 = boto3.client('ec2', region_name=region)

# 获取 AMI
print("获取 AMI...")
amis = ec2.describe_images(
    Owners=['amazon'],
    Filters=[
        {'Name': 'name', 'Values': ['al2023-ami-*-x86_64']},
        {'Name': 'state', 'Values': ['available']}
    ]
)
ami_id = sorted(amis['Images'], key=lambda x: x['CreationDate'])[-1]['ImageId']
print(f"AMI: {ami_id}\n")

# 获取所有可用区
azs = ec2.describe_availability_zones(
    Filters=[{'Name': 'state', 'Values': ['available']}]
)

# 测试实例类型
types = ['m5.large', 'm5.xlarge', 'm6i.large', 'm6i.xlarge','m6i.2xlarge','m7i.xlarge','m7i.2xlarge','m7a.xlarge']

print(f"区域: {region}")
print(f"VPC: {vpc_id}\n")
print("=" * 80)

results = {}

for az_info in azs['AvailabilityZones']:
    az = az_info['ZoneName']
    
    # 获取该 AZ 的子网
    subnets = ec2.describe_subnets(
        Filters=[
            {'Name': 'vpc-id', 'Values': [vpc_id]},
            {'Name': 'availability-zone', 'Values': [az]}
        ]
    )
    
    if not subnets['Subnets']:
        continue
    
    subnet_id = subnets['Subnets'][0]['SubnetId']
    print(f"\n{az} (子网: {subnet_id})")
    print("-" * 80)
    
    results[az] = {'subnet_id': subnet_id, 'types': {}}
    
    for itype in types:
        try:
            ec2.run_instances(
                ImageId=ami_id,
                InstanceType=itype,
                MinCount=1,
                MaxCount=1,
                SubnetId=subnet_id,
                DryRun=True
            )
        except Exception as e:
            error = str(e)
            if 'DryRunOperation' in error:
                print(f"  {itype:15} ✓ 有容量")
                results[az]['types'][itype] = True
            elif 'InsufficientInstanceCapacity' in error:
                print(f"  {itype:15} ✗ 容量不足")
                results[az]['types'][itype] = False
            else:
                print(f"  {itype:15} ? {error[:50]}")
                results[az]['types'][itype] = None

# 推荐配置
print("\n" + "=" * 80)
print("推荐配置")
print("=" * 80)

good_azs = []
for az, data in results.items():
    if all(data['types'].get(t) for t in types):
        good_azs.append(az)

if good_azs:
    print("\n以下可用区有足够容量:")
    for az in good_azs:
        print(f"  - {az}: {results[az]['subnet_id']}")
    
    print("\n建议配置:")
    print("aws:")
    print(f"  region: {region}")
    print(f"  vpc_id: {vpc_id}")
    print("  subnets:")
    for az in good_azs[:3]:
        print(f"    - subnet_id: {results[az]['subnet_id']}")
        print(f"      availability_zone: {az}")
else:
    print("\n没有找到所有实例类型都有容量的可用区")
    print("建议使用 m5 系列")
