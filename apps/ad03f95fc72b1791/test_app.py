import pytest
import json
import time
from typing import Dict, Any
from decimal import Decimal
from app import MovieCatalogService

class TestMovieCatalogService:
    """Integration tests for the Movie Catalog Service."""
    
    @pytest.fixture(autouse=True)
    def setup(self, localstack_endpoint, sample_movies):
        """Setup test instance and data."""
        self.service = MovieCatalogService(localstack_endpoint)
        self.sample_movies = sample_movies
        
        # Small delay to ensure infrastructure is ready
        time.sleep(2)
    
    def test_infrastructure_health_check(self):
        """Test that all infrastructure components are healthy and accessible."""
        health = self.service.health_check()
        
        assert health['dynamodb'] is True, "DynamoDB table should be accessible"
        assert health['api_gateway'] is True, "API Gateway should be accessible"
        assert health['lambda'] is True, "Lambda function should be accessible"
    
    def test_discover_api_endpoint(self):
        """Test API Gateway endpoint discovery."""
        endpoint = self.service.discover_api_endpoint()
        
        assert endpoint is not None, "Should discover API endpoint"
        assert 'movies' in endpoint, "Endpoint should contain movies path"
        assert self.service.api_endpoint == endpoint, "Should set instance endpoint"
    
    def test_add_single_movie_via_api(self):
        """Test adding a single movie through API Gateway."""
        movie = self.sample_movies[0].copy()
        
        # Add movie via API
        result = self.service.add_movie_via_api(movie)
        
        assert result is not None, "Should return response"
        assert 'message' in result or 'statusCode' in result, "Should have valid response structure"
        
        # Verify movie was stored in DynamoDB
        stored_movie = self.service.get_movie_from_db(movie['year'], movie['title'])
        assert stored_movie is not None, "Movie should be stored in database"
        assert stored_movie['year'] == movie['year'], "Year should match"
        assert stored_movie['title'] == movie['title'], "Title should match"
        assert stored_movie['info']['genre'] == movie['info']['genre'], "Genre should match"
    
    def test_bulk_movie_import(self):
        """Test bulk importing multiple movies."""
        results = self.service.bulk_import_movies(self.sample_movies)
        
        assert results['success'] == len(self.sample_movies), f"Should import all {len(self.sample_movies)} movies successfully"
        assert results['failed'] == 0, "Should have no failures"
        assert len(results['errors']) == 0, "Should have no errors"
        
        # Verify all movies are in database
        for movie in self.sample_movies:
            stored_movie = self.service.get_movie_from_db(movie['year'], movie['title'])
            assert stored_movie is not None, f"Movie {movie['title']} should be stored"
    
    def test_movie_retrieval_and_querying(self):
        """Test retrieving and querying movies from the database."""
        # First, import test data
        self.service.bulk_import_movies(self.sample_movies)
        
        # Test getting movies by year
        movies_2023 = self.service.get_movies_by_year(2023)
        assert len(movies_2023) > 0, "Should find movies from 2023"
        assert all(movie['year'] == 2023 for movie in movies_2023), "All movies should be from 2023"
        
        # Test getting specific movie
        specific_movie = self.service.get_movie_from_db(2022, "Comedy Night")
        assert specific_movie is not None, "Should find specific movie"
        assert specific_movie['info']['genre'] == "Comedy", "Genre should match"
    
    def test_movie_rating_update(self):
        """Test updating movie ratings."""
        # Import a movie first
        movie = self.sample_movies[0].copy()
        self.service.add_movie_via_api(movie)
        
        # Update rating
        new_rating = 9.5
        success = self.service.update_movie_rating(movie['year'], movie['title'], new_rating)
        assert success is True, "Rating update should succeed"
        
        # Verify update
        updated_movie = self.service.get_movie_from_db(movie['year'], movie['title'])
        assert updated_movie is not None, "Updated movie should exist"
        assert abs(updated_movie['info']['rating'] - new_rating) < 0.01, "Rating should be updated"
    
    def test_top_rated_movies_filtering(self):
        """Test filtering movies by rating threshold."""
        # Import all test movies
        self.service.bulk_import_movies(self.sample_movies)
        
        # Get top-rated movies (rating >= 8.0)
        top_movies = self.service.get_top_rated_movies(min_rating=8.0)
        
        assert len(top_movies) > 0, "Should find top-rated movies"
        for movie in top_movies:
            rating = movie['info']['rating']
            assert rating >= 8.0, f"Movie {movie['title']} rating {rating} should be >= 8.0"
        
        # Verify sorting (highest rating first)
        if len(top_movies) > 1:
            for i in range(len(top_movies) - 1):
                current_rating = top_movies[i]['info']['rating']
                next_rating = top_movies[i + 1]['info']['rating']
                assert current_rating >= next_rating, "Movies should be sorted by rating descending"
    
    def test_movie_statistics_calculation(self):
        """Test calculation of movie collection statistics."""
        # Import test movies
        self.service.bulk_import_movies(self.sample_movies)
        
        stats = self.service.get_movie_statistics()
        
        assert stats['total_movies'] == len(self.sample_movies), "Total count should match imported movies"
        assert stats['average_rating'] > 0, "Average rating should be calculated"
        assert isinstance(stats['genres'], dict), "Genres should be a dictionary"
        assert isinstance(stats['years'], dict), "Years should be a dictionary"
        
        # Verify genre distribution
        expected_genres = {movie['info']['genre'] for movie in self.sample_movies}
        actual_genres = set(stats['genres'].keys())
        assert expected_genres.issubset(actual_genres), "All genres should be represented"
        
        # Verify year distribution
        expected_years = {str(movie['year']) for movie in self.sample_movies}
        actual_years = set(stats['years'].keys())
        assert expected_years.issubset(actual_years), "All years should be represented"
    
    def test_error_handling_invalid_movie_data(self):
        """Test error handling with invalid movie data."""
        # Test missing required fields
        invalid_movie = {"title": "Incomplete Movie"}
        
        with pytest.raises(Exception):
            self.service.add_movie_via_api(invalid_movie)
        
        # Test invalid year type
        invalid_movie2 = {
            "year": "not_a_number",
            "title": "Bad Year Movie",
            "info": {"genre": "Drama"}
        }
        
        with pytest.raises(Exception):
            self.service.add_movie_via_api(invalid_movie2)
    
    def test_movie_schema_validation(self):
        """Test movie data schema validation."""
        # Valid movie should pass
        valid_movie = self.sample_movies[0]
        assert self.service.validate_movie_schema(valid_movie) is True
        
        # Invalid movies should fail
        invalid_cases = [
            {"title": "Missing Year", "info": {}},  # Missing year
            {"year": 2023, "info": {}},  # Missing title
            {"year": 2023, "title": "Missing Info"},  # Missing info
            {"year": "2023", "title": "Bad Year", "info": {}},  # Wrong year type
            {"year": 2023, "title": "", "info": {}},  # Empty title
            {"year": 2023, "title": "Bad Info", "info": "not_dict"},  # Wrong info type
        ]
        
        for invalid_movie in invalid_cases:
            with pytest.raises(ValueError):
                self.service.validate_movie_schema(invalid_movie)
    
    def test_duplicate_movie_handling(self):
        """Test handling of duplicate movie entries."""
        movie = self.sample_movies[0].copy()
        
        # Add movie first time
        result1 = self.service.add_movie_via_api(movie)
        assert result1 is not None
        
        # Add same movie again (should update or handle gracefully)
        movie['info']['rating'] = 9.9  # Modify rating
        result2 = self.service.add_movie_via_api(movie)
        assert result2 is not None
        
        # Verify movie exists with updated data
        stored_movie = self.service.get_movie_from_db(movie['year'], movie['title'])
        assert stored_movie is not None
        assert abs(stored_movie['info']['rating'] - 9.9) < 0.01, "Should have updated rating"
    
    def test_empty_database_statistics(self):
        """Test statistics calculation on empty database."""
        stats = self.service.get_movie_statistics()
        
        assert stats['total_movies'] == 0, "Empty database should have zero movies"
        assert stats['average_rating'] == 0, "Empty database should have zero average rating"
        assert stats['genres'] == {}, "Empty database should have no genres"
        assert stats['years'] == {}, "Empty database should have no years"
    
    def test_nonexistent_movie_retrieval(self):
        """Test retrieving movies that don't exist."""
        # Try to get a movie that doesn't exist
        movie = self.service.get_movie_from_db(1999, "Nonexistent Movie")
        assert movie is None, "Should return None for nonexistent movie"
        
        # Try to get movies for a year with no movies
        movies = self.service.get_movies_by_year(1900)
        assert len(movies) == 0, "Should return empty list for year with no movies"