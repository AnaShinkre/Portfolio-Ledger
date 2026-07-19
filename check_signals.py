"""
Daily portfolio check: pulls quotes from Stooq (no API key required),
recomputes tax-aware sell signals for your positions, and screens a
fixed universe of large-cap tickers for a simple "lower volatility,
above its long-run trend" candidate list.

Writes everything to status.json, which the HTML tool reads on sync.
This script never places trades and never decides anything for you —
it only computes numbers and writes them to a file.
"""

import csv
import io
import json
import math
import datetime
import urllib.request

STOOQ_QUOTE = "https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv"
STOOQ_HIST = "https://stooq.com/q/d/l/?s={sym}&i=d"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range={rng}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

# Fixed screening universe: well-established large-cap names across sectors.
# This list is a starting point, not an endorsement — edit it freely.
CANDIDATE_UNIVERSE = [
    "JNJ", "PG", "KO", "PEP", "WMT", "MCD", "COST", "JPM", "V", "MA",
    "MSFT", "AAPL", "UNH", "HD", "MRK", "ABBV", "PFE", "VZ", "T", "XOM",
    "CVX", "NEE", "DUK", "SO", "MMM", "CAT", "HON", "LOW", "TGT", "CL",
]


def _get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode()


def stooq_symbol(ticker):
    return ticker.lower() + ".us"


def fetch_quote_stooq(ticker):
    text = _get(STOOQ_QUOTE.format(sym=stooq_symbol(ticker)))
    reader = csv.DictReader(io.StringIO(text))
    row = next(reader, None)
    if not row:
        return None
    close = row.get("Close")
    if close in (None, "N/D", ""):
        return None
    return float(close)


def fetch_quote_yahoo(ticker):
    text = _get(YAHOO_CHART.format(sym=ticker, rng="5d"))
    data = json.loads(text)
    result = data.get("chart", {}).get("result")
    if not result:
        return None
    price = result[0].get("meta", {}).get("regularMarketPrice")
    return float(price) if price is not None else None


def fetch_quote(ticker):
    try:
        p = fetch_quote_stooq(ticker)
        if p:
            return p
    except Exception as e:
        print(f"  stooq quote failed for {ticker}: {e}")
    try:
        p = fetch_quote_yahoo(ticker)
        if p:
            return p
    except Exception as e:
        print(f"  yahoo quote failed for {ticker}: {e}")
    return None


def fetch_history_stooq(ticker, max_rows=260):
    text = _get(STOOQ_HIST.format(sym=stooq_symbol(ticker)))
    rows = list(csv.DictReader(io.StringIO(text)))
    closes = []
    for row in rows[-max_rows:]:
        c = row.get("Close")
        if c and c not in ("N/D", ""):
            closes.append(float(c))
    return closes


def fetch_history_yahoo(ticker):
    text = _get(YAHOO_CHART.format(sym=ticker, rng="1y"))
    data = json.loads(text)
    result = data.get("chart", {}).get("result")
    if not result:
        return []
    closes_raw = result[0]["indicators"]["quote"][0].get("close", [])
    return [c for c in closes_raw if c is not None]


def fetch_history(ticker, max_rows=260):
    try:
        closes = fetch_history_stooq(ticker, max_rows)
        if closes:
            return closes
    except Exception as e:
        print(f"  stooq history failed for {ticker}: {e}")
    try:
        closes = fetch_history_yahoo(ticker)
        if closes:
            return closes
    except Exception as e:
        print(f"  yahoo history failed for {ticker}: {e}")
    return []


def annualized_volatility(closes):
    if len(closes) < 20:
        return None
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return math.sqrt(var) * math.sqrt(252)


def sma(closes, window):
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def compute_signal(pos, settings, price, today):
    purchase_date = datetime.date.fromisoformat(pos["date"])
    holding_days = (today - purchase_date).days
    is_lt = holding_days >= 365
    total_cost = pos["shares"] * pos["cost"]
    current_value = pos["shares"] * price
    unrealized = current_value - total_cost
    rate = settings["ltRate"] if is_lt else settings["stRate"]
    after_tax = unrealized * (1 - rate / 100) if unrealized > 0 else unrealized
    lt_after_tax = unrealized * (1 - settings["ltRate"] / 100) if unrealized > 0 else unrealized
    days_to_lt = max(0, 365 - holding_days)
    tax_savings = lt_after_tax - after_tax

    signal, detail = "HOLD", f"Profit below ${settings['threshold']} threshold."
    if unrealized <= 0:
        signal, detail = "HOLD", "No gain currently."
    elif is_lt and after_tax >= settings["threshold"]:
        signal, detail = "SELL", "Long-term rate applies. Clears threshold."
    elif not is_lt and after_tax >= settings["threshold"]:
        if days_to_lt <= 60 and tax_savings >= 25:
            signal, detail = "WAIT", f"{days_to_lt}d to long-term could save ~${tax_savings:.0f} tax."
        else:
            signal, detail = "SELL", "Short-term rate but still clears threshold."
    elif not is_lt and lt_after_tax >= settings["threshold"]:
        signal, detail = "WAIT", f"{days_to_lt}d to long-term status would clear threshold."

    return {
        "ticker": pos["ticker"],
        "shares": pos["shares"],
        "price": round(price, 2),
        "unrealized": round(unrealized, 2),
        "afterTax": round(after_tax, 2),
        "holdingDays": holding_days,
        "isLT": is_lt,
        "signal": signal,
        "detail": detail,
    }


def main():
    positions = load_json("positions.json", [])
    settings = load_json("settings.json", {"stRate": 24, "ltRate": 15, "threshold": 200})
    today = datetime.date.today()

    signals = []
    for pos in positions:
        print(f"Fetching quote for {pos['ticker']}...")
        price = fetch_quote(pos["ticker"])
        if price is None:
            print(f"  -> unavailable")
            signals.append({"ticker": pos["ticker"], "error": "quote_unavailable"})
            continue
        print(f"  -> {price}")
        signals.append(compute_signal(pos, settings, price, today))

    candidates = []
    for t in CANDIDATE_UNIVERSE:
        try:
            closes = fetch_history(t)
            if not closes:
                continue
            price = closes[-1]
            vol = annualized_volatility(closes)
            sma200 = sma(closes, 200)
            if vol is None or sma200 is None:
                continue
            candidates.append({
                "ticker": t,
                "price": round(price, 2),
                "volatility": round(vol, 4),
                "aboveSMA200": price >= sma200,
            })
        except Exception:
            continue

    stable = sorted([c for c in candidates if c["aboveSMA200"]], key=lambda c: c["volatility"])
    top_candidates = stable[:6]

    status = {
        "generatedAt": datetime.datetime.utcnow().isoformat() + "Z",
        "signals": signals,
        "safeCandidates": top_candidates,
        "note": (
            "Screen = lowest realized volatility among a fixed large-cap universe, "
            "currently trading above its 200-day average. Not a recommendation to buy; "
            "purchase decisions are yours alone."
        ),
    }
    with open("status.json", "w") as f:
        json.dump(status, f, indent=2)
    print(f"Wrote status.json with {len(signals)} signals and {len(top_candidates)} candidates.")


if __name__ == "__main__":
    main()
