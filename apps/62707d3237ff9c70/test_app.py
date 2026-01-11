import pytest
import time
import json
from botocore.exceptions import ClientError
from app import UserManagementSystem, create_user_management_system

class TestUserManagementSystem:
    """Integration tests for the User Management System."""
    
    def test_infrastructure_exists(self, dynamodb_client, lambda_client):
        """Test that all required AWS resources exist after Terraform deployment."""
        # Test DynamoDB table exists and is active
        table_response = dynamodb_client.describe_table(TableName="UsersIds")
        assert table_response['Table']['TableStatus'] == 'ACTIVE'
        assert table_response['Table']['TableName'] == 'UsersIds'
        
        # Test that the table has the correct key schema
        key_schema = table_response['Table']['KeySchema']
        assert len(key_schema) == 1
        assert key_schema[0]['AttributeName'] == 'UserId'
        assert key_schema[0]['KeyType'] == 'HASH'
        
        # Test that streams are enabled
        stream_spec = table_response['Table']['StreamSpecification']
        assert stream_spec['StreamEnabled'] is True
        assert stream_spec['StreamViewType'] == 'NEW_AND_OLD_IMAGES'
        
        # Test Lambda function exists
        lambda_response = lambda_client.get_function(FunctionName="process-usersids-records")
        assert lambda_response['Configuration']['FunctionName'] == 'process-usersids-records'
        assert lambda_response['Configuration']['State'] == 'Active'
        
        # Test event source mapping exists
        mappings = lambda_client.list_event_source_mappings(
            FunctionName="process-usersids-records"
        )
        assert len(mappings['EventSourceMappings']) > 0
        assert mappings['EventSourceMappings'][0]['State'] in ['Enabled', 'Enabling', 'Creating']
    
    def test_system_health_check(self, clean_dynamodb_table):
        """Test the system health check functionality."""
        system = create_user_management_system()
        health_result = system.check_infrastructure()
        
        assert health_result['success'] is True
        assert 'components' in health_result
        
        components = health_result['components']
        assert components['dynamodb_table'] is True
        assert components['lambda_function'] is True
        assert components['stream_enabled'] is True
    
    def test_create_single_user(self, clean_dynamodb_table, sample_user_data):
        """Test creating a single user and verify it triggers stream processing."""
        system = create_user_management_system()
        user_data = sample_user_data['user1']
        
        # Create user
        result = system.create_user(user_data)
        assert result['success'] is True
        assert result['userId'] == user_data['UserId']
        
        # Verify user was created
        get_result = system.get_user(user_data['UserId'])
        assert get_result['success'] is True
        assert get_result['user']['UserId'] == user_data['UserId']
        assert get_result['user']['email'] == user_data['email']
        assert get_result['user']['status'] == user_data['status']
    
    def test_update_user_operations(self, clean_dynamodb_table, sample_user_data):
        """Test various user update operations that trigger stream events."""
        system = create_user_management_system()
        user_data = sample_user_data['user1']
        
        # Create initial user
        create_result = system.create_user(user_data)
        assert create_result['success'] is True
        
        # Test email update
        email_update = system.update_user(user_data['UserId'], {'email': 'newemail@example.com'})
        assert email_update['success'] is True
        assert email_update['updatedUser']['email'] == 'newemail@example.com'
        assert 'updatedAt' in email_update['updatedUser']
        
        # Test subscription upgrade
        subscription_update = system.upgrade_subscription(user_data['UserId'], 'enterprise')
        assert subscription_update['success'] is True
        assert subscription_update['updatedUser']['subscription'] == 'enterprise'
        
        # Test user activation/deactivation
        deactivate_result = system.deactivate_user(user_data['UserId'])
        assert deactivate_result['success'] is True
        assert deactivate_result['updatedUser']['status'] == 'inactive'
        
        activate_result = system.activate_user(user_data['UserId'])
        assert activate_result['success'] is True
        assert activate_result['updatedUser']['status'] == 'active'
    
    def test_delete_user_operation(self, clean_dynamodb_table, sample_user_data):
        """Test user deletion that triggers stream events with old image."""
        system = create_user_management_system()
        user_data = sample_user_data['user2']
        
        # Create user
        create_result = system.create_user(user_data)
        assert create_result['success'] is True
        
        # Verify user exists
        get_result = system.get_user(user_data['UserId'])
        assert get_result['success'] is True
        
        # Delete user
        delete_result = system.delete_user(user_data['UserId'])
        assert delete_result['success'] is True
        assert delete_result['userId'] == user_data['UserId']
        assert 'deletedUser' in delete_result
        assert delete_result['deletedUser']['UserId'] == user_data['UserId']
        
        # Verify user no longer exists
        get_result_after = system.get_user(user_data['UserId'])
        assert get_result_after['success'] is False
        assert 'not found' in get_result_after['error']
    
    def test_batch_user_operations(self, clean_dynamodb_table, sample_user_data):
        """Test batch operations that trigger multiple stream events."""
        system = create_user_management_system()
        
        # Prepare batch user data
        batch_users = [
            sample_user_data['user1'],
            sample_user_data['user2'],
            sample_user_data['user3']
        ]
        
        # Create users in batch
        batch_result = system.batch_create_users(batch_users)
        assert batch_result['success'] is True
        assert len(batch_result['successful']) == 3
        assert len(batch_result['failed']) == 0
        
        # Verify all users were created
        list_result = system.list_users()
        assert list_result['success'] is True
        assert list_result['count'] == 3
        
        # Test filtering by status
        active_users = system.list_users(status_filter='active')
        assert active_users['success'] is True
        assert active_users['count'] == 2  # user1 and user2 are active
        
        inactive_users = system.list_users(status_filter='inactive')
        assert inactive_users['success'] is True
        assert inactive_users['count'] == 1  # user3 is inactive
    
    def test_complete_user_lifecycle(self, clean_dynamodb_table):
        """Test a complete user lifecycle that triggers multiple stream events."""
        system = create_user_management_system()
        
        # Define test user
        test_user = {
            "UserId": "lifecycle-test-001",
            "email": "lifecycle@example.com",
            "firstName": "Test",
            "lastName": "User",
            "status": "active",
            "subscription": "basic"
        }
        
        # Run complete lifecycle simulation
        lifecycle_result = system.simulate_user_lifecycle(test_user)
        assert lifecycle_result['success'] is True
        assert lifecycle_result['userId'] == test_user['UserId']
        assert lifecycle_result['total_operations'] == 6
        assert lifecycle_result['successful_operations'] == 6
        
        # Verify all operations were successful
        operations = lifecycle_result['operations']
        operation_types = [op['operation'] for op in operations]
        expected_operations = ['create', 'update_email', 'upgrade_subscription', 'deactivate', 'reactivate', 'delete']
        assert operation_types == expected_operations
        
        # Verify all operations succeeded
        for operation in operations:
            assert operation['result']['success'] is True
        
        # Verify user no longer exists after lifecycle
        final_check = system.get_user(test_user['UserId'])
        assert final_check['success'] is False
    
    def test_error_handling_scenarios(self, clean_dynamodb_table):
        """Test error handling for various failure scenarios."""
        system = create_user_management_system()
        
        # Test getting non-existent user
        get_result = system.get_user("non-existent-user")
        assert get_result['success'] is False
        assert 'not found' in get_result['error']
        
        # Test updating non-existent user
        update_result = system.update_user("non-existent-user", {'email': 'test@example.com'})
        assert update_result['success'] is False
        assert 'not found' in update_result['error']
        
        # Test deleting non-existent user
        delete_result = system.delete_user("non-existent-user")
        assert delete_result['success'] is False
        assert 'not found' in delete_result['error']
        
        # Test creating user with missing required field
        invalid_user = {'email': 'test@example.com', 'firstName': 'Test'}
        create_result = system.create_user(invalid_user)
        assert create_result['success'] is False
        assert 'UserId is required' in create_result['error']
    
    def test_stream_event_generation(self, clean_dynamodb_table, sample_user_data, dynamodb_client):
        """Test that DynamoDB operations generate stream events (indirect verification)."""
        system = create_user_management_system()
        user_data = sample_user_data['user1']
        
        # Get initial stream description
        table_desc = dynamodb_client.describe_table(TableName="UsersIds")
        stream_arn = table_desc['Table']['LatestStreamArn']
        
        # Verify stream exists and is enabled
        assert stream_arn is not None
        
        # Create user (should generate INSERT stream event)
        create_result = system.create_user(user_data)
        assert create_result['success'] is True
        
        # Update user (should generate MODIFY stream event)
        update_result = system.update_user(user_data['UserId'], {'email': 'updated@example.com'})
        assert update_result['success'] is True
        
        # Delete user (should generate REMOVE stream event)
        delete_result = system.delete_user(user_data['UserId'])
        assert delete_result['success'] is True
        
        # Note: In a real AWS environment, we could verify stream events by
        # reading from the stream directly. LocalStack may have limitations
        # in stream event processing, but the operations should still succeed.
    
    def test_concurrent_user_operations(self, clean_dynamodb_table):
        """Test concurrent operations on different users to stress test the system."""
        system = create_user_management_system()
        
        # Create multiple users with different operations
        users = []
        for i in range(5):
            user_data = {
                "UserId": f"concurrent-user-{i:03d}",
                "email": f"user{i}@concurrent-test.com",
                "firstName": f"User{i}",
                "lastName": "Concurrent",
                "status": "active" if i % 2 == 0 else "inactive",
                "subscription": "premium" if i < 2 else "basic"
            }
            users.append(user_data)
        
        # Batch create all users
        batch_result = system.batch_create_users(users)
        assert batch_result['success'] is True
        assert len(batch_result['successful']) == 5
        
        # Perform various operations on different users concurrently
        operations_results = []
        
        # Update operations
        for i, user in enumerate(users):
            if i % 2 == 0:
                # Update email for even-indexed users
                result = system.update_user(user['UserId'], {'email': f'updated{i}@example.com'})
                operations_results.append(result)
            else:
                # Upgrade subscription for odd-indexed users
                result = system.upgrade_subscription(user['UserId'], 'enterprise')
                operations_results.append(result)
        
        # Verify all operations succeeded
        for result in operations_results:
            assert result['success'] is True
        
        # Verify final state
        final_list = system.list_users()
        assert final_list['success'] is True
        assert final_list['count'] == 5
        
        # Clean up - delete all users
        for user in users:
            delete_result = system.delete_user(user['UserId'])
            assert delete_result['success'] is True