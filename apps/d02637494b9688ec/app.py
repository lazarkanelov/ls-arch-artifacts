import boto3
import json
import logging
import os
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TransactionProcessor:
    """A realistic transaction processing system using EventBridge and Lambda.
    
    This application simulates a financial transaction processing pipeline where:
    1. Transaction events are published to EventBridge
    2. Events matching EU location pattern (EUR-*) trigger Lambda processing
    3. Lambda function processes transactions for fraud detection and compliance
    4. Results are logged and can be queried
    """
    
    def __init__(self, endpoint_url: Optional[str] = None):
        self.endpoint_url = endpoint_url or os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
        
        # Initialize AWS clients
        self.events_client = boto3.client(
            "events",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.lambda_client = boto3.client(
            "lambda",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.logs_client = boto3.client(
            "logs",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
    
    def publish_transaction_event(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Publish a transaction event to EventBridge.
        
        Args:
            transaction_data: Dictionary containing transaction details
            
        Returns:
            Response from EventBridge put_events call
        """
        event_entry = {
            "Source": "custom.myApp",
            "DetailType": "transaction",
            "Detail": json.dumps(transaction_data),
            "Time": datetime.utcnow()
        }
        
        try:
            response = self.events_client.put_events(
                Entries=[event_entry]
            )
            logger.info(f"Published transaction event: {transaction_data.get('transactionId')}")
            return response
        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            raise
    
    def batch_publish_transactions(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Publish multiple transaction events in batch.
        
        Args:
            transactions: List of transaction dictionaries
            
        Returns:
            List of responses from EventBridge
        """
        responses = []
        
        # EventBridge supports up to 10 events per batch
        batch_size = 10
        
        for i in range(0, len(transactions), batch_size):
            batch = transactions[i:i + batch_size]
            
            entries = []
            for transaction in batch:
                entry = {
                    "Source": "custom.myApp",
                    "DetailType": "transaction",
                    "Detail": json.dumps(transaction),
                    "Time": datetime.utcnow()
                }
                entries.append(entry)
            
            try:
                response = self.events_client.put_events(Entries=entries)
                responses.append(response)
                logger.info(f"Published batch of {len(entries)} transactions")
            except Exception as e:
                logger.error(f"Failed to publish batch: {e}")
                raise
        
        return responses
    
    def invoke_lambda_directly(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Directly invoke the Lambda function for testing.
        
        Args:
            payload: Event payload to send to Lambda
            
        Returns:
            Lambda function response
        """
        try:
            response = self.lambda_client.invoke(
                FunctionName="ConsumerFunction",
                InvocationType="RequestResponse",
                Payload=json.dumps(payload)
            )
            
            result = json.loads(response['Payload'].read().decode('utf-8'))
            logger.info(f"Lambda invocation successful: {result}")
            return result
        except Exception as e:
            logger.error(f"Lambda invocation failed: {e}")
            raise
    
    def get_lambda_logs(self, minutes_back: int = 10) -> List[str]:
        """Retrieve recent Lambda function logs.
        
        Args:
            minutes_back: How many minutes back to search for logs
            
        Returns:
            List of log messages
        """
        log_group_name = "/aws/lambda/ConsumerFunction"
        
        try:
            # Get log streams
            streams_response = self.logs_client.describe_log_streams(
                logGroupName=log_group_name,
                orderBy="LastEventTime",
                descending=True,
                limit=5
            )
            
            log_messages = []
            
            # Get recent log events
            start_time = int((datetime.utcnow() - timedelta(minutes=minutes_back)).timestamp() * 1000)
            
            for stream in streams_response.get('logStreams', []):
                try:
                    events_response = self.logs_client.get_log_events(
                        logGroupName=log_group_name,
                        logStreamName=stream['logStreamName'],
                        startTime=start_time
                    )
                    
                    for event in events_response.get('events', []):
                        log_messages.append(event['message'].strip())
                        
                except Exception as stream_error:
                    logger.warning(f"Could not get events from stream {stream['logStreamName']}: {stream_error}")
                    continue
            
            return log_messages
            
        except Exception as e:
            logger.warning(f"Could not retrieve logs: {e}")
            return []
    
    def check_infrastructure(self) -> Dict[str, bool]:
        """Check if all required AWS resources exist.
        
        Returns:
            Dictionary showing status of each resource
        """
        status = {}
        
        # Check Lambda function
        try:
            self.lambda_client.get_function(FunctionName="ConsumerFunction")
            status['lambda_function'] = True
        except Exception:
            status['lambda_function'] = False
        
        # Check EventBridge rule
        try:
            rules = self.events_client.list_rules(NamePrefix="eventbridge-lambda-")
            status['eventbridge_rule'] = len(rules.get('Rules', [])) > 0
        except Exception:
            status['eventbridge_rule'] = False
        
        return status
    
    def simulate_fraud_detection_workflow(self) -> Dict[str, Any]:
        """Simulate a complete fraud detection workflow.
        
        This creates a realistic scenario where:
        1. Multiple transactions are processed
        2. EU transactions trigger Lambda processing (due to EUR- location prefix)
        3. High-value transactions are flagged for review
        4. Processing results are collected
        
        Returns:
            Summary of the workflow execution
        """
        # Sample transactions with different risk profiles
        transactions = [
            {
                "transactionId": "txn-001",
                "amount": 150.00,
                "currency": "EUR",
                "location": "EUR-AMSTERDAM",
                "merchantId": "merchant-retail-001",
                "merchantCategory": "grocery",
                "timestamp": datetime.utcnow().isoformat(),
                "customerId": "customer-123"
            },
            {
                "transactionId": "txn-002",
                "amount": 5000.00,
                "currency": "EUR",
                "location": "EUR-BERLIN",
                "merchantId": "merchant-luxury-002",
                "merchantCategory": "jewelry",
                "timestamp": datetime.utcnow().isoformat(),
                "customerId": "customer-456"
            },
            {
                "transactionId": "txn-003",
                "amount": 25.50,
                "currency": "USD",
                "location": "USD-NEWYORK",
                "merchantId": "merchant-cafe-003",
                "merchantCategory": "restaurant",
                "timestamp": datetime.utcnow().isoformat(),
                "customerId": "customer-789"
            },
            {
                "transactionId": "txn-004",
                "amount": 15000.00,
                "currency": "EUR",
                "location": "EUR-ZURICH",
                "merchantId": "merchant-auto-004",
                "merchantCategory": "automotive",
                "timestamp": datetime.utcnow().isoformat(),
                "customerId": "customer-101"
            }
        ]
        
        logger.info("Starting fraud detection workflow simulation...")
        
        # Publish all transactions
        publish_responses = self.batch_publish_transactions(transactions)
        
        # Wait for processing
        time.sleep(5)
        
        # Get processing logs
        logs = self.get_lambda_logs(minutes_back=2)
        
        # Count expected EU transactions (should have triggered Lambda)
        eu_transactions = [t for t in transactions if t['location'].startswith('EUR-')]
        
        workflow_summary = {
            "total_transactions_published": len(transactions),
            "eu_transactions_count": len(eu_transactions),
            "publish_responses": publish_responses,
            "processing_logs": logs,
            "high_value_transactions": [
                t for t in eu_transactions if t['amount'] > 1000
            ]
        }
        
        logger.info(f"Workflow completed. EU transactions: {len(eu_transactions)}, Logs captured: {len(logs)}")
        
        return workflow_summary
    
    def create_transaction(self, customer_id: str, amount: float, location: str, 
                          merchant_id: str, merchant_category: str = "general") -> Dict[str, Any]:
        """Create and publish a single transaction.
        
        Args:
            customer_id: Customer identifier
            amount: Transaction amount
            location: Transaction location (format: CURRENCY-CITY)
            merchant_id: Merchant identifier
            merchant_category: Category of merchant
            
        Returns:
            Transaction data that was published
        """
        transaction = {
            "transactionId": f"txn-{int(time.time())}",
            "amount": amount,
            "currency": location.split('-')[0],
            "location": location,
            "merchantId": merchant_id,
            "merchantCategory": merchant_category,
            "timestamp": datetime.utcnow().isoformat(),
            "customerId": customer_id
        }
        
        self.publish_transaction_event(transaction)
        return transaction