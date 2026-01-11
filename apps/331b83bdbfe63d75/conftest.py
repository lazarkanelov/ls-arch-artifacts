import pytest
import boto3
import os
import logging
from typing import Generator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture(scope="session")
def aws_credentials():
    """Mocked AWS Credentials for LocalStack."""
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_SECURITY_TOKEN"] = "test"
    os.environ["AWS_SESSION_TOKEN"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

@pytest.fixture(scope="session")
def localstack_endpoint() -> str:
    """Get LocalStack endpoint URL."""
    return os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")

@pytest.fixture(scope="session")
def s3_client(aws_credentials, localstack_endpoint) -> Generator[boto3.client, None, None]:
    """Create S3 client for LocalStack."""
    client = boto3.client(
        "s3",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    yield client

@pytest.fixture(scope="session")
def lambda_client(aws_credentials, localstack_endpoint) -> Generator[boto3.client, None, None]:
    """Create Lambda client for LocalStack."""
    client = boto3.client(
        "lambda",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    yield client

@pytest.fixture(scope="session")
def apigateway_client(aws_credentials, localstack_endpoint) -> Generator[boto3.client, None, None]:
    """Create API Gateway v2 client for LocalStack."""
    client = boto3.client(
        "apigatewayv2",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    yield client

@pytest.fixture(scope="session")
def logs_client(aws_credentials, localstack_endpoint) -> Generator[boto3.client, None, None]:
    """Create CloudWatch Logs client for LocalStack."""
    client = boto3.client(
        "logs",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    yield client

@pytest.fixture(scope="session")
def iam_client(aws_credentials, localstack_endpoint) -> Generator[boto3.client, None, None]:
    """Create IAM client for LocalStack."""
    client = boto3.client(
        "iam",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    yield client

@pytest.fixture(scope="session")
def sample_user_data():
    """Sample user registration data for testing."""
    return {
        "users": [
            {
                "email": "john.doe@example.com",
                "name": "John Doe",
                "company": "Tech Corp",
                "role": "developer"
            },
            {
                "email": "jane.smith@example.com",
                "name": "Jane Smith",
                "company": "Data Inc",
                "role": "analyst"
            },
            {
                "email": "bob.wilson@example.com",
                "name": "Bob Wilson",
                "company": "Startup LLC",
                "role": "manager"
            }
        ]
    }

@pytest.fixture(scope="session")
def terraform_outputs():
    """Expected Terraform resource names and configurations."""
    return {
        "lambda_function_name": "test_apigw_integration",
        "s3_bucket_prefix": "apigw-http-api-lambda",
        "api_name": "apigw-http-lambda",
        "iam_role_name": "serverless_lambda",
        "lambda_log_group": "/aws/lambda/test_apigw_integration",
        "api_log_group_prefix": "/aws/api_gw/apigw-http-lambda"
    }