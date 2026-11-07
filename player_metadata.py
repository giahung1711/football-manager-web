"""Player metadata sync using API-SPORTS / API-Football.

Set APISPORTS_KEY in the hosting environment. Metadata is cached for 12 hours.
A player is considered displayable only when nationality, current club and league
are all present. Special ICON/HEROES labels are opt-in via SPECIAL_PLAYER_TYPES
(JSON object: {"Player Name": "ICON" | "HEROES"}); the API does not decide rarity.
"""
import json
import os
import re
import tempfile
import time
from pathlib import Path

import requests

CACHE_FILE = Path(os.environ.get("PLAYER_METADATA_CACHE", "/tmp/fm_player_metadata_cache.json"))
CACHE_TTL = 12 * 60 * 60
API_BASE = "https://v3.football.api-sports.io"


def _norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _read_cache():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _write_cache(cache):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="fm-player-cache-", dir=str(CACHE_FILE.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(cache, stream, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass


def _special_types():
    try:
        raw = json.loads(os.environ.get("SPECIAL_PLAYER_TYPES", "{}"))
        return { _norm(k): str(v).upper() for k, v in raw.items()
                 if str(v).upper() in {"ICON", "HEROES"} }
    except (ValueError, AttributeError):
        return {}


def get_player_metadata(name, force=False):
    """Return complete verified metadata or None; never return placeholder values."""
    if not name:
        return None
    # Retired ICON/HEROES cards need a deliberately curated last-club record;
    # this is accepted only when every required field and the special type exist.
    try:
        curated = json.loads(os.environ.get("SPECIAL_PLAYER_METADATA", "{}"))
        curated_item = next((v for k, v in curated.items() if _norm(k) == _norm(name)), None)
        if isinstance(curated_item, dict):
            special_type = str(curated_item.get("type", "")).upper()
            if (special_type in {"ICON", "HEROES"}
                    and all(curated_item.get(k) for k in ("nationality", "club", "league"))):
                return {"nationality": curated_item["nationality"],
                        "club": curated_item["club"], "league": curated_item["league"],
                        "source": curated_item.get("source", "Admin verified"),
                        "is_icon": special_type == "ICON", "is_hero": special_type == "HEROES",
                        "card_type": special_type}
    except (ValueError, AttributeError, TypeError):
        pass

    api_key = os.environ.get("APISPORTS_KEY", "").strip()
    if not api_key:
        return None

    cache = _read_cache()
    key = _norm(name)
    cached = cache.get(key)
    now = int(time.time())
    if not force and cached and now - int(cached.get("checked_at", 0)) < CACHE_TTL:
        data = cached.get("data")
        return data if isinstance(data, dict) and all(data.get(k) for k in ("nationality", "club", "league")) else None

    try:
        response = requests.get(
            f"{API_BASE}/players",
            params={"search": name, "season": 2026},
            headers={"x-apisports-key": api_key},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        candidates = payload.get("response") or []
        exact = [item for item in candidates
                 if _norm((item.get("player") or {}).get("name")) == key]
        candidates = exact or candidates
        # Prefer a result with a complete team/league/nationality tuple.
        selected = next((item for item in candidates
                         if (item.get("player") or {}).get("nationality")
                         and (item.get("statistics") or [{}])[0].get("team", {}).get("name")
                         and (item.get("statistics") or [{}])[0].get("league", {}).get("name")), None)
        data = None
        if selected:
            athlete = selected.get("player") or {}
            stats = selected.get("statistics") or [{}]
            stat = stats[0] if stats else {}
            team = stat.get("team") or {}
            league = stat.get("league") or {}
            data = {
                "nationality": athlete.get("nationality"),
                "club": team.get("name"),
                "league": league.get("name"),
                "source": "API-Football",
                "updated_at": now,
            }
            if not all(data.get(k) for k in ("nationality", "club", "league")):
                data = None
        cache[key] = {"checked_at": now, "data": data}
        _write_cache(cache)
        return data
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError):
        # Do not replace a previously verified result with guessed metadata.
        return cached.get("data") if cached and isinstance(cached.get("data"), dict) else None


def enrich_player(record):
    """Attach verified metadata for this render without mutating the saved squad."""
    import copy
    result = copy.deepcopy(record)
    meta = get_player_metadata(result.get("name", ""))
    if not meta:
        result["metadata_complete"] = False
        return result
    result.update(meta)
    result["metadata_complete"] = True
    special = _special_types().get(_norm(result.get("name")))
    result["is_icon"] = bool(meta.get("is_icon")) or special == "ICON"
    result["is_hero"] = bool(meta.get("is_hero")) or special == "HEROES"
    result["card_type"] = meta.get("card_type") or special or "REGULAR"
    return result
