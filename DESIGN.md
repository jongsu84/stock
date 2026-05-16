# Design Tokens — JOCOJOSO News Live

도메인: 주식·코인 실시간 뉴스 대시보드 (금융/정보 밀도 높음).
의도: Bloomberg/Reuters 톤 — 신뢰감·진중함·속도감. AI 보라색·이모지 아이콘 회피.

---

## Color

다크 모드 우선. 라이트 모드는 prefers-color-scheme로 자동 전환.

### Surface

| Token | Dark | Light | 용도 |
|-------|------|-------|------|
| `--bg` | `#0a0d14` | `#f6f7fa` | 페이지 배경 |
| `--surface-1` | `#11151f` | `#ffffff` | sticky bar, footer |
| `--surface-2` | `#161b27` | `#ffffff` | 카드 배경 |
| `--surface-3` | `#1c2231` | `#f0f3f9` | hover/active |
| `--border` | `#252c3d` | `#e3e8f0` | 보더 |
| `--border-strong` | `#323a4f` | `#cdd4e0` | 강조 보더 (focus) |

### Text

| Token | Dark | Light | 대비 |
|-------|------|-------|------|
| `--text-1` | `#eaecf2` | `#0f1320` | 11.8 / 13.4 |
| `--text-2` | `#a8aebf` | `#4a5468` | 5.1 / 7.1 |
| `--text-3` | `#6e7689` | `#7a839a` | 3.4 / 3.9 (UI 라벨용) |

### Brand / Action

| Token | Dark | Light | 용도 |
|-------|------|-------|------|
| `--accent` | `#6ea8ff` | `#2860d8` | primary action, focus |
| `--accent-soft` | `rgba(110,168,255,0.14)` | `rgba(40,96,216,0.10)` | 활성 배경 |

### Category Markers (의미 색)

4 카테고리는 **온도 + 명도**로 차별화 (단순 색상 차이가 아니라 톤 분리).

| Token | Color | 카테고리 | 톤 의도 |
|-------|-------|----------|---------|
| `--cat-kr-stock` | `#ff6a6a` | 국내주식 | warm red (한국=상승=빨강) |
| `--cat-us-stock` | `#5fb3ff` | 해외주식 | cool blue (서구=차분) |
| `--cat-kr-coin` | `#f5b042` | 국내코인 | warm amber (활기) |
| `--cat-us-coin` | `#9d7cff` | 해외코인 | cool violet (디지털) |

### Status

| Token | Value | 용도 |
|-------|-------|------|
| `--ok` | `#22c39a` | live dot, NEW |
| `--warn` | `#e8a13a` | loading |
| `--err` | `#ff5a6f` | error |

---

## Typography

폰트: **Pretendard** (한국어 가독성) + **JetBrains Mono** (숫자·시간).

### Scale (1.25 비율 — Major Third)

| Token | Size | Weight | Use |
|-------|------|--------|-----|
| `--fs-1` | 28px | 800 | Display (헤더 브랜드) |
| `--fs-2` | 20px | 700 | Hero 카드 제목 |
| `--fs-3` | 16px | 700 | 카드 제목 |
| `--fs-4` | 14px | 500 | 본문/요약 |
| `--fs-5` | 12px | 600 | 라벨/메타 |
| `--fs-6` | 11px | 700 | 캡션/태그 |

규칙: 한 화면 4단계 이내. tracking은 제목에만 `-0.015em`.

---

## Spacing (8px Grid)

| Token | Value |
|-------|-------|
| `--s-1` | 4px |
| `--s-2` | 8px |
| `--s-3` | 12px |
| `--s-4` | 16px |
| `--s-5` | 24px |
| `--s-6` | 32px |
| `--s-7` | 48px |

---

## Radius

| Token | Value | Use |
|-------|-------|-----|
| `--r-sm` | 6px | tag, dot bg |
| `--r-md` | 10px | button, input |
| `--r-lg` | 14px | card |
| `--r-full` | 999px | pill, status dot |

---

## Elevation

다크 모드에서는 그림자보다 보더로 깊이 표현.

| Token | Value | Use |
|-------|-------|-----|
| `--e-0` | `none` | bare surface |
| `--e-1` | `0 1px 0 var(--border)` | 분리선 |
| `--e-hero` | `0 8px 24px rgba(0,0,0,0.32), 0 0 0 1px var(--border-strong)` | 1순위 카드만 |

---

## Motion

| Token | Value | Use |
|-------|-------|-----|
| `--ease-out` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | 진입 |
| `--ease-spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | press feedback |
| `--dur-fast` | 120ms | hover, focus ring |
| `--dur-base` | 200ms | 카드 in/out |
| `--dur-slow` | 360ms | 신규 카드 highlight pulse |

---

## Visual Hierarchy 규칙 (이 화면 한정)

1. **Hero (1순위)**: 카테고리 최상단 + 10분 이내 NEW 1건 — 큰 카드, accent border-left 3px, 그림자, 제목 `--fs-2`
2. **Fresh (2순위)**: 1시간 이내 — 일반 카드, 시간을 accent로
3. **Standard (3순위)**: 그 외 — muted 카드, 시간 `--text-3`

상태(live/loading/error)는 색상 + 텍스트 동시 표현 (색각 이상 고려).
