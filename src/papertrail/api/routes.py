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
            "message": "Unverified/possibly fabricated citation.",
            "confidence_tier": "NONE"
        }), 404
        
    if verification_result.get('open_access_pdf'):
        return jsonify({
            "status": "success",
            "source": "api",
            "pdf_url": verification_result['open_access_pdf'],
            "metadata": verification_result['metadata'],
            "confidence_score": verification_result['confidence_score'],
            "confidence_tier": verification_result['confidence_tier'],
            "flags": verification_result['flags']
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
            "confidence_score": verification_result['confidence_score'],
            "confidence_tier": "LOW",
            "flags": verification_result['flags'] + ["Sourced via web search, not canonical API."]
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
        "fallback_options": fallback_options,
        "confidence_score": verification_result['confidence_score'],
        "confidence_tier": "FALLBACK",
        "flags": verification_result['flags']
    }), 200

@app.route('/find_papers_batch', methods=['POST'])
@limiter.limit(Config.API_RATE_LIMIT)
def find_papers_batch():
    """
    Batch endpoint that takes a list of citation strings.
    Only runs Stage 1 (API Verification) to prevent DuckDuckGo rate limiting.
    """
    data = request.json
    citations = data.get('citations', [])
    
    if not citations or not isinstance(citations, list):
        return jsonify({"error": "Please provide a list of citation strings in the 'citations' field."}), 400
        
    results = []
    for citation in citations:
        verification = run_stage_1_verification(query=citation)
        if not verification.get('verified'):
            results.append({
                "query": citation,
                "status": "unverified",
                "confidence_tier": "NONE"
            })
        else:
            results.append({
                "query": citation,
                "status": "success" if verification.get("open_access_pdf") else "not_found",
                "pdf_url": verification.get("open_access_pdf"),
                "confidence_score": verification.get("confidence_score"),
                "confidence_tier": verification.get("confidence_tier"),
                "flags": verification.get("flags"),
                "metadata": verification.get("metadata")
            })
            
    return jsonify({"results": results}), 200

if __name__ == '__main__':
    app.run(debug=Config.DEBUG)
