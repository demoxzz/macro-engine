#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yfetch.py — fetcher Yahoo Finance (futures continus), caché, numpy-only.
Endpoint v8/finance/chart (JSON, sans clé). Cache CSV dans /tmp/yfcache/.
Renvoie un dict {date 'YYYY-MM-DD': close} comme qstat.fetch pour FRED.

Univers oil tradable : CL=F (WTI), BZ=F (Brent), HO=F (Heating Oil), RB=F (RBOB).
ATTENTION : séries CONTINUES front-month -> roll gaps (voir detect_roll_gaps).
"""
import urllib.request, json, os, sys, datetime as dt

CACHE = "/tmp/yfcache"; os.makedirs(CACHE, exist_ok=True)
HDR = {"User-Agent": "Mozilla/5.0"}


def fetch(sym):
    """Yahoo daily close, caché. {date: close}."""
    fp = os.path.join(CACHE, sym.replace("=", "_") + ".csv")
    if not os.path.exists(fp) or os.path.getsize(fp) < 50:
        u = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
             f"?period1=0&period2=9999999999&interval=1d")
        try:
            j = json.loads(urllib.request.urlopen(
                urllib.request.Request(u, headers=HDR), timeout=30).read())
            r = j["chart"]["result"][0]
            ts = r["timestamp"]; ind = r["indicators"]
            # actions -> adjclose (splits + dividendes) ; futures -> close brut
            if "adjclose" in ind and ind["adjclose"][0].get("adjclose"):
                cl = ind["adjclose"][0]["adjclose"]
            else:
                cl = ind["quote"][0]["close"]
            with open(fp, "w") as f:
                f.write("Date,Close\n")
                for t, c in zip(ts, cl):
                    if c is None:
                        continue
                    f.write(f"{dt.date.fromtimestamp(t).isoformat()},{c}\n")
        except Exception as e:
            print(f"    ! fetch {sym} echoue: {e}", file=sys.stderr); return {}
    d = {}
    with open(fp) as f:
        next(f, None)
        for line in f:
            p = line.strip().split(",")
            if len(p) < 2:
                continue
            try:
                d[p[0]] = float(p[1])
            except Exception:
                pass
    return d


if __name__ == "__main__":
    for s in ["CL=F", "BZ=F", "HO=F", "RB=F"]:
        x = fetch(s)
        ks = sorted(x)
        print(f"{s:6} n={len(x):6}  {ks[0]} .. {ks[-1]}")
