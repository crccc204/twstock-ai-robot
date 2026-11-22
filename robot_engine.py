#!/usr/bin/env python3
"""
Taiwan Stock NT$100,000 Autonomous Paper-Trading AI Robot (v2 — Cloud & Mobile Edition)
======================================================================================
Institutional-Grade Zero-Cheating Architecture:
1. 65-Stock High-Liquidity Taiwan Universe across 12 Sectors (TWSE/TPEx leaders).
2. Strict T-Day Order Generation -> T+1 OHLC Trigger Fill (Zero Close-Price Cheating!):
   - Day T (13:55): Computes tomorrow's TWSE tick-calibrated Limit Buy orders & OCO
     Stop-Loss / Trailing-Stop / Take-Profit orders based strictly on data up to Day T.
   - Day T+1 (13:55): Verifies Day T's pending orders against Day T+1's REAL Open,
     High, Low, Close. Buy fills ONLY if Low <= LimitBuy; Sell checks conservative
     SL-first rule (Low <= SL -> filled at min(Open, SL), else High >= TP -> max(Open, TP)).
3. Risk & Diversification Discipline:
   - Max 4 concurrent positions (~24% equity each), Max 2 stocks per sector.
   - Market Regime Gate (0050 vs MA20 & MA60): BULL=4 slots, CAUTION=2 slots, BEAR=0 new buys.
   - Volatility-Adjusted Momentum Ranking (RS_20D / ATR%) + Anti-Chasing & RSI Guard.
   - Real Taiwan odd-lot frictions: 0.1425% fee (min NT$1) + 0.30% sell tax + 0.10% slippage.
"""
import csv
import datetime
import json
import os
import sys
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

# 65 High-Liquidity Taiwan Leaders across 12 Diversified Sectors
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


def default_state() -> dict:
    return {
        "version": "v2_t1_trigger_65",
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start_capital": START_CAPITAL,
        "cash": START_CAPITAL,
        "benchmark_0050_start_price": None,
        "benchmark_0050_shares": 0,
        "benchmark_0050_cash": START_CAPITAL,
        "positions": {},       # code -> {name, sector, shares, entry_price, cost_twd, peak_price, entry_date, last_price, atr}
        "pending_orders": [],  # [{action: BUY/SELL, code, name, sector, shares, limit_price, sl_price, tp_price, reason, created_date}]
        "trade_log": [],
        "equity_history": [],
        "last_run_date": "",
        "last_run_time": "",
        "last_regime": "尚未執行",
        "last_summary": "機器人已就緒，首次執行將建立明日掛單清單並自下一個交易日起嚴格驗證觸價成交。",
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
    val = 100.0 - (100.0 / (1.0 + float(up.iloc[-1]) / (float(dn.iloc[-1]) + 1e-9)))
    return round(val, 1)


def fetch_market_snapshot() -> Dict[str, dict]:
    """Batch-download past 5 months of daily OHLCV for all 65 stocks + 0050.TW (~15 seconds)."""
    import yfinance as yf

    syms = [v["sym"] for v in UNIVERSE.values()] + ["0050.TW"]
    raw = yf.download(syms, period="5mo", interval="1d", auto_adjust=True, group_by="ticker", threads=True, progress=False)
    snap: Dict[str, dict] = {}

    def parse_one(code: str, sym: str):
        try:
            df = raw[sym] if isinstance(raw.columns, pd.MultiIndex) else raw
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

    for code, meta in UNIVERSE.items():
        parse_one(code, meta["sym"])
    parse_one("0050", "0050.TW")
    return snap


def run_daily_cycle(market_snapshot: Optional[Dict[str, dict]] = None, force: bool = False) -> dict:
    """
    Executes ONE strict zero-cheating daily cycle:
    Phase 1: Settle yesterday's pending smart orders against TODAY's real Open/High/Low.
    Phase 2: Evaluate today's close & generate TOMORROW's pending smart orders (Buy Limit + OCO Exit).
    """
    state = load_state()
    snap = market_snapshot if market_snapshot is not None else fetch_market_snapshot()
    if not snap or "0050" not in snap:
        raise RuntimeError("無法取得 0050 與台股行情，請確認網路連線。")

    today = snap["0050"]["date"]
    if (not force) and state.get("last_run_date") == today:
        return {"status": "skipped", "message": f"交易日 {today} 已完成結算與掛單。", "state": state}

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
    # PHASE 1: Settle Yesterday's Pending Orders Against TODAY's Real OHLC!
    # =========================================================================
    prev_orders = state.get("pending_orders") or []
    # 1A. Settle SELL / OCO orders first (frees cash & enforces risk control first)
    for ord_item in [o for o in prev_orders if o["action"] == "SELL"]:
        code = ord_item["code"]
        if code not in positions or code not in snap:
            continue
        q = snap[code]
        pos = positions[code]
        fill_price = None
        fill_reason = None

        if ord_item.get("order_kind") == "MARKET_OPEN":
            fill_price = q["open"]
            fill_reason = ord_item.get("reason", "趨勢轉弱隔日開盤出場")
        else:
            sl_p = float(ord_item["sl_price"])
            tp_p = float(ord_item["tp_price"])
            # Conservative tie-break: check Stop-Loss BEFORE Take-Profit!
            if q["low"] <= sl_p:
                fill_price = min(q["open"], sl_p)
                fill_reason = f"盤中觸發停損/移停價 {sl_p} (今日低點 {q['low']})"
            elif q["high"] >= tp_p:
                fill_price = max(q["open"], tp_p)
                fill_reason = f"盤中觸發停利目標價 {tp_p} (今日高點 {q['high']})"

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

    # 1B. Settle BUY Limit orders (fills ONLY if today's Low <= yesterday's Limit Buy!)
    for ord_item in [o for o in prev_orders if o["action"] == "BUY"]:
        code = ord_item["code"]
        if code in positions or code not in snap:
            continue
        if len(positions) >= MAX_POSITIONS:
            break
        q = snap[code]
        lim_p = float(ord_item["limit_price"])
        if q["low"] <= lim_p:
            fill_price = min(q["open"], lim_p)
            exec_p = fill_price * (1.0 + SLIPPAGE)
            # Re-verify cash so we never overdraft
            max_affordable = int((float(state["cash"]) * 0.99) // (exec_p * (1.0 + FEE_RATE)))
            shares = min(int(ord_item["shares"]), max_affordable)
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
                "pnl": 0, "ret_pct": 0.0, "reason": f"盤中拉回觸及限價 {lim_p} 成交 (今日低點 {q['low']})",
            })
            events.append(f"買進成交 {ord_item['name']}({code}) {shares}股 @ {fill_price:.1f}")
        else:
            events.append(f"未觸價失效：{ord_item['name']}({code}) 限價 {lim_p} (今日低點 {q['low']})")

    # Update mark-to-market & peak prices on surviving holdings
    holdings_val = 0.0
    for code, pos in positions.items():
        if code in snap:
            pos["last_price"] = snap[code]["close"]
            pos["peak_price"] = round(max(float(pos["peak_price"]), snap[code]["high"]), 2)
            pos["atr"] = snap[code]["atr14"]
        holdings_val += int(pos["shares"]) * float(pos["last_price"])

    total_eq = round(float(state["cash"]) + holdings_val, 0)

    # =========================================================================
    # PHASE 2: Generate TOMORROW's (T+1) Pending Smart Orders from Today's Close
    # =========================================================================
    m0050 = snap["0050"]
    above_20 = m0050["close"] > m0050["ma20"]
    above_60 = m0050["close"] > m0050["ma60"]
    if above_20 and above_60:
        regime, max_slots = "BULL", 4
        regime_label = "🟢 多頭格局 (0050站穩月線與季線｜上限4檔分散)"
    elif above_60 or above_20:
        regime, max_slots = "CAUTION", 2
        regime_label = "🟡 震盪警戒 (0050介於月季線間｜上限2檔・半倉防守)"
    else:
        regime, max_slots = "BEAR", 0
        regime_label = "🔴 空頭警戒 (0050跌破月線與季線｜禁止新買進・現金保護)"

    new_pending: List[dict] = []

    # 2A. Generate OCO Exit Orders (or Market Open Trend-Break Exit) for Every Held Position
    for code, pos in positions.items():
        if code not in snap:
            continue
        q = snap[code]
        atr = float(pos.get("atr") or q["atr14"])
        entry_p = float(pos["entry_price"])
        peak_p = float(pos["peak_price"])

        # Trend break: if closed below MA20 by > 1%, schedule exit at tomorrow's Open
        if q["close"] < q["ma20"] * 0.99:
            new_pending.append({
                "action": "SELL", "order_kind": "MARKET_OPEN", "code": code,
                "name": pos["name"], "sector": pos["sector"], "shares": int(pos["shares"]),
                "limit_price": q["close"], "sl_price": q["close"], "tp_price": q["close"],
                "reason": f"收盤({q['close']})跌破20日線({q['ma20']})，明日開盤市價出場",
                "created_date": today,
            })
        else:
            hard_sl = max(entry_p * 0.93, entry_p - 1.8 * atr)
            trail_sl = max(peak_p * 0.92, peak_p - 2.2 * atr)
            active_sl = round_twse_tick(max(hard_sl, trail_sl))
            tp_p = round_twse_tick(entry_p + 3.5 * atr)
            new_pending.append({
                "action": "SELL", "order_kind": "OCO_STOP_PROFIT", "code": code,
                "name": pos["name"], "sector": pos["sector"], "shares": int(pos["shares"]),
                "limit_price": None, "sl_price": active_sl, "tp_price": tp_p,
                "reason": f"大戶投OCO停損停利：觸及 {active_sl} 停損/鎖利，或觸及 {tp_p} 停利",
                "created_date": today,
            })

    # 2B. Generate Limit Buy Orders for Open Slots (with Sector Cap <= 2!)
    open_slots = max(0, max_slots - len(positions))
    if open_slots > 0 and float(state["cash"]) >= 12_000.0:
        sector_counts: Dict[str, int] = {}
        for pos in positions.values():
            sec = pos["sector"]
            sector_counts[sec] = sector_counts.get(sec, 0) + 1

        cands = []
        for code, meta in UNIVERSE.items():
            if code in positions or code not in snap:
                continue
            q = snap[code]
            dist_ma20 = q["close"] / q["ma20"] - 1.0
            rs20 = q["ret20"] - m0050["ret20"]
            atr_pct = q["atr14"] / max(1.0, q["close"])

            # Strict Institutional Entry Filters
            if q["close"] <= q["ma20"] or q["ma5"] < q["ma20"] * 0.995:
                continue
            if dist_ma20 > 0.10:
                continue  # Anti-chasing guard
            if q["rsi14"] < 48 or q["rsi14"] > 74:
                continue
            if q["ret1"] <= -0.03:
                continue  # No falling knife
            if rs20 <= (0.03 if regime == "CAUTION" else 0.0):
                continue

            # Risk-Adjusted Momentum + Money Flow Score
            score = (rs20 / max(0.015, atr_pct)) * 10.0 + q["cmf10"] * 25.0
            cands.append((score, code, meta, q))

        cands.sort(key=lambda x: x[0], reverse=True)
        alloc_per_slot = min(float(state["cash"]) / open_slots * 0.96, total_eq * 0.24)
        placed = 0
        for score, code, meta, q in cands:
            if placed >= open_slots:
                break
            sec = meta["sector"]
            if sector_counts.get(sec, 0) >= MAX_PER_SECTOR:
                continue
            # Patient Pullback Limit Buy: Close - 0.30 * ATR14 (TWSE tick calibrated)
            lim_buy = round_twse_tick(q["close"] - 0.30 * q["atr14"])
            sl_p = round_twse_tick(max(lim_buy * 0.93, lim_buy - 1.8 * q["atr14"]))
            tp_p = round_twse_tick(lim_buy + 3.5 * q["atr14"])
            shares = int(alloc_per_slot // (lim_buy * (1.0 + SLIPPAGE + FEE_RATE)))
            if shares < 1:
                continue
            new_pending.append({
                "action": "BUY", "order_kind": "LIMIT_PULLBACK", "code": code,
                "name": meta["name"], "sector": sec, "shares": shares,
                "limit_price": lim_buy, "sl_price": sl_p, "tp_price": tp_p,
                "reason": f"風險調整動能強(RS {(q['ret20']-m0050['ret20'])*100:+.1f}%｜RSI {q['rsi14']})，明日拉回限價 {lim_buy} 承接",
                "created_date": today,
            })
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            placed += 1

    state["pending_orders"] = new_pending
    net_profit = round(total_eq - START_CAPITAL, 0)
    ret_pct = round((total_eq / START_CAPITAL - 1.0) * 100.0, 2)
    summary = "；".join(events) if events else f"今日無觸價成交｜已開出明日 {len(new_pending)} 筆智慧掛單"

    entry = {
        "date": today, "total_equity": total_eq, "net_profit": net_profit, "return_pct": ret_pct,
        "bench_0050_equity": bench_eq, "cash": round(float(state["cash"]), 0),
        "holdings_val": round(holdings_val, 0), "regime": regime_label, "summary": summary,
    }
    if state["equity_history"] and state["equity_history"][-1]["date"] == today:
        state["equity_history"][-1] = entry
    else:
        state["equity_history"].append(entry)

    state["last_run_date"] = today
    state["last_run_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["last_regime"] = regime_label
    state["last_summary"] = summary
    save_state(state)
    return {"status": "ok", "date": today, "entry": entry, "pending_count": len(new_pending), "state": state}


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_state()
        print("Reset to NT$100,000 cash.")
    else:
        res = run_daily_cycle(force="--force" in sys.argv)
        print(f"[{res['status'].upper()}] {res.get('date', '')} | {res.get('message') or res['entry']['summary']}")
