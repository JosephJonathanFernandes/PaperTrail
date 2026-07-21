import pytest
from src.papertrail.api.routes import app
from unittest.mock import patch

@pytest.fixture(autouse=True)
def disable_rate_limiting():
    # Patch the actual limiter check to always pass during tests
    with patch('flask_limiter.Limiter._check_request_limit'):
        yield
