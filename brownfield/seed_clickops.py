"""Create a small "click-ops" estate in Moto: what a team without IaC typically has.

Run against Moto only (source scripts/moto-env.sh first). It refuses to run if
AWS_ENDPOINT_URL is not a local address, so it can never touch a real account.
"""
import os
import sys
from urllib.parse import urlparse

import boto3

endpoint = os.environ.get("AWS_ENDPOINT_URL", "")
if urlparse(endpoint).hostname not in {"127.0.0.1", "localhost"}:
    sys.exit("Refusing to run: AWS_ENDPOINT_URL must point at a local Moto server.")

s3 = boto3.client("s3")
ec2 = boto3.client("ec2")

# A reports bucket made in the console: no encryption settings, no public access block,
# no lifecycle rules, one ad-hoc tag.
s3.create_bucket(Bucket="acme-legacy-reports")
s3.put_bucket_tagging(Bucket="acme-legacy-reports", Tagging={"TagSet": [{"Key": "team", "Value": "analytics"}]})

vpc = ec2.create_vpc(CidrBlock="10.30.0.0/16")["Vpc"]["VpcId"]
ec2.create_tags(Resources=[vpc], Tags=[{"Key": "Name", "Value": "legacy-vpc"}])
subnet = ec2.create_subnet(VpcId=vpc, CidrBlock="10.30.1.0/24", AvailabilityZone="us-east-1a")["Subnet"]["SubnetId"]
ec2.create_tags(Resources=[subnet], Tags=[{"Key": "Name", "Value": "legacy-app"}])
sg = ec2.create_security_group(GroupName="legacy-web", Description="made by hand", VpcId=vpc)["GroupId"]
ec2.authorize_security_group_ingress(
    GroupId=sg,
    IpPermissions=[{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
)
print(f"bucket=acme-legacy-reports vpc={vpc} subnet={subnet} sg={sg}")
