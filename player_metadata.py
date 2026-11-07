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

# Curated records for named special players and the explicitly requested
# Vietnamese custom players. These are presentation metadata only; player
# records, ratings, ownership and progression remain in the normal game state.
_MANUAL_METADATA = {
    _norm("Zidane"): {"nationality": "France", "club": "", "league": "", "card_type": "ICON", "is_icon": True},
    _norm("Beckenbauer"): {"nationality": "Germany", "club": "", "league": "", "card_type": "ICON", "is_icon": True},
    _norm("Matthäus"): {"nationality": "Germany", "club": "", "league": "", "card_type": "ICON", "is_icon": True},
    _norm("Cafu"): {"nationality": "Brazil", "club": "", "league": "", "card_type": "ICON", "is_icon": True},
    _norm("Rio Ferdinand"): {"nationality": "England", "club": "", "league": "", "card_type": "ICON", "is_icon": True},
    _norm("Ronaldinho"): {"nationality": "Brazil", "club": "", "league": "", "card_type": "ICON", "is_icon": True},
    _norm("Lionel Messi"): {
        "nationality": "Argentina", "club": "Inter Miami CF", "league": "Major League Soccer",
        "club_logo": "https://media.api-sports.io/football/teams/9568.png",
        "league_logo": "https://media.api-sports.io/football/leagues/253.png", "card_type": "REGULAR",
    },
    _norm("Cristiano Ronaldo"): {
        "nationality": "Portugal", "club": "Al Nassr", "league": "Saudi Pro League",
        "club_logo": "https://media.api-sports.io/football/teams/250.png",
        "league_logo": "https://media.api-sports.io/football/leagues/307.png", "card_type": "REGULAR",
    },
}
for _vn_name in ("Le Minh", "Chi Hieu", "Minh Khang", "Trieu Vy", "Pun", "Sweet", "Phuc Vinh", "Hoang Quan"):
    _MANUAL_METADATA[_norm(_vn_name)] = {"nationality": "Vietnam", "club": "", "league": "", "card_type": "REGULAR"}

# Country name -> Unicode flag. Unknown/missing values deliberately return an
# empty string so only the unavailable country element is omitted.
_COUNTRY_FLAGS = {
    "argentina":"🇦🇷", "australia":"🇦🇺", "austria":"🇦🇹", "belgium":"🇧🇪", "brazil":"🇧🇷",
    "cameroon":"🇨🇲", "canada":"🇨🇦", "chile":"🇨🇱", "china":"🇨🇳", "colombia":"🇨🇴",
    "croatia":"🇭🇷", "czech republic":"🇨🇿", "czechia":"🇨🇿", "denmark":"🇩🇰", "egypt":"🇪🇬",
    "england":"🏴", "france":"🇫🇷", "germany":"🇩🇪", "ghana":"🇬🇭", "greece":"🇬🇷",
    "ivory coast":"🇨🇮", "cote d'ivoire":"🇨🇮", "iran":"🇮🇷", "iraq":"🇮🇶", "ireland":"🇮🇪",
    "italy":"🇮🇹", "japan":"🇯🇵", "mexico":"🇲🇽", "morocco":"🇲🇦", "netherlands":"🇳🇱",
    "nigeria":"🇳🇬", "norway":"🇳🇴", "poland":"🇵🇱", "portugal":"🇵🇹", "romania":"🇷🇴",
    "scotland":"🏴", "senegal":"🇸🇳", "serbia":"🇷🇸", "south korea":"🇰🇷", "spain":"🇪🇸",
    "sweden":"🇸🇪", "switzerland":"🇨🇭", "turkey":"🇹🇷", "türkiye":"🇹🇷", "ukraine":"🇺🇦",
    "united states":"🇺🇸", "usa":"🇺🇸", "uruguay":"🇺🇾", "wales":"🏴", "vietnam":"🇻🇳",
}

_COUNTRY_ISO = {
    # ISO alpha-2 codes for football nations, aliases as commonly returned by API-Football.
    "afghanistan":"AF", "albania":"AL", "algeria":"DZ", "andorra":"AD", "angola":"AO", "antigua and barbuda":"AG",
    "argentina":"AR", "armenia":"AM", "australia":"AU", "austria":"AT", "azerbaijan":"AZ", "bahamas":"BS",
    "bahrain":"BH", "bangladesh":"BD", "barbados":"BB", "belarus":"BY", "belgium":"BE", "belize":"BZ",
    "benin":"BJ", "bermuda":"BM", "bhutan":"BT", "bolivia":"BO", "bosnia":"BA", "bosnia and herzegovina":"BA",
    "botswana":"BW", "brazil":"BR", "brunei":"BN", "bulgaria":"BG", "burkina faso":"BF", "burundi":"BI",
    "cambodia":"KH", "cameroon":"CM", "canada":"CA", "cape verde":"CV", "central african republic":"CF",
    "chad":"TD", "chile":"CL", "china":"CN", "colombia":"CO", "comoros":"KM", "congo":"CG",
    "costa rica":"CR", "croatia":"HR", "cuba":"CU", "curacao":"CW", "cyprus":"CY", "czech republic":"CZ", "czechia":"CZ",
    "democratic republic of the congo":"CD", "denmark":"DK", "djibouti":"DJ", "dominica":"DM", "dominican republic":"DO",
    "ecuador":"EC", "egypt":"EG", "el salvador":"SV", "england":"GB", "equatorial guinea":"GQ", "eritrea":"ER",
    "estonia":"EE", "eswatini":"SZ", "ethiopia":"ET", "fiji":"FJ", "finland":"FI", "france":"FR", "gabon":"GA",
    "gambia":"GM", "georgia":"GE", "germany":"DE", "ghana":"GH", "gibraltar":"GI", "greece":"GR", "grenada":"GD",
    "guatemala":"GT", "guinea":"GN", "guinea-bissau":"GW", "guyana":"GY", "haiti":"HT", "honduras":"HN",
    "hong kong":"HK", "hungary":"HU", "iceland":"IS", "india":"IN", "indonesia":"ID", "iran":"IR", "iraq":"IQ",
    "ireland":"IE", "israel":"IL", "italy":"IT", "ivory coast":"CI", "cote d'ivoire":"CI", "jamaica":"JM",
    "japan":"JP", "jordan":"JO", "kazakhstan":"KZ", "kenya":"KE", "kosovo":"XK", "kuwait":"KW", "kyrgyzstan":"KG",
    "laos":"LA", "latvia":"LV", "lebanon":"LB", "lesotho":"LS", "liberia":"LR", "libya":"LY", "liechtenstein":"LI",
    "lithuania":"LT", "luxembourg":"LU", "macau":"MO", "madagascar":"MG", "malawi":"MW", "malaysia":"MY",
    "maldives":"MV", "mali":"ML", "malta":"MT", "mauritania":"MR", "mauritius":"MU", "mexico":"MX", "moldova":"MD",
    "monaco":"MC", "mongolia":"MN", "montenegro":"ME", "morocco":"MA", "mozambique":"MZ", "myanmar":"MM",
    "namibia":"NA", "nepal":"NP", "netherlands":"NL", "new zealand":"NZ", "nicaragua":"NI", "niger":"NE", "nigeria":"NG",
    "north korea":"KP", "north macedonia":"MK", "northern ireland":"GB", "norway":"NO", "oman":"OM", "pakistan":"PK",
    "palestine":"PS", "panama":"PA", "papua new guinea":"PG", "paraguay":"PY", "peru":"PE", "philippines":"PH",
    "poland":"PL", "portugal":"PT", "puerto rico":"PR", "qatar":"QA", "romania":"RO", "russia":"RU", "russian federation":"RU",
    "rwanda":"RW", "saint kitts and nevis":"KN", "saint lucia":"LC", "saint vincent":"VC", "samoa":"WS", "san marino":"SM",
    "sao tome and principe":"ST", "saudi arabia":"SA", "scotland":"GB", "senegal":"SN", "serbia":"RS", "seychelles":"SC",
    "sierra leone":"SL", "singapore":"SG", "slovakia":"SK", "slovenia":"SI", "solomon islands":"SB", "somalia":"SO",
    "south africa":"ZA", "south korea":"KR", "south sudan":"SS", "spain":"ES", "sri lanka":"LK", "sudan":"SD",
    "suriname":"SR", "sweden":"SE", "switzerland":"CH", "syria":"SY", "tahiti":"PF", "taiwan":"TW", "tajikistan":"TJ",
    "tanzania":"TZ", "thailand":"TH", "togo":"TG", "tonga":"TO", "trinidad and tobago":"TT", "tunisia":"TN",
    "turkey":"TR", "türkiye":"TR", "turkmenistan":"TM", "uganda":"UG", "ukraine":"UA", "united arab emirates":"AE",
    "united kingdom":"GB", "united states":"US", "usa":"US", "uruguay":"UY", "uzbekistan":"UZ", "vanuatu":"VU",
    "venezuela":"VE", "vietnam":"VN", "wales":"GB", "yemen":"YE", "zambia":"ZM", "zimbabwe":"ZW",
}


def country_flag(country):
    name = str(country or "").strip().casefold()
    # England, Scotland and Wales use Unicode subdivision flag tag sequences.
    subdivision_flags = {
        "england": "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F",
        "scotland": "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F",
        "wales": "\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F",
    }
    known = subdivision_flags.get(name, _COUNTRY_FLAGS.get(name))
    if known:
        return known
    code = _COUNTRY_ISO.get(name)
    if code and len(code) == 2 and code.isalpha():
        return "".join(chr(0x1F1E6 + ord(letter.upper()) - ord("A")) for letter in code)
    return ""

# Common full-name variants for ICON players; names are normalized before match.
_MANUAL_NAME_ALIASES = {
    _norm("Zinedine Zidane"): _norm("Zidane"),
    _norm("Franz Beckenbauer"): _norm("Beckenbauer"),
    _norm("Lothar Matthäus"): _norm("Matthäus"),
    _norm("Lothar Matthaus"): _norm("Matthäus"),
    _norm("Marcos Cafu"): _norm("Cafu"),
    _norm("Ronaldinho Gaucho"): _norm("Ronaldinho"),
    _norm("Ronaldinho Gaúcho"): _norm("Ronaldinho"),
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
        candidates.append({"id": team["id"], "name": team["name"], "logo": team.get("logo", "")})
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
        # Older cache versions stored the league name directly.
        value = cached.get("league")
        return value if isinstance(value, dict) else {"name": value, "logo": cached.get("logo", "")}
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
            leagues.append({"name": league["name"], "logo": league.get("logo", "")})
    unique = {item["name"]: item for item in leagues}
    league_data = next(iter(unique.values())) if len(unique) == 1 else None
    cache[team_cache_key] = {"checked_at": now, "league": league_data}
    _write_cache(cache)
    return league_data


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

        league_data = _get_current_league(team["id"], api_key, cache, now, name)
        if isinstance(league_data, dict):
            league_name = league_data.get("name")
            league_logo = league_data.get("logo")
        else:
            league_name, league_logo = league_data, ""
        data = {
            "nationality": player.get("nationality"),
            "club": team["name"],
            "league": league_name,
            "club_logo": (team.get("logo") or ""),
            "league_logo": league_logo or "",
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

    # Prefer the explicitly curated records for named players. Incomplete
    # records are still useful: the card can render its core and hide only the
    # unavailable metadata elements.
    normalized_name = _norm(name)
    manual_key = _MANUAL_NAME_ALIASES.get(normalized_name, normalized_name)
    manual = _MANUAL_METADATA.get(manual_key)
    if manual:
        return {**manual, "source": "Curated in project", "updated_at": int(time.time())}

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
    # The specifically requested player facts take precedence over older/manual
    # metadata, while keeping the existing core rating/position/level intact.
    normalized_name = _norm(result.get("name", ""))
    manual_key = _MANUAL_NAME_ALIASES.get(normalized_name, normalized_name)
    manual = _MANUAL_METADATA.get(manual_key)
    if manual:
        result.update(manual)
        result["source"] = "Curated in project"
        result["metadata_complete"] = bool(result.get("nationality") and result.get("club") and result.get("league"))
        result["is_icon"] = bool(manual.get("is_icon"))
        result["is_hero"] = bool(manual.get("is_hero"))
        result["country_flag"] = country_flag(result.get("nationality"))
        return result
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
            result["country_flag"] = country_flag(result.get("nationality"))
            return result
        if result.get("club") and result.get("league"):
            result["metadata_complete"] = True
            result["is_icon"] = card_type == "ICON"
            result["is_hero"] = card_type == "HEROES"
            result["country_flag"] = country_flag(result.get("nationality"))
            return result
    meta = get_player_metadata(result.get("name", ""))
    if not meta:
        # A custom record may already contain useful manually entered fields.
        # Keep these rather than marking the player ineligible for rendering.
        result["metadata_complete"] = bool(result.get("nationality") and result.get("club") and result.get("league"))
        card_type = str(result.get("card_type", "REGULAR")).upper()
        result["is_icon"] = bool(result.get("is_icon")) or card_type == "ICON"
        result["is_hero"] = bool(result.get("is_hero")) or card_type == "HEROES"
        result["country_flag"] = country_flag(result.get("nationality"))
        return result
    result.update(meta)
    result["metadata_complete"] = bool(result.get("nationality") and result.get("club") and result.get("league"))
    result["country_flag"] = country_flag(result.get("nationality"))
    special = _special_types().get(_norm(result.get("name")))
    record_type = str(result.get("card_type", "REGULAR")).upper()
    result["is_icon"] = bool(meta.get("is_icon")) or special == "ICON" or record_type == "ICON"
    result["is_hero"] = bool(meta.get("is_hero")) or special == "HEROES" or record_type == "HEROES"
    result["card_type"] = meta.get("card_type") or special or record_type
    return result
