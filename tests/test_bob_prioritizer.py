from datetime import UTC, datetime, timedelta

from bob.prioritizer import rank_leads, score_lead

_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _lead(distress=50, **overrides):
    lead = {"id": "lead-1", "properties": {"distress_score": distress}}
    lead.update(overrides)
    return lead


def _ago(hours):
    return (_NOW - timedelta(hours=hours)).isoformat()


def test_distress_score_is_the_baseline():
    score, reasons = score_lead(_lead(distress=60), _NOW)
    assert score == 70.0
    assert "distress 60" in reasons


def test_someone_who_asked_for_a_callback_jumps_the_queue():
    plain = score_lead(_lead(distress=50, call_attempts=1), _NOW)[0]
    asked = score_lead(_lead(distress=50, call_attempts=1, priority_callback=True), _NOW)[0]
    assert asked > plain


def test_a_booked_walkthrough_outranks_an_equally_distressed_lead():
    plain = score_lead(_lead(distress=50, call_attempts=1), _NOW)[0]
    booked = score_lead(_lead(distress=50, call_attempts=1, appointment_at=_ago(-24)), _NOW)[0]
    assert booked > plain


def test_motivation_learned_on_a_call_raises_priority():
    low = score_lead(_lead(call_attempts=1, motivation_level=2), _NOW)[0]
    high = score_lead(_lead(call_attempts=1, motivation_level=9), _NOW)[0]
    assert high > low


def test_never_called_leads_get_a_nudge():
    fresh = score_lead(_lead(call_attempts=0), _NOW)[0]
    tried = score_lead(_lead(call_attempts=1), _NOW)[0]
    assert fresh > tried


def test_repeatedly_unreachable_leads_fall_down_the_queue():
    few = score_lead(_lead(call_attempts=1), _NOW)[0]
    many = score_lead(_lead(call_attempts=6), _NOW)[0]
    assert many < few


def test_voicemail_cap_pushes_a_lead_down():
    normal = score_lead(_lead(call_attempts=2, voicemail_count=1), _NOW)[0]
    capped = score_lead(_lead(call_attempts=2, voicemail_count=3), _NOW)[0]
    assert capped < normal


def test_unreliable_list_data_is_deprioritised():
    good = _lead(call_attempts=1)
    good["properties"]["data_confidence"] = 1.0
    bad = _lead(call_attempts=1)
    bad["properties"]["data_confidence"] = 0.4

    assert score_lead(bad, _NOW)[0] < score_lead(good, _NOW)[0]


def test_a_due_callback_is_urgent():
    due = score_lead(_lead(call_attempts=1, callback_scheduled_at=_ago(2)), _NOW)[0]
    plain = score_lead(_lead(call_attempts=1), _NOW)[0]
    assert due > plain


def test_a_future_callback_is_not_yet_urgent():
    future = score_lead(_lead(call_attempts=1, callback_scheduled_at=_ago(-48)), _NOW)[0]
    plain = score_lead(_lead(call_attempts=1), _NOW)[0]
    assert future == plain


def test_urgent_timeline_counts():
    urgent = score_lead(_lead(call_attempts=1, timeline_urgency="asap"), _NOW)[0]
    vague = score_lead(_lead(call_attempts=1, timeline_urgency="sometime next year"), _NOW)[0]
    assert urgent > vague


def test_score_is_bounded():
    everything = _lead(
        distress=100,
        priority_callback=True,
        appointment_at=_ago(-1),
        motivation_level=10,
        is_hot_lead=True,
        timeline_urgency="asap",
        call_attempts=0,
        callback_scheduled_at=_ago(1),
    )
    score, _ = score_lead(everything, _NOW)
    assert 0 <= score <= 100


def test_bad_timestamps_do_not_crash_the_ranking():
    score, _ = score_lead(_lead(last_called_at="not-a-date", callback_scheduled_at="junk"), _NOW)
    assert score >= 0


def test_a_waiting_person_outranks_even_the_hottest_cold_lead():
    leads = [
        _lead(distress=100, call_attempts=1),
        _lead(distress=20, call_attempts=1, priority_callback=True),
        _lead(distress=55, call_attempts=1),
    ]
    ranked = rank_leads(leads, _NOW)

    assert ranked[0]["waiting_on_human"] is True, (
        "someone who asked for a callback is a person waiting, not a score to compare"
    )
    assert "they asked for a callback" in ranked[0]["priority_reasons"]


def test_a_due_callback_also_counts_as_waiting():
    leads = [
        _lead(distress=100, call_attempts=1),
        _lead(distress=10, call_attempts=1, callback_scheduled_at=_ago(3)),
    ]
    ranked = rank_leads(leads, _NOW)
    assert ranked[0]["waiting_on_human"] is True


def test_nobody_waiting_falls_back_to_score_order():
    leads = [_lead(distress=30, call_attempts=1), _lead(distress=80, call_attempts=1)]
    ranked = rank_leads(leads, _NOW)
    assert ranked[0]["call_priority"] > ranked[1]["call_priority"]


def test_ranking_explains_itself():
    ranked = rank_leads([_lead(call_attempts=0, motivation_level=8)], _NOW)
    reasons = ranked[0]["priority_reasons"]

    assert any("motivation" in r for r in reasons)
    assert any("never tried" in r for r in reasons)


def test_the_dialer_sort_matches_bob_ranking(monkeypatch):
    from backend.lib import db

    rows = [
        {"id": "cold-hot-property", "owner_phone": "+12094771234", "call_priority": 95,
         "waiting_on_human": False, "properties": {"distress_score": 95}},
        {"id": "asked-for-callback", "owner_phone": "+12094775678", "call_priority": 30,
         "waiting_on_human": True, "properties": {"distress_score": 20}},
    ]

    class _Resp:
        data = rows

    class _Q:
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def or_(self, *a, **k): return self
        def order(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self): return _Resp()
        @property
        def not_(self): return self
        def in_(self, *a, **k): return self
        def is_(self, *a, **k): return self

    class _Client:
        def table(self, name): return _Q()

    monkeypatch.setattr(db, "get_client", lambda: _Client())

    results = db.get_leads_for_outbound(min_score=0, limit=10)

    assert results[0]["id"] == "asked-for-callback", (
        "bob ranks a waiting person first; the dialer must dial in that same order"
    )
