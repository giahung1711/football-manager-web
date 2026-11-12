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
import queue
import threading
import unicodedata
from datetime import datetime, timezone
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
# API-Football Free: stay well below typical per-minute limits and reserve
# part of the daily allowance for manual/API dashboard checks.
REQUEST_INTERVAL_SECONDS = 7.5
MAX_DAILY_REQUESTS = 60
API_BASE = "https://v3.football.api-sports.io"


def _ascii_name(value):
    value = str(value or "").casefold().replace("ø", "o").replace("ł", "l")
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def _norm(value):
    return re.sub(r"[^a-z0-9]+", "", _ascii_name(value))


def _name_tokens(value):
    return set(re.findall(r"[a-z0-9]+", _ascii_name(value)))


# Correct common in-game spelling variants before asking the provider.
_SEARCH_ALIASES = {
    _norm("Grabiel Magalhaes"): "Gabriel Magalhaes",
}

_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_METADATA_QUEUE = queue.Queue()
_PENDING_LOCK = threading.Lock()
_PENDING_NAMES = set()
_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False


class APIRequestBudgetExhausted(Exception):
    pass


def _reserve_daily_request():
    """Count requests locally and stop before consuming the whole Free quota."""
    cache = _read_cache()
    today = datetime.now(timezone.utc).date().isoformat()
    budget = cache.get("__api_daily_budget__")
    if not isinstance(budget, dict) or budget.get("date") != today:
        budget = {"date": today, "count": 0}
    count = int(budget.get("count", 0))
    if count >= MAX_DAILY_REQUESTS:
        return False
    budget["count"] = count + 1
    cache["__api_daily_budget__"] = budget
    _write_cache(cache)
    return True


def _start_metadata_worker():
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        thread = threading.Thread(target=_metadata_worker, name="fm-player-metadata", daemon=True)
        thread.start()
        _WORKER_STARTED = True


def _queue_metadata_refresh(name):
    key = _norm(name)
    if not key:
        return
    with _PENDING_LOCK:
        if key in _PENDING_NAMES:
            return
        _PENDING_NAMES.add(key)
    _start_metadata_worker()
    _METADATA_QUEUE.put((name, key))


def _metadata_worker():
    while True:
        name, key = _METADATA_QUEUE.get()
        try:
            _fetch_player_metadata(name)
        except Exception as exc:
            logger.error("metadata background sync failed player=%s error=%s", name, type(exc).__name__)
        finally:
            with _PENDING_LOCK:
                _PENDING_NAMES.discard(key)
            _METADATA_QUEUE.task_done()


def _read_cache():
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_cache(cache):
    try:
        # API request reservations are written immediately before each HTTP
        # call. Merge the newest counter so a later metadata-cache write cannot
        # accidentally reset the daily safety limit using an older snapshot.
        try:
            latest = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            latest_budget = latest.get("__api_daily_budget__") if isinstance(latest, dict) else None
            current_budget = cache.get("__api_daily_budget__")
            if isinstance(latest_budget, dict) and (
                    not isinstance(current_budget, dict) or
                    latest_budget.get("date") == current_budget.get("date") and
                    int(latest_budget.get("count", 0)) > int(current_budget.get("count", 0))):
                cache["__api_daily_budget__"] = latest_budget
        except (OSError, ValueError, TypeError):
            pass
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
    """Serialized, paced API request with a conservative daily budget."""
    global _LAST_REQUEST_AT
    with _REQUEST_LOCK:
        wait = REQUEST_INTERVAL_SECONDS - (time.monotonic() - _LAST_REQUEST_AT)
        if wait > 0:
            time.sleep(wait)
        if not _reserve_daily_request():
            raise APIRequestBudgetExhausted("local daily API request budget reached")
        _LAST_REQUEST_AT = time.monotonic()
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
        candidates.append({"id": team["id"], "name": team["name"], "logo": team.get("logo") or ""})
    # A player should normally be associated with one current squad. If the API
    # returns multiple ambiguous teams, do not silently choose one.
    unique = {str(x["id"]): x for x in candidates}
    return next(iter(unique.values())) if len(unique) == 1 else None


def _cached_team_for_player(cache, player_id, now):
    target = str(player_id)
    for cache_key, item in cache.items():
        if not cache_key.startswith("__team_squad__") or not isinstance(item, dict):
            continue
        if now - int(item.get("checked_at", 0)) >= CACHE_TTL:
            continue
        if target in {str(value) for value in item.get("player_ids", [])}:
            team = item.get("team")
            if isinstance(team, dict) and team.get("id") and team.get("name"):
                return team
    return None


def _cache_team_squad(cache, squad_rows, team, now):
    for row in squad_rows:
        row_team = row.get("team") or {}
        if str(row_team.get("id")) != str(team.get("id")):
            continue
        players = row.get("players")
        if isinstance(players, list) and players:
            ids = [str(item.get("id")) for item in players
                   if isinstance(item, dict) and item.get("id")]
            if ids:
                cache[f"__team_squad__{team['id']}"] = {
                    "checked_at": now, "team": team, "player_ids": ids,
                }
                _write_cache(cache)
        return


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


def _fetch_player_metadata(name, force=False):
    """Fetch one player in the background; called only by the paced worker."""
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
    search_name = _SEARCH_ALIASES.get(key, name)
    search_key = _norm(search_name)
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
        response = _api_get("players/profiles", {"search": search_name}, api_key)
        profiles = _api_payload(response, "players/profiles", name, api_key)
        if profiles is None:
            if response.status_code in (401, 403, 429) or response.status_code >= 500:
                _remember_provider_failure(cache, response.status_code, now)
            return cached.get("data") if isinstance(cached, dict) and _complete_metadata(cached.get("data")) else None

        exact = [row for row in profiles
                 if _norm((row.get("player") or {}).get("name")) == search_key]
        if len(exact) == 1:
            pool = exact
        elif len(exact) > 1:
            pool = []  # identical names with multiple profiles are ambiguous
        else:
            query_tokens = _name_tokens(search_name)
            scored = []
            for row in profiles:
                athlete_name = (row.get("player") or {}).get("name", "")
                candidate_tokens = _name_tokens(athlete_name)
                score = len(query_tokens & candidate_tokens) / max(1, len(query_tokens))
                if score >= 0.8:
                    scored.append((score, row))
            best_score = max((score for score, _ in scored), default=0)
            best = [row for score, row in scored if score == best_score]
            pool = best if len(best) == 1 else []
        player = next(((row.get("player") or {}) for row in pool
                       if (row.get("player") or {}).get("id") and
                       (row.get("player") or {}).get("nationality")), None)
        if not player:
            cache[key] = {"checked_at": now, "data": None}
            _write_cache(cache)
            logger.warning("API-Football profile not found/ambiguous player=%s", name)
            return None

        # Reuse a verified team roster when the provider returned the full
        # squad list for an earlier player from the same club.
        team = _cached_team_for_player(cache, player["id"], now)
        if not team:
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
            _cache_team_squad(cache, squads, team, now)

        league_name = _get_current_league(team["id"], api_key, cache, now, name)
        data = {
            "nationality": player.get("nationality"),
            "club": team["name"],
            "club_logo_url": team.get("logo", ""),
            "photo_url": player.get("photo", ""),
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

    except APIRequestBudgetExhausted:
        logger.warning("API-Football daily safety budget reached; remaining player lookups paused")
    except requests.Timeout:
        logger.error("API-Football timeout player=%s", name)
        _remember_provider_failure(cache, 0, now)
    except requests.RequestException as exc:
        logger.error("API-Football network failure player=%s error=%s", name, type(exc).__name__)
        _remember_provider_failure(cache, 0, now)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        logger.exception("API-Football invalid response player=%s error=%s", name, type(exc).__name__)

    return cached.get("data") if isinstance(cached, dict) and _complete_metadata(cached.get("data")) else None



def get_player_metadata(name, force=False):
    """Return cached verified data immediately and queue any needed refresh.

    Rendering never performs provider I/O. A single daemon worker processes
    names one at a time with a 7.5-second gap between every API request.
    """
    if not name:
        return None

    # Retired ICON/HEROES may be configured with nationality only. Their
    # retired status and special card type must be explicitly Admin-curated.
    try:
        curated = json.loads(os.environ.get("SPECIAL_PLAYER_METADATA", "{}"))
        curated_item = next((v for k, v in curated.items() if _norm(k) == _norm(name)), None)
        if isinstance(curated_item, dict):
            special_type = str(curated_item.get("type", "")).upper()
            retired = bool(curated_item.get("retired") or curated_item.get("career_status") == "retired")
            if retired and special_type in {"ICON", "HEROES"} and curated_item.get("nationality"):
                return {
                    "nationality": curated_item["nationality"], "club": "", "league": "",
                    "source": curated_item.get("source", "Admin verified"),
                    "is_icon": special_type == "ICON", "is_hero": special_type == "HEROES",
                    "card_type": special_type, "career_status": "retired",
                }
            if special_type in {"ICON", "HEROES"} and all(
                    curated_item.get(k) for k in ("nationality", "club", "league")):
                return {
                    "nationality": curated_item["nationality"], "club": curated_item["club"],
                    "league": curated_item["league"],
                    "source": curated_item.get("source", "Admin verified"),
                    "is_icon": special_type == "ICON", "is_hero": special_type == "HEROES",
                    "card_type": special_type,
                }
    except (ValueError, AttributeError, TypeError):
        logger.warning("SPECIAL_PLAYER_METADATA is invalid; skipping curated records")

    cache = _read_cache()
    key = _norm(name)
    cached = cache.get(key)
    now = int(time.time())
    if isinstance(cached, dict):
        data = cached.get("data")
        ttl = CACHE_TTL if _complete_metadata(data) else NEGATIVE_CACHE_TTL
        if now - int(cached.get("checked_at", 0)) < ttl and not force:
            return data if _complete_metadata(data) else None
        # Continue showing last verified data while refreshing it in background.
        stale_verified = data if _complete_metadata(data) else None
    else:
        stale_verified = None

    if not os.environ.get("APISPORTS_KEY", "").strip():
        return stale_verified
    _queue_metadata_refresh(name)
    return stale_verified


def enrich_player(record):
    """Attach verified metadata for this render without mutating the saved squad."""
    import copy
    result = copy.deepcopy(record)
    if str(result.get("name", "")).strip().casefold() == "zidane":
        result["name"] = "Zinedine Zidane"
    if result.get("name") == "Zinedine Zidane":
        result.setdefault("position", "CAM")
        result.setdefault("rating", 101)
        result.setdefault("level", 0)
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
    # Keep game-owned card fields authoritative. Provider metadata must never
    # overwrite the saved name, position, OVR, upgrade level, or event identity.
    core_fields = {key: copy.deepcopy(result.get(key)) for key in (
        "name", "position", "rating", "level", "event_card",
        "original_rating", "card_season", "market_value", "photo_url"
    ) if key in result}
    meta = get_player_metadata(result.get("name", ""))
    if not meta:
        result["metadata_complete"] = False
        return result
    result.update(meta)
    result.update(core_fields)
    result["metadata_complete"] = True
    special = _special_types().get(_norm(result.get("name")))
    result["is_icon"] = bool(meta.get("is_icon")) or special == "ICON"
    result["is_hero"] = bool(meta.get("is_hero")) or special == "HEROES"
    result["card_type"] = meta.get("card_type") or special or "REGULAR"
    return result
