# seedup-news — 시드업 뉴스 심부름꾼

텔레그램 채널에 사람들이 올린 **언론사 기사 링크**만 골라 3시간마다 시드업 회원사이트 창고(Supabase `news` 표)에 저장한다.
링크 수집에는 AI를 쓰지 않는다(TOP3 선정에만 하이쿠 4.5 사용). 뉴스 본문을 복사하지 않고 **제목·언론사·시각·링크**만 저장한다.

- 실행: GitHub Actions `news.yml` (3시간마다 07분, 한국 09·12·15·18·21·00·03·06시)
- TOP3: 실행마다 새 기사 3건 이상이면 Claude Haiku 4.5가 최근 24시간 기사 중 3개 선정 → 저장소 `market/news_top3.json` (Secrets `ANTHROPIC_API_KEY`)
- 비밀값: 저장소 Settings → Secrets (`TG_API_ID`, `TG_API_HASH`, `TG_STRING_SESSION`, `SEEDUP_BOT_EMAIL`, `SEEDUP_BOT_PW`) — 코드에 없다
- 보관: 30일 지난 뉴스는 실행 때마다 삭제
- 로컬 시험: `DRY_RUN=1 WINDOW_MIN=1440 python news_collect.py` (저장 안 하고 목록만 출력)
