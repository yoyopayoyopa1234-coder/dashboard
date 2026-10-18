"""매일 시세·M2를 받아 data.json으로 저장 (GitHub Actions에서 실행)."""
import csv, io, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

LOG = []
def get(url, tries=2, uas=({"User-Agent": "curl/8.5.0"}, UA)):
    last = None
    for ua in uas:
        for i in range(tries):
            t0 = time.time()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=20) as r:
                    return r.read().decode()
            except Exception as e:
                last = e
                LOG.append(f"{url[:70]} ua={ua['User-Agent'][:12]} {type(e).__name__}:{e} {time.time()-t0:.0f}s")
                time.sleep(2)
    raise last

def yahoo(sym, iv, rng=None):
    j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng or {"1wk": "10y", "1d": "5y", "1mo": "20y"}.get(iv, "max")}&interval={iv}"))
    res = j["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(res["timestamp"]):
        if q["close"][i] is None:
            continue
        out.append([t, *(round(q[k][i], 4) if q[k][i] is not None else q["close"][i] for k in ("open", "high", "low", "close"))])
    # Yahoo가 진행 중인 봉을 한 번 더 붙여 보내는 경우 → 직전 봉에 합침 (TradingView와 값 일치)
    if len(out) >= 2:
        a, b = out[-2], out[-1]
        da, db = datetime.fromtimestamp(a[0], timezone.utc), datetime.fromtimestamp(b[0], timezone.utc)
        same = ((iv == "1mo" and (da.year, da.month) == (db.year, db.month)) or
                (iv == "1wk" and (db - da).days < 7) or (iv == "1d" and da.date() == db.date()))
        if same:
            out[-2:] = [[a[0], a[1], max(a[2], b[2]), min(a[3], b[3]), b[4]]]
    # 마지막 봉 종가가 빈 값으로 오는 경우 → 실시간 시세(meta)로 채움 (하루 전 가격으로 되돌아가는 오류 방지)
    meta = res.get("meta", {})
    px, mt = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if px and mt and out and mt > out[-1][0]:
        dl, dm = datetime.fromtimestamp(out[-1][0], timezone.utc), datetime.fromtimestamp(mt, timezone.utc)
        same = ((iv == "1mo" and (dl.year, dl.month) == (dm.year, dm.month)) or
                (iv == "1wk" and (dm - dl).days < 7) or (iv == "1d" and dl.date() == dm.date()))
        if same:
            last = out[-1]; last[4] = round(px, 4); last[2] = max(last[2], px); last[3] = min(last[3], px)
        else:
            hi_ = meta.get("regularMarketDayHigh") or px; lo_ = meta.get("regularMarketDayLow") or px
            out.append([mt, round(px, 4), round(max(hi_, px), 4), round(min(lo_, px), 4), round(px, 4)])
    return out  # [unix, o, h, l, c]

def fred(sid):
    rows = list(csv.reader(io.StringIO(get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"))))[1:]
    return {d[:7]: float(v) for d, v in rows if v not in (".", "")}

def ecb_m2():
    txt = get("https://data-api.ecb.europa.eu/service/data/BSI/M.U2.Y.V.M20.X.1.U2.2300.Z01.E?format=csvdata&startPeriod=2010-01")
    r = list(csv.DictReader(io.StringIO(txt)))
    return {x["TIME_PERIOD"][:7]: float(x["OBS_VALUE"]) * 1e6 for x in r if x.get("OBS_VALUE")}

def dbnomics(code):
    j = json.loads(get(f"https://api.db.nomics.world/v22/series/{code}?observations=1&format=json"))
    doc = j["series"]["docs"][0]
    return {p[:7]: float(v) for p, v in zip(doc["period"], doc["value"]) if v not in (None, "NA") and isinstance(v, (int, float))}

def boj(code):
    j = json.loads(get(f"https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=json&lang=en&db=MD02&code={code}&startDate=201001"))
    out = {}
    for res in j.get("RESULTSET", []):
        vals = res.get("VALUES", {})
        for d, v in zip(vals.get("SURVEY_DATES", []), vals.get("VALUES", [])):
            if v not in (None, ""): out[f"{str(d)[:4]}-{str(d)[4:6]}"] = float(v)
    return out

def boe(code):
    url = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes"
           f"&Datefrom=01/Jan/2010&Dateto=now&SeriesCodes={code}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
    rows = list(csv.reader(io.StringIO(get(url))))[1:]
    out = {}
    for r in rows:
        if len(r) < 2 or not r[1].strip(): continue
        d = datetime.strptime(r[0].strip(), "%d %b %Y")
        out[d.strftime("%Y-%m")] = float(r[1])
    return out


def nbs_m2():
    """중국 국가통계국 직접 조회 (2010년~), 단위 億元"""
    import urllib.parse
    dfw = json.dumps([{"wdcode": "zb", "valuecode": "A0D01"}, {"wdcode": "sj", "valuecode": "2010-"}], separators=(",", ":"))
    url = ("https://data.stats.gov.cn/easyquery.htm?m=QueryData&dbcode=hgyd&rowcode=zb&colcode=sj&wds=%5B%5D&dfwds="
           + urllib.parse.quote(dfw) + f"&k1={int(time.time()*1000)}")
    j = json.loads(get(url))
    out = {}
    for n in j["returndata"]["datanodes"]:
        code = n["code"]  # zb.A0D0101_sj.202608
        if "A0D0101_" not in code or not n["data"]["hasdata"]: continue
        ym = code.split("sj.")[1]; out[f"{ym[:4]}-{ym[4:6]}"] = float(n["data"]["data"])
    return out

def probe_dbnomics():
    for q in ("IMF/IFS?q=china%20broad%20money", "IMF/IFS?q=china%20money%20supply%20M2", "IMF/MFS_MA?q=china"):
        try:
            j = json.loads(get(f"https://api.db.nomics.world/v22/series/{q}&observations=0&limit=8&format=json", tries=1))
            docs = j.get("series", {}).get("docs", [])
            LOG.append("probe " + q + " → " + " | ".join(f"{d.get('series_code')}:{d.get('series_name','')[:50]}" for d in docs))
        except Exception as e:
            LOG.append(f"probe {q} fail {e}")


def cn_merged():
    """중국 M2: 여러 소스를 이어붙임 (뒤쪽 소스가 우선). 각 소스 단위는 normalize로 맞춤"""
    parts = []
    for nm, fn in (("FRED", lambda: fred("MYAGM2CNM189N")), ("IFS", lambda: dbnomics("IMF/IFS/M.CN.FDSB_XDC")),
                   ("IFS2", lambda: dbnomics("IMF/IFS/M.CN.FDSBM_XDC")), ("NBS", lambda: dbnomics("NBS/M_A0D01/A0D0101"))):
        try:
            m = normalize(fn(), "CN"); parts.append(m)
            LOG.append(f"CN part {nm} {min(m)}~{max(m)} n={len(m)}")
        except Exception as e:
            LOG.append(f"CN part {nm} fail {str(e)[:80]}")
    out = {}
    for m in parts: out.update(m)
    if not out: raise ValueError("CN 소스 없음")
    return out

# 나라별 M2(현지 통화) 정상 크기 범위 — 원자료 단위(백만·십억)를 자동 보정
SCALE = {"US": (1e13, 1e14), "EU": (8e12, 4e13), "CN": (1e14, 1e15), "JP": (8e14, 4e15), "GB": (1e12, 1e13)}
def normalize(m, name):
    lo, hi = SCALE[name]; v = m[max(m)]
    for mul in (1, 1e3, 1e4, 1e6, 1e8, 1e9, 1e12):
        if lo <= v * mul <= hi:
            return {k: x * mul for k, x in m.items()}
    raise ValueError(f"{name} 단위 판별 실패 (마지막 값 {v})")

def add_months(k, n):
    y, m = int(k[:4]), int(k[5:7]) + n
    y += (m - 1) // 12; m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"

def months_between(a, b):
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])

def fill_gaps(m, notes, name):
    """중간 빈 달만 기하 보간 (미래 연장은 하지 않음 — TradingView처럼 최신 발표값을 유지)"""
    ks = sorted(m); out = dict(m)
    for k1, k2 in zip(ks, ks[1:]):
        n = months_between(k1, k2)
        if n > 1:
            g = (m[k2] / m[k1]) ** (1 / n)
            for j in range(1, n): out[add_months(k1, j)] = m[k1] * g ** j
            if n > 3: notes.append(f"{name} {add_months(k1, 1)}~{add_months(k2, -1)} 보간")
    return out

def global_m2():
    """TradingView Global M2 방식: 각국 M2(현지통화, 최신 발표값 유지) × 일별 환율 → 달러 합계"""
    countries = [
        ("US", [lambda: fred("M2SL")], None),
        ("EU", [ecb_m2, lambda: dbnomics("ECB/BSI/M.U2.Y.V.M20.X.1.U2.2300.Z01.E")], ("EURUSD=X", False)),
        ("CN", [cn_merged], ("CNY=X", True)),
        ("JP", [lambda: boj("MAM1NAM2M2MO"), lambda: dbnomics("BOJ/MD02/MAM1NAM2M2MO")], ("JPY=X", True)),
        ("GB", [lambda: boe("LPMAUYN"), lambda: dbnomics("BOE/6/LPMAUYN")], ("GBPUSD=X", False)),
    ]
    now = datetime.now(timezone.utc).strftime("%Y-%m")
    notes, local = [], []
    for name, cands, fx in countries:
        for ci, loader in enumerate(cands):
            try:
                m = normalize(loader(), name); last = max(m)
                LOG.append(f"M2 {name}#{ci} ok {min(m)}~{last} n={len(m)}")
                if last < add_months(now, -12): continue
                if last < add_months(now, -3): notes.append(f"{name} {last} 이후 미발표(최신값 유지)")
                local.append((name, fill_gaps(m, notes, name), fx)); break
            except Exception as e:
                LOG.append(f"M2 {name}#{ci} fail: {type(e).__name__}: {str(e)[:120]}")
    if not local:
        return {"rows": [], "n": 0, "countries": [], "notes": notes}
    # 일별 환율 (Yahoo)
    fxd = {}
    for name, m, fx in local:
        if fx:
            r = yahoo(fx[0], "1d")
            fxd[name] = {datetime.fromtimestamp(x[0], timezone.utc).strftime("%Y-%m-%d"): x[4] for x in r}
    days = sorted(set().union(*[set(v) for v in fxd.values()])) if fxd else []
    days = [d for d in days if d >= "2016-01-01"]
    rows, lastfx = [], {}
    for d in days:
        mk, tot, ok = d[:7], 0.0, True
        for name, m, fx in local:
            keys = [k for k in m if k <= mk]
            if not keys: ok = False; break
            v = m[max(keys)]                       # 그 달 또는 가장 최근 발표값
            if fx:
                rate = fxd[name].get(d, lastfx.get(name))
                if rate is None: ok = False; break
                lastfx[name] = rate
                v = v / rate if fx[1] else v * rate
            tot += v
        if ok: rows.append([d, round(tot / 1e12, 3)])
    return {"rows": rows, "n": len(local), "countries": [n_ for n_, *_ in local], "notes": notes, "freq": "daily"}

def main():
    data = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "ohlc": {}}
    for key, sym, iv in [("MSTR_1d", "MSTR", "1d"), ("MSTR_1wk", "MSTR", "1wk"), ("MSTR_1mo", "MSTR", "1mo"), ("BTC_1mo", "BTC-USD", "1mo")]:
        try:
            data["ohlc"][key] = yahoo(sym, iv)
            r = data["ohlc"][key]
            if iv == "1mo" and len(r) > 3 and (r[-2][0] - r[-3][0]) > 45 * 86400:
                LOG.append(f"{key}: 월봉 간격 이상(분기봉 의심)")
            print(key, len(data["ohlc"][key]))
        except Exception as e:
            print("FAIL", key, e)
    try:
        from tv_m2 import global_m2 as tv_global_m2
        data["m2"] = tv_global_m2(LOG.append)
    except Exception as e:
        LOG.append(f"TradingView M2 실패 → 자체 계산 사용: {str(e)[:150]}")
        data["m2"] = global_m2()
    data["log"] = LOG[-40:]
    print("M2 rows", len(data["m2"]["rows"]), data["m2"]["countries"])
    if not all(k in data["ohlc"] for k in ("MSTR_1d", "MSTR_1wk", "MSTR_1mo")):
        raise SystemExit("일부 시세를 받지 못함 — 기존 data.json 유지")
    with open("data.json", "w") as f:
        json.dump(data, f, separators=(",", ":"))


if __name__ == "__main__":
    main()
