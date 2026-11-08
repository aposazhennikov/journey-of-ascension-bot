"""HTTP routes for the 3D meridian map Telegram Mini App."""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from aiohttp import web

from .utils import (
    MERIDIAN_LOCALIZED_NAMES, MERIDIAN_METADATA, _clean_point_location, _localized_location,
    _metadata_label, _point_setup_practice_hint, localized_point_name,
)

if TYPE_CHECKING:
    from .utils import MeridiansManager

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
WEBAPP_LANGUAGES = ("ru", "en", "uz", "kz")
# Telegram reports Kazakh as "kk", the content files use "kz".
LANGUAGE_ALIASES = {"kk": "kz"}
# Project point prefixes -> WHO standard codes (the stored alt_code values are inconsistent).
WHO_PREFIXES = {
    "P": "LU", "GI": "LI", "E": "ST", "RP": "SP", "C": "HT", "IG": "SI", "V": "BL",
    "R": "KI", "MC": "PC", "TR": "TE", "VB": "GB", "F": "LR", "VG": "GV", "VC": "CV",
}


def who_code(code: str) -> str:
    match = re.match(r"([A-Z]+)(\d+)$", code or "")
    if not match or match.group(1) not in WHO_PREFIXES:
        return ""
    return f"{WHO_PREFIXES[match.group(1)]} {match.group(2)}"


def _plain(text: str) -> str:
    return re.sub(r"</?b>", "", text or "")


def normalize_webapp_language(language: str) -> str:
    language = LANGUAGE_ALIASES.get((language or "").lower(), (language or "").lower())
    return language if language in WEBAPP_LANGUAGES else "ru"


def build_meridians_payload(meridians_manager: "MeridiansManager", language: str) -> Dict[str, Any]:
    """Compact meridian data the 3D page needs: names, activity window and points."""

    def pick(i18n: Dict[str, Any]) -> Dict[str, Any]:
        return i18n.get(language) or i18n.get("en") or {}

    def pair_name(pair_id: str) -> str:
        if not pair_id or pair_id == "none":
            return _metadata_label("pair", "none", language)
        names = MERIDIAN_LOCALIZED_NAMES.get(pair_id, {})
        return names.get(language, names.get("en", pair_id))

    meridians = []
    for meridian in meridians_manager.get_recommended_path_meridians():
        text = pick(meridian.get("i18n", {}))
        meta = MERIDIAN_METADATA.get(meridian.get("id"), {})
        meridians.append({
            "id": meridian.get("id"),
            "name": text.get("name", meridian.get("id")),
            "direction": text.get("direction", ""),
            "description": _plain(text.get("description", "")),
            "intro_practice": text.get("intro_practice", ""),
            "active_time": meridian.get("active_time"),
            "passive_time": meridian.get("passive_time"),
            "system": meta.get("system"),
            "element": meta.get("element"),
            "pair": meta.get("pair") if meta.get("pair") != "none" else None,
            "level": meta.get("level"),
            "labels": {
                "system": _metadata_label("system", meta.get("system", ""), language) if meta else "",
                "element": _metadata_label("element", meta.get("element", ""), language) if meta else "",
                "level": _metadata_label("level", meta.get("level", ""), language) if meta else "",
                "pair": pair_name(meta.get("pair", "none")) if meta else "",
            },
            "points": [
                {
                    "code": point.get("code"),
                    "who": who_code(point.get("code")),
                    "name": localized_point_name(point, language) or point.get("code"),
                    # same cleaning as the bot: no editorial tails ("Находят и используют точку, когда пациент…")
                    "location": _clean_point_location(_localized_location(point, language)),
                    "setup": _point_setup_practice_hint(_localized_location(point, language), language),
                    "observation": pick(point.get("i18n", {})).get("observation_question", ""),
                }
                for point in meridian.get("points", [])
            ],
        })
    return {"language": language, "meridians": meridians}


def setup_webapp_routes(app: web.Application, meridians_manager: "MeridiansManager") -> None:
    """Serve the Mini App page, its static files and the meridian data endpoint."""

    async def index_handler(request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEBAPP_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    async def redirect_handler(request: web.Request) -> web.Response:
        raise web.HTTPFound(f"/webapp/{('?' + request.query_string) if request.query_string else ''}")

    async def meridians_handler(request: web.Request) -> web.Response:
        language = normalize_webapp_language(request.query.get("lang", "ru"))
        response = web.json_response(build_meridians_payload(meridians_manager, language))
        response.enable_compression()  # ~500 KB of Cyrillic text shrinks to well under 100 KB
        return response

    lang_cache: Dict[Any, bytes] = {}

    def extras_for(path: Path, language: str) -> bytes:
        """point_extras.json holds the texts of all four languages (~1 MB); a phone needs one."""
        key = (str(path), language, path.stat().st_mtime)
        if key not in lang_cache:
            data = json.loads(path.read_text(encoding="utf-8"))
            for entry in data.get("points", {}).values():
                i18n = entry.get("i18n") or {}
                entry["i18n"] = {k: v for k, v in i18n.items() if k == language}
            lang_cache.clear()
            lang_cache[key] = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return lang_cache[key]

    async def json_asset_handler(request: web.Request) -> web.Response:
        # the asset JSON files (point texts, poses, coordinates) are large and compress ~6x;
        # the static route below sends them uncompressed
        name = request.match_info["name"]
        path = WEBAPP_DIR / "assets" / f"{name}.json"
        if not re.fullmatch(r"[a-z0-9_]+", name) or not path.is_file():
            raise web.HTTPNotFound()
        body = path.read_bytes()
        if name == "point_extras" and request.query.get("lang"):
            body = extras_for(path, normalize_webapp_language(request.query["lang"]))
        response = web.Response(body=body, content_type="application/json", charset="utf-8")
        response.enable_compression()
        return response

    async def cache_headers(request: web.Request, response: web.StreamResponse) -> None:
        # Modules are imported without version suffixes, so they must be revalidated;
        # the body models are large and versioned through ?v=, so they may be cached.
        path = request.path
        if not path.startswith("/webapp"):
            return
        if path.endswith((".js", ".css", ".json", "/")) or "/api/" in path:
            response.headers["Cache-Control"] = "no-cache"
        elif path.endswith(".glb"):
            response.headers["Cache-Control"] = "public, max-age=86400"

    app.on_response_prepare.append(cache_headers)
    app.router.add_get("/webapp", redirect_handler)
    app.router.add_get("/webapp/", index_handler)
    app.router.add_get("/webapp/api/meridians", meridians_handler)
    app.router.add_get("/webapp/assets/{name}.json", json_asset_handler)
    app.router.add_static("/webapp/", WEBAPP_DIR, show_index=False)
