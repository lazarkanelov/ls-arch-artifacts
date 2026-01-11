import json
import boto3
import requests
import os
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class User:
    """User data model for registration system."""
    email: str
    name: str
    company: str
    role: str
    registration_id: str = None
    timestamp: str = None
    
    def __post_init__(self):
        if not self.registration_id:
            self.registration_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

class UserRegistrationService:
    """Service for handling user registrations through API Gateway and Lambda."""
    
    def __init__(self, api_endpoint: str, localstack_endpoint: str = None):
        self.api_endpoint = api_endpoint.rstrip('/')
        self.localstack_endpoint = localstack_endpoint or os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
        
        # Initialize AWS clients
        self.lambda_client = boto3.client(
            "lambda",
            endpoint_url=self.localstack_endpoint,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.localstack_endpoint,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.logs_client = boto3.client(
            "logs",
            endpoint_url=self.localstack_endpoint,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
    
    def register_user(self, user_data: Dict[str, str]) -> Dict[str, Any]:
        """Register a new user through the API Gateway endpoint."""
        user = User(**user_data)
        
        payload = {
            "action": "register",
            "user": asdict(user)
        }
        
        try:
            response = requests.post(
                f"{self.api_endpoint}/register",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"User registered successfully: {user.email}")
                return result
            else:
                logger.error(f"Registration failed: {response.status_code} - {response.text}")
                raise Exception(f"Registration failed with status {response.status_code}")
                
        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise
    
    def get_user(self, registration_id: str) -> Dict[str, Any]:
        """Retrieve user information by registration ID."""
        try:
            response = requests.get(
                f"{self.api_endpoint}/user/{registration_id}",
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                raise Exception(f"Failed to retrieve user with status {response.status_code}")
                
        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise
    
    def list_registrations(self, company: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all registrations, optionally filtered by company."""
        params = {}
        if company:
            params['company'] = company
            
        try:
            response = requests.get(
                f"{self.api_endpoint}/registrations",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get('registrations', [])
            else:
                raise Exception(f"Failed to list registrations with status {response.status_code}")
                
        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise
    
    def update_user_role(self, registration_id: str, new_role: str) -> Dict[str, Any]:
        """Update a user's role."""
        payload = {
            "action": "update_role",
            "registration_id": registration_id,
            "new_role": new_role
        }
        
        try:
            response = requests.put(
                f"{self.api_endpoint}/user/{registration_id}/role",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Role update failed with status {response.status_code}")
                
        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise
    
    def delete_registration(self, registration_id: str) -> bool:
        """Delete a user registration."""
        try:
            response = requests.delete(
                f"{self.api_endpoint}/user/{registration_id}",
                timeout=30
            )
            
            return response.status_code == 200
                
        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise
    
    def get_registration_analytics(self) -> Dict[str, Any]:
        """Get analytics about registrations."""
        try:
            response = requests.get(
                f"{self.api_endpoint}/analytics",
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Analytics request failed with status {response.status_code}")
                
        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise
    
    def invoke_lambda_directly(self, function_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Directly invoke the Lambda function for testing purposes."""
        try:
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            result = json.loads(response['Payload'].read().decode())
            logger.info(f"Lambda invoked successfully: {function_name}")
            return result
            
        except Exception as e:
            logger.error(f"Lambda invocation failed: {str(e)}")
            raise
    
    def check_s3_registration_backup(self, bucket_name: str) -> List[str]:
        """Check if registration backups are being stored in S3."""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix='registrations/'
            )
            
            if 'Contents' in response:
                return [obj['Key'] for obj in response['Contents']]
            else:
                return []
                
        except Exception as e:
            logger.error(f"S3 check failed: {str(e)}")
            raise
    
    def get_lambda_logs(self, log_group: str, hours_back: int = 1) -> List[Dict[str, Any]]:
        """Retrieve recent Lambda logs for debugging."""
        try:
            # Calculate time range
            end_time = int(time.time() * 1000)
            start_time = end_time - (hours_back * 3600 * 1000)
            
            response = self.logs_client.filter_log_events(
                logGroupName=log_group,
                startTime=start_time,
                endTime=end_time
            )
            
            events = []
            for event in response.get('events', []):
                events.append({
                    'timestamp': datetime.fromtimestamp(event['timestamp'] / 1000).isoformat(),
                    'message': event['message'].strip()
                })
            
            return events
            
        except Exception as e:
            logger.error(f"Log retrieval failed: {str(e)}")
            return []
    
    def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the API."""
        try:
            response = requests.get(
                f"{self.api_endpoint}/health",
                timeout=10
            )
            
            return {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'status_code': response.status_code,
                'response_time_ms': response.elapsed.total_seconds() * 1000,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def bulk_register_users(self, users: List[Dict[str, str]]) -> Dict[str, Any]:
        """Register multiple users in a batch operation."""
        results = {
            'successful': [],
            'failed': [],
            'total_processed': len(users)
        }
        
        for user_data in users:
            try:
                result = self.register_user(user_data)
                results['successful'].append({
                    'email': user_data['email'],
                    'registration_id': result.get('registration_id')
                })
            except Exception as e:
                results['failed'].append({
                    'email': user_data['email'],
                    'error': str(e)
                })
        
        results['success_rate'] = len(results['successful']) / len(users) if users else 0
        return results