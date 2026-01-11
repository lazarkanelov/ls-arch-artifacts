import json
import time
import pytest
from typing import Dict, List, Any
from app import OrderProcessingSystem


class TestOrderProcessingSystem:
    """Integration tests for the order processing system."""
    
    @pytest.fixture(autouse=True)
    def setup(self, localstack_endpoint):
        """Set up test instance for each test."""
        self.system = OrderProcessingSystem(endpoint_url=localstack_endpoint)
    
    def test_infrastructure_resources_exist(self, sqs_client, sns_client, cloudwatch_client):
        """Test that all required AWS resources are provisioned correctly."""
        # Test SQS queues exist
        queues_response = sqs_client.list_queues()
        queue_urls = queues_response.get("QueueUrls", [])
        
        # Should have at least one queue (the main processing queue)
        assert len(queue_urls) > 0, "No SQS queues found"
        
        # Test SNS topics exist
        topics_response = sns_client.list_topics()
        topics = topics_response.get("Topics", [])
        
        # Should have at least one topic for notifications
        assert len(topics) > 0, "No SNS topics found"
        
        # Test CloudWatch is accessible
        try:
            cloudwatch_client.list_metrics(Namespace="AWS/SQS")
        except Exception as e:
            pytest.fail(f"CloudWatch not accessible: {e}")
    
    def test_order_submission_workflow(self, test_data, queue_cleanup):
        """Test complete order submission workflow."""
        order = test_data["orders"][0]
        
        # Submit order to queue
        result = self.system.submit_order(order)
        
        assert result["success"] is True
        assert "message_id" in result
        assert result["order_id"] == order["order_id"]
        
        # Verify order is in queue
        queue_url = self.system.get_queue_url("order-processing-queue")
        queue_cleanup.append(queue_url)
        
        metrics = self.system.get_queue_metrics("order-processing-queue")
        assert metrics["approximate_number_of_messages"] >= 1
    
    def test_order_processing_end_to_end(self, test_data, queue_cleanup):
        """Test end-to-end order processing including notifications."""
        orders = test_data["orders"]
        
        # Submit multiple orders
        submitted_orders = []
        for order in orders:
            result = self.system.submit_order(order)
            assert result["success"] is True
            submitted_orders.append(result)
        
        queue_url = self.system.get_queue_url("order-processing-queue")
        queue_cleanup.append(queue_url)
        
        # Wait a moment for messages to be available
        time.sleep(1)
        
        # Process orders
        processed_results = self.system.process_orders(max_messages=len(orders))
        
        assert len(processed_results) == len(orders)
        
        # Verify processing results
        for result in processed_results:
            assert "order_id" in result
            assert "processing_result" in result
            
            processing_result = result["processing_result"]
            if processing_result["success"]:
                assert "payment_id" in processing_result
                assert "shipping_label" in processing_result
                assert processing_result["status"] == "processed"
        
        # Verify queue is empty after processing
        metrics = self.system.get_queue_metrics("order-processing-queue")
        successful_orders = sum(1 for r in processed_results if r["processing_result"]["success"])
        expected_remaining = len(orders) - successful_orders
        assert metrics["approximate_number_of_messages"] == expected_remaining
    
    def test_payment_failure_handling(self, queue_cleanup):
        """Test handling of payment failures."""
        # Create order with high total to trigger payment failure
        expensive_order = {
            "order_id": "ORD-EXPENSIVE",
            "customer_id": "CUST-999",
            "items": [{"sku": "LUXURY-ITEM", "quantity": 1, "price": 600.00}],
            "total": 600.00,
            "status": "pending"
        }
        
        # Submit order
        submit_result = self.system.submit_order(expensive_order)
        assert submit_result["success"] is True
        
        queue_url = self.system.get_queue_url("order-processing-queue")
        queue_cleanup.append(queue_url)
        
        # Wait for message availability
        time.sleep(1)
        
        # Process order (should fail at payment stage)
        processed_results = self.system.process_orders(max_messages=1)
        
        assert len(processed_results) == 1
        result = processed_results[0]
        
        assert result["order_id"] == expensive_order["order_id"]
        assert result["processing_result"]["success"] is False
        assert "payment" in result["processing_result"]["error"]
        assert result["processing_result"]["stage"] == "payment"
    
    def test_inventory_check_failure(self, queue_cleanup):
        """Test inventory check failure handling."""
        # Create order with out-of-stock item
        out_of_stock_order = {
            "order_id": "ORD-OOS",
            "customer_id": "CUST-888",
            "items": [{"sku": "OUT-OF-STOCK", "quantity": 1, "price": 50.00}],
            "total": 50.00,
            "status": "pending"
        }
        
        submit_result = self.system.submit_order(out_of_stock_order)
        assert submit_result["success"] is True
        
        queue_url = self.system.get_queue_url("order-processing-queue")
        queue_cleanup.append(queue_url)
        
        time.sleep(1)
        
        processed_results = self.system.process_orders(max_messages=1)
        
        assert len(processed_results) == 1
        result = processed_results[0]
        
        assert result["processing_result"]["success"] is False
        assert "inventory" in result["processing_result"]["error"].lower()
        assert result["processing_result"]["stage"] == "inventory_check"
    
    def test_sns_notification_publishing(self, test_data):
        """Test SNS notification publishing functionality."""
        notification_data = {
            "type": "test_notification",
            "order_id": "TEST-001",
            "message": "This is a test notification",
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        # Publish to customer notifications topic
        result = self.system.publish_notification(
            "customer-notifications-topic", 
            notification_data
        )
        
        assert result["success"] is True
        assert "message_id" in result
        assert "topic_arn" in result
        
        # Test publishing to inventory updates topic
        inventory_notification = {
            "type": "inventory_update",
            "order_id": "TEST-002",
            "items": test_data["inventory_updates"],
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        result = self.system.publish_notification(
            "inventory-updates-topic",
            inventory_notification
        )
        
        assert result["success"] is True
        assert "message_id" in result
    
    def test_queue_monitoring_and_metrics(self, test_data, queue_cleanup):
        """Test queue monitoring and metrics collection."""
        # Submit several orders to create queue backlog
        orders = test_data["orders"]
        for order in orders:
            self.system.submit_order(order)
        
        queue_url = self.system.get_queue_url("order-processing-queue")
        queue_cleanup.append(queue_url)
        
        time.sleep(1)
        
        # Get queue metrics
        metrics = self.system.get_queue_metrics("order-processing-queue")
        
        assert "approximate_number_of_messages" in metrics
        assert metrics["approximate_number_of_messages"] >= len(orders)
        assert "visibility_timeout" in metrics
        
        # Test backlog monitoring with low threshold to trigger alert
        monitoring_result = self.system.monitor_queue_backlog(
            "order-processing-queue", 
            threshold=1
        )
        
        assert monitoring_result["alert_triggered"] is True
        assert monitoring_result["message_count"] >= len(orders)
        assert "timestamp" in monitoring_result
    
    def test_error_handling_invalid_queue(self):
        """Test error handling for invalid queue operations."""
        invalid_order = {
            "order_id": "INVALID-001",
            "customer_id": "CUST-INVALID",
            "items": [],  # Empty items should cause validation failure
            "total": 0,
            "status": "pending"
        }
        
        # This should succeed in submitting but fail in processing
        result = self.system.submit_order(invalid_order)
        assert result["success"] is True
        
        # Process should handle validation failure
        time.sleep(1)
        processed_results = self.system.process_orders(max_messages=1)
        
        if processed_results:
            result = processed_results[0]
            assert result["processing_result"]["success"] is False
            assert "validation" in result["processing_result"]["error"].lower()
    
    def test_message_attributes_and_filtering(self, test_data, queue_cleanup):
        """Test SQS message attributes for filtering and routing."""
        order = test_data["orders"][0]
        
        # Submit order and verify message attributes
        result = self.system.submit_order(order)
        assert result["success"] is True
        
        queue_url = self.system.get_queue_url("order-processing-queue")
        queue_cleanup.append(queue_url)
        
        time.sleep(1)
        
        # Receive message and verify attributes
        response = self.system.sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            MessageAttributeNames=["All"]
        )
        
        messages = response.get("Messages", [])
        assert len(messages) > 0
        
        message = messages[0]
        attributes = message.get("MessageAttributes", {})
        
        assert "order_id" in attributes
        assert attributes["order_id"]["StringValue"] == order["order_id"]
        assert "customer_id" in attributes
        assert attributes["customer_id"]["StringValue"] == order["customer_id"]
        assert "total_amount" in attributes
        assert float(attributes["total_amount"]["StringValue"]) == order["total"]
    
    def test_concurrent_order_processing(self, test_data, queue_cleanup):
        """Test processing multiple orders concurrently."""
        # Create multiple orders with different characteristics
        orders = [
            {**test_data["orders"][0], "order_id": f"CONCURRENT-{i}"}
            for i in range(5)
        ]
        
        # Submit all orders
        submitted = []
        for order in orders:
            result = self.system.submit_order(order)
            assert result["success"] is True
            submitted.append(result)
        
        queue_url = self.system.get_queue_url("order-processing-queue")
        queue_cleanup.append(queue_url)
        
        time.sleep(2)  # Wait for all messages to be available
        
        # Process all orders in one batch
        processed_results = self.system.process_orders(max_messages=10)
        
        # Should have processed all submitted orders
        successful_processes = [r for r in processed_results if r["processing_result"]["success"]]
        assert len(successful_processes) == len(orders)
        
        # Verify all orders were processed with unique payment IDs
        payment_ids = [r["processing_result"]["payment_id"] for r in successful_processes]
        assert len(set(payment_ids)) == len(payment_ids)  # All unique
        
        # Verify all orders got shipping labels
        shipping_labels = [r["processing_result"]["shipping_label"] for r in successful_processes]
        assert len(set(shipping_labels)) == len(shipping_labels)  # All unique