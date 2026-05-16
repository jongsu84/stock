"use strict";

const API_NEWS = "/api/news";
const API_REFRESH = "/api/refresh";
const AUTO_REFRESH_MS = 60_000;
const NEW_THRESHOLD_MS = 10 * 60 * 1000;

const MARKET_LABELS = {
  kr_stock: "국내주식",
  us_stock: "해외주식",
  kr_coin: "국내코인",
  us_coin: "해외코인",
};

const MARKET_TAG_CLASS = {
  kr_stock: "kr-stock",
  us_stock: "us-stock",
  kr_coin: "kr-coin",
  us_coin: "us-coin",
};

const state = {
  items: [],
  filter: "kr_stock",
  query: "",
  seenIds: new Set(),
  firstLoad: true,
  lastUpdated: null,
};

const els = {
  list: document.getElementById("newsList"),
  colTitle: document.getElementById("activeColTitle"),
  countLabel: document.getElementById("countLabel"),
  statusLine: document.getElementById("statusLine"),
  updatedAt: document.getElementById("updatedAt"),
  autoRefresh: document.getElementById("autoRefresh"),
  liveDot: document.getElementById("liveDot"),
  refreshBtn: document.getElementById("refreshBtn"),
  search: document.getElementById("searchInput"),
  tabs: document.querySelectorAll(".tab"),
};

function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function timeAgo(iso) {
  if (!iso) return "";
  const now = Date.now();
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "";
  const diff = Math.max(0, now - t);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "방금 전";
  if (m < 60) return `${m}분 전`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}시간 전`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}일 전`;
  const dt = new Date(iso);
  return `${dt.getFullYear()}.${String(dt.getMonth() + 1).padStart(2, "0")}.${String(dt.getDate()).padStart(2, "0")}`;
}

function matchesQuery(item, q) {
  if (!q) return true;
  const hay = `${item.title} ${item.summary} ${item.source}`.toLowerCase();
  return hay.includes(q);
}

function renderCard(item, isNew) {
  const tagClass = MARKET_TAG_CLASS[item.market] || "kr-stock";
  const tagLabel = MARKET_LABELS[item.market] || item.market;
  return `
    <a class="card${isNew ? " new" : ""}" href="${escapeHtml(item.link)}" target="_blank" rel="noopener">
      <div class="card-meta">
        <span class="tag ${tagClass}">${tagLabel}</span>
        <span>${escapeHtml(item.source)}</span>
        <span class="sep">·</span>
        <span class="card-time">${timeAgo(item.published)}</span>
      </div>
      <h3 class="card-title">${escapeHtml(item.title)}</h3>
      ${item.summary ? `<p class="card-summary">${escapeHtml(item.summary)}</p>` : ""}
    </a>
  `;
}

function render() {
  const q = state.query.trim().toLowerCase();
  const now = Date.now();

  const filtered = state.items.filter(
    (i) => i.market === state.filter && matchesQuery(i, q)
  );

  if (!filtered.length) {
    els.list.innerHTML = `<div class="empty">표시할 뉴스가 없습니다</div>`;
  } else {
    els.list.innerHTML = filtered
      .map((item) => {
        const t = new Date(item.published).getTime();
        const isNew =
          !state.firstLoad && !state.seenIds.has(item.id) && now - t < NEW_THRESHOLD_MS;
        return renderCard(item, isNew);
      })
      .join("");
  }

  // 카테고리별 카운트 표시
  const perMarket = Object.keys(MARKET_LABELS).reduce((acc, m) => {
    acc[m] = state.items.filter((i) => i.market === m).length;
    return acc;
  }, {});
  els.countLabel.textContent =
    `${filtered.length}건  ` +
    Object.entries(perMarket)
      .map(([m, n]) => `${MARKET_LABELS[m]} ${n}`)
      .join(" · ");

  els.colTitle.textContent = MARKET_LABELS[state.filter] || state.filter;
}

function applyFilter() {
  els.tabs.forEach((t) =>
    t.classList.toggle("active", t.dataset.filter === state.filter)
  );
  render();
}

async function fetchNews(triggeredByUser = false) {
  els.liveDot.classList.remove("error");
  els.liveDot.classList.add("loading");
  els.statusLine.textContent = "불러오는 중…";
  if (triggeredByUser) {
    els.refreshBtn.classList.add("spinning");
    try {
      await fetch(API_REFRESH, { method: "POST" });
    } catch (_) {}
  }
  try {
    const res = await fetch(API_NEWS, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.items = data.items || [];
    state.lastUpdated = data.last_updated;
    render();
    state.items.forEach((i) => state.seenIds.add(i.id));
    state.firstLoad = false;
    els.liveDot.classList.remove("loading", "error");
    const stamp = data.last_updated
      ? new Date(data.last_updated).toLocaleTimeString("ko-KR")
      : "—";
    els.statusLine.textContent = `최근 업데이트: ${stamp}`;
    els.updatedAt.textContent = `마지막 수집: ${stamp}`;
  } catch (err) {
    console.error(err);
    els.liveDot.classList.remove("loading");
    els.liveDot.classList.add("error");
    els.statusLine.textContent = `오류: ${err.message}`;
  } finally {
    els.refreshBtn.classList.remove("spinning");
  }
}

function setupEvents() {
  els.refreshBtn.addEventListener("click", () => fetchNews(true));
  els.tabs.forEach((t) =>
    t.addEventListener("click", () => {
      state.filter = t.dataset.filter;
      applyFilter();
    })
  );

  let qTimer;
  els.search.addEventListener("input", (e) => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => {
      state.query = e.target.value || "";
      render();
    }, 120);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== els.search) {
      e.preventDefault();
      els.search.focus();
    }
    if (e.key === "r" && (e.metaKey || e.ctrlKey) && e.shiftKey) {
      e.preventDefault();
      fetchNews(true);
    }
    // 숫자 키 1-4로 탭 빠른 이동
    if (["1", "2", "3", "4"].includes(e.key) && document.activeElement !== els.search) {
      const filters = ["kr_stock", "us_stock", "kr_coin", "us_coin"];
      state.filter = filters[parseInt(e.key, 10) - 1];
      applyFilter();
    }
  });
}

function startAutoRefresh() {
  els.autoRefresh.textContent = `자동 새로고침: ${AUTO_REFRESH_MS / 1000}초`;
  setInterval(fetchNews, AUTO_REFRESH_MS);
  setInterval(render, 30_000); // refresh relative times
}

setupEvents();
applyFilter();
fetchNews();
startAutoRefresh();
