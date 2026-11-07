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


def get_player_metadata(name, force=False):
    """Return complete verified metadata or None; never return placeholders."""
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
    if not force and isinstance(cached, dict):
        data = cached.get("data")
        ttl = CACHE_TTL if _complete_metadata(data) else NEGATIVE_CACHE_TTL
        if now - int(cached.get("checked_at", 0)) < ttl:
            if _complete_metadata(data):
                logger.info("metadata cache hit player=%s", name)
                return data
            logger.info("metadata negative-cache hit player=%s; retry after TTL", name)
            return None

    logger.info("API-Football lookup started player=%s season=2026", name)
    try:
        response = requests.get(
            f"{API_BASE}/players",
            params={"search": name, "season": 2026},
            headers={"x-apisports-key": api_key},
            timeout=(4, 12),
        )
        if response.status_code != 200:
            logger.error("API-Football HTTP failure player=%s status=%s", name, response.status_code)
            return cached.get("data") if isinstance(cached, dict) and _complete_metadata(cached.get("data")) else None

        payload = response.json()
        api_errors = payload.get("errors")
        if api_errors:
            # API may return HTTP 200 with an errors object (invalid key/quota/etc.).
            logger.error("API-Football response error player=%s details=%s", name,
                         json.dumps(api_errors, ensure_ascii=False)[:500])
            return cached.get("data") if isinstance(cached, dict) and _complete_metadata(cached.get("data")) else None

        candidates = payload.get("response") or []
        exact = [item for item in candidates
                 if _norm((item.get("player") or {}).get("name")) == key]
        pool = exact or candidates
        selected = next((item for item in pool
                         if (item.get("player") or {}).get("nationality")
                         and (item.get("statistics") or [{}])[0].get("team", {}).get("name")
                         and (item.get("statistics") or [{}])[0].get("league", {}).get("name")), None)

        if not selected:
            logger.warning("API-Football no complete exact/usable result player=%s candidates=%s exact=%s",
                           name, len(candidates), len(exact))
            cache[key] = {"checked_at": now, "data": None}
            _write_cache(cache)
            return None

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
        if not _complete_metadata(data):
            logger.warning("API-Football incomplete result player=%s", name)
            cache[key] = {"checked_at": now, "data": None}
            _write_cache(cache)
            return None

        cache[key] = {"checked_at": now, "data": data}
        _write_cache(cache)
        logger.info("API-Football verified player=%s club=%s league=%s nationality=%s",
                    name, data["club"], data["league"], data["nationality"])
        return data

    except requests.Timeout:
        logger.error("API-Football timeout player=%s", name)
    except requests.RequestException as exc:
        logger.error("API-Football network failure player=%s error=%s", name, type(exc).__name__)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        logger.exception("API-Football invalid response player=%s error=%s", name, type(exc).__name__)

    # Preserve a previously verified record during transient failures.
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
