# -*- coding: utf-8 -*-
"""
시드업 뉴스 심부름꾼 (2026-09-08)
─────────────────────────────────────────────────────────────
할 일: 텔레그램 채널 20개의 최근 글에서 "언론사 기사 링크"만 골라
      시드업 창고(수파베이스 news 표)에 저장한다. AI 안 씀, 비용 0.
흐름: ①텔레그램 읽기 → ②링크 뽑기(본문·링크서식·미리보기) → ③유튜브·X·블로그 등 뉴스 아닌 것 버림
      → ④단축주소 풀기 → ⑤같은 기사 1건으로 합침 → ⑥제목·언론사·시각과 함께 저장
      → ⑦30일 지난 뉴스 삭제
실행: 깃허브 액션이 매시간. 로컬 시험: DRY_RUN=1 python news_collect.py
비밀값: 환경변수로만 받는다 (TG_API_ID, TG_API_HASH, TG_STRING_SESSION, SEEDUP_BOT_EMAIL, SEEDUP_BOT_PW)
      — 코드·깃에 절대 안 넣는다 (CLAUDE.md 규칙 19).
"""
import html
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))
DRY_RUN = os.environ.get("DRY_RUN") == "1"
WINDOW_MIN = int(os.environ.get("WINDOW_MIN") or "75")   # 최근 몇 분치를 읽나 (1시간 주기 + 15분 겹침, 중복은 표가 걸러줌)
KEEP_DAYS = 30                                            # 보관 기간 [제안값 — 형님 확정 전]

def need(k):
    v = (os.environ.get(k) or "").strip()
    if not v:
        raise SystemExit("환경변수 없음: " + k + " — 비밀값이 없으면 멈춘다 (규칙 19)")
    return v

# ── 텔레그램 채널 (브리핑용 20개와 동일, tg-briefing daily_briefing.py CHANNELS) ──
CHANNELS = [
    -1001909745040, -1002471352838, -1003440775529, -1001600798466,
    -1002811177424, -1002249953555, -1001260023521, -1001086116949,
    -1001171797194, -1001378197756, -1001051936811, -1001932462219,
    -1001619402703, -1001589472530, -1001278234374, -1003365343708,
    -1002802623353, -1001884573458, -1001818302157, -1001868194326,
]

# ── 시드업 창고 ──
SEEDUP_URL = "https://kkhnvoedetjqshdzfaby.supabase.co"
SEEDUP_KEY = "sb_publishable_oS5QMaq2Ny8VZfw2eApMVw_AQKV4A0h"  # 사이트에 이미 공개된 클라이언트 키 — 비밀 아님

# ── 뉴스가 아닌 곳 (버림) ──
NOT_NEWS = re.compile(
    r"(^|\.)(youtube\.com|youtu\.be|t\.me|telegram\.me|x\.com|twitter\.com|instagram\.com|facebook\.com|threads\.(net|com)"
    r"|blog\.naver\.com|m\.blog\.naver\.com|cafe\.naver\.com|post\.naver\.com|tistory\.com|brunch\.co\.kr|medium\.com"
    r"|stockeasy\.intellio\.kr|kakao\.com|open\.kakao\.com|docs\.google\.com|drive\.google\.com|notion\.so|notion\.site"
    r"|dart\.fss\.or\.kr|kind\.krx\.co\.kr|finance\.naver\.com|m\.stock\.naver\.com|stock\.naver\.com|tradingview\.com"
    r"|investing\.com|smartstore\.naver\.com|coupang\.com|forms\.gle|linktr\.ee|apple\.com|play\.google\.com|github\.com"
    r"|substack\.com|google\.com|downdetector\.com|openai\.com|seoulsos\.com|shinhansec\.com|sks\.co\.kr|kiwoom\.com"
    r"|maily\.so|stibee\.com|mailchi\.mp|beehiiv\.com|us-insight\.com|gamemeca\.com|jayjoai\.com|inven\.co\.kr|ruliweb\.com|dcinside\.com|fmkorea\.com|clien\.net|ppomppu\.co\.kr|steampowered\.com|remio\.ai|notateslaapp\.com|imeritz\.com|miraeasset\.com|kbsec\.com|nhqv\.com|samsungpop\.com|hanaw\.com|daishin\.com|kiwoom\.com|truefriend\.com)$", re.I)
# 기사가 아닌 파일·첨부·홈페이지 (경로 기준)
NOT_ARTICLE_PATH = re.compile(r"(\.pdf|\.do|\.hwp|\.xlsx?|\.pptx?)($|\?)|attachmentId=|/research/|/WorkFlow/|^/?$", re.I)
# 단축주소 (원래 주소로 풀어야 하는 곳)
SHORT = re.compile(r"(^|\.)(buly\.kr|naver\.me|vo\.la|bit\.ly|han\.gl|url\.kr|t\.ly|tinyurl\.com|share\.google|goo\.gl|lrl\.kr|me2\.do|c11\.kr|zrr\.kr|abit\.ly|is\.gd|ow\.ly|dub\.sh|rb\.gy)$", re.I)

# 언론사 이름표 (없으면 도메인 그대로)
SOURCE = {
    "n.news.naver.com": "네이버뉴스", "news.naver.com": "네이버뉴스", "m.news.naver.com": "네이버뉴스",
    "biz.chosun.com": "조선비즈", "chosun.com": "조선일보", "hankyung.com": "한국경제", "mk.co.kr": "매일경제",
    "news.einfomax.co.kr": "연합인포맥스", "einfomax.co.kr": "연합인포맥스", "mt.co.kr": "머니투데이",
    "edaily.co.kr": "이데일리", "yna.co.kr": "연합뉴스", "yonhapnews.co.kr": "연합뉴스", "dt.co.kr": "디지털타임스",
    "g-enews.com": "글로벌이코노믹", "theguru.co.kr": "더구루", "newsprime.co.kr": "프라임경제", "dealsite.co.kr": "딜사이트",
    "reuters.com": "로이터", "bloomberg.com": "블룸버그", "wsj.com": "WSJ", "ft.com": "FT", "cnbc.com": "CNBC",
    "marketwatch.com": "마켓워치", "barrons.com": "배런스", "wallstreetcn.com": "월스트리트견문",
    "sedaily.com": "서울경제", "fnnews.com": "파이낸셜뉴스", "newsis.com": "뉴시스", "news1.kr": "뉴스1",
    "asiae.co.kr": "아시아경제", "heraldcorp.com": "헤럴드경제", "etnews.com": "전자신문", "thebell.co.kr": "더벨",
    "zdnet.co.kr": "지디넷코리아", "kmib.co.kr": "국민일보", "hani.co.kr": "한겨레", "joongang.co.kr": "중앙일보",
    "donga.com": "동아일보", "khan.co.kr": "경향신문", "news.mtn.co.kr": "머니투데이방송", "mtn.co.kr": "머니투데이방송",
    "infostockdaily.co.kr": "인포스탁데일리", "thelec.kr": "디일렉", "ajunews.com": "아주경제", "newspim.com": "뉴스핌",
    "ceoscoredaily.com": "CEO스코어데일리", "v.daum.net": "다음뉴스", "etoday.co.kr": "이투데이", "it.chosun.com": "IT조선",
    "kookje.co.kr": "국제신문", "financialpost.co.kr": "파이낸셜포스트", "market-ink.co.kr": "마켓인", "semafor.com": "세마포",
    "newsscene.co.kr": "뉴스씬", "catchnews.kr": "캐치뉴스", "smartbizn.com": "스마트비즈", "businesspost.co.kr": "비즈니스포스트",
    "trendforce.com": "트렌드포스", "inews24.com": "아이뉴스24", "ddaily.co.kr": "디지털데일리", "econovill.com": "이코노믹리뷰", "biz.heraldcorp.com": "헤럴드경제", "nytimes.com": "NYT", "theinformation.com": "디인포메이션",
}

URL_RE = re.compile(r"https?://[^\s<>\"'\)\]\}]+")
TRAIL = re.compile(r"[\.\,\!\?\:\;\)\]\}\>»…]+$")
UTM = ("utm_", "fbclid", "gclid", "igshid", "ref", "sfnsn", "mibextid", "share_")


def host_of(u):
    try:
        h = urllib.parse.urlsplit(u).netloc.lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def _bridge(u):
    # 네이버 앱 공유 다리주소(link.naver.com/bridge?url=...): 진짜 주소가 url= 뒤에 들어 있다
    if "link.naver.com/bridge" in u:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(u).query).get("url")
        if q:
            return q[0]
    return u


def unshorten(u):
    u = _bridge(u)
    if "link.naver.com" in u:
        return u
    try:
        r = requests.head(u, allow_redirects=True, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        f = r.url
        if not f or f == u:
            r = requests.get(u, allow_redirects=True, timeout=8, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
            r.close()
            f = r.url or u
        return _bridge(f)   # 단축주소가 네이버 다리주소로 떨어지는 경우(naver.me → link.naver.com/bridge)까지 풀기
    except Exception:
        return u


def normalize(u):
    """중복 판별용 열쇠. 네이버 모바일/PC 주소를 하나로, 추적용 꼬리(utm 등)는 뗀다."""
    p = urllib.parse.urlsplit(u)
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host in ("m.news.naver.com", "news.naver.com"):
        host = "n.news.naver.com"
    host = re.sub(r"^(view|m|mobile)\.", "", host)
    path = re.sub(r"^/mnews/", "/", p.path)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith(UTM)]
    if host == "n.news.naver.com":
        q = []  # 기사 번호는 경로에 있음 (/article/언론사/번호)
    qs = urllib.parse.urlencode(sorted(q))
    return urllib.parse.urlunsplit(("https", host, path.rstrip("/") or "/", qs, ""))


def clean_title(t):
    t = html.unescape(t or "").replace("​", "").strip()
    t = re.sub(r"[*_`]+", "", t)                       # 텔레그램 마크다운 별표 제거
    t = re.sub(r"^[^\w\[\(【'\"‘“가-힣A-Za-z0-9]+", "", t)  # 앞머리 이모지·기호 제거
    t = re.sub(r"^[①-⑳]\s*", "", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"^[\[\(【]?(속보|단독|특징주|마감시황|종합|영상)[\]\)】]?\s*", lambda m: "[" + m.group(1) + "] ", t)
    t = re.sub(r"\s*[-–|]\s*[가-힣A-Za-z0-9 ]{2,12}$", "", t) if len(t) > 30 else t   # "제목 - 언론사" 꼬리 제거
    return t[:140].strip()


def looks_like_title(t):
    """본문 문장(…다. / ~요 / 관계자는 …)이 아니라 기사 제목처럼 생겼는지"""
    t = (t or "").strip()
    if not (8 <= len(t) <= 90):
        return False
    if re.search(r"(다|요|죠|음|임|됨|함)[\.…]?$", t) and not re.search(r"[\]\)\"'”’]$", t):
        return False
    if re.match(r"^[①-⑳▪▫◦·\-•]", t) or "관계자는" in t or "밝혔다" in t or "전했다" in t:
        return False
    return True


def title_near_url(text, url):
    """주소가 있는 줄의 바로 앞(최대 2줄)에서 제목을 찾는다 — 정리방 글은 '제목 줄 / 주소 줄' 짝으로 온다."""
    lines = [ln.strip() for ln in (text or "").splitlines()]
    idx = [i for i, ln in enumerate(lines) if url in ln]
    for i in idx:
        same = URL_RE.sub("", lines[i]).strip(" -·•|:")
        if len(same) >= 8:
            return same                       # 같은 줄에 제목이 함께 있는 경우
        for j in (i - 1, i - 2):
            if j < 0:
                break
            ln = lines[j]
            if not ln or URL_RE.search(ln):
                continue
            ln = ln.strip(" -·•|:")
            if len(ln) >= 8:
                return ln
    return ""


def title_from_text(text, url):
    lines = [ln.strip() for ln in (text or "").splitlines()]
    for ln in lines:
        if not ln or url in ln or URL_RE.fullmatch(ln):
            continue
        ln = URL_RE.sub("", ln).strip(" -·•|")
        if len(ln) >= 8:
            return ln
    return ""


_fetch_budget = [40]   # 기사 페이지를 직접 열어 제목을 읽는 횟수 상한 (한 번 실행당)
def title_from_page(url):
    if _fetch_budget[0] <= 0:
        return ""
    _fetch_budget[0] -= 1
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
        raw = r.raw.read(200000, decode_content=True)
        r.close()
        for enc in ("utf-8", "euc-kr", "cp949"):
            try:
                t = raw.decode(enc); break
            except Exception:
                t = ""
        Q = "[\"']"
        m = (re.search(r"property=" + Q + "og:title" + Q + r"[^>]*content=" + Q + r"([^\"']+)", t)
             or re.search(r"content=" + Q + r"([^\"']+)" + Q + r"[^>]*property=" + Q + "og:title", t)
             or re.search(r"<title[^>]*>([^<]+)</title>", t, re.I))
        return m.group(1) if m else ""
    except Exception:
        return ""


def collect():
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.types import MessageEntityTextUrl

    since = datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MIN)
    client = TelegramClient(StringSession(need("TG_STRING_SESSION")), int(need("TG_API_ID")), need("TG_API_HASH"))
    client.connect()
    if not client.is_user_authorized():
        raise SystemExit("텔레그램 세션 만료 — 로컬에서 세션 재발급 필요")

    found = {}   # url_key → row
    n_msgs = n_links = 0
    for cid in CHANNELS:
        try:
            for m in client.iter_messages(cid, limit=300):
                if m.date < since:
                    break
                n_msgs += 1
                text = m.text or ""
                urls = []
                for u in URL_RE.findall(text):
                    urls.append(TRAIL.sub("", u))
                anchor_text = {}
                for e in (m.entities or []):
                    if isinstance(e, MessageEntityTextUrl):
                        urls.append(e.url)
                        anchor_text[e.url] = text[e.offset:e.offset + e.length].strip()
                used_titles = set()
                wp = getattr(m, "web_preview", None)
                wp_url = getattr(wp, "url", None) if wp else None
                wp_title = getattr(wp, "title", None) if wp else None
                if wp_url:
                    urls.append(wp_url)
                seen_here = set()
                for u in urls:
                    if not u.startswith("http") or u in seen_here:
                        continue
                    seen_here.add(u)
                    h = host_of(u)
                    if not h or NOT_NEWS.search(h):
                        continue
                    real = unshorten(u) if (SHORT.search(h) or "link.naver.com" in h) else u
                    h2 = host_of(real)
                    if not h2 or NOT_NEWS.search(h2) or NOT_ARTICLE_PATH.search(urllib.parse.urlsplit(real).path or "/"):
                        continue
                    key = normalize(real)
                    if key in found:
                        continue
                    # 제목 고르기 (순서): ①링크서식의 글자 ②텔레그램 미리보기 제목(기사 실제 제목)
                    #   ③주소 바로 앞 줄(제목처럼 생긴 경우만) ④글이 링크 1~2개짜리면 첫 줄(제목처럼 생긴 경우만)
                    #   ⑤그래도 없으면 기사 페이지의 제목을 직접 읽음 ⑥마지막으로 앞 줄 그대로
                    title = ""
                    if u in anchor_text and looks_like_title(anchor_text[u]):
                        title = clean_title(anchor_text[u])
                    if not title and wp_title and (wp_url == u or wp_url == real):
                        title = clean_title(wp_title)
                    near = clean_title(title_near_url(text, u))
                    if not title and looks_like_title(near):
                        title = near
                    first = clean_title(title_from_text(text, u)) if len(urls) <= 2 else ""
                    if not title and looks_like_title(first):
                        title = first
                    if not title or title in used_titles:
                        pt = clean_title(title_from_page(real))
                        if re.search(r"are you a robot|access denied|just a moment|attention required|403 forbidden|captcha|bot detection|페이지를 찾을 수 없", pt, re.I):
                            pt = ""   # 봇 차단 페이지의 제목은 기사 제목이 아니다
                        if len(pt) >= 8 and pt.lower().replace("www.", "") not in (h2, h2.split(".")[0]):
                            title = pt
                    if not title or title in used_titles:
                        head = clean_title(title_from_text(text, u))
                        if looks_like_title(head):
                            title = head
                    if not title:
                        title = near or first
                    if not title or len(title) < 8 or title in used_titles:
                        continue   # 제목을 못 만들면 회원에게 보여줄 수 없으니 버림
                    used_titles.add(title)
                    h_src = re.sub(r"^(m|view|mobile|news|www)\.", "", h2)
                    found[key] = {
                        "url_key": key, "url": real, "title": title,
                        "source": SOURCE.get(h2) or SOURCE.get(h_src) or h_src, "domain": h2,
                        "published_at": m.date.astimezone(timezone.utc).isoformat(),
                    }
                    n_links += 1
        except Exception as ex:
            print("채널 읽기 실패", cid, str(ex)[:100])
    client.disconnect()
    print("최근 {}분: 글 {}건 → 뉴스 링크 {}건".format(WINDOW_MIN, n_msgs, len(found)))
    return list(found.values())


def seedup_login():
    r = requests.post(SEEDUP_URL + "/auth/v1/token?grant_type=password",
                      headers={"apikey": SEEDUP_KEY, "Content-Type": "application/json"},
                      json={"email": need("SEEDUP_BOT_EMAIL"), "password": need("SEEDUP_BOT_PW")}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def save(rows):
    token = seedup_login()
    H = {"apikey": SEEDUP_KEY, "Authorization": "Bearer " + token, "Content-Type": "application/json"}
    # 같은 기사(url_key)는 건너뜀 — 표의 unique 제약 + ignore-duplicates
    r = requests.post(SEEDUP_URL + "/rest/v1/news?on_conflict=url_key",
                      headers=dict(H, Prefer="resolution=ignore-duplicates,return=representation"),
                      json=rows, timeout=60)
    if not r.ok:
        raise RuntimeError("저장 실패 HTTP {} {}".format(r.status_code, r.text[:200]))
    inserted = len(r.json()) if r.text.strip().startswith("[") else -1
    print("새로 저장 {}건 (중복 제외)".format(inserted))
    # 30일 지난 뉴스 청소
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()
    d = requests.delete(SEEDUP_URL + "/rest/v1/news?published_at=lt." + urllib.parse.quote(cutoff),
                        headers=dict(H, Prefer="return=representation"), timeout=60)
    print("{}일 지난 뉴스 삭제 {}건".format(KEEP_DAYS, len(d.json()) if d.ok and d.text.strip().startswith("[") else "?"))
    return inserted


def main():
    rows = collect()
    rows.sort(key=lambda r: r["published_at"])
    for r in rows:
        print(" ", r["published_at"][11:16], "|", r["source"], "|", r["title"][:60], "|", r["url"][:70])
    if DRY_RUN:
        print("DRY_RUN — 저장 안 함")
        return
    if not rows:
        print("저장할 뉴스 없음")
        return
    save(rows)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
