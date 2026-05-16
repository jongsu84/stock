"""Stock news dashboard backend.

Aggregates Korean and overseas stock news from public RSS feeds,
caches results in memory, and serves them via a JSON API.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable

import feedparser
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("dashboard")

REFRESH_INTERVAL_SECONDS = 180  # 3 minutes
REQUEST_TIMEOUT_SECONDS = 10
MAX_ITEMS_PER_FEED = 20
MAX_TOTAL_ITEMS = 80


# (market, source_label, feed_url)
FEEDS: list[tuple[str, str, str]] = [
    # 국내 — 증권/금융 중심
    ("kr", "한국경제 증권", "https://rss.hankyung.com/feed/stock.xml"),
    ("kr", "한국경제 금융", "https://rss.hankyung.com/feed/finance.xml"),
    ("kr", "매일경제 증권", "https://www.mk.co.kr/rss/50200011/"),
    ("kr", "매일경제 증권일반", "https://www.mk.co.kr/rss/50300009/"),
    ("kr", "매일경제 코스피", "https://www.mk.co.kr/rss/50200012/"),
    ("kr", "매일경제 코스닥", "https://www.mk.co.kr/rss/50200013/"),
    ("kr", "연합뉴스 경제", "https://www.yna.co.kr/rss/economy.xml"),
    # 해외 — 마켓/증권 중심
    ("us", "Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("us", "CNBC Top News", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
    ("us", "MarketWatch Top", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("us", "MarketWatch RealTime", "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"),
    ("us", "Investing.com Stock", "https://www.investing.com/rss/news_25.rss"),
    ("us", "Investing.com Market", "https://www.investing.com/rss/news_301.rss"),
    ("us", "SeekingAlpha Market", "https://seekingalpha.com/market_currents.xml"),
]


@dataclass
class NewsItem:
    id: str
    market: str
    source: str
    title: str
    summary: str
    link: str
    published: str  # ISO 8601
    published_ts: float


class NewsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[NewsItem] = []
        self._last_updated: float = 0.0
        self._fetch_error_count = 0

    def replace(self, items: list[NewsItem]) -> None:
        with self._lock:
            self._items = items
            self._last_updated = time.time()

    def snapshot(self) -> tuple[list[NewsItem], float]:
        with self._lock:
            return list(self._items), self._last_updated


store = NewsStore()


def strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:280]


def parse_published(entry: feedparser.FeedParserDict) -> tuple[str, float]:
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct:
            ts = time.mktime(struct)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.isoformat(), ts
    now = datetime.now(timezone.utc)
    return now.isoformat(), now.timestamp()


def make_id(market: str, source: str, link: str, title: str) -> str:
    base = f"{market}|{source}|{link or title}"
    return str(abs(hash(base)))


def fetch_feed(market: str, source: str, url: str) -> list[NewsItem]:
    log.info("fetching feed: %s (%s)", source, market)
    try:
        parsed = feedparser.parse(
            url,
            request_headers={
                "User-Agent": "Mozilla/5.0 (StockNewsDashboard/1.0)",
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("feed error %s: %s", source, exc)
        return []

    if parsed.bozo and not parsed.entries:
        log.warning("feed bozo %s: %s", source, parsed.bozo_exception)
        return []

    items: list[NewsItem] = []
    for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
        title = strip_html(entry.get("title", "")) or "(제목 없음)"
        link = entry.get("link", "")
        summary = strip_html(entry.get("summary", "") or entry.get("description", ""))
        published_iso, published_ts = parse_published(entry)
        items.append(
            NewsItem(
                id=make_id(market, source, link, title),
                market=market,
                source=source,
                title=title,
                summary=summary,
                link=link,
                published=published_iso,
                published_ts=published_ts,
            )
        )
    return items


def refresh_all() -> None:
    start = time.time()
    all_items: list[NewsItem] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(fetch_feed, market, source, url): (market, source)
            for market, source, url in FEEDS
        }
        for fut in as_completed(futures):
            try:
                items = fut.result(timeout=REQUEST_TIMEOUT_SECONDS + 5)
                all_items.extend(items)
            except Exception as exc:  # noqa: BLE001
                market, source = futures[fut]
                log.warning("future failed %s/%s: %s", market, source, exc)

    seen_ids: set[str] = set()
    deduped: list[NewsItem] = []
    for item in sorted(all_items, key=lambda x: x.published_ts, reverse=True):
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        deduped.append(item)

    deduped = deduped[:MAX_TOTAL_ITEMS]
    store.replace(deduped)
    log.info(
        "refresh done in %.2fs, %d items (kr=%d, us=%d)",
        time.time() - start,
        len(deduped),
        sum(1 for i in deduped if i.market == "kr"),
        sum(1 for i in deduped if i.market == "us"),
    )


def background_loop() -> None:
    while True:
        try:
            refresh_all()
        except Exception as exc:  # noqa: BLE001
            log.exception("refresh loop error: %s", exc)
        time.sleep(REFRESH_INTERVAL_SECONDS)


_bg_lock = threading.Lock()
_bg_started = False


def ensure_background_started() -> None:
    """Idempotently start the background fetch loop.

    Module-level threads can be unreliable under some gunicorn worker
    configurations, so we also call this lazily from request handlers.
    """
    global _bg_started
    if _bg_started:
        return
    with _bg_lock:
        if _bg_started:
            return
        _bg_started = True
        log.info("starting background fetch loop")
        threading.Thread(target=background_loop, daemon=True).start()


app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)


@app.before_request
def _ensure_bg() -> None:
    ensure_background_started()


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/news")
def api_news():
    items, last_updated = store.snapshot()
    return jsonify(
        {
            "last_updated": datetime.fromtimestamp(last_updated, tz=timezone.utc).isoformat()
            if last_updated
            else None,
            "refresh_interval_seconds": REFRESH_INTERVAL_SECONDS,
            "count": len(items),
            "items": [asdict(i) for i in items],
        }
    )


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    threading.Thread(target=refresh_all, daemon=True).start()
    return jsonify({"status": "refreshing"})


@app.route("/api/health")
def api_health():
    items, last_updated = store.snapshot()
    return jsonify(
        {
            "items": len(items),
            "last_updated_epoch": last_updated,
            "feeds_configured": len(FEEDS),
        }
    )


# Best-effort start at import time. The @app.before_request hook above
# guarantees the loop runs even if this fails under some WSGI servers.
ensure_background_started()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
