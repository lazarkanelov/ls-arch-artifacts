import pytest
import boto3
import os


@pytest.fixture(scope="session")
def aws_credentials():
    """Mocked AWS Credentials for LocalStack."""
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="session")
def localstack_endpoint():
    """LocalStack endpoint URL."""
    return os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")


@pytest.fixture(scope="session")
def ec2_client(aws_credentials, localstack_endpoint):
    """Create EC2 client for LocalStack."""
    return boto3.client(
        "ec2",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )


@pytest.fixture(scope="session")
def ec2_resource(aws_credentials, localstack_endpoint):
    """Create EC2 resource for LocalStack."""
    return boto3.resource(
        "ec2",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )


@pytest.fixture(scope="module")
def vpc_config():
    """VPC configuration for testing."""
    return {
        "cidr_block": "10.0.0.0/16",
        "enable_dns_hostnames": True,
        "enable_dns_support": True
    }


@pytest.fixture(scope="module")
def subnet_config():
    """Subnet configuration for testing."""
    return {
        "public_subnets": {
            "public-web-1": {
                "cidr": "10.0.1.0/24",
                "az": "us-east-1a",
                "type": "web"
            },
            "public-web-2": {
                "cidr": "10.0.2.0/24",
                "az": "us-east-1b",
                "type": "web"
            }
        },
        "private_subnets": {
            "private-app-1": {
                "cidr": "10.0.10.0/24",
                "az": "us-east-1a",
                "type": "app"
            },
            "private-app-2": {
                "cidr": "10.0.20.0/24",
                "az": "us-east-1b",
                "type": "app"
            }
        }
    }


@pytest.fixture(scope="module")
def security_groups_config():
    """Security groups configuration for testing."""
    return {
        "web_sg": {
            "name": "web-security-group",
            "description": "Security group for web servers",
            "ingress_rules": [
                {
                    "from_port": 80,
                    "to_port": 80,
                    "protocol": "tcp",
                    "cidr_blocks": ["0.0.0.0/0"]
                },
                {
                    "from_port": 443,
                    "to_port": 443,
                    "protocol": "tcp",
                    "cidr_blocks": ["0.0.0.0/0"]
                }
            ]
        },
        "app_sg": {
            "name": "app-security-group",
            "description": "Security group for application servers",
            "ingress_rules": [
                {
                    "from_port": 8080,
                    "to_port": 8080,
                    "protocol": "tcp",
                    "source_security_group_id": "web_sg"
                }
            ]
        }
    }


@pytest.fixture(scope="function")
def cleanup_resources(ec2_client):
    """Cleanup AWS resources after each test."""
    created_resources = {
        "instances": [],
        "security_groups": [],
        "vpcs": [],
        "subnets": [],
        "nat_gateways": [],
        "internet_gateways": [],
        "route_tables": []
    }
    
    yield created_resources
    
    # Cleanup instances
    if created_resources["instances"]:
        try:
            ec2_client.terminate_instances(InstanceIds=created_resources["instances"])
        except Exception as e:
            print(f"Error terminating instances: {e}")
    
    # Cleanup security groups
    for sg_id in created_resources["security_groups"]:
        try:
            ec2_client.delete_security_group(GroupId=sg_id)
        except Exception as e:
            print(f"Error deleting security group {sg_id}: {e}")
    
    # Cleanup NAT gateways
    for nat_id in created_resources["nat_gateways"]:
        try:
            ec2_client.delete_nat_gateway(NatGatewayId=nat_id)
        except Exception as e:
            print(f"Error deleting NAT gateway {nat_id}: {e}")
    
    # Cleanup subnets
    for subnet_id in created_resources["subnets"]:
        try:
            ec2_client.delete_subnet(SubnetId=subnet_id)
        except Exception as e:
            print(f"Error deleting subnet {subnet_id}: {e}")
    
    # Cleanup VPCs
    for vpc_id in created_resources["vpcs"]:
        try:
            ec2_client.delete_vpc(VpcId=vpc_id)
        except Exception as e:
            print(f"Error deleting VPC {vpc_id}: {e}")