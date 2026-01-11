import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import boto3
from botocore.exceptions import ClientError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderProcessingSystem:
    """E-commerce order processing system using SQS queues and SNS notifications."""
    
    def __init__(self, endpoint_url: Optional[str] = None):
        """Initialize the order processing system.
        
        Args:
            endpoint_url: LocalStack endpoint URL for testing
        """
        self.endpoint_url = endpoint_url or os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
        
        # Initialize AWS clients
        self.sqs = boto3.client(
            "sqs",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.sns = boto3.client(
            "sns",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.cloudwatch = boto3.client(
            "cloudwatch",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        # Cache for queue URLs and topic ARNs
        self._queue_urls = {}
        self._topic_arns = {}
    
    def get_queue_url(self, queue_name: str) -> str:
        """Get SQS queue URL by name.
        
        Args:
            queue_name: Name of the SQS queue
            
        Returns:
            Queue URL
            
        Raises:
            Exception: If queue is not found
        """
        if queue_name not in self._queue_urls:
            try:
                response = self.sqs.get_queue_url(QueueName=queue_name)
                self._queue_urls[queue_name] = response["QueueUrl"]
            except ClientError as e:
                logger.error(f"Failed to get queue URL for {queue_name}: {e}")
                raise
        
        return self._queue_urls[queue_name]
    
    def get_topic_arn(self, topic_name: str) -> str:
        """Get SNS topic ARN by name.
        
        Args:
            topic_name: Name of the SNS topic
            
        Returns:
            Topic ARN
            
        Raises:
            Exception: If topic is not found
        """
        if topic_name not in self._topic_arns:
            try:
                response = self.sns.list_topics()
                for topic in response.get("Topics", []):
                    arn = topic["TopicArn"]
                    if arn.endswith(f":{topic_name}"):
                        self._topic_arns[topic_name] = arn
                        break
                else:
                    raise Exception(f"Topic {topic_name} not found")
            except ClientError as e:
                logger.error(f"Failed to get topic ARN for {topic_name}: {e}")
                raise
        
        return self._topic_arns[topic_name]
    
    def submit_order(self, order_data: Dict[str, Any], queue_name: str = "order-processing-queue") -> Dict[str, Any]:
        """Submit an order for processing.
        
        Args:
            order_data: Order information including customer, items, and total
            queue_name: SQS queue name for order processing
            
        Returns:
            Dictionary with submission status and message ID
        """
        try:
            # Add timestamp and processing metadata
            enriched_order = {
                **order_data,
                "submitted_at": datetime.utcnow().isoformat(),
                "processing_stage": "submitted",
                "retry_count": 0
            }
            
            queue_url = self.get_queue_url(queue_name)
            
            response = self.sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(enriched_order),
                MessageAttributes={
                    "order_id": {
                        "StringValue": order_data["order_id"],
                        "DataType": "String"
                    },
                    "customer_id": {
                        "StringValue": order_data["customer_id"],
                        "DataType": "String"
                    },
                    "total_amount": {
                        "StringValue": str(order_data["total"]),
                        "DataType": "Number"
                    }
                }
            )
            
            logger.info(f"Order {order_data['order_id']} submitted successfully")
            
            return {
                "success": True,
                "message_id": response["MessageId"],
                "order_id": order_data["order_id"]
            }
            
        except Exception as e:
            logger.error(f"Failed to submit order {order_data.get('order_id', 'unknown')}: {e}")
            return {
                "success": False,
                "error": str(e),
                "order_id": order_data.get("order_id")
            }
    
    def process_orders(self, queue_name: str = "order-processing-queue", max_messages: int = 10) -> List[Dict[str, Any]]:
        """Process orders from the SQS queue.
        
        Args:
            queue_name: SQS queue name to process messages from
            max_messages: Maximum number of messages to process
            
        Returns:
            List of processing results
        """
        processed_orders = []
        
        try:
            queue_url = self.get_queue_url(queue_name)
            
            # Receive messages from queue
            response = self.sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=min(max_messages, 10),
                MessageAttributeNames=["All"],
                WaitTimeSeconds=2
            )
            
            messages = response.get("Messages", [])
            logger.info(f"Processing {len(messages)} orders from queue")
            
            for message in messages:
                try:
                    # Parse order data
                    order_data = json.loads(message["Body"])
                    receipt_handle = message["ReceiptHandle"]
                    
                    # Simulate order processing business logic
                    processing_result = self._process_single_order(order_data)
                    
                    if processing_result["success"]:
                        # Delete message from queue on successful processing
                        self.sqs.delete_message(
                            QueueUrl=queue_url,
                            ReceiptHandle=receipt_handle
                        )
                        
                        # Send notifications
                        self._send_order_notifications(order_data, processing_result)
                        
                        logger.info(f"Successfully processed order {order_data['order_id']}")
                    else:
                        logger.error(f"Failed to process order {order_data['order_id']}: {processing_result['error']}")
                    
                    processed_orders.append({
                        "order_id": order_data["order_id"],
                        "processing_result": processing_result,
                        "message_id": message.get("MessageId")
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    processed_orders.append({
                        "error": str(e),
                        "message_id": message.get("MessageId")
                    })
            
        except Exception as e:
            logger.error(f"Failed to process orders from queue {queue_name}: {e}")
        
        return processed_orders
    
    def _process_single_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single order with business logic.
        
        Args:
            order_data: Order information
            
        Returns:
            Processing result dictionary
        """
        try:
            # Validate order
            if not self._validate_order(order_data):
                return {
                    "success": False,
                    "error": "Order validation failed",
                    "stage": "validation"
                }
            
            # Check inventory (simulated)
            inventory_check = self._check_inventory(order_data["items"])
            if not inventory_check["available"]:
                return {
                    "success": False,
                    "error": f"Insufficient inventory for items: {inventory_check['unavailable_items']}",
                    "stage": "inventory_check"
                }
            
            # Process payment (simulated)
            payment_result = self._process_payment(order_data)
            if not payment_result["success"]:
                return {
                    "success": False,
                    "error": f"Payment failed: {payment_result['error']}",
                    "stage": "payment"
                }
            
            # Update inventory
            self._update_inventory(order_data["items"])
            
            # Create shipping label (simulated)
            shipping_info = self._create_shipping_label(order_data)
            
            return {
                "success": True,
                "payment_id": payment_result["payment_id"],
                "shipping_label": shipping_info["tracking_number"],
                "processed_at": datetime.utcnow().isoformat(),
                "status": "processed"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stage": "processing"
            }
    
    def _validate_order(self, order_data: Dict[str, Any]) -> bool:
        """Validate order data."""
        required_fields = ["order_id", "customer_id", "items", "total"]
        return all(field in order_data for field in required_fields) and len(order_data["items"]) > 0
    
    def _check_inventory(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Simulate inventory check."""
        # Simulate some items being out of stock
        unavailable_items = []
        for item in items:
            if item["sku"] == "OUT-OF-STOCK" or item["quantity"] > 100:
                unavailable_items.append(item["sku"])
        
        return {
            "available": len(unavailable_items) == 0,
            "unavailable_items": unavailable_items
        }
    
    def _process_payment(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate payment processing."""
        # Simulate payment failure for orders over $500
        if order_data["total"] > 500:
            return {
                "success": False,
                "error": "Credit card declined"
            }
        
        return {
            "success": True,
            "payment_id": f"PAY-{int(time.time())}"
        }
    
    def _update_inventory(self, items: List[Dict[str, Any]]) -> None:
        """Simulate inventory update."""
        logger.info(f"Updating inventory for {len(items)} items")
        # In a real system, this would update a database
    
    def _create_shipping_label(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate shipping label creation."""
        return {
            "tracking_number": f"TRACK-{order_data['order_id']}-{int(time.time())}"
        }
    
    def _send_order_notifications(self, order_data: Dict[str, Any], processing_result: Dict[str, Any]) -> None:
        """Send notifications via SNS for processed orders."""
        try:
            # Send order confirmation notification
            confirmation_message = {
                "type": "order_confirmation",
                "order_id": order_data["order_id"],
                "customer_id": order_data["customer_id"],
                "total": order_data["total"],
                "payment_id": processing_result.get("payment_id"),
                "tracking_number": processing_result.get("shipping_label"),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.publish_notification("customer-notifications-topic", confirmation_message)
            
            # Send inventory update notification
            inventory_message = {
                "type": "inventory_update",
                "order_id": order_data["order_id"],
                "items": order_data["items"],
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.publish_notification("inventory-updates-topic", inventory_message)
            
        except Exception as e:
            logger.error(f"Failed to send notifications for order {order_data['order_id']}: {e}")
    
    def publish_notification(self, topic_name: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """Publish notification to SNS topic.
        
        Args:
            topic_name: SNS topic name
            message: Message to publish
            
        Returns:
            Publication result
        """
        try:
            topic_arn = self.get_topic_arn(topic_name)
            
            response = self.sns.publish(
                TopicArn=topic_arn,
                Message=json.dumps(message),
                Subject=f"Order System: {message.get('type', 'notification')}",
                MessageAttributes={
                    "message_type": {
                        "StringValue": message.get("type", "unknown"),
                        "DataType": "String"
                    },
                    "order_id": {
                        "StringValue": message.get("order_id", "unknown"),
                        "DataType": "String"
                    }
                }
            )
            
            logger.info(f"Published notification to {topic_name}: {message.get('type')}")
            
            return {
                "success": True,
                "message_id": response["MessageId"],
                "topic_arn": topic_arn
            }
            
        except Exception as e:
            logger.error(f"Failed to publish notification to {topic_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_queue_metrics(self, queue_name: str) -> Dict[str, Any]:
        """Get CloudWatch metrics for a queue.
        
        Args:
            queue_name: SQS queue name
            
        Returns:
            Queue metrics dictionary
        """
        try:
            queue_url = self.get_queue_url(queue_name)
            
            # Get queue attributes
            attributes = self.sqs.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=["All"]
            )["Attributes"]
            
            return {
                "approximate_number_of_messages": int(attributes.get("ApproximateNumberOfMessages", 0)),
                "approximate_number_of_messages_not_visible": int(attributes.get("ApproximateNumberOfMessagesNotVisible", 0)),
                "approximate_number_of_messages_delayed": int(attributes.get("ApproximateNumberOfMessagesDelayed", 0)),
                "created_timestamp": attributes.get("CreatedTimestamp"),
                "visibility_timeout": int(attributes.get("VisibilityTimeout", 30))
            }
            
        except Exception as e:
            logger.error(f"Failed to get metrics for queue {queue_name}: {e}")
            return {}
    
    def monitor_queue_backlog(self, queue_name: str, threshold: int = 10) -> Dict[str, Any]:
        """Monitor queue backlog and return alert if threshold exceeded.
        
        Args:
            queue_name: SQS queue name to monitor
            threshold: Alert threshold for message count
            
        Returns:
            Monitoring result with alert status
        """
        metrics = self.get_queue_metrics(queue_name)
        message_count = metrics.get("approximate_number_of_messages", 0)
        
        alert_triggered = message_count >= threshold
        
        monitoring_result = {
            "queue_name": queue_name,
            "message_count": message_count,
            "threshold": threshold,
            "alert_triggered": alert_triggered,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if alert_triggered:
            logger.warning(f"Queue backlog alert: {queue_name} has {message_count} messages (threshold: {threshold})")
            
            # Send alert notification
            alert_message = {
                "type": "queue_backlog_alert",
                "queue_name": queue_name,
                "message_count": message_count,
                "threshold": threshold,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.publish_notification("customer-notifications-topic", alert_message)
        
        return monitoring_result