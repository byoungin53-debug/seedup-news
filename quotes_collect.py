# -*- coding: utf-8 -*-
"""
시드업 홈 「오늘의 증시」 지수 띠용 시세 수집기 (2026-09-08, 형님 결정: 시안 3 · 코스피·코스닥·S&P500·나스닥·다우 · 업데이트 되게)
네이버 금융 공개 시세(무료, AI 없음)를 받아 시드업 저장소 resources/market/quotes.json 에 쓴다. 30분마다 깃허브 액션이 실행.
브라우저는 네이버를 직접 못 부르므로(교차 출처 차단 확인) 이 파일을 거친다.
비밀값: SEEDUP_BOT_EMAIL, SEEDUP_BOT_PW (환경변수, 코드에 없음)
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))
SEEDUP_URL = "https://kkhnvoedetjqshdzfaby.supabase.co"
SEEDUP_KEY = "sb_publishable_oS5QMaq2Ny8VZfw2eApMVw_AQKV4A0h"  # 사이트에 공개된 클라이언트 키 — 비밀 아님
OBJ = "market/quotes.json"
NH = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}
INDEXES = [  # (표시 이름, 네이버 경로, 국내/해외)
    ("코스피", "domestic/index/KOSPI", "kr"),
    ("코스닥", "domestic/index/KOSDAQ", "kr"),
    ("S&P500", "worldstock/index/.INX", "us"),
    ("나스닥", "worldstock/index/.IXIC", "us"),
    ("다우", "worldstock/index/.DJI", "us"),
]


def need(k):
    v = (os.environ.get(k) or "").strip()
    if not v:
        raise SystemExit("환경변수 없음: " + k)
    return v


def fetch_one(name, path, region):
    r = requests.get("https://polling.finance.naver.com/api/realtime/" + path, headers=NH, timeout=15)
    r.raise_for_status()
    d = (r.json().get("datas") or [None])[0]
    if not d or not d.get("closePrice"):
        raise RuntimeError(name + " 시세 없음")
    return {"name": name, "region": region, "price": d.get("closePrice"),
            "change": d.get("compareToPreviousClosePrice"), "rate": float(d.get("fluctuationsRatio") or 0),
            "status": d.get("marketStatus"), "traded_at": d.get("localTradedAt")}


def main():
    rows, errs = [], []
    for name, path, region in INDEXES:
        try:
            rows.append(fetch_one(name, path, region))
        except Exception as ex:
            errs.append(name + ": " + str(ex)[:80])
    if len(rows) < 3:
        raise SystemExit("시세 대부분 실패 — 저장 안 함: " + "; ".join(errs))
    data = {"fetched_at": datetime.now(KST).isoformat(timespec="seconds"), "items": rows, "errors": errs}
    token = requests.post(SEEDUP_URL + "/auth/v1/token?grant_type=password",
                          headers={"apikey": SEEDUP_KEY, "Content-Type": "application/json"},
                          json={"email": need("SEEDUP_BOT_EMAIL"), "password": need("SEEDUP_BOT_PW")}, timeout=30)
    token.raise_for_status()
    tok = token.json()["access_token"]
    H = {"apikey": SEEDUP_KEY, "Authorization": "Bearer " + tok}
    requests.delete(SEEDUP_URL + "/storage/v1/object/resources/" + OBJ, headers=H, timeout=30)
    up = requests.post(SEEDUP_URL + "/storage/v1/object/resources/" + OBJ,
                       headers=dict(H, **{"Content-Type": "application/json"}),
                       data=json.dumps(data, ensure_ascii=False).encode("utf-8"), timeout=60)
    if not up.ok:
        raise SystemExit("저장 실패 HTTP {} {}".format(up.status_code, up.text[:150]))
    # 재확인
    s = requests.post(SEEDUP_URL + "/storage/v1/object/sign/resources/" + OBJ,
                      headers=dict(H, **{"Content-Type": "application/json"}), json={"expiresIn": 120}, timeout=30)
    back = requests.get(SEEDUP_URL + "/storage/v1" + s.json()["signedURL"], timeout=30).json()
    if back.get("fetched_at") != data["fetched_at"]:
        raise SystemExit("저장 후 재확인 불일치")
    print("시세 저장 완료", data["fetched_at"], " | ".join("{} {} ({:+.2f}%)".format(r["name"], r["price"], r["rate"]) for r in rows),
          ("| 실패: " + "; ".join(errs)) if errs else "")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
