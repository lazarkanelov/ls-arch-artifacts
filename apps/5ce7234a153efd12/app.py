import boto3
import json
import os
import zipfile
import tempfile
from typing import Dict, Any, Optional, List
from pathlib import Path
import logging
from botocore.exceptions import ClientError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ContentTransformerEdgeManager:
    """Manages a Lambda@Edge function for content transformation in CloudFront distributions."""
    
    def __init__(self):
        self.endpoint_url = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
        self.aws_config = {
            "endpoint_url": self.endpoint_url,
            "aws_access_key_id": "test",
            "aws_secret_access_key": "test",
            "region_name": "us-east-1"
        }
        
        self.lambda_client = boto3.client("lambda", **self.aws_config)
        self.s3_client = boto3.client("s3", **self.aws_config)
        self.ssm_client = boto3.client("ssm", **self.aws_config)
        self.iam_client = boto3.client("iam", **self.aws_config)
        self.logs_client = boto3.client("logs", **self.aws_config)
    
    def create_lambda_deployment_package(self, 
                                       function_code: str, 
                                       config_data: Dict[str, Any],
                                       package_json: Optional[str] = None) -> str:
        """Create a deployment package (zip file) for the Lambda@Edge function.
        
        Args:
            function_code: The JavaScript code for the Lambda function
            config_data: Configuration data to be written as config.json
            package_json: Optional package.json content
            
        Returns:
            Path to the created zip file
        """
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
            with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Add the main function code
                zip_file.writestr('index.js', function_code)
                
                # Add configuration file
                zip_file.writestr('config.json', json.dumps(config_data, indent=2))
                
                # Add package.json if provided
                if package_json:
                    zip_file.writestr('package.json', package_json)
                else:
                    # Default package.json
                    default_package = {
                        "name": "content-transformer-edge",
                        "version": "1.0.0",
                        "description": "Lambda@Edge function for content transformation",
                        "main": "index.js",
                        "dependencies": {
                            "@aws-sdk/client-ssm": "^3.0.0"
                        }
                    }
                    zip_file.writestr('package.json', json.dumps(default_package, indent=2))
            
            return temp_zip.name
    
    def upload_to_s3(self, zip_file_path: str, bucket_name: str, key: str) -> Dict[str, Any]:
        """Upload the Lambda deployment package to S3.
        
        Args:
            zip_file_path: Path to the zip file to upload
            bucket_name: S3 bucket name
            key: S3 object key
            
        Returns:
            S3 object metadata
        """
        try:
            with open(zip_file_path, 'rb') as zip_file:
                response = self.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=key,
                    Body=zip_file.read(),
                    ContentType='application/zip'
                )
                logger.info(f"Successfully uploaded {key} to S3 bucket {bucket_name}")
                return response
        except ClientError as e:
            logger.error(f"Failed to upload to S3: {e}")
            raise
    
    def create_ssm_parameters(self, parameters: Dict[str, str]) -> Dict[str, str]:
        """Create SSM parameters for the Lambda function.
        
        Args:
            parameters: Dictionary of parameter names and values
            
        Returns:
            Dictionary of parameter names and ARNs
        """
        created_params = {}
        
        for name, value in parameters.items():
            try:
                response = self.ssm_client.put_parameter(
                    Name=name,
                    Value=value,
                    Type='SecureString',
                    Tier='Standard' if len(value) <= 4096 else 'Advanced',
                    Description=f"Parameter for content-transformer-edge Lambda function",
                    Overwrite=True
                )
                
                # Get the parameter to retrieve its ARN
                param_info = self.ssm_client.describe_parameters(
                    Filters=[
                        {
                            'Key': 'Name',
                            'Values': [name]
                        }
                    ]
                )
                
                if param_info['Parameters']:
                    created_params[name] = param_info['Parameters'][0].get('ARN', '')
                    logger.info(f"Created SSM parameter: {name}")
                
            except ClientError as e:
                logger.error(f"Failed to create SSM parameter {name}: {e}")
                raise
        
        return created_params
    
    def verify_lambda_function(self, function_name: str) -> Dict[str, Any]:
        """Verify that the Lambda function exists and get its configuration.
        
        Args:
            function_name: Name of the Lambda function
            
        Returns:
            Lambda function configuration
        """
        try:
            response = self.lambda_client.get_function(FunctionName=function_name)
            logger.info(f"Lambda function {function_name} exists and is configured")
            return response
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.error(f"Lambda function {function_name} not found")
            raise
    
    def invoke_lambda_for_testing(self, function_name: str, test_event: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke the Lambda function with a test CloudFront event.
        
        Args:
            function_name: Name of the Lambda function
            test_event: CloudFront event to test with
            
        Returns:
            Lambda invocation response
        """
        try:
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(test_event)
            )
            
            result = {
                'StatusCode': response['StatusCode'],
                'ExecutedVersion': response['ExecutedVersion']
            }
            
            if 'Payload' in response:
                payload = response['Payload'].read()
                if payload:
                    result['Payload'] = json.loads(payload.decode('utf-8'))
            
            if 'LogResult' in response:
                result['LogResult'] = response['LogResult']
            
            logger.info(f"Successfully invoked Lambda function {function_name}")
            return result
            
        except ClientError as e:
            logger.error(f"Failed to invoke Lambda function: {e}")
            raise
    
    def create_cloudfront_test_events(self) -> Dict[str, Dict[str, Any]]:
        """Create sample CloudFront events for testing Lambda@Edge function.
        
        Returns:
            Dictionary of test event types and their payloads
        """
        viewer_request_event = {
            "Records": [
                {
                    "cf": {
                        "config": {
                            "distributionDomainName": "d123.cloudfront.net",
                            "distributionId": "EXAMPLE",
                            "eventType": "viewer-request",
                            "requestId": "MRVMF7KydIvxMWfJIglgwHQwZsbG2IhRJ07sn9AkKUFSHS9EXAMPLE=="
                        },
                        "request": {
                            "clientIp": "203.0.113.178",
                            "headers": {
                                "host": [
                                    {
                                        "key": "Host",
                                        "value": "d111111abcdef8.cloudfront.net"
                                    }
                                ],
                                "user-agent": [
                                    {
                                        "key": "User-Agent",
                                        "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                                    }
                                ]
                            },
                            "method": "GET",
                            "querystring": "",
                            "uri": "/test"
                        }
                    }
                }
            ]
        }
        
        mobile_request_event = {
            "Records": [
                {
                    "cf": {
                        "config": {
                            "distributionDomainName": "d123.cloudfront.net",
                            "distributionId": "EXAMPLE",
                            "eventType": "viewer-request",
                            "requestId": "MOBILE123KydIvxMWfJIglgwHQwZsbG2IhRJ07sn9AkKUFSHS9EXAMPLE=="
                        },
                        "request": {
                            "clientIp": "203.0.113.178",
                            "headers": {
                                "host": [
                                    {
                                        "key": "Host",
                                        "value": "d111111abcdef8.cloudfront.net"
                                    }
                                ],
                                "user-agent": [
                                    {
                                        "key": "User-Agent",
                                        "value": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) Mobile/15E148"
                                    }
                                ]
                            },
                            "method": "GET",
                            "querystring": "",
                            "uri": "/mobile-test"
                        }
                    }
                }
            ]
        }
        
        origin_response_event = {
            "Records": [
                {
                    "cf": {
                        "config": {
                            "distributionDomainName": "d123.cloudfront.net",
                            "distributionId": "EXAMPLE",
                            "eventType": "origin-response",
                            "requestId": "RESPONSE123KydIvxMWfJIglgwHQwZsbG2IhRJ07sn9AkKUFSHS9EXAMPLE=="
                        },
                        "request": {
                            "clientIp": "203.0.113.178",
                            "headers": {
                                "host": [
                                    {
                                        "key": "Host",
                                        "value": "example.com"
                                    }
                                ]
                            },
                            "method": "GET",
                            "querystring": "",
                            "uri": "/content"
                        },
                        "response": {
                            "status": "200",
                            "statusDescription": "OK",
                            "headers": {
                                "content-type": [
                                    {
                                        "key": "Content-Type",
                                        "value": "text/html; charset=UTF-8"
                                    }
                                ]
                            }
                        }
                    }
                }
            ]
        }
        
        return {
            "viewer-request": viewer_request_event,
            "mobile-request": mobile_request_event,
            "origin-response": origin_response_event
        }
    
    def verify_iam_role(self, role_name: str) -> Dict[str, Any]:
        """Verify that the IAM role for Lambda@Edge exists.
        
        Args:
            role_name: Name of the IAM role
            
        Returns:
            IAM role information
        """
        try:
            response = self.iam_client.get_role(RoleName=role_name)
            logger.info(f"IAM role {role_name} exists")
            return response
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchEntity':
                logger.error(f"IAM role {role_name} not found")
            raise
    
    def verify_s3_bucket(self, bucket_name: str) -> Dict[str, Any]:
        """Verify that the S3 bucket exists.
        
        Args:
            bucket_name: Name of the S3 bucket
            
        Returns:
            S3 bucket information
        """
        try:
            response = self.s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"S3 bucket {bucket_name} exists")
            return response
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.error(f"S3 bucket {bucket_name} not found")
            raise
    
    def verify_cloudwatch_log_group(self, log_group_name: str) -> Dict[str, Any]:
        """Verify that the CloudWatch log group exists.
        
        Args:
            log_group_name: Name of the log group
            
        Returns:
            CloudWatch log group information
        """
        try:
            response = self.logs_client.describe_log_groups(
                logGroupNamePrefix=log_group_name
            )
            
            if response['logGroups']:
                for log_group in response['logGroups']:
                    if log_group['logGroupName'] == log_group_name:
                        logger.info(f"CloudWatch log group {log_group_name} exists")
                        return log_group
            
            raise ClientError(
                {'Error': {'Code': 'ResourceNotFoundException'}},
                'describe_log_groups'
            )
            
        except ClientError as e:
            logger.error(f"CloudWatch log group {log_group_name} not found: {e}")
            raise
    
    def get_ssm_parameters(self, parameter_names: List[str]) -> Dict[str, str]:
        """Retrieve SSM parameters.
        
        Args:
            parameter_names: List of parameter names to retrieve
            
        Returns:
            Dictionary of parameter names and values
        """
        parameters = {}
        
        for name in parameter_names:
            try:
                response = self.ssm_client.get_parameter(
                    Name=name,
                    WithDecryption=True
                )
                parameters[name] = response['Parameter']['Value']
                logger.info(f"Retrieved SSM parameter: {name}")
                
            except ClientError as e:
                logger.error(f"Failed to retrieve SSM parameter {name}: {e}")
                raise
        
        return parameters