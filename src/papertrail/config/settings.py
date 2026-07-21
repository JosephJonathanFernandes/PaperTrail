import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

class Config:
    """Application configuration settings."""
    # Used for querying the Unpaywall API
    UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL", "default@example.com")
    
    # Threshold for Stage 2 search candidates
    MIN_SCORE_THRESHOLD = int(os.getenv("MIN_SCORE_THRESHOLD", "50"))
    
    # API Rate Limit (e.g. '10/minute', '5/second')
    API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/minute")
    
    # Environment settings
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "t")
