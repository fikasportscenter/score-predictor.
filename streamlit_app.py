def hl_key():
    return secret("APIFOOTBALL_KEY").strip()


def _hl_get(path, params, key):
    """One APIfootball request, counted against the daily budget."""
    h = _hl_state()
    today = datetime.now(timezone.utc).date().isoformat()
    if h["day"] != today:
        h["day"], h["used"] = today, 0
    if h["used"] >= hl_budget():
        raise RuntimeError("daily request limit reached")
    h["used"] += 1
    q = urllib.parse.urlencode(dict(params, APIkey=key))
    req = urllib.request.Request("https://apiv3.apifootball.com/?" + q,
                                 headers={"User-Agent": "score-predictor"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch_day(day, key, max_calls=None):
    """All matches of one date, in Uganda time. Returns (rows, calls_used)."""
    data = _hl_get("", {"action": "get_events", "from": day, "to": day,
                        "timezone": "Africa/Kampala"}, key)
    if isinstance(data, dict):      # APIfootball answers with a dict when empty or on error
        if data.get("error") in (401, 403, 429):
            raise RuntimeError(str(data.get("message")))
        return [], 1
    return data, 1


def _norm(r):
    hn, an = r.get("match_hometeam_name"), r.get("match_awayteam_name")
    if not hn or not an or not r.get("match_date"):
        return None
    try:
        d = datetime.strptime(r["match_date"], "%Y-%m-%d")
        hh, mm = (r.get("match_time") or "00:00").split(":")[:2]
        when = datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=UG_TZ)
    except Exception:
        return None
    hs, as_ = str(r.get("match_hometeam_score", "")), str(r.get("match_awayteam_score", ""))
    score = (int(hs), int(as_)) if hs.isdigit() and as_.isdigit() else None
    return {"id": r.get("match_id"), "when": when,
            "country": r.get("country_name") or "", "league": r.get("league_name") or "",
            "home": hn, "away": an,
            "state": r.get("match_status") or "Not started", "score": score}