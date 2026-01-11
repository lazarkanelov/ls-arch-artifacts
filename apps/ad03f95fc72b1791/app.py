import json
import logging
import requests
import boto3
import os
from typing import Dict, Any, List, Optional
from decimal import Decimal
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MovieCatalogService:
    """A movie catalog service that manages movies via API Gateway and DynamoDB."""
    
    def __init__(self, localstack_endpoint: str = None):
        self.endpoint_url = localstack_endpoint or os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
        self.region = "us-east-1"
        
        # Initialize AWS clients
        self.dynamodb = boto3.resource(
            "dynamodb",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.apigateway = boto3.client(
            "apigatewayv2",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.lambda_client = boto3.client(
            "lambda",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.table_name = "Movies"
        self.api_endpoint = None
        
    def discover_api_endpoint(self) -> str:
        """Discover the API Gateway endpoint dynamically."""
        try:
            # List APIs to find the one with the expected name pattern
            response = self.apigateway.get_apis()
            
            for api in response.get('Items', []):
                if 'apigw-http-lambda' in api['Name']:
                    api_id = api['ApiId']
                    # Construct the endpoint URL
                    self.api_endpoint = f"{self.endpoint_url.rstrip('/')}/{api_id}/movies"
                    logger.info(f"Discovered API endpoint: {self.api_endpoint}")
                    return self.api_endpoint
            
            raise ValueError("API Gateway not found")
            
        except Exception as e:
            logger.error(f"Error discovering API endpoint: {str(e)}")
            raise
    
    def add_movie_via_api(self, movie_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a movie through the API Gateway endpoint."""
        if not self.api_endpoint:
            self.discover_api_endpoint()
        
        try:
            # Convert any Decimal values to float for JSON serialization
            json_data = json.loads(json.dumps(movie_data, default=self._decimal_converter))
            
            response = requests.post(
                self.api_endpoint,
                json=json_data,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            logger.info(f"API Response Status: {response.status_code}")
            logger.info(f"API Response Body: {response.text}")
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"API request failed with status {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"Error adding movie via API: {str(e)}")
            raise
    
    def get_movie_from_db(self, year: int, title: str) -> Optional[Dict[str, Any]]:
        """Retrieve a movie directly from DynamoDB."""
        try:
            table = self.dynamodb.Table(self.table_name)
            response = table.get_item(
                Key={
                    'year': year,
                    'title': title
                }
            )
            
            item = response.get('Item')
            if item:
                # Convert Decimal values to float for easier handling
                return json.loads(json.dumps(item, default=self._decimal_converter))
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving movie from DB: {str(e)}")
            raise
    
    def get_movies_by_year(self, year: int) -> List[Dict[str, Any]]:
        """Get all movies for a specific year."""
        try:
            table = self.dynamodb.Table(self.table_name)
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('year').eq(year)
            )
            
            items = response.get('Items', [])
            return [json.loads(json.dumps(item, default=self._decimal_converter)) for item in items]
            
        except Exception as e:
            logger.error(f"Error getting movies by year: {str(e)}")
            raise
    
    def update_movie_rating(self, year: int, title: str, new_rating: float) -> bool:
        """Update a movie's rating."""
        try:
            table = self.dynamodb.Table(self.table_name)
            
            response = table.update_item(
                Key={
                    'year': year,
                    'title': title
                },
                UpdateExpression="SET info.rating = :rating",
                ExpressionAttributeValues={
                    ':rating': Decimal(str(new_rating))
                },
                ReturnValues="UPDATED_NEW"
            )
            
            return 'Attributes' in response
            
        except Exception as e:
            logger.error(f"Error updating movie rating: {str(e)}")
            raise
    
    def bulk_import_movies(self, movies: List[Dict[str, Any]]) -> Dict[str, int]:
        """Bulk import multiple movies via API."""
        results = {
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        for movie in movies:
            try:
                self.add_movie_via_api(movie)
                results['success'] += 1
                logger.info(f"Successfully imported: {movie['title']} ({movie['year']})")
            except Exception as e:
                results['failed'] += 1
                error_msg = f"Failed to import {movie['title']} ({movie['year']}): {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        return results
    
    def get_top_rated_movies(self, min_rating: float = 8.0) -> List[Dict[str, Any]]:
        """Get all movies with rating above the threshold."""
        try:
            table = self.dynamodb.Table(self.table_name)
            response = table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('info.rating').gte(Decimal(str(min_rating)))
            )
            
            items = response.get('Items', [])
            # Sort by rating descending
            sorted_items = sorted(items, key=lambda x: float(x.get('info', {}).get('rating', 0)), reverse=True)
            
            return [json.loads(json.dumps(item, default=self._decimal_converter)) for item in sorted_items]
            
        except Exception as e:
            logger.error(f"Error getting top rated movies: {str(e)}")
            raise
    
    def validate_movie_schema(self, movie_data: Dict[str, Any]) -> bool:
        """Validate movie data structure."""
        required_fields = ['year', 'title', 'info']
        
        for field in required_fields:
            if field not in movie_data:
                raise ValueError(f"Missing required field: {field}")
        
        if not isinstance(movie_data['year'], int):
            raise ValueError("Year must be an integer")
            
        if not isinstance(movie_data['title'], str) or not movie_data['title'].strip():
            raise ValueError("Title must be a non-empty string")
            
        if not isinstance(movie_data['info'], dict):
            raise ValueError("Info must be a dictionary")
        
        return True
    
    def get_movie_statistics(self) -> Dict[str, Any]:
        """Get statistics about the movie collection."""
        try:
            table = self.dynamodb.Table(self.table_name)
            response = table.scan()
            
            items = response.get('Items', [])
            
            if not items:
                return {
                    'total_movies': 0,
                    'average_rating': 0,
                    'genres': {},
                    'years': {}
                }
            
            total_movies = len(items)
            ratings = []
            genres = {}
            years = {}
            
            for item in items:
                # Extract rating
                rating = item.get('info', {}).get('rating')
                if rating:
                    ratings.append(float(rating))
                
                # Extract genre
                genre = item.get('info', {}).get('genre')
                if genre:
                    genres[genre] = genres.get(genre, 0) + 1
                
                # Extract year
                year = item.get('year')
                if year:
                    years[str(year)] = years.get(str(year), 0) + 1
            
            avg_rating = sum(ratings) / len(ratings) if ratings else 0
            
            return {
                'total_movies': total_movies,
                'average_rating': round(avg_rating, 2),
                'genres': genres,
                'years': years
            }
            
        except Exception as e:
            logger.error(f"Error getting movie statistics: {str(e)}")
            raise
    
    def _decimal_converter(self, obj):
        """Convert Decimal objects to float for JSON serialization."""
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def health_check(self) -> Dict[str, bool]:
        """Check the health of all components."""
        health = {
            'dynamodb': False,
            'api_gateway': False,
            'lambda': False
        }
        
        # Check DynamoDB
        try:
            table = self.dynamodb.Table(self.table_name)
            table.table_status
            health['dynamodb'] = True
        except Exception:
            pass
        
        # Check API Gateway
        try:
            self.discover_api_endpoint()
            health['api_gateway'] = True
        except Exception:
            pass
        
        # Check Lambda (by trying to list functions)
        try:
            response = self.lambda_client.list_functions()
            lambda_functions = [f for f in response.get('Functions', []) if 'pattern-movies-post' in f['FunctionName']]
            health['lambda'] = len(lambda_functions) > 0
        except Exception:
            pass
        
        return health