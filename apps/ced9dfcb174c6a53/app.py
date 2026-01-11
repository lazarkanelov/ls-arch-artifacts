import boto3
import json
import os
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import csv
import io


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DocumentProcessingPipeline:
    """A document processing pipeline that handles file uploads and processing via S3 and Lambda."""
    
    def __init__(self, bucket_name: str, function_name: str = "process-s3-new-objects"):
        self.bucket_name = bucket_name
        self.function_name = function_name
        
        # Initialize AWS clients
        endpoint_url = os.environ.get('LOCALSTACK_ENDPOINT', 'http://localhost:4566')
        
        self.s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            region_name='us-east-1',
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )
        
        self.lambda_client = boto3.client(
            'lambda',
            endpoint_url=endpoint_url,
            region_name='us-east-1',
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )
        
        self.logs_client = boto3.client(
            'logs',
            endpoint_url=endpoint_url,
            region_name='us-east-1',
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )
    
    def upload_document(self, file_content: bytes, key: str, content_type: str = 'application/octet-stream') -> Dict[str, Any]:
        """Upload a document to S3, which will trigger Lambda processing."""
        try:
            response = self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=file_content,
                ContentType=content_type,
                Metadata={
                    'uploaded_at': datetime.utcnow().isoformat(),
                    'file_size': str(len(file_content)),
                    'processing_status': 'pending'
                }
            )
            
            logger.info(f"Successfully uploaded {key} to {self.bucket_name}")
            return {
                'success': True,
                'key': key,
                'etag': response.get('ETag'),
                'size': len(file_content)
            }
        except Exception as e:
            logger.error(f"Failed to upload {key}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def upload_csv_data(self, csv_content: str, filename: str) -> Dict[str, Any]:
        """Upload CSV data for processing."""
        key = f"data/csv/{filename}"
        return self.upload_document(
            csv_content.encode('utf-8'),
            key,
            'text/csv'
        )
    
    def upload_json_data(self, json_content: str, filename: str) -> Dict[str, Any]:
        """Upload JSON data for processing."""
        key = f"data/json/{filename}"
        return self.upload_document(
            json_content.encode('utf-8'),
            key,
            'application/json'
        )
    
    def upload_image(self, image_content: bytes, filename: str) -> Dict[str, Any]:
        """Upload image file for processing."""
        key = f"images/{filename}"
        return self.upload_document(
            image_content,
            key,
            'image/jpeg'
        )
    
    def list_processed_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        """List files in the S3 bucket with their metadata."""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            files = []
            for obj in response.get('Contents', []):
                # Get object metadata
                head_response = self.s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=obj['Key']
                )
                
                files.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'etag': obj['ETag'],
                    'content_type': head_response.get('ContentType'),
                    'metadata': head_response.get('Metadata', {})
                })
            
            return files
        except Exception as e:
            logger.error(f"Failed to list files: {str(e)}")
            return []
    
    def get_file_content(self, key: str) -> Optional[bytes]:
        """Retrieve file content from S3."""
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return response['Body'].read()
        except Exception as e:
            logger.error(f"Failed to get file {key}: {str(e)}")
            return None
    
    def wait_for_lambda_execution(self, timeout: int = 30) -> bool:
        """Wait for Lambda function to be executed by checking CloudWatch logs."""
        start_time = time.time()
        log_group_name = f"/aws/lambda/{self.function_name}"
        
        while time.time() - start_time < timeout:
            try:
                # Check if log group exists
                self.logs_client.describe_log_groups(
                    logGroupNamePrefix=log_group_name
                )
                
                # Get recent log streams
                streams_response = self.logs_client.describe_log_streams(
                    logGroupName=log_group_name,
                    orderBy='LastEventTime',
                    descending=True,
                    limit=5
                )
                
                if streams_response['logStreams']:
                    return True
                    
            except self.logs_client.exceptions.ResourceNotFoundException:
                pass  # Log group doesn't exist yet
            except Exception as e:
                logger.debug(f"Error checking logs: {str(e)}")
            
            time.sleep(2)
        
        return False
    
    def process_employee_data(self, csv_data: str) -> Dict[str, Any]:
        """Process employee CSV data through the pipeline."""
        # Upload the CSV file
        upload_result = self.upload_csv_data(csv_data, f"employees_{int(time.time())}.csv")
        
        if not upload_result['success']:
            return upload_result
        
        # Wait for processing
        processing_completed = self.wait_for_lambda_execution()
        
        # Parse CSV to provide summary
        reader = csv.DictReader(io.StringIO(csv_data))
        employees = list(reader)
        
        return {
            'success': True,
            'upload_key': upload_result['key'],
            'processing_triggered': processing_completed,
            'summary': {
                'total_employees': len(employees),
                'departments': list(set(emp.get('department', '') for emp in employees)),
                'avg_salary': sum(float(emp.get('salary', 0)) for emp in employees) / len(employees) if employees else 0
            }
        }
    
    def process_transaction_data(self, json_data: str) -> Dict[str, Any]:
        """Process transaction JSON data through the pipeline."""
        # Upload the JSON file
        upload_result = self.upload_json_data(json_data, f"transaction_{int(time.time())}.json")
        
        if not upload_result['success']:
            return upload_result
        
        # Wait for processing
        processing_completed = self.wait_for_lambda_execution()
        
        # Parse JSON to provide summary
        try:
            transaction = json.loads(json_data)
            return {
                'success': True,
                'upload_key': upload_result['key'],
                'processing_triggered': processing_completed,
                'summary': {
                    'transaction_id': transaction.get('transaction_id'),
                    'amount': transaction.get('amount'),
                    'currency': transaction.get('currency'),
                    'items_count': len(transaction.get('items', [])),
                    'timestamp': transaction.get('timestamp')
                }
            }
        except json.JSONDecodeError as e:
            return {
                'success': False,
                'error': f"Invalid JSON data: {str(e)}"
            }
    
    def process_image_batch(self, images: List[tuple]) -> Dict[str, Any]:
        """Process a batch of images through the pipeline."""
        results = []
        
        for image_content, filename in images:
            upload_result = self.upload_image(image_content, filename)
            results.append({
                'filename': filename,
                'upload_success': upload_result['success'],
                'size': len(image_content),
                'key': upload_result.get('key')
            })
        
        # Wait for processing
        processing_completed = self.wait_for_lambda_execution()
        
        return {
            'success': True,
            'batch_size': len(images),
            'processing_triggered': processing_completed,
            'results': results,
            'total_size': sum(len(img[0]) for img in images)
        }
    
    def get_processing_summary(self) -> Dict[str, Any]:
        """Get a summary of all processed files."""
        files = self.list_processed_files()
        
        summary = {
            'total_files': len(files),
            'total_size': sum(f['size'] for f in files),
            'file_types': {},
            'by_folder': {}
        }
        
        for file_info in files:
            # Count by content type
            content_type = file_info.get('content_type', 'unknown')
            summary['file_types'][content_type] = summary['file_types'].get(content_type, 0) + 1
            
            # Count by folder
            folder = file_info['key'].split('/')[0] if '/' in file_info['key'] else 'root'
            summary['by_folder'][folder] = summary['by_folder'].get(folder, 0) + 1
        
        return summary
    
    def cleanup_test_data(self, prefix: str = "") -> Dict[str, Any]:
        """Clean up test data from S3 bucket."""
        try:
            files = self.list_processed_files(prefix)
            deleted_count = 0
            
            for file_info in files:
                self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=file_info['key']
                )
                deleted_count += 1
            
            return {
                'success': True,
                'deleted_files': deleted_count
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }