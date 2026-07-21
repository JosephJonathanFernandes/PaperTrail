import pytest
import responses
from src.papertrail.core.scoring import is_shadow_library, score_candidate
from src.papertrail.services.search import resolve_redirect

def test_38_exactmatch_blocklist_domain_scihubse():
    assert is_shadow_library("https://sci-hub.se/paper") == True
    assert score_candidate("https://sci-hub.se/paper", "Title", "Author", "Title", "Snippet") == -1

def test_39_regexmatched_mirror_scihubst_scihubru():
    assert is_shadow_library("https://sci-hub.st/123") == True
    assert is_shadow_library("http://sci-hub.ru/123") == True
    assert is_shadow_library("https://libgen.rs/book") == True
    assert is_shadow_library("https://libgen.li/book") == True

def test_40_case_variation_scihubse_scihubse():
    assert is_shadow_library("HTTPS://SCI-HUB.SE/PAPER") == True
    assert is_shadow_library("Http://LibGen.Is") == True

def test_41_blocklist_domain_with_trailing_slash__query_params():
    assert is_shadow_library("https://sci-hub.se/?q=123&v=4#frag") == True
    assert is_shadow_library("https://libgen.is/#foo") == True

def test_42_substring_false_positive_notlibgenorg_libgenorgfakehostcom():
    assert is_shadow_library("https://sci-hub.se.edu.fake.com") == False
    assert is_shadow_library("https://notlibgen.org") == False

def test_43_legit_domain_resembling_pattern_arxivmirrororg_if_not_an():
    assert is_shadow_library("https://arxiv-mirror.org") == False

@responses.activate
def test_44_url_that_200s_directly_on_a_clean_domain():
    responses.add(
        responses.HEAD,
        "https://tinyurl.com/some-fake-redirect",
        status=302,
        headers={"Location": "https://sci-hub.se/paper"}
    )
    responses.add(
        responses.HEAD,
        "https://sci-hub.se/paper",
        status=200
    )
    
    final_url = resolve_redirect("https://tinyurl.com/some-fake-redirect")
    assert final_url == "https://sci-hub.se/paper"
    assert score_candidate(final_url, "Title", "Author", "Title", "Snippet") == -1

def test_45_edu_domain_scoring():
    score = score_candidate("https://stanford.edu/paper.pdf", "Title", "Author", "Title", "Snippet")
    # Exact title + .edu domain = 25 + 50 = 75
    assert score >= 75

def test_46_arxivorgbiorxivorgssrncomosfio_scoring():
    score = score_candidate("https://arxiv.org/pdf/1234.pdf", "Title", "Author", "Title", "Snippet")
    assert score >= 75

def test_47_researchgatenetacademiaedu_scoring():
    score = score_candidate("https://researchgate.net/paper.pdf", "Title", "Author", "Title", "Snippet")
    assert score >= 50

def test_48_domain_not_in_any_category_random_blog():
    score = score_candidate("https://myrandomblog.com/paper.pdf", "Title", "Author", "Title", "Snippet")
    assert score == 25 # base score for title exact match

def test_49_ip_address_as_a_domain_http19216811paperpdf():
    score = score_candidate("http://192.168.1.1/paper.pdf", "Title", "Author", "Title", "Snippet")
    assert score == 25 # no domain bonus
