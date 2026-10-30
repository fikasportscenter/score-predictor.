#!/usr/bin/env python3
"""
Football score predictor - NO API KEY NEEDED.
Downloads free match results from football-data.co.uk, shows each team's last
6 matches, and predicts the scoreline with a Poisson model.
Includes opponent-strength weighting and home/away splits.

Usage:
  python predictor_nokey.py "Arsenal" "Chelsea"
  python predictor_nokey.py "Real Madrid" "Barcelona"
  python predictor_nokey.py --demo          (offline test)

Team names use the site's spelling, e.g. "Man United", "Man City", "Ath Madrid",
"Inter", "Bayern Munich". Partial names work ("Man U", "Bayern").
"""
import argparse
import csv
import io
import math
import sys
import urllib.request
from datetime import datetime

BASE = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
SEASONS = ["2627", "2526"]   # current season first, then previous (to fill early-season gaps)
LEAGUES = {                  # code -> name
    "E0": "Premier League", "E1": "Championship", "SP1": "La Liga",
    "I1": "Serie A", "D1": "Bundesliga", "F1": "Ligue 1",
    "N1": "Eredivisie", "P1": "Primeira Liga", "SC0": "Scottish Premiership",
}
DEFAULT_AVG_GOALS = 1.35
HOME_ADVANTAGE = 1.05
N = 6
SHRINK = 0.25
VENUE_WEIGHT = 2.0
OPP_SHRINK = 0.35


# ---------- data ----------
def _parse_date(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            pass
    return None


def download(code, season):
    """Return list of finished matches: dict(date, home, away, hg, ag)."""
    url = BASE.format(season=season, code=code)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=25).read()
    except Exception:
        return []
    text = raw.decode("utf-8-sig", errors="replace")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        d = _parse_date(r.get("Date") or "")
        try:
            hg, ag = int(r["FTHG"]), int(r["FTAG"])
        except (KeyError, ValueError, TypeError):
            continue
        if d and r.get("HomeTeam") and r.get("AwayTeam"):
            rows.append({"date": d, "home": r["HomeTeam"].strip(),
                         "away": r["AwayTeam"].strip(), "hg": hg, "ag": ag})
    return rows


def load_league(code):
    rows = []
    for s in SEASONS:
        rows += download(code, s)
    return rows


def find_team_names(query, rows):
    q = query.lower().strip()
    names = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
    exact = [n for n in names if n.lower() == q]
    return exact or [n for n in names if q in n.lower()]


def locate(query, league_cache):
    """Search all leagues for the team. Returns (team_name, rows)."""
    for code in LEAGUES:
        if code not in league_cache:
            league_cache[code] = load_league(code)
        hits = find_team_names(query, league_cache[code])
        if hits:
            if len(hits) > 1:
                print(f"'{query}' matches {hits}; using '{hits[0]}'.")
            return hits[0], league_cache[code]
    sys.exit(f"Team '{query}' not found. Try the site's spelling "
             f"(e.g. 'Man United', 'Ath Madrid').")


def last_matches(team, rows, n=N):
    mine = [r for r in rows if team in (r["home"], r["away"])]
    mine.sort(key=lambda r: r["date"])
    out = []
    for r in mine[-n:]:
        home = r["home"] == team
        out.append({"date": r["date"].strftime("%Y-%m-%d"), "home": home,
                    "opp": r["away"] if home else r["home"],
                    "gf": r["hg"] if home else r["ag"],
                    "ga": r["ag"] if home else r["hg"]})
    return out


def ratings_from(rows):
    """Attack/defence per team (1.0 = average) from all loaded results."""
    gf, ga, pl = {}, {}, {}
    for r in rows:
        for t, f, a in ((r["home"], r["hg"], r["ag"]), (r["away"], r["ag"], r["hg"])):
            gf[t] = gf.get(t, 0) + f
            ga[t] = ga.get(t, 0) + a
            pl[t] = pl.get(t, 0) + 1
    total_games = sum(pl.values())
    if not total_games:
        return {}, DEFAULT_AVG_GOALS
    avg = sum(gf.values()) / total_games
    return ({t: (gf[t] / pl[t] / avg, ga[t] / pl[t] / avg)
             for t in pl if pl[t] >= 5}, avg)


# ---------- analysis ----------
def _damp(x):
    return (1 - OPP_SHRINK) * x + OPP_SHRINK


def summarise(matches, ratings, playing_home):
    sw = agf = aga = 0.0
    for m in matches:
        opp_att, opp_def = ratings.get(m["opp"], (1.0, 1.0))
        w = VENUE_WEIGHT if m["home"] == playing_home else 1.0
        agf += w * m["gf"] / max(_damp(opp_def), 0.3)
        aga += w * m["ga"] / max(_damp(opp_att), 0.3)
        sw += w
    n = len(matches)
    gf = sum(m["gf"] for m in matches)
    ga = sum(m["ga"] for m in matches)
    wins = sum(m["gf"] > m["ga"] for m in matches)
    draws = sum(m["gf"] == m["ga"] for m in matches)
    form = "".join("W" if m["gf"] > m["ga"] else "D" if m["gf"] == m["ga"]
                   else "L" for m in matches)
    venue = [m for m in matches if m["home"] == playing_home]
    return {"n": n, "adj_gf": agf / sw, "adj_ga": aga / sw,
            "gf": gf / n, "ga": ga / n, "w": wins, "d": draws,
            "l": n - wins - draws, "form": form,
            "clean": sum(m["ga"] == 0 for m in matches),
            "venue_n": len(venue),
            "venue_gf": sum(m["gf"] for m in venue) / len(venue) if venue else None,
            "venue_ga": sum(m["ga"] for m in venue) / len(venue) if venue else None}


def shrink(v, avg):
    return (1 - SHRINK) * v + SHRINK * avg


def poisson(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def predict(hs, as_, avg):
    h_att, h_def = shrink(hs["adj_gf"], avg) / avg, shrink(hs["adj_ga"], avg) / avg
    a_att, a_def = shrink(as_["adj_gf"], avg) / avg, shrink(as_["adj_ga"], avg) / avg
    lam_h = h_att * a_def * avg * HOME_ADVANTAGE
    lam_a = a_att * h_def * avg / HOME_ADVANTAGE
    grid = {(i, j): poisson(i, lam_h) * poisson(j, lam_a)
            for i in range(9) for j in range(9)}
    return {"xg_home": lam_h, "xg_away": lam_a,
            "home": sum(p for (i, j), p in grid.items() if i > j),
            "draw": sum(p for (i, j), p in grid.items() if i == j),
            "away": sum(p for (i, j), p in grid.items() if i < j),
            "top": sorted(grid.items(), key=lambda kv: -kv[1])[:3],
            "over25": sum(p for (i, j), p in grid.items() if i + j > 2),
            "btts": sum(p for (i, j), p in grid.items() if i > 0 and j > 0)}


# ---------- output ----------
def show_team(name, matches, s, ratings, playing_home):
    print(f"\n{name} - last {s['n']} matches (* = same venue as upcoming match)")
    for m in matches:
        v = "H" if m["home"] else "A"
        star = "*" if m["home"] == playing_home else " "
        print(f"  {m['date']} ({v}){star} vs {m['opp']:<20} {m['gf']}-{m['ga']}")
    print(f"  Form {s['form']} | W{s['w']} D{s['d']} L{s['l']} | "
          f"{s['gf']:.2f} scored / {s['ga']:.2f} conceded per game | "
          f"clean sheets {s['clean']}")
    print(f"  Opponent-adjusted: {s['adj_gf']:.2f} scored / {s['adj_ga']:.2f} conceded")
    where = "home" if playing_home else "away"
    if s["venue_n"]:
        print(f"  At {where} ({s['venue_n']} games): "
              f"{s['venue_gf']:.2f} scored / {s['venue_ga']:.2f} conceded")


def show_prediction(home, away, p):
    print(f"\n=== {home} vs {away} ===")
    print(f"Expected goals: {p['xg_home']:.2f} - {p['xg_away']:.2f}")
    (i, j), pr = p["top"][0]
    print(f"Most likely score: {i}-{j} ({pr:.0%})")
    print("Other likely: " + ", ".join(f"{a}-{b} ({q:.0%})" for (a, b), q in p["top"][1:]))
    print(f"{home} win {p['home']:.0%} | Draw {p['draw']:.0%} | {away} win {p['away']:.0%}")
    print(f"Over 2.5 goals {p['over25']:.0%} | Both score {p['btts']:.0%}")
    print("\nNote: statistical estimate from recent form only. Not betting advice.")


def demo_rows():
    import random
    random.seed(1)
    teams = ["Home FC", "Away FC", "Team C", "Team D", "Team E", "Team F"]
    rows, d = [], datetime(2026, 8, 1)
    for k in range(40):
        h, a = random.sample(teams, 2)
        rows.append({"date": d.replace(day=1 + k % 28, month=8 + k // 28),
                     "home": h, "away": a,
                     "hg": random.randint(0, 3), "ag": random.randint(0, 2)})
    return rows


def run(home_q, away_q, cache=None, demo=False):
    cache = {} if cache is None else cache
    if demo:
        rows = demo_rows()
        hn, an, pool = "Home FC", "Away FC", rows
    else:
        print("Downloading data (first run can take ~20 seconds)...")
        hn, hrows = locate(home_q, cache)
        an, arows = locate(away_q, cache)
        pool = hrows if hrows is arows else hrows + arows
    ratings, avg = ratings_from(pool)
    hm, am = last_matches(hn, pool), last_matches(an, pool)
    if len(hm) < 3 or len(am) < 3:
        sys.exit("Not enough recent matches found for one of the teams.")
    hs, as_ = summarise(hm, ratings, True), summarise(am, ratings, False)
    show_team(hn, hm, hs, ratings, True)
    show_team(an, am, as_, ratings, False)
    show_prediction(hn, an, predict(hs, as_, avg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("home", nargs="?")
    ap.add_argument("away", nargs="?")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if not a.demo and not (a.home and a.away):
        ap.error("give home and away team names")
    run(a.home, a.away, demo=a.demo)


if __name__ == "__main__":
    main()
