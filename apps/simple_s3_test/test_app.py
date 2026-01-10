"""Tests for simple S3 infrastructure."""
import pytest


def test_s3_bucket_exists(s3_client):
    """Test that at least one S3 bucket exists after terraform apply."""
    response = s3_client.list_buckets()
    buckets = response.get("Buckets", [])
    assert len(buckets) >= 1, "Expected at least one S3 bucket"
    
    # Check that our test bucket exists (starts with lsqm-test-bucket)
    bucket_names = [b["Name"] for b in buckets]
    test_buckets = [name for name in bucket_names if name.startswith("lsqm-test-bucket")]
    assert len(test_buckets) >= 1, f"Expected test bucket, found: {bucket_names}"


def test_s3_put_and_get_object(s3_client):
    """Test that we can put and get objects from the bucket."""
    response = s3_client.list_buckets()
    buckets = response.get("Buckets", [])
    
    # Find our test bucket
    bucket_names = [b["Name"] for b in buckets]
    test_bucket = next((name for name in bucket_names if name.startswith("lsqm-test-bucket")), None)
    
    if test_bucket is None:
        pytest.skip("No test bucket found")
    
    # Put an object
    test_content = "Hello from LSQM test!"
    s3_client.put_object(
        Bucket=test_bucket,
        Key="test-object.txt",
        Body=test_content.encode()
    )
    
    # Get the object back
    response = s3_client.get_object(Bucket=test_bucket, Key="test-object.txt")
    retrieved_content = response["Body"].read().decode("utf-8")
    
    assert retrieved_content == test_content


def test_s3_list_objects(s3_client):
    """Test that we can list objects in the bucket."""
    response = s3_client.list_buckets()
    buckets = response.get("Buckets", [])
    
    bucket_names = [b["Name"] for b in buckets]
    test_bucket = next((name for name in bucket_names if name.startswith("lsqm-test-bucket")), None)
    
    if test_bucket is None:
        pytest.skip("No test bucket found")
    
    # List objects
    response = s3_client.list_objects_v2(Bucket=test_bucket)
    # Should work without error
    assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
