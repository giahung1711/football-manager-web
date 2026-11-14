"""Local-only player metadata helpers.

No external football API, HTTP request, background worker, or API key is used.
Player metadata may come from records explicitly curated by the Admin through
SPECIAL_PLAYER_METADATA or from Admin-gifted player records.
"""
import json
import os
import re
import unicodedata
import copy


def _norm(value):
    value = str(value or "").casefold().replace("ø", "o").replace("ł", "l")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", value)


def _curated_metadata():
    try:
        raw = json.loads(os.environ.get("SPECIAL_PLAYER_METADATA", "{}"))
        return raw if isinstance(raw, dict) else {}
    except (ValueError, TypeError):
        return {}


def _special_types():
    try:
        raw = json.loads(os.environ.get("SPECIAL_PLAYER_TYPES", "{}"))
        if not isinstance(raw, dict):
            return {}
        return {
            _norm(name): str(card_type).upper()
            for name, card_type in raw.items()
            if str(card_type).upper() in {"ICON", "HEROES"}
        }
    except (ValueError, TypeError):
        return {}


def get_player_metadata(name, force=False):
    """Return only Admin-curated metadata; never contact an external service."""
    if not name:
        return None
    wanted = _norm(name)
    item = next(
        (value for key, value in _curated_metadata().items()
         if _norm(key) == wanted and isinstance(value, dict)),
        None,
    )
    if not item:
        return None

    card_type = str(item.get("type", "")).upper()
    if card_type not in {"ICON", "HEROES"}:
        return None

    nationality = str(item.get("nationality") or "").strip()
    retired = bool(item.get("retired") or item.get("career_status") == "retired")
    if not nationality:
        return None
    if not retired and not all(str(item.get(k) or "").strip() for k in ("club", "league")):
        return None

    return {
        "nationality": nationality,
        "club": "" if retired else str(item.get("club") or ""),
        "league": "" if retired else str(item.get("league") or ""),
        "source": item.get("source", "Admin verified"),
        "is_icon": card_type == "ICON",
        "is_hero": card_type == "HEROES",
        "card_type": card_type,
        **({"career_status": "retired"} if retired else {}),
    }


def enrich_player(record):
    """Enrich a card from Admin-curated data only; never mutate saved records."""
    result = copy.deepcopy(record or {})
    name = str(result.get("name", "")).strip()
    if name.casefold() == "zidane":
        result["name"] = "Zinedine Zidane"
        name = result["name"]
        result.setdefault("position", "CAM")
        result.setdefault("rating", 101)
        result.setdefault("level", 0)

    # Admin-gifted records are authoritative and need no external lookup.
    if result.get("metadata_admin_verified") and result.get("nationality"):
        card_type = str(result.get("card_type", "REGULAR")).upper()
        retired = result.get("career_status") == "retired"
        if retired and card_type in {"ICON", "HEROES"}:
            result["club"] = ""
            result["league"] = ""
            result["metadata_complete"] = True
        elif result.get("club") and result.get("league"):
            result["metadata_complete"] = True
        else:
            result["metadata_complete"] = False
        result["is_icon"] = card_type == "ICON"
        result["is_hero"] = card_type == "HEROES"
        return result

    # Only explicitly curated ICON/HEROES records can add metadata here.
    meta = get_player_metadata(name)
    if not meta:
        result["metadata_complete"] = bool(
            result.get("nationality") and
            ((result.get("career_status") == "retired" and result.get("card_type") in {"ICON", "HEROES"})
             or (result.get("club") and result.get("league")))
        )
        return result

    core_fields = {
        key: copy.deepcopy(result[key])
        for key in ("name", "position", "rating", "level", "event_card",
                    "original_rating", "card_season", "market_value", "photo_url")
        if key in result
    }
    result.update(meta)
    result.update(core_fields)
    result["metadata_complete"] = True
    return result
