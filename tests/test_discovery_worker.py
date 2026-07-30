from backend.lib import db
from discovery import worker


def _match(reddit_id="p1"):
    return {
        "reddit_id": reddit_id,
        "subreddit": "Stockton",
        "title": "need to sell my house fast",
        "body": "facing foreclosure",
        "url": "https://reddit.com/r/Stockton/p1",
        "author": "user1",
        "created_utc": 1000,
        "post_score": 5,
        "intent_score": 8,
        "intent_label": "hot",
    }


def test_run_once_inserts_new_matches(monkeypatch):
    monkeypatch.setattr(worker, "fetch_matches", lambda: [_match("p1"), _match("p2")])
    monkeypatch.setattr(db, "get_reddit_match_by_reddit_id", lambda reddit_id: None)
    inserted = []
    monkeypatch.setattr(db, "insert_reddit_match", lambda data: inserted.append(data["reddit_id"]))

    results = worker.run_once()

    assert results["fetched"] == 2
    assert results["new_matches"] == 2
    assert inserted == ["p1", "p2"]


def test_run_once_skips_existing_matches(monkeypatch):
    monkeypatch.setattr(worker, "fetch_matches", lambda: [_match("p1")])
    monkeypatch.setattr(db, "get_reddit_match_by_reddit_id", lambda reddit_id: {"id": "existing-row"})
    called = {"count": 0}

    def _fake_insert(data):
        called["count"] += 1

    monkeypatch.setattr(db, "insert_reddit_match", _fake_insert)

    results = worker.run_once()

    assert results["new_matches"] == 0
    assert called["count"] == 0


def test_run_once_counts_errors_without_crashing(monkeypatch):
    monkeypatch.setattr(worker, "fetch_matches", lambda: [_match("p1")])

    def _raise(reddit_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "get_reddit_match_by_reddit_id", _raise)

    results = worker.run_once()

    assert results["errors"] == 1


def test_run_once_empty_matches(monkeypatch):
    monkeypatch.setattr(worker, "fetch_matches", lambda: [])
    results = worker.run_once()
    assert results == {"fetched": 0, "new_matches": 0, "errors": 0}
