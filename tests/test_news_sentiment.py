"""
Unit tests for NewsSentimentScout (CryptoPanic, Fear & Greed, and Open RSS).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scouts.news_sentiment import NewsSentimentScout


def test_fear_and_greed_index_parsing(tmp_path):
    scout = NewsSentimentScout(cache_dir=tmp_path)
    mock_resp = {
        "name": "Fear and Greed Index",
        "data": [
            {"value": "15", "value_classification": "Extreme Fear"},
            {"value": "20", "value_classification": "Extreme Fear"},
            {"value": "25", "value_classification": "Fear"},
        ],
    }
    with patch("requests.get") as mock_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_resp
        mock_get.return_value = resp

        res = scout.fetch_fear_and_greed_index(force_refresh=True)
        assert res["value"] == 15
        assert res["classification"] == "Extreme Fear"
        assert res["historical_7d_avg"] == 20.0


def test_cryptopanic_disabled_kill_switch(tmp_path):
    scout = NewsSentimentScout(cache_dir=tmp_path)
    scout.enabled = False
    res = scout.fetch_cryptopanic_posts(force_refresh=True)
    assert res["status"] == "disabled"
    assert res["posts"] == []


def test_cryptopanic_unauthenticated_fallback(tmp_path):
    scout = NewsSentimentScout(cache_dir=tmp_path)
    scout.enabled = True
    scout.api_key = ""
    res = scout.fetch_cryptopanic_posts(force_refresh=True)
    assert res["status"] == "unauthenticated"
    assert res["posts"] == []


def test_cryptopanic_successful_fetch(tmp_path):
    scout = NewsSentimentScout(cache_dir=tmp_path)
    scout.enabled = True
    scout.api_key = "test_auth_token"

    mock_cp = {
        "results": [
            {
                "id": 12345,
                "title": "Hyperliquid Launches Major Perpetual Upgrade",
                "url": "https://cryptopanic.com/news/12345",
                "domain": "coindesk.com",
                "published_at": "2026-11-19T02:00:00Z",
                "currencies": [{"code": "HYPE"}],
                "votes": {"positive": 45, "negative": 2, "important": 30},
            }
        ]
    }
    with patch("requests.get") as mock_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_cp
        mock_get.return_value = resp

        res = scout.fetch_cryptopanic_posts(currencies=["HYPE"], force_refresh=True)
        assert res["status"] == "ok"
        assert len(res["posts"]) == 1
        post = res["posts"][0]
        assert post["title"] == "Hyperliquid Launches Major Perpetual Upgrade"
        assert "HYPE" in post["currencies"]
        assert post["votes_important"] == 30


def test_rss_breaking_news_token_matching(tmp_path):
    scout = NewsSentimentScout(cache_dir=tmp_path)
    mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Cointelegraph</title>
        <item>
          <title>Aave Protocol V4 Proposes Major Fee Switch Expansion</title>
          <link>https://cointelegraph.com/news/aave-v4</link>
          <pubDate>Thu, 19 Nov 2026 01:00:00 GMT</pubDate>
          <description>Aave governance discussion expands buyback.</description>
        </item>
      </channel>
    </rss>
    """
    with patch("requests.get") as mock_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.content = mock_xml.encode("utf-8")
        mock_get.return_value = resp

        articles = scout.fetch_rss_breaking_news(portfolio_symbols=["AAVE", "HYPE"], force_refresh=True)
        assert len(articles) == 1
        assert "AAVE" in articles[0]["matched_portfolio_tokens"]
