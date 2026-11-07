"""Verified player metadata sync using API-SPORTS / API-Football.

APISPORTS_KEY is read only at runtime. Successful metadata is cached for 12h;
negative lookups are cached briefly to avoid repeatedly spending API quota.
Temporary/API failures are never cached as missing player data. Logs never
include credentials or full request headers.
"""
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path

import requests

logger = logging.getLogger("player_metadata")
CACHE_FILE = Path(os.environ.get("PLAYER_METADATA_CACHE", "/tmp/fm_player_metadata_cache.json"))
CACHE_TTL = 12 * 60 * 60
NEGATIVE_CACHE_TTL = 15 * 60
# Provider-wide cooldown prevents every page render from retrying dozens of players.
AUTH_COOLDOWN = 15 * 60
RATE_LIMIT_COOLDOWN = 5 * 60
SERVER_COOLDOWN = 2 * 60
API_BASE = "https://v3.football.api-sports.io"


def _norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _read_cache():
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_cache(cache):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="fm-player-cache-", dir=str(CACHE_FILE.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(cache, stream, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
    except OSError as exc:
        logger.warning("metadata cache write failed: %s", type(exc).__name__)


def _special_types():
    try:
        raw = json.loads(os.environ.get("SPECIAL_PLAYER_TYPES", "{}"))
        return {_norm(k): str(v).upper() for k, v in raw.items()
                if str(v).upper() in {"ICON", "HEROES"}}
    except (ValueError, AttributeError, TypeError):
        logger.warning("SPECIAL_PLAYER_TYPES is invalid JSON")
        return {}


def _complete_metadata(data):
    return isinstance(data, dict) and all(data.get(k) for k in ("nationality", "club", "league"))


def _api_get(endpoint, params, api_key):
    """One API request with safe logging; never logs the API key."""
    return requests.get(
        f"{API_BASE}/{endpoint}",
        params=params,
        headers={"x-apisports-key": api_key},
        timeout=(4, 12),
    )


def _safe_response_detail(response, api_key=""):
    """Return a short provider error detail without exposing credentials."""
    try:
        detail = (response.text or "").strip()
    except Exception:
        detail = ""
    if api_key:
        detail = detail.replace(api_key, "[REDACTED]")
    detail = re.sub(r"(?i)(x-apisports-key|authorization)(\s*[:=]\s*)[^,;\s]+",
                    r"\1\2[REDACTED]", detail)
    return re.sub(r"\s+", " ", detail)[:500] or "<empty response body>"


def _api_payload(response, endpoint, player_name, api_key=""):
    if response.status_code != 200:
        logger.error("API-Football HTTP failure endpoint=%s player=%s status=%s detail=%s",
                     endpoint, player_name, response.status_code,
                     _safe_response_detail(response, api_key))
        return None
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        logger.error("API-Football response error endpoint=%s player=%s details=%s",
                     endpoint, player_name, json.dumps(errors, ensure_ascii=False)[:300])
        return None
    return payload.get("response") or []


def _remember_provider_failure(cache, status, now):
    if status in (401, 403):
        delay = AUTH_COOLDOWN
    elif status == 429:
        delay = RATE_LIMIT_COOLDOWN
    else:
        delay = SERVER_COOLDOWN
    cache["__provider_cooldown__"] = {"until": now + delay, "status": status}
    _write_cache(cache)


def _extract_team_id(squad_rows, player_id):
    """Read current team association from /players/squads without guessing."""
    candidates = []
    for row in squad_rows:
        if not isinstance(row, dict):
            continue
        team = row.get("team") or {}
        if not team.get("id") or not team.get("name"):
            continue
        players = row.get("players")
        # If API supplies a player list, require the requested player to be in it.
        if isinstance(players, list) and players:
            if not any(str(x.get("id")) == str(player_id) for x in players if isinstance(x, dict)):
                continue
        candidates.append({"id": team["id"], "name": team["name"]})
    # A player should normally be associated with one current squad. If the API
    # returns multiple ambiguous teams, do not silently choose one.
    unique = {str(x["id"]): x for x in candidates}
    return next(iter(unique.values())) if len(unique) == 1 else None


def _get_current_league(team_id, api_key, cache, now, player_name):
    team_cache_key = f"__team_league__{team_id}"
    cached = cache.get(team_cache_key)
    if isinstance(cached, dict) and now - int(cached.get("checked_at", 0)) < CACHE_TTL:
        return cached.get("league")
    response = _api_get("leagues", {"team": team_id, "current": "true"}, api_key)
    rows = _api_payload(response, "leagues", player_name, api_key)
    if rows is None:
        if response.status_code in (401, 403, 429) or response.status_code >= 500:
            _remember_provider_failure(cache, response.status_code, now)
        return None
    # Ignore cups; only accept one unambiguous active domestic league.
    leagues = []
    for row in rows:
        league = row.get("league") or {}
        if str(league.get("type", "")).casefold() == "league" and league.get("name"):
            leagues.append(league["name"])
    leagues = sorted(set(leagues))
    league_name = leagues[0] if len(leagues) == 1 else None
    cache[team_cache_key] = {"checked_at": now, "league": league_name}
    _write_cache(cache)
    return league_name


def get_player_metadata(name, force=False):
    """Return complete verified metadata from season-independent profile/squad APIs."""
    if not name:
        return None

    # Retired ICON/HEROES cards require an explicitly curated complete record.
    try:
        curated = json.loads(os.environ.get("SPECIAL_PLAYER_METADATA", "{}"))
        curated_item = next((v for k, v in curated.items() if _norm(k) == _norm(name)), None)
        if isinstance(curated_item, dict):
            special_type = str(curated_item.get("type", "")).upper()
            if special_type in {"ICON", "HEROES"} and all(
                    curated_item.get(k) for k in ("nationality", "club", "league")):
                logger.info("metadata curated hit player=%s type=%s", name, special_type)
                return {
                    "nationality": curated_item["nationality"],
                    "club": curated_item["club"],
                    "league": curated_item["league"],
                    "source": curated_item.get("source", "Admin verified"),
                    "is_icon": special_type == "ICON",
                    "is_hero": special_type == "HEROES",
                    "card_type": special_type,
                }
    except (ValueError, AttributeError, TypeError):
        logger.warning("SPECIAL_PLAYER_METADATA is invalid; skipping curated records")

    api_key = os.environ.get("APISPORTS_KEY", "").strip()
    if not api_key:
        logger.error("API-Football disabled: APISPORTS_KEY is missing")
        return None

    cache = _read_cache()
    key = _norm(name)
    cached = cache.get(key)
    now = int(time.time())
    cooldown = cache.get("__provider_cooldown__")
    if isinstance(cooldown, dict) and now < int(cooldown.get("until", 0)):
        # The provider failure was already logged at its source; avoid one log
        # line per player/render while the shared cooldown is active.
        return cached.get("data") if isinstance(cached, dict) and _complete_metadata(cached.get("data")) else None
    if not force and isinstance(cached, dict):
        data = cached.get("data")
        ttl = CACHE_TTL if _complete_metadata(data) else NEGATIVE_CACHE_TTL
        if now - int(cached.get("checked_at", 0)) < ttl:
            return data if _complete_metadata(data) else None

    try:
        logger.info("API-Football profile lookup started player=%s", name)
        # /players/profiles is season-independent; unlike /players it does not
        # require a statistics season that may be unavailable on the Free plan.
        response = _api_get("players/profiles", {"search": name}, api_key)
        profiles = _api_payload(response, "players/profiles", name, api_key)
        if profiles is None:
            if response.status_code in (401, 403, 429) or response.status_code >= 500:
                _remember_provider_failure(cache, response.status_code, now)
            return cached.get("data") if isinstance(cached, dict) and _complete_metadata(cached.get("data")) else None

        exact = [row for row in profiles if _norm((row.get("player") or {}).get("name")) == key]
        pool = exact or profiles
        player = next(((row.get("player") or {}) for row in pool
                       if (row.get("player") or {}).get("id") and
                       (row.get("player") or {}).get("nationality")), None)
        if not player:
            cache[key] = {"checked_at": now, "data": None}
            _write_cache(cache)
            logger.warning("API-Football profile not found/ambiguous player=%s", name)
            return None

        # Ask for the player's current squad association, not historical stats.
        response = _api_get("players/squads", {"player": player["id"]}, api_key)
        squads = _api_payload(response, "players/squads", name, api_key)
        if squads is None:
            if response.status_code in (401, 403, 429) or response.status_code >= 500:
                _remember_provider_failure(cache, response.status_code, now)
            return cached.get("data") if isinstance(cached, dict) and _complete_metadata(cached.get("data")) else None
        team = _extract_team_id(squads, player["id"])
        if not team:
            logger.warning("API-Football current squad unresolved player=%s id=%s", name, player["id"])
            cache[key] = {"checked_at": now, "data": None}
            _write_cache(cache)
            return None

        league_name = _get_current_league(team["id"], api_key, cache, now, name)
        data = {
            "nationality": player.get("nationality"),
            "club": team["name"],
            "league": league_name,
            "source": "API-Football",
            "updated_at": now,
        }
        if not _complete_metadata(data):
            logger.warning("API-Football metadata incomplete player=%s club=%s league_resolved=%s",
                           name, team["name"], bool(league_name))
            cache[key] = {"checked_at": now, "data": None}
            _write_cache(cache)
            return None

        cache.pop("__provider_cooldown__", None)
        cache[key] = {"checked_at": now, "data": data}
        _write_cache(cache)
        logger.info("API-Football verified player=%s club=%s league=%s nationality=%s",
                    name, data["club"], data["league"], data["nationality"])
        return data

    except requests.Timeout:
        logger.error("API-Football timeout player=%s", name)
        _remember_provider_failure(cache, 0, now)
    except requests.RequestException as exc:
        logger.error("API-Football network failure player=%s error=%s", name, type(exc).__name__)
        _remember_provider_failure(cache, 0, now)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        logger.exception("API-Football invalid response player=%s error=%s", name, type(exc).__name__)

    return cached.get("data") if isinstance(cached, dict) and _complete_metadata(cached.get("data")) else None


def enrich_player(record):
    """Attach verified metadata for this render without mutating the saved squad."""
    import copy
    result = copy.deepcopy(record)
    # Admin-gifted records carry reviewed metadata and a source URL. A fully
    # retired ICON/HEROES player needs nationality + special badge only.
    if result.get("metadata_admin_verified") and result.get("nationality"):
        card_type = str(result.get("card_type", "REGULAR")).upper()
        retired = result.get("career_status") == "retired"
        if retired and card_type in {"ICON", "HEROES"}:
            result["club"] = ""
            result["league"] = ""
            result["metadata_complete"] = True
            result["is_icon"] = card_type == "ICON"
            result["is_hero"] = card_type == "HEROES"
            return result
        if result.get("club") and result.get("league"):
            result["metadata_complete"] = True
            result["is_icon"] = card_type == "ICON"
            result["is_hero"] = card_type == "HEROES"
            return result
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
