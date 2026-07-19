# Daily portfolio automation

This runs your portfolio check every weekday, on GitHub's free infrastructure,
whether or not your computer or browser is open. It never buys or sells
anything — it only computes numbers and writes them to `status.json`, which
the HTML tool reads.

## One-time setup (about 5 minutes)

1. **Create a repo.** On github.com, click *New repository*. Any name works,
   e.g. `portfolio-ledger`. Public or private both work (private is fine —
   the automation still runs; the HTML tool just needs the raw file URL,
   which works for public repos without extra setup, or you can generate a
   token for a private repo if you prefer it hidden).

2. **Upload these files**, keeping the folder structure:
   - `check_signals.py`
   - `positions.json`
   - `settings.json`
   - `.github/workflows/daily-check.yml`

   Easiest way: on the repo page, click *Add file → Upload files*, drag in
   everything (GitHub will preserve the `.github/workflows/` path if you
   drag the whole folder, or create the file manually if it flattens it).

3. **Edit `positions.json`** with your real holdings (ticker, shares, cost
   per share, purchase date, one entry per position). Edit `settings.json`
   if you want different tax rates or a threshold other than $200.

4. **Enable Actions.** Go to the *Actions* tab of your repo — GitHub may ask
   you to confirm you want workflows enabled. Click through it.

5. **Run it once manually** to check it works: Actions tab →
   *Daily Portfolio Check* → *Run workflow*. After ~30 seconds, refresh the
   repo's file list — you should see a new `status.json` appear.

6. **Connect the HTML tool.** Open the tool, go to settings, and enter your
   repo as `yourusername/portfolio-ledger`. Click *Sync latest automated
   check*. Your signals and safe-stock candidates will now show up.

After that, it runs automatically every weekday at 21:00 UTC (after US
market close) — just open the tool and hit sync whenever you want the
latest read. No API keys, no paid services, no server to maintain.

## Updating your positions

Whenever you buy or sell, edit `positions.json` in the repo (or use GitHub's
web editor) — the next scheduled run will pick up the change. The workflow
also runs on-demand any time from the Actions tab.

## Notes

- Price data comes from Stooq, a free quote source — no API key needed.
  Quotes can lag the live market by a few minutes.
- The "safe candidates" screen checks a fixed list of ~30 well-known
  large-cap tickers (see `CANDIDATE_UNIVERSE` in `check_signals.py`) for
  low recent volatility and an upward price trend. Edit that list to suit
  your own interests — it's a mechanical filter, not investment advice.
- This is not tax or financial advice. Confirm real filings with a
  professional.
