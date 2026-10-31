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
