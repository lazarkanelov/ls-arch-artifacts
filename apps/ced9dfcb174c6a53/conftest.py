import pytest
import boto3
import os
import tempfile
import json
from typing import Generator


@pytest.fixture
def aws_credentials():
    """Set AWS credentials for LocalStack."""
    os.environ['AWS_ACCESS_KEY_ID'] = 'test'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'


@pytest.fixture
def s3_client(aws_credentials):
    """Create S3 client for LocalStack."""
    return boto3.client(
        's3',
        endpoint_url=os.environ.get('LOCALSTACK_ENDPOINT', 'http://localhost:4566'),
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )


@pytest.fixture
def lambda_client(aws_credentials):
    """Create Lambda client for LocalStack."""
    return boto3.client(
        'lambda',
        endpoint_url=os.environ.get('LOCALSTACK_ENDPOINT', 'http://localhost:4566'),
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )


@pytest.fixture
def iam_client(aws_credentials):
    """Create IAM client for LocalStack."""
    return boto3.client(
        'iam',
        endpoint_url=os.environ.get('LOCALSTACK_ENDPOINT', 'http://localhost:4566'),
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )


@pytest.fixture
def logs_client(aws_credentials):
    """Create CloudWatch Logs client for LocalStack."""
    return boto3.client(
        'logs',
        endpoint_url=os.environ.get('LOCALSTACK_ENDPOINT', 'http://localhost:4566'),
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )


@pytest.fixture
def sample_image_data() -> bytes:
    """Generate sample image data for testing."""
    # Simple bitmap header + data for a 2x2 pixel image
    return b'\x42\x4d\x3a\x00\x00\x00\x00\x00\x00\x00\x36\x00\x00\x00\x28\x00\x00\x00\x02\x00\x00\x00\x02\x00\x00\x00\x01\x00\x18\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\x00\x00\x00\x00\xff\x00\x00\x00\xff\x00\xff\x00\x00'


@pytest.fixture
def sample_csv_data() -> str:
    """Generate sample CSV data for testing."""
    return """name,email,age,department,salary
John Doe,john.doe@company.com,28,Engineering,75000
Jane Smith,jane.smith@company.com,32,Marketing,68000
Bob Johnson,bob.johnson@company.com,45,Sales,82000
Alice Williams,alice.williams@company.com,29,Engineering,77000
Charlie Brown,charlie.brown@company.com,38,Finance,71000"""


@pytest.fixture
def sample_json_data() -> str:
    """Generate sample JSON data for testing."""
    return json.dumps({
        "transaction_id": "txn_12345",
        "user_id": "user_67890",
        "amount": 129.99,
        "currency": "USD",
        "timestamp": "2024-01-15T10:30:00Z",
        "items": [
            {"id": "item_1", "name": "Product A", "price": 59.99, "quantity": 1},
            {"id": "item_2", "name": "Product B", "price": 70.00, "quantity": 1}
        ],
        "shipping_address": {
            "street": "123 Main St",
            "city": "Anytown",
            "state": "CA",
            "zip": "12345"
        }
    }, indent=2)


@pytest.fixture
def temp_file() -> Generator[str, None, None]:
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        yield f.name
    os.unlink(f.name)