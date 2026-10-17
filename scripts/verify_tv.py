"""참고 사이트(AgiTQ)와 TradingView 공개 페이지를 열어 수치를 텍스트로 저장 (검증용)."""
import json, os, re, time
from playwright.sync_api import sync_playwright
OUT = "captures"; os.makedirs(OUT, exist_ok=True)
PAGES = [
    ("agitq", "https://0x7f-core.github.io/AgiTQ-Android/", 25),
    ("tv_spx_tech", "https://www.tradingview.com/symbols/SP-SPX/technicals/", 15),
    ("tv_qqq_tech", "https://www.tradingview.com/symbols/NASDAQ-QQQ/technicals/", 15),
    ("tv_tqqq_tech", "https://www.tradingview.com/symbols/NASDAQ-TQQQ/technicals/", 15),
    ("tv_spx", "https://www.tradingview.com/symbols/SP-SPX/", 10),
    ("tv_qqq", "https://www.tradingview.com/symbols/NASDAQ-QQQ/", 10),
    ("tv_tqqq", "https://www.tradingview.com/symbols/NASDAQ-TQQQ/", 10),
]
res = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 2200}, locale="en-US",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
    pg = ctx.new_page()
    for name, url, wait in PAGES:
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=60000); time.sleep(wait)
            if "technicals" in url:
                for lab in ("1 day", "1D"):
                    try: pg.get_by_role("button", name=lab).first.click(timeout=2000); time.sleep(3); break
                    except Exception: pass
            txt = pg.evaluate("() => document.body.innerText")
            res[name] = {"url": url, "text": re.sub(r"[ \t]+", " ", txt)[:20000]}
            pg.screenshot(path=f"{OUT}/{name}.png", full_page=False)
        except Exception as e:
            res[name] = {"url": url, "error": str(e)[:300]}
    b.close()
res["_at"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
json.dump(res, open(f"{OUT}/verify.json", "w"), ensure_ascii=False, indent=1)
print({k: (len(v.get("text", "")) if isinstance(v, dict) else v) for k, v in res.items()})
