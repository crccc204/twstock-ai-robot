#!/usr/bin/env python3
"""
Taiwan Stock NT$100,000 Autonomous Paper-Trading AI Robot (v4 — 5-Layer Quant + Gemini LLM Analyst)
==================================================================================================
Hybrid Institutional Architecture:
  [Deterministic Code — Execution & Risk Discipline]
  1. Market Regime Gate (0050 vs MA20 & MA60): BULL=4 slots, CAUTION=2 slots, BEAR=0 new buys.
  2. Official Fundamentals (TWSE + TPEx OpenAPI): Monthly Revenue YoY%, PE, Dividend Yield.
  3. Official Daily Institutional Chips (TWSE T86 + TPEx 3-Insti): Foreign + Trust net lots!
  4. 65-Stock 12-Sector Trend & Risk-Adjusted Momentum (RS20 / ATR% + CMF10 + RSI 48-74).
  5. Strict T+1 Through-Fill Execution: Buy fills ONLY if Low <= Limit - 2*Tick;
     TP fills ONLY if High >= TP + 1*Tick; SL fills conservatively on Low <= SL.

  [Daily Single-Call Gemini LLM Research Agent — Semantic Analysis & Guru Tracker]
  - Replaces brittle keyword counting with true LLM semantic news reading (1 API call/day!).
  - Selects 3-5 favored stocks from the 65-stock pool with clear reasons & risks.
  - Summarizes Foreign Institutional flows & Global Investing Gurus (Buffett / 13F / Wall St).
  - Flags genuine semantic red-flag events without ever overriding hard risk rules.
  - Reads GEMINI_API_KEY securely from environment (GitHub Secrets) — never hardcoded!
"""
import concurrent.futures
import csv
import datetime
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
os.makedirs(DOCS_DIR, exist_ok=True)
STATE_FILE = os.path.join(DOCS_DIR, "portfolio_state.json")
TRADES_CSV = os.path.join(DOCS_DIR, "trade_history.csv")
EQUITY_CSV = os.path.join(DOCS_DIR, "daily_equity_log.csv")

START_CAPITAL = 100_000.0
FEE_RATE = 0.001425
TAX_STOCK = 0.003
SLIPPAGE = 0.001
MAX_POSITIONS = 4
MAX_PER_SECTOR = 2

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

UNIVERSE: Dict[str, Dict[str, str]] = {
    # 半導體與晶圓封測
    "2330": {"name": "台積電", "sym": "2330.TW", "sector": "半導體"},
    "2303": {"name": "聯電", "sym": "2303.TW", "sector": "半導體"},
    "3711": {"name": "日月光投控", "sym": "3711.TW", "sector": "半導體"},
    "2449": {"name": "京元電子", "sym": "2449.TW", "sector": "半導體"},
    "6239": {"name": "力成", "sym": "6239.TW", "sector": "半導體"},
    "5347": {"name": "世界", "sym": "5347.TWO", "sector": "半導體"},
    "6488": {"name": "環球晶", "sym": "6488.TWO", "sector": "半導體"},
    # IC設計與IP
    "2454": {"name": "聯發科", "sym": "2454.TW", "sector": "IC設計"},
    "3034": {"name": "聯詠", "sym": "3034.TW", "sector": "IC設計"},
    "2379": {"name": "瑞昱", "sym": "2379.TW", "sector": "IC設計"},
    "3661": {"name": "世芯-KY", "sym": "3661.TW", "sector": "IC設計"},
    "3443": {"name": "創意", "sym": "3443.TW", "sector": "IC設計"},
    "5269": {"name": "祥碩", "sym": "5269.TW", "sector": "IC設計"},
    "3529": {"name": "力旺", "sym": "3529.TWO", "sector": "IC設計"},
    "8299": {"name": "群聯", "sym": "8299.TWO", "sector": "IC設計"},
    # AI伺服器與電腦代工
    "2317": {"name": "鴻海", "sym": "2317.TW", "sector": "AI伺服器"},
    "2382": {"name": "廣達", "sym": "2382.TW", "sector": "AI伺服器"},
    "3231": {"name": "緯創", "sym": "3231.TW", "sector": "AI伺服器"},
    "6669": {"name": "緯穎", "sym": "6669.TW", "sector": "AI伺服器"},
    "2357": {"name": "華碩", "sym": "2357.TW", "sector": "AI伺服器"},
    "2376": {"name": "技嘉", "sym": "2376.TW", "sector": "AI伺服器"},
    "2356": {"name": "英業達", "sym": "2356.TW", "sector": "AI伺服器"},
    "4938": {"name": "和碩", "sym": "4938.TW", "sector": "AI伺服器"},
    "2395": {"name": "研華", "sym": "2395.TW", "sector": "AI伺服器"},
    "2059": {"name": "川湖", "sym": "2059.TW", "sector": "AI伺服器"},
    # 散熱・PCB・載板
    "3017": {"name": "奇鋐", "sym": "3017.TW", "sector": "散熱PCB"},
    "3324": {"name": "雙鴻", "sym": "3324.TWO", "sector": "散熱PCB"},
    "3653": {"name": "健策", "sym": "3653.TW", "sector": "散熱PCB"},
    "2383": {"name": "台光電", "sym": "2383.TW", "sector": "散熱PCB"},
    "2368": {"name": "金像電", "sym": "2368.TW", "sector": "散熱PCB"},
    "3037": {"name": "欣興", "sym": "3037.TW", "sector": "散熱PCB"},
    "8046": {"name": "南電", "sym": "8046.TW", "sector": "散熱PCB"},
    "6274": {"name": "台燿", "sym": "6274.TWO", "sector": "散熱PCB"},
    # 網通與光通訊
    "2345": {"name": "智邦", "sym": "2345.TW", "sector": "網通光通訊"},
    "6285": {"name": "啟碁", "sym": "6285.TW", "sector": "網通光通訊"},
    "3596": {"name": "智易", "sym": "3596.TW", "sector": "網通光通訊"},
    "3450": {"name": "聯鈞", "sym": "3450.TW", "sector": "網通光通訊"},
    "4979": {"name": "華星光", "sym": "4979.TWO", "sector": "網通光通訊"},
    # 電源・重電・機械
    "2308": {"name": "台達電", "sym": "2308.TW", "sector": "電源重電"},
    "2301": {"name": "光寶科", "sym": "2301.TW", "sector": "電源重電"},
    "1519": {"name": "華城", "sym": "1519.TW", "sector": "電源重電"},
    "1513": {"name": "中興電", "sym": "1513.TW", "sector": "電源重電"},
    "1503": {"name": "士電", "sym": "1503.TW", "sector": "電源重電"},
    "1590": {"name": "亞德客-KY", "sym": "1590.TW", "sector": "電源重電"},
    "2049": {"name": "上銀", "sym": "2049.TW", "sector": "電源重電"},
    # 光學與被動元件
    "3008": {"name": "大立光", "sym": "3008.TW", "sector": "光學被動"},
    "2327": {"name": "國巨", "sym": "2327.TW", "sector": "光學被動"},
    "8069": {"name": "元太", "sym": "8069.TWO", "sector": "光學被動"},
    # 金融金控
    "2881": {"name": "富邦金", "sym": "2881.TW", "sector": "金融金控"},
    "2882": {"name": "國泰金", "sym": "2882.TW", "sector": "金融金控"},
    "2891": {"name": "中信金", "sym": "2891.TW", "sector": "金融金控"},
    "2886": {"name": "兆豐金", "sym": "2886.TW", "sector": "金融金控"},
    "2884": {"name": "玉山金", "sym": "2884.TW", "sector": "金融金控"},
    "2885": {"name": "元大金", "sym": "2885.TW", "sector": "金融金控"},
    "2890": {"name": "永豐金", "sym": "2890.TW", "sector": "金融金控"},
    "2892": {"name": "第一金", "sym": "2892.TW", "sector": "金融金控"},
    # 航運與航空
    "2603": {"name": "長榮", "sym": "2603.TW", "sector": "航運航空"},
    "2609": {"name": "陽明", "sym": "2609.TW", "sector": "航運航空"},
    "2615": {"name": "萬海", "sym": "2615.TW", "sector": "航運航空"},
    "2618": {"name": "長榮航", "sym": "2618.TW", "sector": "航運航空"},
    # 電信與防禦內需
    "2412": {"name": "中華電", "sym": "2412.TW", "sector": "電信內需"},
    "3045": {"name": "台灣大", "sym": "3045.TW", "sector": "電信內需"},
    "4904": {"name": "遠傳", "sym": "4904.TW", "sector": "電信內需"},
    "1216": {"name": "統一", "sym": "1216.TW", "sector": "電信內需"},
    # 傳產龍頭
    "2207": {"name": "和泰車", "sym": "2207.TW", "sector": "傳產工業"},
}


def get_twse_tick(price: float) -> float:
    if price < 10.0: return 0.01
    if price < 50.0: return 0.05
    if price < 100.0: return 0.10
    if price < 500.0: return 0.50
    if price < 1000.0: return 1.00
    return 5.00


def round_twse_tick(price: float) -> float:
    p = max(0.01, float(price))
    t = get_twse_tick(p)
    r = round(p / t) * t
    dec = 2 if t < 0.1 else (1 if t < 1.0 else 0)
    return round(r, dec)


def parse_num(val) -> Optional[float]:
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace("+", "").replace("X", "")
    if not s or s in ("-", "--", "---", "----", "N/A", "NaN"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def http_get_json(url: str, timeout: int = 14):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def fetch_rss_headlines(query: str, limit: int = 4) -> List[str]:
    try:
        q = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=6) as resp:
            root = ET.fromstring(resp.read())
        return [item.findtext("title", "").strip() for item in root.findall(".//item")[:limit] if item.findtext("title")]
    except Exception:
        return []


def fetch_official_fundamentals() -> Dict[str, dict]:
    """Fetch official TWSE + TPEx PE, Dividend Yield, PB, and Monthly Revenue YoY%."""
    urls = {
        "twse_val": "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
        "twse_rev": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
        "tpex_val": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
        "tpex_rev": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",
    }
    raw = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(http_get_json, u, 14): k for k, u in urls.items()}
        for f in concurrent.futures.as_completed(futs):
            k = futs[f]
            try:
                raw[k] = f.result() or []
            except Exception as exc:
                print(f"[Fundamentals] Warning {k}: {exc}")
                raw[k] = []

    fund: Dict[str, dict] = {}
    for r in raw.get("twse_val", []):
        c = str(r.get("Code", "")).strip()
        if c in UNIVERSE:
            fund.setdefault(c, {})
            fund[c]["pe"] = parse_num(r.get("PEratio"))
            fund[c]["dy"] = parse_num(r.get("DividendYield"))
            fund[c]["pb"] = parse_num(r.get("PBratio"))

    for r in raw.get("tpex_val", []):
        c = str(r.get("SecuritiesCompanyCode", "")).strip()
        if c in UNIVERSE:
            fund.setdefault(c, {})
            fund[c]["pe"] = parse_num(r.get("PriceEarningRatio"))
            fund[c]["dy"] = parse_num(r.get("YieldRatio"))
            fund[c]["pb"] = parse_num(r.get("PriceBookRatio"))

    for key in ("twse_rev", "tpex_rev"):
        for r in raw.get(key, []):
            c = str(r.get("公司代號", "")).strip()
            if c in UNIVERSE:
                fund.setdefault(c, {})
                fund[c]["rev_yoy"] = parse_num(r.get("營業收入-去年同月增減(%)"))

    return fund


def fetch_institutional_chips() -> Dict[str, dict]:
    """
    Fetch official daily Foreign Investor (外資) & Investment Trust (投信) net lots
    from TWSE RWD T86 and TPEx OpenAPI. Gracefully returns {} if unavailable.
    """
    chips: Dict[str, dict] = {}
    today = datetime.date.today()

    # 1. TWSE T86 (walk back up to 5 weekdays to match latest trading day)
    for offset in range(0, 7):
        d = today - datetime.timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        ymd = d.strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={ymd}&selectType=ALLBUT0999&response=json"
        try:
            data = http_get_json(url, timeout=14)
            if data.get("stat") != "OK" or not data.get("data"):
                continue
            fields = data.get("fields") or []
            idx_code = 0
            idx_f = next((i for i, f in enumerate(fields) if "外陸資買賣超股數" in f and "不含" in f), 4)
            idx_t = next((i for i, f in enumerate(fields) if "投信買賣超股數" in f), 10)
            for row in data["data"]:
                c = str(row[idx_code]).strip()
                if c in UNIVERSE:
                    f_sh = parse_num(row[idx_f]) or 0.0
                    t_sh = parse_num(row[idx_t]) or 0.0
                    chips[c] = {
                        "foreign_lots": round(f_sh / 1000.0, 1),
                        "trust_lots": round(t_sh / 1000.0, 1),
                        "inst_lots": round((f_sh + t_sh) / 1000.0, 1),
                    }
            if chips:
                break
        except Exception as exc:
            print(f"[Chips TWSE] {ymd} skipped: {exc}")

    # 2. TPEx 3-Institutional Daily Trading OpenAPI
    try:
        rows = http_get_json("https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading", timeout=14)
        for r in rows or []:
            c = str(r.get("SecuritiesCompanyCode", "")).strip()
            if c in UNIVERSE:
                f_sh = parse_num(r.get("ForeignInvestorsNetBuySellShares")) or 0.0
                t_sh = parse_num(r.get("SecuritiesInvestmentTrustCompaniesNetBuySellShares")) or 0.0
                chips[c] = {
                    "foreign_lots": round(f_sh / 1000.0, 1),
                    "trust_lots": round(t_sh / 1000.0, 1),
                    "inst_lots": round((f_sh + t_sh) / 1000.0, 1),
                }
    except Exception as exc:
        print(f"[Chips TPEx] Warning: {exc}")

    return chips


def call_gemini_research_agent(
    trade_date: str,
    regime_label: str,
    m0050: dict,
    top_candidates: List[dict],
    guru_headlines: List[str],
    api_key: str,
) -> dict:
    """
    Single daily Gemini API call (1 request/day!) acting as an institutional research analyst:
    - Picks 3-5 favored stocks from the 65-stock pool with clear reasons & risks
    - Tracks global investing gurus (Buffett/13F/Wall St) & foreign flows
    - Flags genuine severe semantic news red flags (replaces brittle keyword counting)
    """
    fallback = {
        "updated_date": trade_date,
        "engine": "量化摘要保底 (未設定 GEMINI_API_KEY 或連線逾時)",
        "market_view": f"目前大盤處於「{regime_label}」，0050 收 {m0050['close']} 元（20日線 {m0050['ma20']} / 60日線 {m0050['ma60']}）。",
        "top_picks": [
            {
                "code": c["code"], "name": c["name"], "stance": "量化強勢",
                "reason": f"20日相對強度 {c['rs20_pct']:+.1f}%、月營收 {c['rev_str']}、外資+投信 {c['inst_lots']:+.0f}張。",
                "risk": f"短線留意 RSI {c['rsi14']} 與大盤波動風險。",
            }
            for c in top_candidates[:3]
        ],
        "guru_tracker": guru_headlines[:3] if guru_headlines else ["今日暫無新增國際大佬／外資動向新聞。"],
        "red_flag_codes": [],
    }

    if not api_key or len(api_key.strip()) < 10:
        return fallback

    prompt = (
        f"你是專業的台灣股市量化投研分析師。請根據以下 {trade_date} 實盤數據、三大法人籌碼、月營收估值與最新新聞，"
        f"回傳嚴格的 JSON（不要輸出 Markdown 標記或額外說明文字）。\n\n"
        f"【大盤環境】{regime_label}｜0050 收盤 {m0050['close']}｜20日線 {m0050['ma20']}｜60日線 {m0050['ma60']}\n\n"
        f"【65檔核心池量化排名前10檔候選股與最新新聞】\n"
        + json.dumps(top_candidates[:10], ensure_ascii=False)
        + "\n\n【國際投資大佬（巴菲特/13F/橋水/ARK）與外資大行最新新聞標題】\n"
        + json.dumps(guru_headlines[:8], ensure_ascii=False)
        + "\n\n請回傳以下 JSON 格式（繁體中文、客觀精簡、不誇大）：\n"
        "{\n"
        '  "market_view": "2句話總結今日台股大盤結構與操作建議",\n'
        '  "top_picks": [\n'
        '    {"code": "代號", "name": "股名", "stance": "偏多觀察/基本面強勢/防禦配置", "reason": "結合技術面+營收估值+外資投信籌碼+新聞的看好理由(40字內)", "risk": "主要風險提醒(25字內)"}\n'
        '  ],\n'
        '  "guru_tracker": ["2至3條精簡重點，整理最新外資大行與國際大佬(如巴菲特/13F/對沖基金)動向，若新聞無相關則寫近期無重大變動"],\n'
        '  "red_flag_codes": ["僅列出最新新聞確實爆發重大實質利空(如下修財測、砍單、虧損、停工、違約)的股票代號，沒地雷請回傳空陣列[]"]\n'
        "}\n"
        "注意：top_picks 請從上述候選股中選出最看好的 3 到 5 檔。"
    )

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }).encode("utf-8")

    ctx = ssl.create_default_context()
    for model_name in ("gemini-2.5-flash", "gemini-2.0-flash"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={urllib.parse.quote(api_key.strip())}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            txt = body["candidates"][0]["content"]["parts"][0]["text"].strip()
            txt = re.sub(r"^```json\s*|\s*```$", "", txt, flags=re.DOTALL).strip()
            parsed = json.loads(txt)
            return {
                "updated_date": trade_date,
                "engine": f"Gemini AI ({model_name})",
                "market_view": str(parsed.get("market_view") or fallback["market_view"]),
                "top_picks": (parsed.get("top_picks") or fallback["top_picks"])[:5],
                "guru_tracker": (parsed.get("guru_tracker") or fallback["guru_tracker"])[:4],
                "red_flag_codes": [str(x).strip() for x in (parsed.get("red_flag_codes") or [])],
            }
        except Exception as exc:
            print(f"[Gemini LLM] {model_name} failed: {exc}")

    return fallback


def default_state() -> dict:
    return {
        "version": "v4_5layer_gemini_65",
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start_capital": START_CAPITAL,
        "cash": START_CAPITAL,
        "benchmark_0050_start_price": None,
        "benchmark_0050_shares": 0,
        "benchmark_0050_cash": START_CAPITAL,
        "positions": {},
        "pending_orders": [],
        "ai_briefing": None,
        "trade_log": [],
        "equity_history": [],
        "last_run_date": "",
        "last_run_time": "",
        "last_regime": "尚未執行",
        "last_summary": "v4 五層量化＋Gemini AI 投研簡報引擎已就緒。",
    }


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    st = default_state()
    save_state(st)
    return st


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    if state.get("trade_log"):
        with open(TRADES_CSV, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["date", "action", "code", "name", "sector", "shares", "price", "fee_tax", "pnl", "ret_pct", "reason"])
            w.writeheader()
            for t in state["trade_log"]:
                w.writerow({k: t.get(k, "") for k in w.fieldnames})

    if state.get("equity_history"):
        with open(EQUITY_CSV, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["date", "total_equity", "net_profit", "return_pct", "bench_0050_equity", "cash", "holdings_val", "regime", "summary"])
            w.writeheader()
            for e in state["equity_history"]:
                w.writerow({k: e.get(k, "") for k in w.fieldnames})


def reset_state() -> dict:
    st = default_state()
    save_state(st)
    return st


def compute_rsi(series: pd.Series, n: int = 14) -> float:
    d = series.diff()
    up = d.clip(lower=0.0).ewm(alpha=1.0 / n, adjust=False).mean()
    dn = (-d.clip(upper=0.0)).ewm(alpha=1.0 / n, adjust=False).mean()
    return round(100.0 - (100.0 / (1.0 + float(up.iloc[-1]) / (float(dn.iloc[-1]) + 1e-9))), 1)


def fetch_market_snapshot() -> Dict[str, dict]:
    import yfinance as yf
    try:
        yf.set_tz_cache_location("/tmp/yf_tz_cache")
    except Exception:
        pass

    snap: Dict[str, dict] = {}

    def parse_df(code: str, df: pd.DataFrame):
        try:
            if df is None or df.empty:
                return
            if isinstance(df.columns, pd.MultiIndex):
                df = df.droplevel(0, axis=1) if "Close" not in df.columns.get_level_values(0) else df.droplevel(1, axis=1)
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if len(df) < 62:
                return
            c, h, l, o, v = df["Close"], df["High"], df["Low"], df["Open"], df["Volume"]
            close = float(c.iloc[-1])
            prev = float(c.iloc[-2])
            pc = c.shift(1)
            tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
            atr14 = float(tr.ewm(alpha=1.0 / 14, adjust=False).mean().iloc[-1])
            clv = ((c - l) - (h - c)) / (h - l + 1e-9)
            cmf10 = float((clv * v).tail(10).sum() / (v.tail(10).sum() + 1e-9))

            snap[code] = {
                "date": str(df.index[-1].date()),
                "open": round(float(o.iloc[-1]), 2),
                "high": round(float(h.iloc[-1]), 2),
                "low": round(float(l.iloc[-1]), 2),
                "close": round(close, 2),
                "prev": round(prev, 2),
                "ret1": close / prev - 1.0,
                "ret5": close / float(c.iloc[-6]) - 1.0,
                "ret20": close / float(c.iloc[-21]) - 1.0,
                "ma5": round(float(c.tail(5).mean()), 2),
                "ma20": round(float(c.tail(20).mean()), 2),
                "ma60": round(float(c.tail(60).mean()), 2),
                "atr14": round(max(atr14, close * 0.012), 2),
                "rsi14": compute_rsi(c, 14),
                "cmf10": round(cmf10, 3),
            }
        except Exception:
            pass

    for _ in range(3):
        try:
            df0050 = yf.download("0050.TW", period="5mo", interval="1d", auto_adjust=True, threads=False, progress=False)
            parse_df("0050", df0050)
            if "0050" in snap:
                break
        except Exception:
            pass
        time.sleep(2)

    items = list(UNIVERSE.items())
    for i in range(0, len(items), 25):
        chunk = items[i:i + 25]
        syms = [meta["sym"] for _, meta in chunk]
        try:
            raw = yf.download(syms, period="5mo", interval="1d", auto_adjust=True, group_by="ticker", threads=False, progress=False)
            for code, meta in chunk:
                try:
                    sub = raw[meta["sym"]] if isinstance(raw.columns, pd.MultiIndex) else raw
                    parse_df(code, sub)
                except Exception:
                    pass
        except Exception as exc:
            print(f"[MarketData] Batch {i} warning: {exc}")

    return snap


def run_daily_cycle(
    market_snapshot: Optional[Dict[str, dict]] = None,
    fundamentals_map: Optional[Dict[str, dict]] = None,
    chips_map: Optional[Dict[str, dict]] = None,
    llm_fn=None,
    force: bool = False,
) -> dict:
    state = load_state()
    snap = market_snapshot if market_snapshot is not None else fetch_market_snapshot()
    if not snap or "0050" not in snap:
        raise RuntimeError("無法取得 0050 與台股行情，請確認網路連線。")

    # Auto-heal any duplicate or out-of-order dates in equity_history (e.g. from stale Yahoo cache)
    if state.get("equity_history"):
        dedup = {}
        for rec in state["equity_history"]:
            if rec.get("date"):
                dedup[rec["date"]] = rec
        cleaned = [dedup[d] for d in sorted(dedup.keys())]
        if cleaned != state["equity_history"]:
            state["equity_history"] = cleaned
            state["last_run_date"] = cleaned[-1]["date"]
            save_state(state)

    today = snap["0050"]["date"]
    last_d = state.get("last_run_date") or ""
    if (not force) and last_d and today <= last_d:
        return {"status": "skipped", "message": f"略過舊/重複資料日 {today} (帳本最新已達 {last_d})。", "state": state}

    fund_map = fundamentals_map if fundamentals_map is not None else fetch_official_fundamentals()
    chip_map = chips_map if chips_map is not None else fetch_institutional_chips()

    # Initialize 0050 Benchmark on Day 1
    p0050 = snap["0050"]["close"]
    if state["benchmark_0050_start_price"] is None:
        sh0 = int(START_CAPITAL // (p0050 * (1.0 + SLIPPAGE + FEE_RATE)))
        c0 = sh0 * p0050 * (1.0 + SLIPPAGE)
        f0 = max(1.0, c0 * FEE_RATE)
        state["benchmark_0050_start_price"] = p0050
        state["benchmark_0050_shares"] = sh0
        state["benchmark_0050_cash"] = round(START_CAPITAL - c0 - f0, 2)
    bench_eq = round(state["benchmark_0050_cash"] + state["benchmark_0050_shares"] * p0050, 0)

    events = []
    positions = state["positions"]

    # =========================================================================
    # PHASE 1: Strict T+1 Through-Fill Settlement
    # =========================================================================
    prev_orders = state.get("pending_orders") or []
    for ord_item in [o for o in prev_orders if o["action"] == "SELL"]:
        code = ord_item["code"]
        if code not in positions or code not in snap:
            continue
        q = snap[code]
        pos = positions[code]
        fill_price, fill_reason = None, None

        if ord_item.get("order_kind") == "MARKET_OPEN":
            fill_price = q["open"]
            fill_reason = ord_item.get("reason", "趨勢轉弱隔日開盤出場")
        else:
            sl_p = float(ord_item["sl_price"])
            tp_p = float(ord_item["tp_price"])
            tp_through = round_twse_tick(tp_p + get_twse_tick(tp_p))
            if q["low"] <= sl_p:
                fill_price = min(q["open"], sl_p)
                fill_reason = f"盤中觸發停損/移停價 {sl_p} (今日低點 {q['low']})"
            elif q["high"] >= tp_through:
                fill_price = max(q["open"], tp_p)
                fill_reason = f"盤中穿價停利 {tp_p} (高點 {q['high']} ≥ {tp_through})"

        if fill_price is not None:
            exec_p = fill_price * (1.0 - SLIPPAGE)
            gross = exec_p * int(pos["shares"])
            fee = max(1.0, gross * FEE_RATE)
            tax = gross * TAX_STOCK
            net_proc = gross - fee - tax
            pnl = net_proc - float(pos["cost_twd"])
            ret_pct = (net_proc / float(pos["cost_twd"]) - 1.0) * 100.0
            state["cash"] = round(float(state["cash"]) + net_proc, 2)
            state["trade_log"].append({
                "date": today, "action": "SELL", "code": code, "name": pos["name"], "sector": pos["sector"],
                "shares": int(pos["shares"]), "price": round(fill_price, 2), "fee_tax": round(fee + tax, 1),
                "pnl": round(pnl, 0), "ret_pct": round(ret_pct, 2), "reason": fill_reason,
            })
            events.append(f"賣出成交 {pos['name']}({code}) @ {fill_price:.1f} ({pnl:+,.0f}元)")
            del positions[code]

    for ord_item in [o for o in prev_orders if o["action"] == "BUY"]:
        code = ord_item["code"]
        if code in positions or code not in snap:
            continue
        if len(positions) >= MAX_POSITIONS:
            break
        q = snap[code]
        lim_p = float(ord_item["limit_price"])
        buy_through = round_twse_tick(lim_p - 2.0 * get_twse_tick(lim_p))
        if q["low"] <= buy_through:
            fill_price = min(q["open"], lim_p)
            exec_p = fill_price * (1.0 + SLIPPAGE)
            max_aff = int((float(state["cash"]) * 0.99) // (exec_p * (1.0 + FEE_RATE)))
            shares = min(int(ord_item["shares"]), max_aff)
            if shares < 1:
                continue
            gross = exec_p * shares
            fee = max(1.0, gross * FEE_RATE)
            cost_twd = gross + fee
            state["cash"] = round(float(state["cash"]) - cost_twd, 2)
            positions[code] = {
                "name": ord_item["name"], "sector": ord_item["sector"], "shares": shares,
                "entry_price": round(fill_price, 2), "cost_twd": round(cost_twd, 2),
                "peak_price": round(max(fill_price, q["high"]), 2), "entry_date": today,
                "last_price": q["close"], "atr": q["atr14"],
            }
            state["trade_log"].append({
                "date": today, "action": "BUY", "code": code, "name": ord_item["name"], "sector": ord_item["sector"],
                "shares": shares, "price": round(fill_price, 2), "fee_tax": round(fee, 1),
                "pnl": 0, "ret_pct": 0.0, "reason": f"穿價2檔買進 {lim_p} 成交 (低點 {q['low']} ≤ {buy_through})",
            })
            events.append(f"穿價買進 {ord_item['name']}({code}) {shares}股 @ {fill_price:.1f}")
        else:
            events.append(f"未穿價2檔失效：{ord_item['name']}({code}) 限價 {lim_p} (需≤{buy_through}，今日低點 {q['low']})")

    holdings_val = 0.0
    for code, pos in positions.items():
        if code in snap:
            pos["last_price"] = snap[code]["close"]
            pos["peak_price"] = round(max(float(pos["peak_price"]), snap[code]["high"]), 2)
            pos["atr"] = snap[code]["atr14"]
        holdings_val += int(pos["shares"]) * float(pos["last_price"])
    total_eq = round(float(state["cash"]) + holdings_val, 0)

    # =========================================================================
    # PHASE 2: 5-Layer Quantitative Ranking (incl. Foreign+Trust Chips) + Daily LLM
    # =========================================================================
    m0050 = snap["0050"]
    above_20 = m0050["close"] > m0050["ma20"]
    above_60 = m0050["close"] > m0050["ma60"]
    if above_20 and above_60:
        regime, max_slots = "BULL", 4
        regime_label = "🟢 多頭格局 (0050站穩月季線｜上限4檔｜v4五層+AI)"
    elif above_60 or above_20:
        regime, max_slots = "CAUTION", 2
        regime_label = "🟡 震盪警戒 (0050介於月季線間｜上限2檔｜v4五層+AI)"
    else:
        regime, max_slots = "BEAR", 0
        regime_label = "🔴 空頭警戒 (0050雙破月季線｜禁止新買進｜v4五層+AI)"

    # Rank ALL 65 stocks for both LLM Research Briefing & Deterministic Order Screening
    ranked_all = []
    for code, meta in UNIVERSE.items():
        if code not in snap:
            continue
        q = snap[code]
        f = fund_map.get(code, {})
        ch = chip_map.get(code, {})
        pe, dy, rev_yoy = f.get("pe"), f.get("dy"), f.get("rev_yoy")
        f_lots = float(ch.get("foreign_lots", 0.0))
        t_lots = float(ch.get("trust_lots", 0.0))
        inst_lots = float(ch.get("inst_lots", 0.0))

        dist_ma20 = q["close"] / q["ma20"] - 1.0
        rs20 = q["ret20"] - m0050["ret20"]
        atr_pct = q["atr14"] / max(1.0, q["close"])

        # Composite Quantitative Score (Tech + CMF + Fundamentals + Foreign/Trust Chips)
        tech_s = (rs20 / max(0.015, atr_pct)) * 10.0 + q["cmf10"] * 20.0
        rev_b = float(np.clip((rev_yoy or 0.0) * 0.25, -4.0, 12.0)) if rev_yoy is not None else 0.0
        val_b = (5.0 if (pe is not None and 0 < pe <= 18.0) else 0.0) + (4.0 if (dy is not None and dy >= 3.5) else 0.0)
        chip_b = float(np.clip(np.sign(inst_lots) * np.log1p(abs(inst_lots)) * 1.4, -8.0, 10.0))
        total_s = round(tech_s + rev_b + val_b + chip_b, 2)

        # Deterministic Hard Entry Gates
        passes_hard_gates = (
            code not in positions
            and q["close"] > q["ma20"]
            and q["ma5"] >= q["ma20"] * 0.995
            and dist_ma20 <= 0.10
            and 48 <= q["rsi14"] <= 74
            and q["ret1"] > -0.03
            and rs20 > (0.03 if regime == "CAUTION" else 0.0)
            and (rev_yoy is None or rev_yoy >= -15.0)
            and not (pe is not None and pe > 40.0 and (rev_yoy is None or rev_yoy < 25.0))
            and inst_lots > -5000.0  # Avoid massive foreign/trust dumping
        )

        ranked_all.append({
            "score": total_s, "code": code, "name": meta["name"], "sector": meta["sector"],
            "passes_hard_gates": passes_hard_gates, "close": q["close"], "rs20_pct": round(rs20 * 100, 1),
            "rsi14": q["rsi14"], "pe": pe, "dy": dy, "rev_yoy": rev_yoy,
            "rev_str": f"{rev_yoy:+.1f}%" if rev_yoy is not None else "--",
            "pe_str": f"{pe:.1f}" if pe is not None else "--",
            "foreign_lots": f_lots, "trust_lots": t_lots, "inst_lots": inst_lots,
            "q": q,
        })

    ranked_all.sort(key=lambda x: (1 if x["passes_hard_gates"] else 0, x["score"]), reverse=True)

    # Fetch fresh headlines ONLY for Top 10 stocks + Global Investing Gurus (fast ~2s)
    llm_top10 = []
    if market_snapshot is None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            guru_fut = ex.submit(fetch_rss_headlines, "巴菲特 OR 波克夏 OR 13F OR 外資大行 台股 OR 橋水", 8)
            news_futs = {ex.submit(fetch_rss_headlines, f"{c['name']} {c['code']} 財報 OR 法說 OR 營收", 3): c["code"] for c in ranked_all[:10]}
            guru_headlines = guru_fut.result()
            news_by_code = {news_futs[f]: f.result() for f in concurrent.futures.as_completed(news_futs)}
    else:
        guru_headlines = ["巴菲特波克夏最新13F持股報告觀察", "外資法人調整亞洲半導體部位"]
        news_by_code = {c["code"]: [f"{c['name']}最新營運與法說追蹤"] for c in ranked_all[:10]}

    for c in ranked_all[:10]:
        llm_top10.append({
            "code": c["code"], "name": c["name"], "sector": c["sector"], "close": c["close"],
            "rs20_pct": c["rs20_pct"], "rsi14": c["rsi14"], "rev_str": c["rev_str"], "pe_str": c["pe_str"],
            "foreign_lots": c["foreign_lots"], "trust_lots": c["trust_lots"], "inst_lots": c["inst_lots"],
            "passes_buy_gate": c["passes_hard_gates"], "news": news_by_code.get(c["code"], []),
        })

    # Run Single Daily Gemini LLM Agent Call (reads GEMINI_API_KEY from env / GitHub Secrets)
    api_key = os.environ.get("GEMINI_API_KEY", "")
    ai_briefing = (
        llm_fn(today, regime_label, m0050, llm_top10, guru_headlines, api_key)
        if llm_fn is not None
        else call_gemini_research_agent(today, regime_label, m0050, llm_top10, guru_headlines, api_key)
    )
    red_flag_set = set(ai_briefing.get("red_flag_codes") or [])

    # 2A. OCO Exit / Trend-Break Orders for Held Positions (100% Deterministic Code)
    new_pending: List[dict] = []
    for code, pos in positions.items():
        if code not in snap:
            continue
        q = snap[code]
        atr = float(pos.get("atr") or q["atr14"])
        entry_p, peak_p = float(pos["entry_price"]), float(pos["peak_price"])

        if q["close"] < q["ma20"] * 0.99:
            new_pending.append({
                "action": "SELL", "order_kind": "MARKET_OPEN", "code": code,
                "name": pos["name"], "sector": pos["sector"], "shares": int(pos["shares"]),
                "limit_price": q["close"], "sl_price": q["close"], "tp_price": q["close"],
                "reason": f"收盤({q['close']})跌破20日線({q['ma20']})，明日開盤出場",
                "created_date": today,
            })
        else:
            active_sl = round_twse_tick(max(max(entry_p * 0.93, entry_p - 1.8 * atr), max(peak_p * 0.92, peak_p - 2.2 * atr)))
            tp_p = round_twse_tick(entry_p + 3.5 * atr)
            new_pending.append({
                "action": "SELL", "order_kind": "OCO_STOP_PROFIT", "code": code,
                "name": pos["name"], "sector": pos["sector"], "shares": int(pos["shares"]),
                "limit_price": None, "sl_price": active_sl, "tp_price": tp_p,
                "reason": f"大戶投OCO：停損/移停 {active_sl}｜停利 {tp_p}",
                "created_date": today,
            })

    # 2B. Buy Limit Orders (100% Deterministic Code + Optional LLM Red-Flag Veto)
    open_slots = max(0, max_slots - len(positions))
    ai_vetoed = []
    if open_slots > 0 and float(state["cash"]) >= 12_000.0:
        sector_counts: Dict[str, int] = {}
        for pos in positions.values():
            sector_counts[pos["sector"]] = sector_counts.get(pos["sector"], 0) + 1

        eligible = [c for c in ranked_all if c["passes_hard_gates"]]
        alloc_per_slot = min(float(state["cash"]) / open_slots * 0.96, total_eq * 0.24)
        placed = 0
        for c in eligible:
            if placed >= open_slots:
                break
            if sector_counts.get(c["sector"], 0) >= MAX_PER_SECTOR:
                continue
            if c["code"] in red_flag_set:
                ai_vetoed.append(f"{c['name']}({c['code']})")
                continue
            q = c["q"]
            lim_buy = round_twse_tick(q["close"] - 0.30 * q["atr14"])
            sl_p = round_twse_tick(max(lim_buy * 0.93, lim_buy - 1.8 * q["atr14"]))
            tp_p = round_twse_tick(lim_buy + 3.5 * q["atr14"])
            shares = int(alloc_per_slot // (lim_buy * (1.0 + SLIPPAGE + FEE_RATE)))
            if shares < 1:
                continue
            new_pending.append({
                "action": "BUY", "order_kind": "LIMIT_PULLBACK", "code": c["code"],
                "name": c["name"], "sector": c["sector"], "shares": shares,
                "limit_price": lim_buy, "sl_price": sl_p, "tp_price": tp_p,
                "reason": f"RS {c['rs20_pct']:+.1f}%｜營收{c['rev_str']}｜PE {c['pe_str']}｜法人{c['inst_lots']:+.0f}張",
                "created_date": today,
            })
            sector_counts[c["sector"]] = sector_counts.get(c["sector"], 0) + 1
            placed += 1

    state["version"] = "v4_5layer_gemini_65"
    state["pending_orders"] = new_pending
    state["ai_briefing"] = ai_briefing
    net_profit = round(total_eq - START_CAPITAL, 0)
    ret_pct = round((total_eq / START_CAPITAL - 1.0) * 100.0, 2)

    parts = ["; ".join(events) if events else f"今日無觸價成交｜已開出明日 {len(new_pending)} 筆掛單"]
    if ai_vetoed:
        parts.append("AI語意避雷跳過：" + "、".join(ai_vetoed))
    summary = "｜".join(parts)

    entry = {
        "date": today, "total_equity": total_eq, "net_profit": net_profit, "return_pct": ret_pct,
        "bench_0050_equity": bench_eq, "cash": round(float(state["cash"]), 0),
        "holdings_val": round(holdings_val, 0), "regime": regime_label, "summary": summary,
    }
    dedup = {rec["date"]: rec for rec in state.get("equity_history", []) if rec.get("date")}
    dedup[today] = entry
    state["equity_history"] = [dedup[d] for d in sorted(dedup.keys())]

    state["last_run_date"] = today
    state["last_run_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["last_regime"] = regime_label
    state["last_summary"] = summary
    save_state(state)
    return {"status": "ok", "date": today, "entry": entry, "state": state}


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_state()
        print("Reset to NT$100,000 cash.")
    else:
        res = run_daily_cycle(force="--force" in sys.argv)
        print(f"[{res['status'].upper()}] {res.get('date', '')} | {res.get('message') or res['entry']['summary']}")
