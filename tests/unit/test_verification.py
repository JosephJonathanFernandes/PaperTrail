from src.papertrail.core.scoring import calculate_confidence

def test_calculate_confidence_exact_match():
    metadata = {"title": "Attention Is All You Need", "authors": [{"family": "Vaswani"}]}
    result = calculate_confidence(None, "Attention Is All You Need", "Vaswani", metadata)
    assert result["score"] == 100
    assert result["tier"] == "HIGH"
    assert len(result["flags"]) == 0

def test_calculate_confidence_author_mismatch():
    metadata = {"title": "Attention Is All You Need", "authors": [{"family": "Vaswani"}]}
    result = calculate_confidence(None, "Attention Is All You Need", "Smith", metadata)
    assert result["score"] < 100
    assert any("Author mismatch" in flag for flag in result["flags"])

def test_calculate_confidence_title_drift():
    metadata = {"title": "Attention Is All You Need", "authors": [{"family": "Vaswani"}]}
    # A slightly off title should lower the score but not destroy it completely
    result = calculate_confidence(None, "Attention is what you need", "Vaswani", metadata)
    assert result["score"] < 100
    assert result["score"] > 50
    assert any("Title mismatch" in flag for flag in result["flags"])
