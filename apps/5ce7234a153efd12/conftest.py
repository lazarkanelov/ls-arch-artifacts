import pytest
import boto3
import os
import tempfile
import shutil
from typing import Generator


@pytest.fixture(scope="session")
def localstack_endpoint() -> str:
    """Get LocalStack endpoint URL from environment."""
    return os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")


@pytest.fixture(scope="session")
def aws_credentials() -> dict:
    """Return test AWS credentials for LocalStack."""
    return {
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
        "region_name": "us-east-1"
    }


@pytest.fixture(scope="session")
def lambda_client(localstack_endpoint: str, aws_credentials: dict):
    """Create Lambda client for LocalStack."""
    return boto3.client(
        "lambda",
        endpoint_url=localstack_endpoint,
        **aws_credentials
    )


@pytest.fixture(scope="session")
def s3_client(localstack_endpoint: str, aws_credentials: dict):
    """Create S3 client for LocalStack."""
    return boto3.client(
        "s3",
        endpoint_url=localstack_endpoint,
        **aws_credentials
    )


@pytest.fixture(scope="session")
def ssm_client(localstack_endpoint: str, aws_credentials: dict):
    """Create SSM client for LocalStack."""
    return boto3.client(
        "ssm",
        endpoint_url=localstack_endpoint,
        **aws_credentials
    )


@pytest.fixture(scope="session")
def iam_client(localstack_endpoint: str, aws_credentials: dict):
    """Create IAM client for LocalStack."""
    return boto3.client(
        "iam",
        endpoint_url=localstack_endpoint,
        **aws_credentials
    )


@pytest.fixture(scope="session")
def logs_client(localstack_endpoint: str, aws_credentials: dict):
    """Create CloudWatch Logs client for LocalStack."""
    return boto3.client(
        "logs",
        endpoint_url=localstack_endpoint,
        **aws_credentials
    )


@pytest.fixture(scope="session")
def temp_dir() -> Generator[str, None, None]:
    """Create a temporary directory for test files."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture(scope="session")
def lambda_function_config():
    """Configuration for the Lambda@Edge function."""
    return {
        "function_name": "content-transformer-edge",
        "handler": "index.handler",
        "runtime": "nodejs14.x",
        "s3_bucket": "edge-lambda-artifacts",
        "role_name": "content-transformer-edge-role",
        "log_group": "/aws/lambda/content-transformer-edge"
    }


@pytest.fixture(scope="session")
def sample_lambda_code():
    """Sample Lambda@Edge function code for content transformation."""
    return """
const config = require('./config.json');
const { SSMClient, GetParameterCommand } = require('@aws-sdk/client-ssm');

const ssmClient = new SSMClient({ region: 'us-east-1' });

exports.handler = async (event) => {
    console.log('Lambda@Edge request:', JSON.stringify(event, null, 2));
    
    try {
        const request = event.Records[0].cf.request;
        const response = event.Records[0].cf.response || {};
        
        // Check if this is a viewer-request or origin-response event
        const eventType = event.Records[0].cf.config.eventType;
        
        if (eventType === 'viewer-request') {
            // Transform request based on user agent
            const userAgent = request.headers['user-agent'] ? request.headers['user-agent'][0].value : '';
            
            if (userAgent.includes('Mobile')) {
                request.headers['x-device-type'] = [{ key: 'X-Device-Type', value: 'mobile' }];
            } else {
                request.headers['x-device-type'] = [{ key: 'X-Device-Type', value: 'desktop' }];
            }
            
            // Add custom header from config
            if (config.customHeader) {
                request.headers['x-custom'] = [{ key: 'X-Custom', value: config.customHeader }];
            }
            
            return request;
        } else if (eventType === 'origin-response') {
            // Modify response headers
            response.headers['x-processed-by'] = [{ key: 'X-Processed-By', value: 'lambda-edge' }];
            response.headers['x-timestamp'] = [{ key: 'X-Timestamp', value: new Date().toISOString() }];
            
            return response;
        }
        
        return request || response;
    } catch (error) {
        console.error('Error in Lambda@Edge function:', error);
        return event.Records[0].cf.request || event.Records[0].cf.response;
    }
};
"""


@pytest.fixture(scope="session")
def sample_config():
    """Sample configuration data for Lambda@Edge function."""
    return {
        "environment": "test",
        "customHeader": "edge-processed",
        "cacheTimeout": "3600",
        "enableTransformation": "true"
    }


@pytest.fixture(scope="session")
def sample_ssm_params():
    """Sample SSM parameters for the Lambda function."""
    return {
        "/content-transformer/api-key": "test-api-key-12345",
        "/content-transformer/secret-token": "super-secret-token-abcdef",
        "/content-transformer/database-url": "https://api.example.com/db"
    }