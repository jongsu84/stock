# 주식 뉴스 대시보드 (Stock News Live)

국내·해외 주식 뉴스 RSS 피드를 실시간으로 모아 보여주는 반응형 웹 대시보드.

## 구성
- **Backend**: Python 3 + Flask. 백그라운드 스레드가 3분마다 RSS 14개를 병렬 수집하여 메모리 캐시.
- **Frontend**: 정적 HTML/CSS/JS. 60초마다 `/api/news`를 폴링하고 UI 갱신.
- **API**
  - `GET /api/news` — 최신 뉴스 묶음
  - `POST /api/refresh` — 즉시 재수집 트리거
  - `GET /api/health` — 상태 확인

## 실행
```bash
cd /Users/my_mac/Projects/stock-news-dashboard
./run.sh                       # 포어그라운드
# 또는 백그라운드:
nohup ./run.sh > server.log 2>&1 &
```
브라우저에서 http://localhost:5050 접속.

## 기능
- 국내(🇰🇷) / 해외(🇺🇸) 2-컬럼 레이아웃, 모바일에선 1-컬럼으로 자동 변환
- 탭으로 시장 필터, 검색창으로 즉시 키워드 필터
- 최근 10분 내 새 뉴스에는 NEW 뱃지
- 실시간 인디케이터(좌상단 점)로 로딩/오류 상태 시각화
- 다크/라이트 모드 자동 전환 (`prefers-color-scheme`)
- `/` 키로 검색 포커스, `Cmd/Ctrl+Shift+R`로 수동 새로고침

## 수집 피드 (변경: `server.py`의 `FEEDS`)
- 🇰🇷 한국경제(증권/금융), 매일경제(증권/증권일반/코스피/코스닥), 연합뉴스 경제
- 🇺🇸 Yahoo Finance, CNBC, MarketWatch(Top/RealTime), Investing.com(Stock/Market), SeekingAlpha

## 주의
- RSS 피드는 각 매체 정책에 따라 차단·변경될 수 있음. 응답이 비면 `server.log`에서 bozo 경고/HTTP 오류 확인.
- 일부 KR 피드(예: 한국경제)는 비표준 XML이라 feedparser가 일부만 파싱하는 경우가 있음.
- 개인 학습/내부용. 상용 배포 시 WSGI(gunicorn/uwsgi) + 캐시 백엔드(Redis) 권장.
