"""TradingView 저장 레이아웃을 Playwright로 열어 캡처 + 범례 지표값 추출."""
import json, os, re, time
from playwright.sync_api import sync_playwright

TARGETS = [
    # (이름, 레이아웃, 심볼, 주기)  주기 None이면 레이아웃 저장값 사용
    ("mstr_rsi_vix",  "soC8M4NK", "NASDAQ:MSTR", None),
    ("ndx_rsi_vix",   "soC8M4NK", "NASDAQ:NDX",  None),
    ("mstr_bb_vix",   "VDpQAf5w", "NASDAQ:MSTR", None),
    ("tqqq_bb_vix",   "VDpQAf5w", "NASDAQ:TQQQ", None),
    ("mstr_m2",       "fyJI5SCU", "NASDAQ:MSTR", None),
    ("ndx_m2",        "fyJI5SCU", "NASDAQ:NDX",  None),
]
OUT = "captures"; os.makedirs(OUT, exist_ok=True)

LEGEND_JS = r"""
() => {
  const pick = sel => [...document.querySelectorAll(sel)].map(e => e.innerText.replace(/\s+/g,' ').trim()).filter(Boolean);
  return {
    title: document.title,
    url: location.href,
    sources: pick('[data-name="legend-source-item"]'),
    series: pick('[data-name="legend-series-item"]'),
    legendAny: pick('[class*="legend"]').slice(0, 40),
    loginWall: !!document.querySelector('[data-name="header-user-menu-sign-in"], button[name="header-user-menu-sign-in"]'),
  };
}
"""

def run():
    res = {}
    sid, sign = os.environ.get("TV_SESSIONID"), os.environ.get("TV_SESSIONID_SIGN")
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(viewport={"width": 1100, "height": 1300}, device_scale_factor=1, locale="ko-KR",
                            timezone_id="Asia/Seoul",
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
        if sid:
            ck = [{"name": "sessionid", "value": sid, "domain": ".tradingview.com", "path": "/", "secure": True, "httpOnly": True}]
            if sign: ck.append({"name": "sessionid_sign", "value": sign, "domain": ".tradingview.com", "path": "/", "secure": True, "httpOnly": True})
            ctx.add_cookies(ck)
        page = ctx.new_page()
        for name, layout, sym, iv in TARGETS:
            url = f"https://kr.tradingview.com/chart/{layout}/?symbol={sym.replace(':', '%3A')}" + (f"&interval={iv}" if iv else "")
            t0 = time.time()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try: page.wait_for_selector('[data-name="legend-source-item"], [data-name="legend-series-item"]', timeout=40000)
                except Exception: pass
                time.sleep(8)  # 지표 계산 대기
                # 팝업/쿠키 배너 닫기
                for sel in ['button[aria-label="Close"]', '[data-name="close"]', 'button:has-text("Accept")', 'button:has-text("동의")']:
                    try:
                        for el in page.query_selector_all(sel)[:3]: el.click(timeout=1000)
                    except Exception: pass
                page.mouse.move(5, 5)
                info = page.evaluate(LEGEND_JS)
                page.screenshot(path=f"{OUT}/{name}.png")
                info["secs"] = round(time.time() - t0)
                res[name] = info
            except Exception as e:
                res[name] = {"error": str(e)[:300], "url": url}
                try: page.screenshot(path=f"{OUT}/{name}.png")
                except Exception: pass
        b.close()
    res["_meta"] = {"logged_in_cookie": bool(sid), "at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    json.dump(res, open(f"{OUT}/legend.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False)[:3000])

if __name__ == "__main__":
    run()
