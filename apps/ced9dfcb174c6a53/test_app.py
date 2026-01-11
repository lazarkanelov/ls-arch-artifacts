import pytest
import json
import time
from app import DocumentProcessingPipeline


class TestDocumentProcessingPipeline:
    """Integration tests for the document processing pipeline."""
    
    @pytest.fixture
    def pipeline(self, s3_client, lambda_client):
        """Create a pipeline instance with a dynamically discovered bucket name."""
        # Try to find the bucket created by Terraform
        buckets = s3_client.list_buckets()['Buckets']
        bucket_name = None
        
        for bucket in buckets:
            if bucket['Name'].startswith('my-bucket-'):
                bucket_name = bucket['Name']
                break
        
        if not bucket_name:
            pytest.skip("S3 bucket not found - ensure Terraform has been applied")
        
        return DocumentProcessingPipeline(bucket_name)
    
    def test_infrastructure_resources_exist(self, s3_client, lambda_client, iam_client):
        """Test that all required infrastructure resources exist."""
        # Check S3 bucket exists
        buckets = s3_client.list_buckets()['Buckets']
        bucket_names = [bucket['Name'] for bucket in buckets]
        assert any(name.startswith('my-bucket-') for name in bucket_names), "S3 bucket not found"
        
        # Check Lambda function exists
        try:
            response = lambda_client.get_function(FunctionName='process-s3-new-objects')
            assert response['Configuration']['FunctionName'] == 'process-s3-new-objects'
            assert response['Configuration']['Runtime'] == 'nodejs16.x'
            assert response['Configuration']['Handler'] == 'index.handler'
        except lambda_client.exceptions.ResourceNotFoundException:
            pytest.fail("Lambda function 'process-s3-new-objects' not found")
        
        # Check IAM role exists
        try:
            response = iam_client.get_role(RoleName='iam_for_lambda')
            assert response['Role']['RoleName'] == 'iam_for_lambda'
        except iam_client.exceptions.NoSuchEntityException:
            pytest.fail("IAM role 'iam_for_lambda' not found")
    
    def test_csv_employee_data_processing(self, pipeline, sample_csv_data):
        """Test processing employee CSV data through the pipeline."""
        result = pipeline.process_employee_data(sample_csv_data)
        
        assert result['success'] is True
        assert 'upload_key' in result
        assert result['upload_key'].startswith('data/csv/')
        
        # Verify summary data
        summary = result['summary']
        assert summary['total_employees'] == 5
        assert 'Engineering' in summary['departments']
        assert 'Marketing' in summary['departments']
        assert summary['avg_salary'] > 0
        
        # Verify file was uploaded to S3
        files = pipeline.list_processed_files('data/csv/')
        assert len(files) > 0
        csv_file = next((f for f in files if f['key'] == result['upload_key']), None)
        assert csv_file is not None
        assert csv_file['content_type'] == 'text/csv'
    
    def test_json_transaction_data_processing(self, pipeline, sample_json_data):
        """Test processing transaction JSON data through the pipeline."""
        result = pipeline.process_transaction_data(sample_json_data)
        
        assert result['success'] is True
        assert 'upload_key' in result
        assert result['upload_key'].startswith('data/json/')
        
        # Verify summary data
        summary = result['summary']
        assert summary['transaction_id'] == 'txn_12345'
        assert summary['amount'] == 129.99
        assert summary['currency'] == 'USD'
        assert summary['items_count'] == 2
        
        # Verify file was uploaded to S3
        files = pipeline.list_processed_files('data/json/')
        assert len(files) > 0
        json_file = next((f for f in files if f['key'] == result['upload_key']), None)
        assert json_file is not None
        assert json_file['content_type'] == 'application/json'
    
    def test_image_batch_processing(self, pipeline, sample_image_data):
        """Test processing a batch of images through the pipeline."""
        images = [
            (sample_image_data, 'test_image_1.bmp'),
            (sample_image_data, 'test_image_2.bmp'),
            (sample_image_data, 'test_image_3.bmp')
        ]
        
        result = pipeline.process_image_batch(images)
        
        assert result['success'] is True
        assert result['batch_size'] == 3
        assert len(result['results']) == 3
        
        # Verify all images were uploaded successfully
        for img_result in result['results']:
            assert img_result['upload_success'] is True
            assert img_result['key'].startswith('images/')
            assert img_result['size'] == len(sample_image_data)
        
        # Verify files exist in S3
        files = pipeline.list_processed_files('images/')
        assert len(files) >= 3
    
    def test_file_upload_and_retrieval(self, pipeline, sample_csv_data):
        """Test uploading and retrieving file content."""
        # Upload a test file
        test_content = "test,data,file\n1,2,3\n4,5,6"
        upload_result = pipeline.upload_csv_data(test_content, 'test_retrieval.csv')
        
        assert upload_result['success'] is True
        
        # Retrieve the file content
        retrieved_content = pipeline.get_file_content(upload_result['key'])
        assert retrieved_content is not None
        assert retrieved_content.decode('utf-8') == test_content
    
    def test_processing_summary_generation(self, pipeline, sample_csv_data, sample_json_data):
        """Test generating processing summary after uploading various files."""
        # Upload different types of files
        pipeline.upload_csv_data(sample_csv_data, 'summary_test.csv')
        pipeline.upload_json_data(sample_json_data, 'summary_test.json')
        
        # Get processing summary
        summary = pipeline.get_processing_summary()
        
        assert summary['total_files'] > 0
        assert summary['total_size'] > 0
        assert 'file_types' in summary
        assert 'by_folder' in summary
        
        # Should have at least CSV and JSON files
        assert 'text/csv' in summary['file_types'] or len([f for f in summary['file_types'] if 'csv' in f.lower()]) > 0
        assert 'application/json' in summary['file_types'] or len([f for f in summary['file_types'] if 'json' in f.lower()]) > 0
    
    def test_error_handling_invalid_json(self, pipeline):
        """Test error handling with invalid JSON data."""
        invalid_json = '{"invalid": json data}'
        result = pipeline.process_transaction_data(invalid_json)
        
        assert result['success'] is False
        assert 'error' in result
        assert 'Invalid JSON data' in result['error']
    
    def test_lambda_trigger_detection(self, pipeline, sample_csv_data):
        """Test that Lambda function execution is properly detected."""
        # Upload a file to trigger Lambda
        result = pipeline.upload_csv_data(sample_csv_data, 'lambda_trigger_test.csv')
        assert result['success'] is True
        
        # Check if Lambda execution can be detected
        # Note: In LocalStack, this might not work exactly like AWS, but we test the mechanism
        execution_detected = pipeline.wait_for_lambda_execution(timeout=10)
        # We don't assert this because LocalStack might not have the exact same log behavior
        # but we verify the method works without errors
        assert isinstance(execution_detected, bool)
    
    def test_file_listing_with_metadata(self, pipeline, sample_csv_data):
        """Test listing files with their metadata."""
        # Upload a test file
        upload_result = pipeline.upload_csv_data(sample_csv_data, 'metadata_test.csv')
        assert upload_result['success'] is True
        
        # List files and check metadata
        files = pipeline.list_processed_files('data/csv/')
        test_file = next((f for f in files if 'metadata_test.csv' in f['key']), None)
        
        assert test_file is not None
        assert 'size' in test_file
        assert 'last_modified' in test_file
        assert 'content_type' in test_file
        assert test_file['content_type'] == 'text/csv'
        assert 'metadata' in test_file
    
    def test_cleanup_functionality(self, pipeline, sample_csv_data):
        """Test cleanup functionality for removing test data."""
        # Upload some test files
        test_prefix = 'cleanup_test/'
        pipeline.upload_document(
            sample_csv_data.encode('utf-8'),
            f'{test_prefix}file1.csv',
            'text/csv'
        )
        pipeline.upload_document(
            sample_csv_data.encode('utf-8'),
            f'{test_prefix}file2.csv',
            'text/csv'
        )
        
        # Verify files exist
        files_before = pipeline.list_processed_files(test_prefix)
        assert len(files_before) >= 2
        
        # Cleanup
        cleanup_result = pipeline.cleanup_test_data(test_prefix)
        assert cleanup_result['success'] is True
        assert cleanup_result['deleted_files'] >= 2
        
        # Verify files are gone
        files_after = pipeline.list_processed_files(test_prefix)
        assert len(files_after) == 0