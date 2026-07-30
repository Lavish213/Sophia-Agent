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
    assert results["fetched"] == 0
    assert results["new_matches"] == 0
    assert results["errors"] == 0


def test_run_skiptrace_pass_noop_when_not_configured(monkeypatch):
    from backend.scout import skiptrace

    monkeypatch.setattr(skiptrace, "is_configured", lambda: False)
    result = worker.run_skiptrace_pass()
    assert result == {"attempted": 0, "enriched": 0}


def test_run_skiptrace_pass_enriches_leads(monkeypatch):
    from backend.scout import skiptrace

    monkeypatch.setattr(skiptrace, "is_configured", lambda: True)
    monkeypatch.setattr(db, "get_leads_needing_skiptrace", lambda limit: [{"id": "l1"}, {"id": "l2"}])
    monkeypatch.setattr(
        skiptrace, "enrich_lead", lambda lead_id: {"success": lead_id == "l1"}
    )

    result = worker.run_skiptrace_pass()

    assert result == {"attempted": 2, "enriched": 1}


def test_run_skiptrace_pass_survives_a_failing_lead(monkeypatch):
    from backend.scout import skiptrace

    monkeypatch.setattr(skiptrace, "is_configured", lambda: True)
    monkeypatch.setattr(db, "get_leads_needing_skiptrace", lambda limit: [{"id": "l1"}, {"id": "l2"}])

    def _enrich(lead_id):
        if lead_id == "l1":
            raise RuntimeError("api down")
        return {"success": True}

    monkeypatch.setattr(skiptrace, "enrich_lead", _enrich)

    result = worker.run_skiptrace_pass()

    assert result == {"attempted": 2, "enriched": 1}
