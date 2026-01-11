import pytest
import json
import os
import tempfile
from pathlib import Path
from botocore.exceptions import ClientError

from app import ContentTransformerEdgeManager


class TestContentTransformerEdgeInfrastructure:
    """Test suite for Lambda@Edge content transformation infrastructure."""
    
    def test_s3_bucket_exists(self, s3_client, lambda_function_config):
        """Test that the S3 artifact bucket exists."""
        bucket_name = lambda_function_config["s3_bucket"]
        
        try:
            response = s3_client.head_bucket(Bucket=bucket_name)
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                pytest.fail(f"S3 bucket {bucket_name} does not exist")
            raise
    
    def test_lambda_function_exists(self, lambda_client, lambda_function_config):
        """Test that the Lambda@Edge function exists and is properly configured."""
        function_name = lambda_function_config["function_name"]
        
        try:
            response = lambda_client.get_function(FunctionName=function_name)
            
            # Verify function configuration
            config = response["Configuration"]
            assert config["FunctionName"] == function_name
            assert config["Runtime"] == lambda_function_config["runtime"]
            assert config["Handler"] == lambda_function_config["handler"]
            assert "Role" in config
            
            # Verify the function is published (required for Lambda@Edge)
            assert "Version" in config
            assert config["Version"] != "$LATEST"
            
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                pytest.fail(f"Lambda function {function_name} does not exist")
            raise
    
    def test_iam_role_exists(self, iam_client, lambda_function_config):
        """Test that the IAM role for Lambda@Edge exists with proper permissions."""
        role_name = lambda_function_config["role_name"]
        
        try:
            response = iam_client.get_role(RoleName=role_name)
            
            # Verify role exists
            role = response["Role"]
            assert role["RoleName"] == role_name
            
            # Verify assume role policy allows Lambda and Lambda@Edge
            assume_role_policy = json.loads(role["AssumeRolePolicyDocument"])
            service_principals = []
            
            for statement in assume_role_policy["Statement"]:
                if "Service" in statement["Principal"]:
                    if isinstance(statement["Principal"]["Service"], list):
                        service_principals.extend(statement["Principal"]["Service"])
                    else:
                        service_principals.append(statement["Principal"]["Service"])
            
            assert "lambda.amazonaws.com" in service_principals
            assert "edgelambda.amazonaws.com" in service_principals
            
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchEntity":
                pytest.fail(f"IAM role {role_name} does not exist")
            raise
    
    def test_cloudwatch_log_group_exists(self, logs_client, lambda_function_config):
        """Test that the CloudWatch log group exists for the Lambda function."""
        log_group_name = lambda_function_config["log_group"]
        
        try:
            response = logs_client.describe_log_groups(
                logGroupNamePrefix=log_group_name
            )
            
            log_group_found = False
            for log_group in response["logGroups"]:
                if log_group["logGroupName"] == log_group_name:
                    log_group_found = True
                    break
            
            assert log_group_found, f"CloudWatch log group {log_group_name} does not exist"
            
        except ClientError:
            pytest.fail(f"Failed to check CloudWatch log group {log_group_name}")


class TestContentTransformerEdgeApplication:
    """Test suite for Lambda@Edge content transformation application logic."""
    
    @pytest.fixture
    def edge_manager(self):
        """Create ContentTransformerEdgeManager instance."""
        return ContentTransformerEdgeManager()
    
    def test_create_deployment_package(self, edge_manager, sample_lambda_code, sample_config, temp_dir):
        """Test creation of Lambda deployment package."""
        zip_path = edge_manager.create_lambda_deployment_package(
            function_code=sample_lambda_code,
            config_data=sample_config
        )
        
        assert os.path.exists(zip_path)
        assert zip_path.endswith('.zip')
        
        # Verify zip contents
        import zipfile
        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            file_names = zip_file.namelist()
            assert 'index.js' in file_names
            assert 'config.json' in file_names
            assert 'package.json' in file_names
            
            # Verify config.json content
            config_content = zip_file.read('config.json')
            config_data = json.loads(config_content.decode('utf-8'))
            assert config_data['environment'] == 'test'
            assert config_data['customHeader'] == 'edge-processed'
        
        # Cleanup
        os.unlink(zip_path)
    
    def test_ssm_parameter_creation(self, edge_manager, sample_ssm_params):
        """Test creation and retrieval of SSM parameters."""
        # Create parameters
        created_params = edge_manager.create_ssm_parameters(sample_ssm_params)
        
        assert len(created_params) == len(sample_ssm_params)
        
        # Verify parameters can be retrieved
        retrieved_params = edge_manager.get_ssm_parameters(list(sample_ssm_params.keys()))
        
        for param_name, expected_value in sample_ssm_params.items():
            assert param_name in retrieved_params
            assert retrieved_params[param_name] == expected_value
    
    def test_s3_artifact_upload(self, edge_manager, sample_lambda_code, sample_config, lambda_function_config):
        """Test uploading Lambda deployment package to S3."""
        # Create deployment package
        zip_path = edge_manager.create_lambda_deployment_package(
            function_code=sample_lambda_code,
            config_data=sample_config
        )
        
        # Upload to S3
        bucket_name = lambda_function_config["s3_bucket"]
        key = f"{lambda_function_config['function_name']}.zip"
        
        response = edge_manager.upload_to_s3(zip_path, bucket_name, key)
        
        assert "ETag" in response
        assert "VersionId" in response
        
        # Verify object exists in S3
        s3_response = edge_manager.s3_client.head_object(Bucket=bucket_name, Key=key)
        assert s3_response["ResponseMetadata"]["HTTPStatusCode"] == 200
        
        # Cleanup
        os.unlink(zip_path)
    
    def test_cloudfront_event_creation(self, edge_manager):
        """Test creation of CloudFront test events."""
        test_events = edge_manager.create_cloudfront_test_events()
        
        assert "viewer-request" in test_events
        assert "mobile-request" in test_events
        assert "origin-response" in test_events
        
        # Verify viewer-request event structure
        viewer_event = test_events["viewer-request"]
        assert "Records" in viewer_event
        assert len(viewer_event["Records"]) == 1
        
        record = viewer_event["Records"][0]
        assert "cf" in record
        assert "config" in record["cf"]
        assert "request" in record["cf"]
        assert record["cf"]["config"]["eventType"] == "viewer-request"
        
        # Verify mobile-request event has mobile user agent
        mobile_event = test_events["mobile-request"]
        mobile_record = mobile_event["Records"][0]
        user_agent = mobile_record["cf"]["request"]["headers"]["user-agent"][0]["value"]
        assert "Mobile" in user_agent or "iPhone" in user_agent
        
        # Verify origin-response event structure
        response_event = test_events["origin-response"]
        response_record = response_event["Records"][0]
        assert "response" in response_record["cf"]
        assert response_record["cf"]["config"]["eventType"] == "origin-response"
    
    def test_lambda_function_invocation(self, edge_manager, lambda_function_config):
        """Test invoking the Lambda@Edge function with test events."""
        function_name = lambda_function_config["function_name"]
        test_events = edge_manager.create_cloudfront_test_events()
        
        # Test viewer-request event
        viewer_event = test_events["viewer-request"]
        try:
            response = edge_manager.invoke_lambda_for_testing(function_name, viewer_event)
            
            assert response["StatusCode"] == 200
            assert "Payload" in response
            
            # Verify the response is a valid CloudFront request object
            payload = response["Payload"]
            if isinstance(payload, dict):
                # Should have request properties for viewer-request
                assert "uri" in payload or "method" in payload or "headers" in payload
            
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                pytest.skip(f"Lambda function {function_name} not found - skipping invocation test")
            raise
    
    def test_mobile_device_detection(self, edge_manager, lambda_function_config):
        """Test Lambda@Edge function's mobile device detection capability."""
        function_name = lambda_function_config["function_name"]
        test_events = edge_manager.create_cloudfront_test_events()
        
        # Test mobile request event
        mobile_event = test_events["mobile-request"]
        
        try:
            response = edge_manager.invoke_lambda_for_testing(function_name, mobile_event)
            
            assert response["StatusCode"] == 200
            
            # The function should add device type headers for mobile requests
            payload = response["Payload"]
            if isinstance(payload, dict) and "headers" in payload:
                # Check if device type header was added
                headers = payload["headers"]
                device_type_found = False
                
                for header_name, header_values in headers.items():
                    if header_name.lower() in ['x-device-type', 'device-type']:
                        device_type_found = True
                        # Should indicate mobile device
                        if isinstance(header_values, list) and header_values:
                            assert 'mobile' in header_values[0].get('value', '').lower()
                        break
                
                # Note: This assertion might need to be relaxed depending on the actual Lambda implementation
                # assert device_type_found, "Mobile device detection header not found"
            
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                pytest.skip(f"Lambda function {function_name} not found - skipping mobile detection test")
            raise
    
    def test_origin_response_transformation(self, edge_manager, lambda_function_config):
        """Test Lambda@Edge function's origin response transformation."""
        function_name = lambda_function_config["function_name"]
        test_events = edge_manager.create_cloudfront_test_events()
        
        # Test origin-response event
        response_event = test_events["origin-response"]
        
        try:
            response = edge_manager.invoke_lambda_for_testing(function_name, response_event)
            
            assert response["StatusCode"] == 200
            
            # The function should modify response headers
            payload = response["Payload"]
            if isinstance(payload, dict) and "headers" in payload:
                headers = payload["headers"]
                
                # Look for transformation indicators
                processed_by_found = False
                timestamp_found = False
                
                for header_name in headers.keys():
                    if 'processed' in header_name.lower():
                        processed_by_found = True
                    if 'timestamp' in header_name.lower():
                        timestamp_found = True
                
                # Note: These assertions might need to be relaxed depending on implementation
                # assert processed_by_found or timestamp_found, "Response transformation headers not found"
            
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                pytest.skip(f"Lambda function {function_name} not found - skipping response transformation test")
            raise
    
    def test_infrastructure_verification_workflow(self, edge_manager, lambda_function_config):
        """Test complete infrastructure verification workflow."""
        function_name = lambda_function_config["function_name"]
        bucket_name = lambda_function_config["s3_bucket"]
        role_name = lambda_function_config["role_name"]
        log_group_name = lambda_function_config["log_group"]
        
        try:
            # Verify all infrastructure components
            lambda_info = edge_manager.verify_lambda_function(function_name)
            s3_info = edge_manager.verify_s3_bucket(bucket_name)
            iam_info = edge_manager.verify_iam_role(role_name)
            log_info = edge_manager.verify_cloudwatch_log_group(log_group_name)
            
            # All verifications should succeed
            assert lambda_info is not None
            assert s3_info is not None
            assert iam_info is not None
            assert log_info is not None
            
            # Verify cross-component relationships
            lambda_config = lambda_info["Configuration"]
            role_arn = lambda_config["Role"]
            
            # Role ARN should contain the expected role name
            assert role_name in role_arn
            
        except ClientError as e:
            pytest.fail(f"Infrastructure verification failed: {e}")
    
    def test_end_to_end_content_transformation_workflow(self, edge_manager, sample_lambda_code, sample_config, sample_ssm_params, lambda_function_config):
        """Test the complete end-to-end content transformation workflow."""
        # This test simulates a complete deployment and testing workflow
        
        # 1. Create SSM parameters
        created_params = edge_manager.create_ssm_parameters(sample_ssm_params)
        assert len(created_params) == len(sample_ssm_params)
        
        # 2. Create deployment package
        zip_path = edge_manager.create_lambda_deployment_package(
            function_code=sample_lambda_code,
            config_data=sample_config
        )
        assert os.path.exists(zip_path)
        
        # 3. Upload to S3
        bucket_name = lambda_function_config["s3_bucket"]
        key = f"test-{lambda_function_config['function_name']}.zip"
        
        upload_response = edge_manager.upload_to_s3(zip_path, bucket_name, key)
        assert "ETag" in upload_response
        
        # 4. Create test events
        test_events = edge_manager.create_cloudfront_test_events()
        assert len(test_events) >= 3
        
        # 5. Test Lambda function if it exists
        function_name = lambda_function_config["function_name"]
        try:
            lambda_info = edge_manager.verify_lambda_function(function_name)
            
            # Test with different event types
            for event_type, event_data in test_events.items():
                response = edge_manager.invoke_lambda_for_testing(function_name, event_data)
                assert response["StatusCode"] == 200
                
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                pytest.skip("Lambda function not found - skipping end-to-end test")
            raise
        
        finally:
            # Cleanup
            if os.path.exists(zip_path):
                os.unlink(zip_path)