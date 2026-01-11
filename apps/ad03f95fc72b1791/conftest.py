import pytest
import boto3
import os
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture(scope="session")
def aws_credentials():
    """Mocked AWS Credentials for LocalStack."""
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_SECURITY_TOKEN"] = "test"
    os.environ["AWS_SESSION_TOKEN"] = "test"

@pytest.fixture(scope="session")
def localstack_endpoint():
    """LocalStack endpoint URL."""
    return os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")

@pytest.fixture(scope="session")
def dynamodb_client(aws_credentials, localstack_endpoint):
    """DynamoDB client configured for LocalStack."""
    return boto3.client(
        "dynamodb",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

@pytest.fixture(scope="session")
def dynamodb_resource(aws_credentials, localstack_endpoint):
    """DynamoDB resource configured for LocalStack."""
    return boto3.resource(
        "dynamodb",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

@pytest.fixture(scope="session")
def lambda_client(aws_credentials, localstack_endpoint):
    """Lambda client configured for LocalStack."""
    return boto3.client(
        "lambda",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

@pytest.fixture(scope="session")
def s3_client(aws_credentials, localstack_endpoint):
    """S3 client configured for LocalStack."""
    return boto3.client(
        "s3",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

@pytest.fixture(scope="session")
def apigateway_client(aws_credentials, localstack_endpoint):
    """API Gateway v2 client configured for LocalStack."""
    return boto3.client(
        "apigatewayv2",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

@pytest.fixture(scope="session")
def iam_client(aws_credentials, localstack_endpoint):
    """IAM client configured for LocalStack."""
    return boto3.client(
        "iam",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

@pytest.fixture(scope="session")
def cloudwatch_client(aws_credentials, localstack_endpoint):
    """CloudWatch Logs client configured for LocalStack."""
    return boto3.client(
        "logs",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

@pytest.fixture(scope="session")
def terraform_outputs():
    """Expected Terraform resource names and configuration."""
    return {
        "dynamodb_table": "Movies",
        "s3_bucket_prefix": "apigw-lambda-ddb",
        "lambda_name_prefix": "pattern-movies-post",
        "apigw_name_prefix": "apigw-http-lambda",
        "region": "us-east-1"
    }

@pytest.fixture(scope="session")
def sample_movies():
    """Sample movie data for testing."""
    return [
        {
            "year": 2023,
            "title": "The Amazing Adventure",
            "info": {
                "genre": "Action",
                "director": "John Smith",
                "rating": 8.5,
                "plot": "An epic adventure story"
            }
        },
        {
            "year": 2022,
            "title": "Comedy Night",
            "info": {
                "genre": "Comedy",
                "director": "Jane Doe",
                "rating": 7.8,
                "plot": "A hilarious comedy"
            }
        },
        {
            "year": 2024,
            "title": "Future Sci-Fi",
            "info": {
                "genre": "Sci-Fi",
                "director": "Alex Johnson",
                "rating": 9.1,
                "plot": "A futuristic thriller"
            }
        }
    ]