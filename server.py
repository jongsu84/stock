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
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable

import feedparser
import requests
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

# 과거 socket.setdefaulttimeout(15)를 썼으나, 이 설정은 워커 임포트
# 이후 accept()로 생성되는 모든 소켓(= Render proxy ↔ 컨테이너 응답
# 소켓 포함)에 적용되어 HTTP 응답 자체가 15초 후 끊겨 외부에서
# 사이트가 hang되는 증상이 있었다.
# 대신 requests로 RSS를 직접 가져와 feedparser에는 bytes만 넘긴다.
# 그러면 timeout을 requests.get()에 국소적으로 줄 수 있고,
# 전역 소켓 타임아웃은 더 이상 필요 없다.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("dashboard")

REFRESH_INTERVAL_SECONDS = 180  # 3 minutes
REQUEST_TIMEOUT_SECONDS = 10
MAX_ITEMS_PER_FEED = 30
MAX_TOTAL_ITEMS = 120

# 시장 코드: kr_stock(국내주식), us_stock(해외주식), kr_coin(국내코인), us_coin(해외코인)
# Render Free 티어 안정성을 위해 카테고리당 2-3개 핵심 피드만 사용.
# (이전 26개에서 슬림화 — 자원 부담 줄이고 데드라인 안에 안정 수집)
# (market, source_label, feed_url)
FEEDS: list[tuple[str, str, str]] = [
    # ---------- 국내 주식 ----------
    ("kr_stock", "매일경제 증권일반", "https://www.mk.co.kr/rss/50300009/"),
    ("kr_stock", "연합뉴스 경제", "https://www.yna.co.kr/rss/economy.xml"),
    ("kr_stock", "한국경제 증권", "https://rss.hankyung.com/feed/stock.xml"),
    # ---------- 해외 주식 ----------
    ("us_stock", "Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("us_stock", "CNBC Top News", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
    ("us_stock", "MarketWatch Top", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    # ---------- 국내 코인 ----------
    ("kr_coin", "토큰포스트", "https://www.tokenpost.kr/rss"),
    ("kr_coin", "Google뉴스 암호화폐", "https://news.google.com/rss/search?q=암호화폐+OR+비트코인+OR+이더리움&hl=ko&gl=KR&ceid=KR:ko"),
    # ---------- 해외 코인 ----------
    ("us_coin", "CoinDesk", "https://feeds.feedburner.com/CoinDesk"),
    ("us_coin", "CoinTelegraph", "https://cointelegraph.com/rss"),
    ("us_coin", "Decrypt", "https://decrypt.co/feed"),
]

# 시장별 사람이 읽는 라벨
MARKET_LABELS = {
    "kr_stock": "국내주식",
    "us_stock": "해외주식",
    "kr_coin": "국내코인",
    "us_coin": "해외코인",
}


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
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (StockNewsDashboard/1.0)"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
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


REFRESH_DEADLINE_SECONDS = 90  # 전체 refresh 하드 데드라인 (Render 싱가포르 DC 느린 RSS 대응)

# 동시에 여러 refresh_all()이 돌면 워커 수가 N배가 되어 Render 컨테이너가
# 폭발 → 모든 피드 cancel. 한 번에 하나만 실행되도록 mutex.
_refresh_lock = threading.Lock()


def refresh_all() -> None:
    if not _refresh_lock.acquire(blocking=False):
        log.info("refresh already in progress, skipping")
        return
    try:
        _refresh_all_inner()
    finally:
        _refresh_lock.release()


def _refresh_all_inner() -> None:
    start = time.time()
    all_items: list[NewsItem] = []
    # 컨텍스트 매니저 대신 수동 관리 → hang하는 future를 cancel_futures로 강제 종료.
    # 워커 6개 (이전 10개는 Render 자원 한도 초과)
    pool = ThreadPoolExecutor(max_workers=6)
    try:
        futures = {
            pool.submit(fetch_feed, market, source, url): (market, source)
            for market, source, url in FEEDS
        }
        done, not_done = wait(futures, timeout=REFRESH_DEADLINE_SECONDS)
        for fut in done:
            try:
                items = fut.result(timeout=1)
                all_items.extend(items)
            except Exception as exc:  # noqa: BLE001
                market, source = futures[fut]
                log.warning("future failed %s/%s: %s", market, source, exc)
        if not_done:
            log.warning(
                "deadline reached, cancelling %d hanging feeds: %s",
                len(not_done),
                ", ".join(f"{futures[f][0]}/{futures[f][1]}" for f in not_done),
            )
    finally:
        # cancel_futures=True (Python 3.9+): 대기 중인 future는 취소하고
        # 이미 실행 중인 것은 백그라운드에서 끝나도록 두고 즉시 반환.
        pool.shutdown(wait=False, cancel_futures=True)

    seen_ids: set[str] = set()
    deduped: list[NewsItem] = []
    for item in sorted(all_items, key=lambda x: x.published_ts, reverse=True):
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        deduped.append(item)

    deduped = deduped[:MAX_TOTAL_ITEMS]
    elapsed = time.time() - start
    counts = {m: sum(1 for i in deduped if i.market == m) for m in MARKET_LABELS}
    # 핵심: 0건 결과로 기존 정상 데이터를 wipe하지 않음.
    # 모든 피드가 cancel/실패한 경우 이전 store를 유지.
    if deduped:
        store.replace(deduped)
        log.info(
            "refresh done in %.2fs, %d items (%s)",
            elapsed,
            len(deduped),
            ", ".join(f"{m}={n}" for m, n in counts.items()),
        )
    else:
        log.warning(
            "refresh got 0 items in %.2fs — keeping previous store",
            elapsed,
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
    # Fallback: trigger refresh if data is empty or stale.
    # 일부 WSGI 설정에서 백그라운드 루프가 안 도는 경우를 대비.
    stale = (time.time() - last_updated) > REFRESH_INTERVAL_SECONDS
    if not items or stale:
        threading.Thread(target=refresh_all, daemon=True).start()
    return jsonify(
        {
            "last_updated": datetime.fromtimestamp(last_updated, tz=timezone.utc).isoformat()
            if last_updated
            else None,
            "refresh_interval_seconds": REFRESH_INTERVAL_SECONDS,
            "markets": MARKET_LABELS,
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
            "bg_started": _bg_started,
        }
    )


# Render 헬스체크는 부팅 후 즉시 포트 응답이 와야 통과한다.
# 모듈 임포트 시점에 백그라운드 스레드를 시작하면, 일부 환경에서
# import가 늦어져 워커 boot 자체가 timeout되는 사례가 있어
# import는 가볍게 두고, ensure_background_started()는
# @app.before_request 훅에서만 호출한다.

if __name__ == "__main__":
    ensure_background_started()
    port = int(os.environ.get("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
