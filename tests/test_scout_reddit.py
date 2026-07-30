from dataclasses import dataclass, field

from backend.lib.config import get_settings
from backend.scout import reddit


def test_score_intent_hot_keywords():
    score, label = reddit.score_intent("Need to sell my house fast", "facing foreclosure, behind on mortgage")
    assert label == "hot"
    assert score >= 6


def test_score_intent_warm_keywords():
    score, label = reddit.score_intent("Tired landlord looking for advice", "inherited a property")
    assert label == "warm"


def test_score_intent_no_match():
    score, label = reddit.score_intent("What's a good router for my apartment", "")
    assert label == "none"
    assert score == 0


def test_keyword_matches_true():
    assert reddit.keyword_matches("selling my house", "") is True


def test_keyword_matches_false():
    assert reddit.keyword_matches("best pizza in stockton", "") is False


def test_get_reddit_client_none_without_credentials(monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    get_settings.cache_clear()
    try:
        assert reddit.get_reddit_client() is None
    finally:
        get_settings.cache_clear()


def test_fetch_matches_empty_without_client(monkeypatch):
    monkeypatch.setattr(reddit, "get_reddit_client", lambda: None)
    assert reddit.fetch_matches() == []


@dataclass
class _FakePost:
    id: str
    title: str
    selftext: str
    permalink: str
    author: str
    created_utc: int
    score: int


@dataclass
class _FakeSubreddit:
    posts: list

    def new(self, limit):
        return self.posts[:limit]


@dataclass
class _FakeRedditClient:
    posts_by_sub: dict = field(default_factory=dict)

    def subreddit(self, name):
        return _FakeSubreddit(self.posts_by_sub.get(name, []))


def test_fetch_matches_filters_and_scores(monkeypatch):
    hot_post = _FakePost(
        id="p1", title="need to sell my house fast", selftext="facing foreclosure",
        permalink="/r/Stockton/p1", author="user1", created_utc=1000, score=5,
    )
    unrelated_post = _FakePost(
        id="p2", title="best taco truck", selftext="",
        permalink="/r/Stockton/p2", author="user2", created_utc=1001, score=2,
    )
    fake_client = _FakeRedditClient(posts_by_sub={"Stockton": [hot_post, unrelated_post]})
    monkeypatch.setattr(reddit, "get_reddit_client", lambda: fake_client)
    monkeypatch.setattr(reddit, "SUBREDDITS", ["Stockton"])

    matches = reddit.fetch_matches(limit=10)

    assert len(matches) == 1
    assert matches[0]["reddit_id"] == "p1"
    assert matches[0]["intent_label"] == "hot"
    assert matches[0]["url"] == "https://reddit.com/r/Stockton/p1"


def test_fetch_matches_skips_broken_subreddit(monkeypatch):
    class _BrokenClient:
        def subreddit(self, name):
            raise RuntimeError("banned subreddit")

    monkeypatch.setattr(reddit, "get_reddit_client", lambda: _BrokenClient())
    monkeypatch.setattr(reddit, "SUBREDDITS", ["Stockton"])

    matches = reddit.fetch_matches(limit=10)

    assert matches == []
