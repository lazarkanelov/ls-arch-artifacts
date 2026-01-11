import os
import pytest
import boto3
import time
from typing import Dict, Any


@pytest.fixture(scope="session")
def aws_credentials():
    """Mocked AWS Credentials for LocalStack."""
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_SECURITY_TOKEN"] = "test"
    os.environ["AWS_SESSION_TOKEN"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="session")
def localstack_endpoint():
    """Get LocalStack endpoint URL."""
    return os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")


@pytest.fixture(scope="session")
def sqs_client(aws_credentials, localstack_endpoint):
    """Create SQS client for LocalStack."""
    return boto3.client(
        "sqs",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )


@pytest.fixture(scope="session")
def sns_client(aws_credentials, localstack_endpoint):
    """Create SNS client for LocalStack."""
    return boto3.client(
        "sns",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )


@pytest.fixture(scope="session")
def cloudwatch_client(aws_credentials, localstack_endpoint):
    """Create CloudWatch client for LocalStack."""
    return boto3.client(
        "cloudwatch",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )


@pytest.fixture(scope="session")
def test_data():
    """Sample test data for order processing."""
    return {
        "orders": [
            {
                "order_id": "ORD-001",
                "customer_id": "CUST-123",
                "items": [
                    {"sku": "PROD-A", "quantity": 2, "price": 29.99},
                    {"sku": "PROD-B", "quantity": 1, "price": 49.99}
                ],
                "total": 109.97,
                "status": "pending"
            },
            {
                "order_id": "ORD-002",
                "customer_id": "CUST-456",
                "items": [
                    {"sku": "PROD-C", "quantity": 3, "price": 15.50}
                ],
                "total": 46.50,
                "status": "pending"
            }
        ],
        "inventory_updates": [
            {"sku": "PROD-A", "quantity_change": -2, "reason": "order_fulfillment"},
            {"sku": "PROD-B", "quantity_change": -1, "reason": "order_fulfillment"},
            {"sku": "PROD-C", "quantity_change": -3, "reason": "order_fulfillment"}
        ],
        "notifications": [
            {"type": "order_confirmation", "recipient": "customer@example.com"},
            {"type": "shipping_notification", "recipient": "customer@example.com"},
            {"type": "low_inventory_alert", "recipient": "warehouse@company.com"}
        ]
    }


@pytest.fixture(scope="function")
def queue_cleanup(sqs_client):
    """Clean up SQS messages after each test."""
    queues_to_clean = []
    
    yield queues_to_clean
    
    # Purge messages from queues after test
    for queue_url in queues_to_clean:
        try:
            sqs_client.purge_queue(QueueUrl=queue_url)
            # Wait a bit for purge to take effect
            time.sleep(1)
        except Exception:
            pass  # Ignore cleanup errors


@pytest.fixture(scope="session")
def sns_topics():
    """Expected SNS topic names based on Terraform config."""
    return {
        "order_events": "order-events-topic",
        "inventory_updates": "inventory-updates-topic",
        "customer_notifications": "customer-notifications-topic"
    }