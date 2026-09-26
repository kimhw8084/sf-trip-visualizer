"""Trip package descriptor loading and fail-closed package validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlparse


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_CONFIG = json.loads((ROOT / "manifests" / "canonical_pipeline.json").read_text(encoding="utf-8"))
DEFAULT_PACKAGE = PIPELINE_CONFIG.get("authority", {}).get("active_trip_package")
if not isinstance(DEFAULT_PACKAGE, str) or not DEFAULT_PACKAGE:
    raise ValueError("canonical_pipeline.json must select an active trip package descriptor")
SUPPORTED_CURRENCIES = {
    "USD", "CAD", "MXN", "EUR", "GBP", "JPY", "KRW", "CNY", "TWD", "HKD",
    "SGD", "AUD", "NZD", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF",
    "INR", "THB", "IDR", "MYR", "PHP", "VND", "BRL", "ARS", "CLP", "ZAR",
}


class PackageError(ValueError):
    pass


def _package_path(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value or value.startswith("/") or ".." in Path(value).parts:
        raise PackageError(f"Invalid {label} path in trip package: {value!r}")
    path = (ROOT / value).resolve()
    if ROOT not in path.parents:
        raise PackageError(f"{label} path escapes repository: {value}")
    return path


def _safe_host(host: str) -> bool:
    return bool(re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host))


def _validate_provider(provider_id: str, config: dict, policy: dict) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", provider_id) or not isinstance(config, dict):
        raise PackageError(f"Invalid provider declaration: {provider_id!r}")
    if (not isinstance(config.get("label_en"), str) or not config["label_en"].strip()
            or not isinstance(config.get("label_ko"), str) or not config["label_ko"].strip()):
        raise PackageError(f"Provider {provider_id} requires Korean and English display labels")
    kind = config.get("kind")
    if provider_id == "vector":
        if (kind != "vector" or config.get("local") is not True or not config.get("identity")
                or config.get("requires_api_key", False) is not False):
            raise PackageError("The vector provider must declare a local vector identity")
        return
    if kind != "raster":
        raise PackageError(f"Provider {provider_id} has unsupported kind {kind!r}")
    template = config.get("tile_template")
    probe = config.get("health_probe")
    parsed_template = urlparse(str(template))
    parsed_probe = urlparse(str(probe))
    if (parsed_template.scheme != "https" or parsed_template.username or parsed_template.password or parsed_template.port
            or parsed_template.fragment or not _safe_host(parsed_template.hostname or "")
            or parsed_probe.scheme != "https" or parsed_probe.username or parsed_probe.password or parsed_probe.port
            or parsed_probe.fragment or parsed_probe.hostname != parsed_template.hostname
            or not parsed_template.path or not parsed_probe.path.startswith(policy.get("external", {}).get(provider_id, {}).get("path_prefix", "!"))):
        raise PackageError(f"Provider {provider_id} has an unsafe raster URL configuration")
    if not all(token in template for token in ("{z}", "{x}", "{y}")):
        raise PackageError(f"Provider {provider_id} tile template must declare z, x, and y")
    if provider_id not in policy.get("external", {}):
        raise PackageError(f"Provider {provider_id} is missing its external URL policy")
    declared = policy["external"][provider_id]
    if declared.get("host") != parsed_template.hostname or declared.get("path_prefix") != parsed_template.path.rsplit("/{z}/", 1)[0] + "/":
        raise PackageError(f"Provider {provider_id} URL does not match its declared source policy")


def validate_policy(policy: dict, providers: dict) -> None:
    official = policy.get("official_sources")
    if not isinstance(official, dict) or official.get("scheme") != "https" or not isinstance(official.get("hosts"), list) or not official["hosts"]:
        raise PackageError("source_policy.official_sources must declare HTTPS hosts")
    if any(not isinstance(host, str) or host != host.lower() or not _safe_host(host) for host in official["hosts"]):
        raise PackageError("source_policy.official_sources contains an invalid host")
    if len(set(official["hosts"])) != len(official["hosts"]):
        raise PackageError("source_policy.official_sources hosts must be unique")
    directions = policy.get("external", {}).get("directions")
    if not isinstance(directions, dict) or directions.get("scheme") != "https" or not _safe_host(str(directions.get("host", ""))):
        raise PackageError("source_policy.external.directions must declare one HTTPS host")
    paths = directions.get("paths")
    if not isinstance(paths, dict) or not paths or any(not isinstance(path, str) or not path.startswith("/") or ".." in path for path in paths):
        raise PackageError("source_policy.external.directions paths are invalid")
    allowed = directions.get("allowed_query")
    if not isinstance(allowed, list) or len(set(allowed)) != len(allowed) or any(not re.fullmatch(r"[a-z][a-z0-9_]*", key) for key in allowed):
        raise PackageError("source_policy.external.directions query allowlist is invalid")
    links = directions.get("links")
    if not isinstance(links, dict) or not links:
        raise PackageError("source_policy.external.directions must configure safe link templates")
    for kind, template in links.items():
        parsed = urlparse(str(template))
        if parsed.scheme != "https" or parsed.hostname != directions["host"] or parsed.path not in paths or parsed.username or parsed.password or parsed.port or parsed.fragment:
            raise PackageError(f"Directions link {kind!r} does not match its declared HTTPS host/path")
        rule = paths[parsed.path]
        template_keys = set(re.findall(r"\{([a-z]+)\}", str(template)))
        query_keys = {key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
        if (not isinstance(rule, dict) or not set(rule.get("required_query", [])) <= set(allowed)
                or not query_keys <= set(allowed) or not template_keys <= {"query", "origin", "destination"}):
            raise PackageError(f"Directions link {kind!r} has an invalid query rule")
    provider_policy = policy.get("external", {})
    for provider_id, config in providers.items():
        _validate_provider(provider_id, config, policy)
    if set(provider_policy) - (set(providers) | {"directions"}):
        raise PackageError("source policy declares an unconfigured external provider")


def _safe_directions_url(value: str, policy: dict) -> bool:
    directions = policy.get("external", {}).get("directions", {})
    parsed = urlparse(str(value))
    rule = directions.get("paths", {}).get(parsed.path, {})
    try:
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query_keys = [key for key, _ in query]
        query_values = dict(query)
        return (
            parsed.scheme == "https" and parsed.hostname == directions.get("host")
            and parsed.username is None and parsed.password is None and parsed.port is None and not parsed.fragment
            and parsed.path in directions.get("paths", {})
            and len(query_keys) == len(set(query_keys)) and set(query_keys) <= set(directions.get("allowed_query", []))
            and set(rule.get("required_query", [])) <= set(query_keys)
            and all(query_values.get(key) == expected for key, expected in rule.get("required_values", {}).items())
        )
    except ValueError:
        return False


def load_package(package: str | Path | None = None) -> dict:
    relative = str(package or DEFAULT_PACKAGE)
    descriptor_path = _package_path(relative, "descriptor")
    try:
        descriptor = json.loads(descriptor_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PackageError(f"Cannot read trip package descriptor {relative}: {error}") from error
    if not isinstance(descriptor, dict):
        raise PackageError("Trip package descriptor must be a JSON object")
    required = ("schema_version", "trip_identity", "display_title", "slug", "currency", "canonical_data", "projections", "assets", "providers", "source_policy")
    missing = [field for field in required if field not in descriptor]
    if missing:
        raise PackageError("Trip package is missing required field(s): " + ", ".join(missing))
    if descriptor["schema_version"] != 1:
        raise PackageError("Unsupported trip package schema_version")
    if "is_non_shipping_fixture" in descriptor and not isinstance(descriptor["is_non_shipping_fixture"], bool):
        raise PackageError("Trip package is_non_shipping_fixture must be a boolean")
    if "compatibility_alias" in descriptor and (not isinstance(descriptor["compatibility_alias"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.html", descriptor["compatibility_alias"]) or ".." in descriptor["compatibility_alias"]):
        raise PackageError("Trip package compatibility_alias must be a sanitized HTML filename")
    if not isinstance(descriptor["trip_identity"], str) or not descriptor["trip_identity"].strip() or not isinstance(descriptor["display_title"], str) or not descriptor["display_title"].strip():
        raise PackageError("Trip package identity and display title must be non-empty strings")
    if not re.fullmatch(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*", str(descriptor["slug"])):
        raise PackageError("Trip package slug must be a sanitized filename-safe identity")
    if not isinstance(descriptor["currency"], str) or descriptor["currency"] not in SUPPORTED_CURRENCIES:
        raise PackageError(f"Unrecognized trip currency: {descriptor['currency']!r}")
    if not isinstance(descriptor.get("subtitle"), dict) or any(not isinstance(descriptor["subtitle"].get(lang), str) or not descriptor["subtitle"][lang].strip() for lang in ("ko", "en")):
        raise PackageError("Trip package subtitle must be bilingual")
    if not isinstance(descriptor["projections"], dict):
        raise PackageError("Trip package projections must be an object of named paths")
    paths = {"canonical_data": descriptor["canonical_data"], **descriptor["projections"]}
    required_projections = {"route_roles", "route_schedules", "route_geometry", "route_geometry_manifest", "translations", "freshness", "research_ledger", "coordinate_audit", "photos_manifest"}
    missing_projections = sorted(required_projections - set(descriptor["projections"]))
    if missing_projections:
        raise PackageError("Trip package is missing required projection path(s): " + ", ".join(missing_projections))
    for label, value in paths.items():
        path = _package_path(value, label)
        if not path.is_file():
            raise PackageError(f"Trip package {label} asset is missing: {value}")
    assets = descriptor["assets"]
    if not isinstance(assets, dict) or not isinstance(assets.get("photos"), dict) or not isinstance(assets.get("map"), dict):
        raise PackageError("Trip package assets must declare photos and map objects")
    if not isinstance(assets.get("root"), str) or not assets["root"]:
        raise PackageError("Trip package must declare assets.root")
    if not _package_path(assets["root"], "assets.root").is_dir():
        raise PackageError(f"Trip package asset root is missing: {assets['root']}")
    asset_root = _package_path(assets["root"], "assets.root")
    if not isinstance(assets["photos"].get("root"), str):
        raise PackageError("Trip package must declare assets.photos.root")
    photo_root_path = _package_path(assets["photos"]["root"], "assets.photos.root")
    if photo_root_path != asset_root and asset_root not in photo_root_path.parents:
        raise PackageError("Photo root is outside assets.root")
    for label, value in assets["photos"].items():
        if label.endswith("_dir") or label.endswith("_root"):
            path = _package_path(value, f"assets.photos.{label}")
            if path != asset_root and asset_root not in path.parents:
                raise PackageError(f"Photo path is outside assets.root: {value}")
            if not path.is_dir():
                raise PackageError(f"Trip package photo asset directory is missing: {value}")
    map_assets = assets.get("map", {})
    if (not isinstance(map_assets.get("local_resources"), list) or not map_assets.get("vector_archive")
            or not map_assets.get("identity") or not map_assets.get("attribution")):
        raise PackageError("Trip package map must declare a local vector archive, identity, and attribution")
    if map_assets["vector_archive"] not in map_assets.get("local_resources", []):
        raise PackageError("Trip package vector archive must be included in its local resources")
    for field in ("glyphs_template", "sprite_template"):
        template = map_assets.get(field, "")
        prefix = "tripasset://"
        if not isinstance(template, str) or not template.startswith(prefix) or "http" in template or ".." in template:
            raise PackageError(f"Trip package map {field} must point to a declared local resource")
        resource_path = template[len(prefix):].split("/{", 1)[0]
        if not any(resource_path == entry or resource_path.startswith(entry.rstrip("/") + "/") for entry in map_assets["local_resources"]):
            raise PackageError(f"Trip package map {field} is outside its declared local resources")
    relief = map_assets.get("relief")
    if relief and (relief.get("path") not in map_assets["local_resources"] or len(relief.get("coordinates", [])) != 4):
        raise PackageError("Trip package relief resource or bounds are invalid")
    for entry in map_assets.get("local_resources", []):
        path = _package_path(entry, "assets.map.local_resources")
        if path != asset_root and asset_root not in path.parents:
            raise PackageError(f"Map resource is outside assets.root: {entry}")
        if not path.exists():
            raise PackageError(f"Trip package map resource is missing: {entry}")
    if not isinstance(descriptor["providers"], dict) or "vector" not in descriptor["providers"]:
        raise PackageError("Trip package must configure a local vector provider")
    if not isinstance(descriptor["source_policy"], dict):
        raise PackageError("Trip package source_policy must be an object")
    validate_policy(descriptor["source_policy"], descriptor["providers"])
    data = json.loads(_package_path(descriptor["canonical_data"], "canonical_data").read_text())
    if data.get("trip_identity") != descriptor["trip_identity"]:
        raise PackageError("Trip package identity does not match the canonical data identity")
    return {**descriptor, "descriptor_path": relative, "data": data}


def package_input_paths(package: dict) -> list[str]:
    """Every selected package input, including recursive local runtime assets."""
    paths = {package["descriptor_path"], package["canonical_data"], *package["projections"].values()}
    folders = [package["assets"]["photos"]["thumb_dir"], package["assets"]["photos"]["medium_dir"]]
    for relative in (*package["assets"]["map"]["local_resources"], *folders):
        path = _package_path(relative, "package asset")
        if path.is_dir():
            paths.update(str(item.relative_to(ROOT)) for item in path.rglob("*") if item.is_file())
        else:
            paths.add(relative)
    return sorted(paths)


def validate_portable_data(package: dict) -> dict:
    """Structural engine contract shared by all packages, independent of SF QA law."""
    data = package["data"]
    failures = []
    if "providers" in data:
        failures.append("provider configuration belongs to the trip-package descriptor, not canonical itinerary data")
    route_roles = json.loads(_package_path(package["projections"]["route_roles"], "route_roles").read_text())
    schedules = json.loads(_package_path(package["projections"]["route_schedules"], "route_schedules").read_text())
    geometry = json.loads(_package_path(package["projections"]["route_geometry"], "route_geometry").read_text())
    geometry_manifest = json.loads(_package_path(package["projections"]["route_geometry_manifest"], "route_geometry_manifest").read_text())
    photos = json.loads(_package_path(package["projections"]["photos_manifest"], "photos_manifest").read_text())
    freshness = json.loads(_package_path(package["projections"]["freshness"], "freshness").read_text())
    routes = data.get("routes")
    markers = data.get("markers")
    dates = data.get("dates")
    regions = data.get("region_cfg")
    if not isinstance(routes, dict) or not routes:
        failures.append("routes must be a non-empty object")
    if not isinstance(markers, list) or not markers:
        failures.append("markers must be a non-empty list")
    if not isinstance(dates, list) or not dates:
        failures.append("dates must be a non-empty list")
    if not isinstance(regions, dict) or len(regions) < 2 or "overall" not in regions:
        failures.append("region_cfg must declare overall and at least one named region")
    if failures:
        raise PackageError("Trip data contract failed: " + "; ".join(failures))
    route_ids = set(routes)
    place_ids = set()
    date_keys = [item.get("key") for item in dates]
    date_ids = set(date_keys)
    region_ids = set(regions)
    if len(date_keys) != len(date_ids) or any(not isinstance(key, str) or not key.strip() for key in date_keys):
        failures.append("date identities must be non-empty and unique")
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", str(route_id)) for route_id in route_ids):
        failures.append("route identity contains unsupported characters")
    if any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", str(region)) for region in region_ids if region != "overall"):
        failures.append("region identity contains unsupported characters")
    timeline_ids = [item.get("id") for item in data.get("timeline", [])]
    if len(timeline_ids) != len(set(timeline_ids)) or any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", value) for value in timeline_ids):
        failures.append("timeline identities must be filename-safe and unique")
    for route_id, route in routes.items():
        if not route_id or not isinstance(route, dict) or not route.get("title") or not route.get("color"):
            failures.append(f"invalid route identity or display fields: {route_id!r}")
    if sum(bool(route.get("recommended")) for route in routes.values()) != 1:
        failures.append("exactly one route must be recommended")
    role_places = route_roles.get("places", {})
    role_route_ids = set(route_roles.get("route_ids", []))
    if role_route_ids != route_ids or role_places != data.get("route_roles") or set(role_places) != {item.get("place_key") for item in markers}:
        failures.append("route-role projection is stale or does not match canonical route/place identities")
    if schedules.get("routes") != data.get("route_day_models") or set(schedules.get("routes", {})) != route_ids:
        failures.append("route-schedule projection is stale or does not match canonical routes")
    leg_ids = [leg.get("leg_id") for leg in data.get("legs", [])]
    manifest_rows = {item.get("leg_id"): item for item in geometry_manifest.get("legs", [])}
    if len(leg_ids) != len(set(leg_ids)) or set(geometry) != set(leg_ids) or set(manifest_rows) != set(leg_ids):
        failures.append("route geometry/cache manifest identities are missing, duplicate, or stale")
    for leg in data.get("legs", []):
        leg_id = leg.get("leg_id")
        entry = geometry.get(leg_id, {})
        row = manifest_rows.get(leg_id, {})
        signature = [leg.get("from_latlon"), leg.get("to_latlon"), leg.get("mode")]
        if (entry.get("mode") != leg.get("mode") or entry.get("endpoint_signature") != signature
                or entry.get("status") != leg.get("geometry_kind")
                or row.get("status") != entry.get("status") or row.get("mode") != entry.get("mode")
                or row.get("endpoint_signature") != signature
                or row.get("point_count") != len(entry.get("coordinates", []))):
            failures.append(f"route geometry projection is stale for leg {leg_id!r}")
    for marker in markers:
        key = marker.get("place_key")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", key) or key in place_ids:
            failures.append(f"invalid or duplicate place identity: {key!r}")
            continue
        place_ids.add(key)
        if not isinstance(marker.get("lat"), (float, int)) or not isinstance(marker.get("lon"), (float, int)):
            failures.append(f"place {key} has invalid coordinates")
        if not marker.get("routes") or not set(marker["routes"]) <= route_ids:
            failures.append(f"place {key} references an unknown route")
        for occurrence in marker.get("occurrences", []):
            if occurrence.get("route") not in route_ids or occurrence.get("date_key") not in date_ids:
                failures.append(f"place {key} has an occurrence with an unknown route or date")
        directions_url = marker.get("maps_url")
        if directions_url and not _safe_directions_url(directions_url, package["source_policy"]):
            failures.append(f"place {key} directions URL violates package policy")
    place_region = data.get("place_region", {})
    if set(place_region) != place_ids or any(region not in region_ids or region == "overall" for region in place_region.values()):
        failures.append("place_region must map every place to a declared named region")
    for item in data.get("timeline", []):
        if item.get("date_key") not in date_ids or not set(item.get("routes", [])) <= route_ids or not set(item.get("regions", [])) <= region_ids:
            failures.append(f"timeline item {item.get('id')!r} references an unknown date, route, or region")
        if not set(item.get("spatial_keys", [])) <= place_ids:
            failures.append(f"timeline item {item.get('id')!r} references an unknown place")
    for leg in data.get("legs", []):
        if leg.get("date") not in date_ids or not set(leg.get("routes", [])) <= route_ids:
            failures.append(f"leg {leg.get('leg_id')!r} references an unknown date or route")
        if leg.get("from") not in place_ids | set(data.get("endpoint_anchors", {})) or leg.get("to") not in place_ids | set(data.get("endpoint_anchors", {})):
            failures.append(f"leg {leg.get('leg_id')!r} references an unknown endpoint")
    photo_root = package["assets"]["photos"]["root"].rstrip("/") + "/"
    photo_ids = set()
    for asset in photos.get("assets", []):
        identity = (asset.get("place_key"), str(asset.get("role", "")).lower())
        if identity[0] not in place_ids or identity[1] not in {"hero", "experience", "scale_context"} or identity in photo_ids:
            failures.append(f"photo asset has an invalid or duplicate place/role identity: {identity!r}")
        photo_ids.add(identity)
        for field in ("local_thumb_path", "local_medium_path"):
            value = asset.get(field, "")
            if not isinstance(value, str) or not value.startswith(photo_root):
                failures.append(f"photo reference is outside the package photo root: {value!r}")
            else:
                try:
                    if not _package_path(value, field).is_file():
                        failures.append(f"photo reference is missing: {value}")
                except PackageError:
                    failures.append(f"photo reference is invalid: {value!r}")
    for place_id in place_ids:
        if not any(asset_id[0] == place_id and asset_id[1] == "hero" for asset_id in photo_ids):
            failures.append(f"place {place_id} has no local hero photo")
    official_hosts = set(package["source_policy"]["official_sources"]["hosts"])
    freshness_ids = [record.get("fact_id") for record in freshness.get("records", [])]
    if len(freshness_ids) != len(set(freshness_ids)):
        failures.append("freshness fact identities must be unique")
    for record in freshness.get("records", []):
        if not set(record.get("scope", {}).get("place_keys", [])) <= place_ids or not set(record.get("scope", {}).get("dates", [])) <= date_ids:
            failures.append(f"freshness fact {record.get('fact_id')!r} has an unknown place/date scope")
        for source in record.get("source", {}).get("source_urls", []):
            parsed = urlparse(str(source))
            if parsed.scheme != "https" or parsed.hostname not in official_hosts or parsed.username or parsed.password or parsed.port or parsed.fragment:
                failures.append(f"freshness source URL violates package policy in fact {record.get('fact_id')!r}")
    for readiness in data.get("readiness_items", []):
        for source in readiness.get("source", []):
            parsed = urlparse(str(source))
            if parsed.scheme != "https" or parsed.hostname not in official_hosts or parsed.username or parsed.password or parsed.port or parsed.fragment:
                failures.append(f"readiness source URL violates package policy in item {readiness.get('id')!r}")
    if failures:
        raise PackageError("Trip data contract failed: " + "; ".join(failures[:20]))
    return {"status": "PASS", "routes": len(route_ids), "places": len(place_ids), "dates": len(date_ids), "regions": len(region_ids) - 1, "timeline": len(data.get("timeline", [])), "legs": len(data.get("legs", []))}
