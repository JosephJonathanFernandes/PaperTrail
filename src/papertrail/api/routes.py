from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from src.papertrail.services.verification import run_stage_1_verification
from src.papertrail.services.search import run_stage_2_search
from src.papertrail.services.fallback import run_stage_3_fallback
from src.papertrail.config.settings import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize rate limiter using in-memory storage
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[Config.API_RATE_LIMIT],
    storage_uri="memory://"
)

# Configurable threshold for Stage 2 search results loaded from env
MIN_SCORE_THRESHOLD = Config.MIN_SCORE_THRESHOLD

@app.route('/find_paper', methods=['POST'])
@limiter.limit(Config.API_RATE_LIMIT)
def find_paper():
    data = request.json
    
    # Accept either a raw citation string, or structured title/author
    query = data.get('query')
    title = data.get('title')
    author = data.get('author')
    
    if not (query or (title and author)):
        return jsonify({"error": "Missing query or title/author parameters"}), 400
        
    # ==========================================
    # Stage 1: Verification & structured lookup
    # ==========================================
    # Verifies the paper exists and attempts to find a legal OA link via APIs
    verification_result = run_stage_1_verification(query, title, author)
    
    if not verification_result.get('verified'):
        return jsonify({
            "status": "unverified",
            "message": "Unverified/possibly fabricated citation."
        }), 404
        
    if verification_result.get('pdf_url'):
        return jsonify({
            "status": "success",
            "source": "api",
            "pdf_url": verification_result['pdf_url'],
            "metadata": verification_result['metadata']
        }), 200
        
    # ==========================================
    # Stage 2: Web search fallback
    # ==========================================
    # If no OA link was found, try a targeted web search
    search_results = run_stage_2_search(verification_result['metadata'])
    
    # Filter and pick the highest scoring result that passes the threshold
    valid_results = []
    for r in search_results:
        score = r.get('score', 0)
        if score >= MIN_SCORE_THRESHOLD:
            valid_results.append(r)
        else:
            logger.info(f"Rejected search candidate below threshold ({score} < {MIN_SCORE_THRESHOLD}): {r['url']}")
            
    if valid_results:
        # Assuming search_results is already sorted by score descending in run_stage_2_search
        best_match = valid_results[0]
        return jsonify({
            "status": "success",
            "source": "search",
            "pdf_url": best_match['url'],
            "metadata": verification_result['metadata'],
            "score": best_match['score']
        }), 200
        
    # ==========================================
    # Stage 3: No PDF found
    # ==========================================
    # Attempt to find alternative legal ways to access the paper
    fallback_options = run_stage_3_fallback(verification_result['metadata'])
    
    return jsonify({
        "status": "not_found",
        "message": "No free legal PDF found.",
        "metadata": verification_result['metadata'],
        "fallback_options": fallback_options
    }), 200

if __name__ == '__main__':
    app.run(debug=Config.DEBUG)
