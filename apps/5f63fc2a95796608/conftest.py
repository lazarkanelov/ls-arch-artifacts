import os
import boto3
import pytest
from typing import Dict, Any


@pytest.fixture(scope="session")
def aws_config() -> Dict[str, str]:
    """AWS configuration for LocalStack."""
    return {
        "endpoint_url": os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566"),
        "region_name": "us-east-1",
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test"
    }


@pytest.fixture(scope="session")
def ec2_client(aws_config):
    """EC2 client for LocalStack."""
    return boto3.client("ec2", **aws_config)


@pytest.fixture(scope="session")
def vpc_name() -> str:
    """VPC name from Terraform configuration."""
    return "test-vpc"


@pytest.fixture(scope="session")
def infrastructure_config() -> Dict[str, Any]:
    """Infrastructure configuration that matches Terraform variables."""
    return {
        "vpc": {
            "name": "test-vpc",
            "cidr": "10.0.0.0/16",
            "tags": {"Environment": "test", "Project": "networking"}
        },
        "subnets": {
            "public": {
                "web-subnet-1a": {
                    "name": "web-subnet-1a",
                    "cidr": "10.0.1.0/24",
                    "az": "us-east-1a",
                    "type": "web",
                    "tags": {"Tier": "web"}
                },
                "web-subnet-1b": {
                    "name": "web-subnet-1b",
                    "cidr": "10.0.2.0/24",
                    "az": "us-east-1b",
                    "type": "web",
                    "tags": {"Tier": "web"}
                }
            },
            "private": {
                "app-subnet-1a": {
                    "name": "app-subnet-1a",
                    "cidr": "10.0.11.0/24",
                    "az": "us-east-1a",
                    "type": "app",
                    "nat_gateway": "AZ",
                    "tags": {"Tier": "app"}
                },
                "app-subnet-1b": {
                    "name": "app-subnet-1b",
                    "cidr": "10.0.12.0/24",
                    "az": "us-east-1b",
                    "type": "app",
                    "nat_gateway": "AZ",
                    "tags": {"Tier": "app"}
                },
                "db-subnet-1a": {
                    "name": "db-subnet-1a",
                    "cidr": "10.0.21.0/24",
                    "az": "us-east-1a",
                    "type": "db",
                    "nat_gateway": "SINGLE",
                    "tags": {"Tier": "database"}
                },
                "db-subnet-1b": {
                    "name": "db-subnet-1b",
                    "cidr": "10.0.22.0/24",
                    "az": "us-east-1b",
                    "type": "db",
                    "nat_gateway": "SINGLE",
                    "tags": {"Tier": "database"}
                }
            }
        }
    }


@pytest.fixture(scope="session")
def test_instances_config() -> Dict[str, Any]:
    """Configuration for test EC2 instances."""
    return {
        "ami_id": "ami-0c02fb55956c7d316",  # Amazon Linux 2 AMI
        "instance_type": "t3.micro",
        "key_pair_name": "test-key-pair"
    }