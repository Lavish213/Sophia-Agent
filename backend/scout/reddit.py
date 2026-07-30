from __future__ import annotations

from typing import Any

from backend.lib.config import get_settings

SUBREDDITS = [
    "Stockton",
    "Lodi",
    "SanJoaquin",
    "realestate",
    "personalfinance",
    "landlord",
    "RealEstate",
    "FirstTimeHomeBuyer",
    "divorce",
    "foreclosure",
]

KEYWORDS = [
    "sell my house",
    "selling my house",
    "need to sell",
    "sell fast",
    "cash buyer",
    "cash offer",
    "we buy houses",
    "tired landlord",
    "inherited property",
    "behind on mortgage",
    "facing foreclosure",
    "foreclosure",
    "probate",
    "divorce house",
    "sell as-is",
    "as-is",
    "motivated seller",
    "moving fast",
    "need to move",
    "can't afford repairs",
    "tax lien",
    "delinquent",
]

_HOT_KEYWORDS = [
    "sell my house", "need to sell fast", "cash buyer",
    "cash offer", "we buy houses", "facing foreclosure",
    "behind on mortgage", "tax lien",
]

_WARM_KEYWORDS = [
    "tired landlord", "inherited", "probate", "divorce",
    "sell fast", "motivated", "as-is", "moving fast",
]


def score_intent(title: str, body: str) -> tuple[int, str]:
    text = (title + " " + body).lower()
    score = 0

    for kw in _HOT_KEYWORDS:
        if kw in text:
            score += 4

    for kw in _WARM_KEYWORDS:
        if kw in text:
            score += 2

    if score >= 6:
        label = "hot"
    elif score >= 3:
        label = "warm"
    elif score > 0:
        label = "cold"
    else:
        label = "none"

    return score, label


def keyword_matches(title: str, body: str) -> bool:
    text = (title + " " + body).lower()
    return any(kw in text for kw in KEYWORDS)


def get_reddit_client():
    settings = get_settings()
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        return None

    import praw

    return praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
        read_only=True,
    )


def fetch_matches(limit: int | None = None) -> list[dict[str, Any]]:
    reddit = get_reddit_client()
    if not reddit:
        return []

    settings = get_settings()
    fetch_limit = limit if limit is not None else settings.reddit_fetch_limit

    matches = []
    for sub_name in SUBREDDITS:
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.new(limit=fetch_limit):
                title = post.title or ""
                body = getattr(post, "selftext", "") or ""
                if not keyword_matches(title, body):
                    continue
                score, label = score_intent(title, body)
                if label == "none":
                    continue
                matches.append({
                    "reddit_id": post.id,
                    "subreddit": sub_name,
                    "title": title,
                    "body": body[:500],
                    "url": f"https://reddit.com{post.permalink}",
                    "author": str(post.author) if post.author else "deleted",
                    "created_utc": int(post.created_utc),
                    "post_score": post.score,
                    "intent_score": score,
                    "intent_label": label,
                })
        except Exception:
            continue

    matches.sort(key=lambda x: x["intent_score"], reverse=True)
    return matches
