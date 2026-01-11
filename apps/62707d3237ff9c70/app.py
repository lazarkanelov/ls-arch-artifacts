import boto3
import json
import logging
from typing import Dict, List, Optional, Any
from botocore.exceptions import ClientError
import time
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserManagementSystem:
    """A realistic user management system that demonstrates DynamoDB streams and Lambda processing."""
    
    def __init__(self, endpoint_url: Optional[str] = None):
        """Initialize the user management system with AWS clients."""
        self.endpoint_url = endpoint_url or os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
        
        self.dynamodb_resource = boto3.resource(
            "dynamodb",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.dynamodb_client = boto3.client(
            "dynamodb",
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
        
        self.table_name = "UsersIds"
        self.lambda_function_name = "process-usersids-records"
        
        self.users_table = self.dynamodb_resource.Table(self.table_name)
    
    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user in the system.
        
        This will trigger a DynamoDB stream event that the Lambda function will process.
        """
        try:
            # Add timestamp if not provided
            if 'createdAt' not in user_data:
                user_data['createdAt'] = datetime.utcnow().isoformat() + 'Z'
            
            # Ensure required fields
            if 'UserId' not in user_data:
                raise ValueError("UserId is required")
            
            # Set default status if not provided
            if 'status' not in user_data:
                user_data['status'] = 'active'
            
            response = self.users_table.put_item(Item=user_data)
            logger.info(f"Created user: {user_data['UserId']}")
            
            return {
                'success': True,
                'userId': user_data['UserId'],
                'message': 'User created successfully'
            }
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing user.
        
        This will trigger a DynamoDB stream event with both old and new images.
        """
        try:
            # Build update expression
            update_expression_parts = []
            expression_attribute_values = {}
            expression_attribute_names = {}
            
            for key, value in updates.items():
                if key != 'UserId':  # Can't update the hash key
                    attr_name = f"#{key}"
                    attr_value = f":{key}"
                    update_expression_parts.append(f"{attr_name} = {attr_value}")
                    expression_attribute_names[attr_name] = key
                    expression_attribute_values[attr_value] = value
            
            if not update_expression_parts:
                return {'success': False, 'error': 'No valid fields to update'}
            
            # Add updatedAt timestamp
            update_expression_parts.append("#updatedAt = :updatedAt")
            expression_attribute_names["#updatedAt"] = "updatedAt"
            expression_attribute_values[":updatedAt"] = datetime.utcnow().isoformat() + 'Z'
            
            update_expression = "SET " + ", ".join(update_expression_parts)
            
            response = self.users_table.update_item(
                Key={'UserId': user_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
                ReturnValues='ALL_NEW'
            )
            
            logger.info(f"Updated user: {user_id}")
            
            return {
                'success': True,
                'userId': user_id,
                'updatedUser': response.get('Attributes', {}),
                'message': 'User updated successfully'
            }
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return {'success': False, 'error': f'User {user_id} not found'}
            logger.error(f"Error updating user: {str(e)}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Error updating user: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def delete_user(self, user_id: str) -> Dict[str, Any]:
        """Delete a user from the system.
        
        This will trigger a DynamoDB stream event with the old image.
        """
        try:
            response = self.users_table.delete_item(
                Key={'UserId': user_id},
                ReturnValues='ALL_OLD'
            )
            
            if 'Attributes' not in response:
                return {'success': False, 'error': f'User {user_id} not found'}
            
            logger.info(f"Deleted user: {user_id}")
            
            return {
                'success': True,
                'userId': user_id,
                'deletedUser': response['Attributes'],
                'message': 'User deleted successfully'
            }
        except Exception as e:
            logger.error(f"Error deleting user: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_user(self, user_id: str) -> Dict[str, Any]:
        """Retrieve a user by ID."""
        try:
            response = self.users_table.get_item(Key={'UserId': user_id})
            
            if 'Item' not in response:
                return {'success': False, 'error': f'User {user_id} not found'}
            
            return {
                'success': True,
                'user': response['Item']
            }
        except Exception as e:
            logger.error(f"Error retrieving user: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def list_users(self, status_filter: Optional[str] = None) -> Dict[str, Any]:
        """List all users, optionally filtered by status."""
        try:
            if status_filter:
                response = self.users_table.scan(
                    FilterExpression="#status = :status",
                    ExpressionAttributeNames={"#status": "status"},
                    ExpressionAttributeValues={":status": status_filter}
                )
            else:
                response = self.users_table.scan()
            
            users = response.get('Items', [])
            
            return {
                'success': True,
                'users': users,
                'count': len(users)
            }
        except Exception as e:
            logger.error(f"Error listing users: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def batch_create_users(self, users: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create multiple users in a batch operation.
        
        This will trigger multiple DynamoDB stream events.
        """
        try:
            successful_users = []
            failed_users = []
            
            with self.users_table.batch_writer() as batch:
                for user_data in users:
                    try:
                        # Add timestamp if not provided
                        if 'createdAt' not in user_data:
                            user_data['createdAt'] = datetime.utcnow().isoformat() + 'Z'
                        
                        # Set default status if not provided
                        if 'status' not in user_data:
                            user_data['status'] = 'active'
                        
                        batch.put_item(Item=user_data)
                        successful_users.append(user_data['UserId'])
                        
                    except Exception as e:
                        failed_users.append({
                            'userId': user_data.get('UserId', 'unknown'),
                            'error': str(e)
                        })
            
            logger.info(f"Batch created {len(successful_users)} users")
            
            return {
                'success': True,
                'successful': successful_users,
                'failed': failed_users,
                'message': f'Successfully created {len(successful_users)} users'
            }
        except Exception as e:
            logger.error(f"Error in batch create: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def activate_user(self, user_id: str) -> Dict[str, Any]:
        """Activate a user account."""
        return self.update_user(user_id, {'status': 'active'})
    
    def deactivate_user(self, user_id: str) -> Dict[str, Any]:
        """Deactivate a user account."""
        return self.update_user(user_id, {'status': 'inactive'})
    
    def upgrade_subscription(self, user_id: str, new_subscription: str) -> Dict[str, Any]:
        """Upgrade user subscription level."""
        return self.update_user(user_id, {'subscription': new_subscription})
    
    def check_infrastructure(self) -> Dict[str, Any]:
        """Check if all required AWS resources exist and are properly configured."""
        results = {
            'dynamodb_table': False,
            'lambda_function': False,
            'stream_enabled': False,
            'event_source_mapping': False
        }
        
        try:
            # Check DynamoDB table
            table_response = self.dynamodb_client.describe_table(TableName=self.table_name)
            results['dynamodb_table'] = table_response['Table']['TableStatus'] == 'ACTIVE'
            
            # Check if stream is enabled
            stream_spec = table_response['Table'].get('StreamSpecification', {})
            results['stream_enabled'] = stream_spec.get('StreamEnabled', False)
            
            # Check Lambda function
            try:
                lambda_response = self.lambda_client.get_function(FunctionName=self.lambda_function_name)
                results['lambda_function'] = lambda_response['Configuration']['State'] == 'Active'
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceNotFoundException':
                    logger.error(f"Error checking Lambda function: {str(e)}")
            
            # Check event source mapping
            try:
                mappings = self.lambda_client.list_event_source_mappings(
                    FunctionName=self.lambda_function_name
                )
                results['event_source_mapping'] = len(mappings.get('EventSourceMappings', [])) > 0
            except ClientError as e:
                logger.error(f"Error checking event source mappings: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error checking infrastructure: {str(e)}")
            return {'success': False, 'error': str(e)}
        
        all_healthy = all(results.values())
        
        return {
            'success': True,
            'healthy': all_healthy,
            'components': results
        }
    
    def simulate_user_lifecycle(self, base_user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate a complete user lifecycle to test the stream processing.
        
        This creates a user, updates them multiple times, and then deletes them.
        Each operation should trigger stream events.
        """
        try:
            user_id = base_user_data['UserId']
            operations = []
            
            # 1. Create user
            create_result = self.create_user(base_user_data)
            operations.append({'operation': 'create', 'result': create_result})
            
            if not create_result['success']:
                return {'success': False, 'error': 'Failed to create user', 'operations': operations}
            
            # Wait a moment for stream processing
            time.sleep(0.1)
            
            # 2. Update user email
            update_result1 = self.update_user(user_id, {'email': 'updated.email@example.com'})
            operations.append({'operation': 'update_email', 'result': update_result1})
            
            time.sleep(0.1)
            
            # 3. Upgrade subscription
            upgrade_result = self.upgrade_subscription(user_id, 'premium')
            operations.append({'operation': 'upgrade_subscription', 'result': upgrade_result})
            
            time.sleep(0.1)
            
            # 4. Deactivate user
            deactivate_result = self.deactivate_user(user_id)
            operations.append({'operation': 'deactivate', 'result': deactivate_result})
            
            time.sleep(0.1)
            
            # 5. Reactivate user
            reactivate_result = self.activate_user(user_id)
            operations.append({'operation': 'reactivate', 'result': reactivate_result})
            
            time.sleep(0.1)
            
            # 6. Delete user
            delete_result = self.delete_user(user_id)
            operations.append({'operation': 'delete', 'result': delete_result})
            
            successful_operations = sum(1 for op in operations if op['result']['success'])
            
            return {
                'success': True,
                'userId': user_id,
                'operations': operations,
                'successful_operations': successful_operations,
                'total_operations': len(operations),
                'message': f'Completed lifecycle with {successful_operations}/{len(operations)} successful operations'
            }
            
        except Exception as e:
            logger.error(f"Error in user lifecycle simulation: {str(e)}")
            return {'success': False, 'error': str(e)}

def create_user_management_system() -> UserManagementSystem:
    """Factory function to create a UserManagementSystem instance."""
    return UserManagementSystem()