"""Top picks: finds upcoming fixtures where the model gives a high chance of a
home/away win, over 1.5 or 2.5 goals, or both-teams-score yes/no.
Also builds an accumulator (total model odds about 5) and back-tests recent
days so visitors can see how past picks did.
Needs predictor_nokey.py beside it."""
import csv
import io
import math
import urllib.request
from datetime import datetime, timedelta, timezone

import predictor_nokey as p

FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"

# A match is a "top pick" when the model gives at least this chance.
PICK_MIN = {"win": 0.65, "over15": 0.82, "over25": 0.66, "btts_yes": 0.65, "btts_no": 0.67}

# Accumulator: combine one pick per match until the model odds reach the target.
ACC_TARGET = 5.0      # total odds wanted
ACC_MAX_PROB = 0.80   # skip legs so likely that their odds are tiny (e.g. 1.05)
ACC_MAX_LEGS = 10


def load_fixtures():
    """Upcoming fixtures as a list of dicts. Raises RuntimeError if unavailable."""
    try:
        req = urllib.request.Request(FIXTURES_URL, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=25).read()
    except Exception:
        raise RuntimeError("Could not download the fixtures list right now. Please try again.")
    out = []
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace"))):
        d = p._parse_date(r.get("Date") or "")
        home, away = (r.get("HomeTeam") or "").strip(), (r.get("AwayTeam") or "").strip()
        if d and home and away:
            out.append({"div": (r.get("Div") or "").strip(), "date": d.date(),
                        "time": (r.get("Time") or "").strip(), "home": home, "away": away})
    if not out:
        raise RuntimeError("The fixtures list is empty right now.")
    return out


def picks_for(pr):
    picks = []
    if pr["home"] >= PICK_MIN["win"]:
        picks.append(("Home win", pr["home"]))
    if pr["away"] >= PICK_MIN["win"]:
        picks.append(("Away win", pr["away"]))
    # Chance of 2+ total goals, from the two expected-goal values (total goals is Poisson).
    total = pr["xg_home"] + pr["xg_away"]
    over15 = 1 - math.exp(-total) * (1 + total)
    if over15 >= PICK_MIN["over15"]:
        picks.append(("Over 1.5 goals", over15))
    if pr["over25"] >= PICK_MIN["over25"]:
        picks.append(("Over 2.5 goals", pr["over25"]))
    if pr["btts"] >= PICK_MIN["btts_yes"]:
        picks.append(("Both teams score: Yes", pr["btts"]))
    if 1 - pr["btts"] >= PICK_MIN["btts_no"]:
        picks.append(("Both teams score: No", 1 - pr["btts"]))
    return sorted(picks, key=lambda x: -x[1])


def build_accumulator(cands, target=ACC_TARGET):
    """cands: list of dicts with 'prob' (one best pick per match). Takes the most
    likely legs first and finishes with the likeliest leg that reaches the target.
    Odds are model odds (1 / probability), not bookmaker odds. Returns None if the
    target cannot be reached."""
    pool = sorted((c for c in cands if c["prob"] <= ACC_MAX_PROB), key=lambda c: -c["prob"])
    legs, odds = [], 1.0
    while pool and len(legs) < ACC_MAX_LEGS:
        finisher = next((c for c in pool if odds / c["prob"] >= target), None)
        if finisher:
            legs.append(finisher)
            odds /= finisher["prob"]
            break
        c = pool.pop(0)
        legs.append(c)
        odds /= c["prob"]
    if odds < target:
        return None
    chance = 1.0
    for c in legs:
        chance *= c["prob"]
    return {"legs": legs, "odds": odds, "chance": chance}


def _acc_candidates(entries):
    """entries: list of (match_dict, [(market, prob, extra), ...] sorted best first).
    One candidate per match: its best pick under ACC_MAX_PROB."""
    out = []
    for m, picks in entries:
        for market, prob, extra in picks:
            if prob <= ACC_MAX_PROB:
                out.append({"league": m["league"], "home": m["home"], "away": m["away"],
                            "market": market, "prob": prob, **extra})
                break
    return out


def compute_picks(league_cache, days=3, today=None):
    """Returns {'matches': [...], 'analysed': n, 'days': days, 'acc': {...}}.
    league_cache is the dict filled by predictor_nokey.load_all()."""
    fixtures = load_fixtures()
    today = today or datetime.now(timezone.utc).date()
    end = today + timedelta(days=days)
    upcoming = [f for f in fixtures if today <= f["date"] < end]

    per_div = {}   # div -> (rows, names, ratings, avg)

    def league(div):
        if div not in per_div:
            rows = league_cache.get(div) or []
            names = {r["home"] for r in rows} | {r["away"] for r in rows}
            ratings, avg = p.ratings_from(rows) if rows else ({}, p.DEFAULT_AVG_GOALS)
            per_div[div] = (rows, names, ratings, avg)
        return per_div[div]

    matches, analysed = [], 0
    for f in upcoming:
        rows, names, ratings, avg = league(f["div"])
        if not rows:
            continue

        def resolve(q):
            if q in names:
                return q
            hits = p.find_team_names(q, rows)
            return hits[0] if hits else None

        home, away = resolve(f["home"]), resolve(f["away"])
        if not home or not away or home == away:
            continue
        hm, am = p.last_matches(home, rows), p.last_matches(away, rows)
        if len(hm) < 3 or len(am) < 3:
            continue
        analysed += 1
        pr = p.predict(p.summarise(hm, ratings, True), p.summarise(am, ratings, False), avg)
        picks = picks_for(pr)
        if picks:
            matches.append({"date": f["date"], "time": f["time"],
                            "league": p.LEAGUES.get(f["div"], f["div"]),
                            "home": home, "away": away, "picks": picks})
    matches.sort(key=lambda m: (m["date"], -m["picks"][0][1]))
    acc = build_accumulator(_acc_candidates(
        [(m, [(mk, pr, {}) for mk, pr in m["picks"]]) for m in matches]))
    return {"matches": matches, "analysed": analysed, "days": days, "acc": acc}


# ---------- results of past days (back-test) ----------
def _hit(market, hg, ag):
    return {
        "Home win": hg > ag,
        "Away win": ag > hg,
        "Over 1.5 goals": hg + ag >= 2,
        "Over 2.5 goals": hg + ag >= 3,
        "Both teams score: Yes": hg > 0 and ag > 0,
        "Both teams score: No": hg == 0 or ag == 0,
    }[market]


def compute_results(league_cache, days_back=7, today=None):
    """Re-runs the pick rules on matches already played, for each of the last
    `days_back` days, using ONLY results from before that day. Marks every pick
    hit or miss. All picks are included (no cherry-picking)."""
    today = today or datetime.now(timezone.utc).date()
    days = []
    for k in range(1, days_back + 1):
        day = today - timedelta(days=k)
        day_matches, day_total, day_hits = [], 0, 0
        for div, rows in league_cache.items():
            played = [r for r in rows if r["date"].date() == day]
            if not played:
                continue
            pool = [r for r in rows if r["date"].date() < day]
            if len(pool) < 30:
                continue
            ratings, avg = p.ratings_from(pool)
            for m in played:
                hm, am = p.last_matches(m["home"], pool), p.last_matches(m["away"], pool)
                if len(hm) < 3 or len(am) < 3:
                    continue
                pr = p.predict(p.summarise(hm, ratings, True),
                               p.summarise(am, ratings, False), avg)
                marked = []
                for market, prob in picks_for(pr):
                    ok = _hit(market, m["hg"], m["ag"])
                    marked.append({"market": market, "prob": prob, "hit": ok})
                    day_total += 1
                    day_hits += ok
                if marked:
                    day_matches.append({"league": p.LEAGUES.get(div, div),
                                        "home": m["home"], "away": m["away"],
                                        "score": f"{m['hg']}-{m['ag']}", "picks": marked})
        day_matches.sort(key=lambda x: -x["picks"][0]["prob"])
        days.append({"date": day, "matches": day_matches, "total": day_total, "hits": day_hits})
    return {"days": days, "days_back": days_back}
