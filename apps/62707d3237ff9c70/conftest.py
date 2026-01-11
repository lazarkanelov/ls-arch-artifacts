import os
import pytest
import boto3
from botocore.exceptions import ClientError
import time

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
    """Create DynamoDB client for LocalStack."""
    return boto3.client(
        "dynamodb",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

@pytest.fixture(scope="session")
def dynamodb_resource(aws_credentials, localstack_endpoint):
    """Create DynamoDB resource for LocalStack."""
    return boto3.resource(
        "dynamodb",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

@pytest.fixture(scope="session")
def lambda_client(aws_credentials, localstack_endpoint):
    """Create Lambda client for LocalStack."""
    return boto3.client(
        "lambda",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

@pytest.fixture(scope="session")
def iam_client(aws_credentials, localstack_endpoint):
    """Create IAM client for LocalStack."""
    return boto3.client(
        "iam",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )

@pytest.fixture(scope="session")
def users_table(dynamodb_resource):
    """Get reference to the UsersIds DynamoDB table."""
    table_name = "UsersIds"
    return dynamodb_resource.Table(table_name)

@pytest.fixture(scope="function")
def clean_dynamodb_table(users_table):
    """Clean DynamoDB table before each test."""
    # Clean up before test
    try:
        scan_response = users_table.scan()
        for item in scan_response.get('Items', []):
            users_table.delete_item(Key={'UserId': item['UserId']})
    except Exception:
        pass  # Table might not exist yet
    
    yield
    
    # Clean up after test
    try:
        scan_response = users_table.scan()
        for item in scan_response.get('Items', []):
            users_table.delete_item(Key={'UserId': item['UserId']})
    except Exception:
        pass

@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "user1": {
            "UserId": "user-001",
            "email": "john.doe@example.com",
            "firstName": "John",
            "lastName": "Doe",
            "status": "active",
            "createdAt": "2024-01-15T10:30:00Z",
            "subscription": "premium"
        },
        "user2": {
            "UserId": "user-002",
            "email": "jane.smith@example.com",
            "firstName": "Jane",
            "lastName": "Smith",
            "status": "active",
            "createdAt": "2024-01-15T11:15:00Z",
            "subscription": "basic"
        },
        "user3": {
            "UserId": "user-003",
            "email": "bob.wilson@example.com",
            "firstName": "Bob",
            "lastName": "Wilson",
            "status": "inactive",
            "createdAt": "2024-01-15T12:00:00Z",
            "subscription": "premium"
        }
    }