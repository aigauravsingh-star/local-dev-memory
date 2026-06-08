from app.core.text_utils import build_summary, classify_query, extract_commit_shas, extract_decision_snippets, extract_file_refs, parse_exchanges


def test_transcript_exchange_parsing():
    exchanges = parse_exchanges("user: change app.py\nassistant: because tests failed\ncontinued")
    assert exchanges[0]["role"] == "user"
    assert "app.py" in exchanges[0]["text"]
    assert exchanges[1]["role"] == "assistant"


def test_decision_snippet_extraction():
    snippets = extract_decision_snippets("We chose SQLite because this is local-only and simple. Another line.")
    assert snippets


def test_summary_building():
    summary = build_summary("user: fix backend/app/main.py\nassistant: decided to add health because smoke tests need it", "Health work")
    assert "Health work" in summary
    assert "backend/app/main.py" in summary


def test_file_reference_extraction():
    refs = extract_file_refs("Changed backend/app/main.py and frontend/src/App.js")
    assert "backend/app/main.py" in refs
    assert "frontend/src/App.js" in refs


def test_query_classification():
    assert classify_query("why did we choose sqlite") == "decision"
    assert classify_query("backend/app/main.py") == "file"
    assert classify_query("commit abcdef1") == "commit"


def test_commit_sha_extraction():
    assert extract_commit_shas("linked abcdef1234567890 and ABCDEF1")[:1] == ["abcdef1234567890"]
