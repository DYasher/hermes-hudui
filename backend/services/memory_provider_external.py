"""Read-only external memory provider views."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.services import memory_service
from backend.services import memory_provider_config
from backend.services.memory_provider_catalog import (
    MEMORY_PROVIDER_OPTIONS,
)

MEMOS_CHINA_BASE_URL = "https://memos.memtensor.cn/api/openmem/v1"
MEMOS_GLOBAL_BASE_URL = "https://api.memt.ai/platform/api/openmem/v1"
COGNEE_DATASET_SCAN_LIMIT = 20


def holographic_db_path() -> Path:
    hermes_home = memory_service.hermes_home()
    config = memory_provider_config.read_config()
    plugin_cfg = config.get("plugins", {})
    if isinstance(plugin_cfg, dict):
        plugin_cfg = plugin_cfg.get("hermes-memory-store", {})
    if not isinstance(plugin_cfg, dict):
        plugin_cfg = {}

    configured = plugin_cfg.get("db_path") or ""
    if not configured:
        return hermes_home / "memory_store.db"

    expanded = str(configured).replace("${HERMES_HOME}", str(hermes_home))
    expanded = expanded.replace("$HERMES_HOME", str(hermes_home))
    path = Path(expanded).expanduser()
    if not path.is_absolute():
        return hermes_home / path
    return path


def split_holographic_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(tag).strip() for tag in raw if str(tag).strip()]
    text = "" if raw is None else str(raw)
    return [tag.strip() for tag in text.split(",") if tag.strip()]


def empty_holographic_external_view(path: Path, reason: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": "holographic",
        "available": True,
        "readonly": True,
        "db_path": str(path),
        "summary": {"total": 0, "categories": {}},
        "items": [],
    }
    if reason:
        payload["reason"] = reason
    return payload


def holographic_external_view(limit: int = 100) -> dict[str, Any]:
    path = holographic_db_path()
    if not path.exists():
        return empty_holographic_external_view(path, "store_not_found")

    uri = f"file:{quote(str(path), safe='/')}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return {
            "provider": "holographic",
            "available": False,
            "readonly": True,
            "db_path": str(path),
            "reason": "sqlite_open_failed",
            "error": str(exc),
            "summary": {"total": 0, "categories": {}},
            "items": [],
        }

    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'facts'"
        ).fetchone()
        if not table:
            return empty_holographic_external_view(path, "facts_table_missing")

        category_rows = conn.execute(
            "SELECT category, COUNT(*) AS count FROM facts GROUP BY category"
        ).fetchall()
        categories = {
            str(row["category"] or "general"): int(row["count"] or 0)
            for row in category_rows
        }
        total = sum(categories.values())

        rows = conn.execute(
            """
            SELECT fact_id, content, category, tags, trust_score, retrieval_count,
                   helpful_count, created_at, updated_at
            FROM facts
            ORDER BY updated_at DESC, fact_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.Error as exc:
        return {
            "provider": "holographic",
            "available": False,
            "readonly": True,
            "db_path": str(path),
            "reason": "sqlite_read_failed",
            "error": str(exc),
            "summary": {"total": 0, "categories": {}},
            "items": [],
        }
    finally:
        conn.close()

    return {
        "provider": "holographic",
        "available": True,
        "readonly": True,
        "db_path": str(path),
        "summary": {"total": total, "categories": categories},
        "items": [
            {
                "id": str(row["fact_id"]),
                "content": row["content"] or "",
                "category": row["category"] or "general",
                "tags": split_holographic_tags(row["tags"]),
                "trust_score": row["trust_score"],
                "retrieval_count": row["retrieval_count"] or 0,
                "helpful_count": row["helpful_count"] or 0,
                "created_at": row["created_at"] or "",
                "updated_at": row["updated_at"] or "",
            }
            for row in rows
        ],
    }


def provider_summary_external_view(provider: str) -> dict[str, Any]:
    info = MEMORY_PROVIDER_OPTIONS[provider]
    values = memory_provider_config.provider_config_values(provider)
    current_mode = memory_provider_config.current_config_mode(info, values)
    configured, _missing_fields, _missing_any = memory_provider_config.required_state_for_mode(
        info,
        values,
        current_mode,
    )
    modes = {mode["id"]: mode for mode in memory_provider_config.mode_specs(info)}
    mode = modes.get(current_mode, {})
    fields = memory_provider_config.field_specs(info)
    visible_field_names = set(mode.get("fields", []))
    configured_fields = [
        field
        for field in fields
        if (not visible_field_names or field["name"] in visible_field_names)
        and field["name"] != "mode"
        and values.get(field["name"], {}).get("configured")
    ]
    missing_field_labels = [
        next((field["label"] for field in fields if field["name"] == name), name)
        for name in _missing_fields
        if name != "mode"
    ]
    missing_any_labels = [
        " / ".join(
            next((field["label"] for field in fields if field["name"] == name), name)
            for name in group
            if name != "mode"
        )
        for group in _missing_any
    ]
    missing_labels = [label for label in [*missing_field_labels, *missing_any_labels] if label]
    configured_labels = [field["label"] for field in configured_fields]
    mode_label = mode.get("label") or current_mode or "default"
    storage = mode.get("storage") or info.get("storage", "")
    config_text = (
        ", ".join(configured_labels)
        if configured_labels
        else "No provider fields are configured yet."
    )
    missing_text = ", ".join(missing_labels) if missing_labels else "No required fields are missing."
    required_labels = [
        next((field["label"] for field in fields if field["name"] == name), name)
        for name in mode.get("required_fields", [])
        if name != "mode"
    ]
    optional_labels = [
        next((field["label"] for field in fields if field["name"] == name), name)
        for name in mode.get("optional_fields", [])
        if name != "mode"
    ]
    requirement_text = (
        ", ".join(required_labels)
        if required_labels
        else "No required direct fields"
    )
    optional_text = ", ".join(optional_labels) if optional_labels else "None"
    file_states = []
    for relative_path in info.get("config_files", []):
        is_directory = str(relative_path).endswith("/")
        path = memory_provider_config.relative_config_path(str(relative_path).rstrip("/"))
        exists = path.is_dir() if is_directory else path.is_file()
        file_states.append(
            {
                "path": str(relative_path),
                "exists": exists,
            }
        )
    file_text = (
        ", ".join(f"{item['path']}: {'present' if item['exists'] else 'missing'}" for item in file_states)
        if file_states
        else "No config files registered."
    )
    items = [
        {
            "id": f"{provider}:runtime",
            "content": f"Mode: {mode_label}; storage: {storage}; configured: {'yes' if configured else 'no'}.",
            "category": "runtime",
            "tags": [tag for tag in [current_mode, storage] if tag],
            "trust_score": 1.0 if configured else 0.0,
            "retrieval_count": 0,
            "helpful_count": 0,
            "created_at": "",
            "updated_at": "",
        },
        {
            "id": f"{provider}:config",
            "content": (
                f"Configured fields: {config_text}. Missing required fields: {missing_text}. "
                f"Required for mode: {requirement_text}. Optional: {optional_text}."
            ),
            "category": "config",
            "tags": [field["name"] for field in configured_fields],
            "trust_score": 1.0 if configured else 0.0,
            "retrieval_count": 0,
            "helpful_count": 0,
            "created_at": "",
            "updated_at": "",
        },
    ]
    if file_states:
        items.append(
            {
                "id": f"{provider}:files",
                "content": f"Config files: {file_text}",
                "category": "files",
                "tags": [item["path"] for item in file_states if item["exists"]],
                "trust_score": 1.0 if all(item["exists"] for item in file_states) else 0.0,
                "retrieval_count": 0,
                "helpful_count": 0,
                "created_at": "",
                "updated_at": "",
            }
        )
    return {
        "provider": provider,
        "available": True,
        "readonly": True,
        "reason": "provider_summary",
        "summary": {
            "total": len(items),
            "categories": {
                "configured_fields": len(configured_fields),
                "missing_required": len(missing_labels),
                "config_files_present": sum(1 for item in file_states if item["exists"]),
                "config_files_missing": sum(1 for item in file_states if not item["exists"]),
            },
        },
        "items": items,
    }


def _join_http_url(base_url: str, path: str) -> str:
    suffix = path if path.startswith("/") else f"/{path}"
    return base_url.rstrip("/") + suffix


def _memory_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if raw is None:
        return []
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _memory_trust_score(raw: dict[str, Any]) -> float:
    score = raw.get("trust_score")
    if isinstance(score, int | float):
        return float(score)
    strength = raw.get("strength")
    if isinstance(strength, int | float):
        return max(0.0, min(float(strength) / 10.0, 1.0))
    return 1.0


def _provider_secret(name: str) -> str:
    env_values = memory_provider_config.read_env_values()
    return env_values.get(name) or os.environ.get(name, "")


def _request_json(
    url: str,
    *,
    headers: dict[str, str],
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[Any, str]:
    body = None
    request_headers = dict(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    response = None
    try:
        response = urlopen(
            Request(url, data=body, headers=request_headers, method=method),
            timeout=3,
        )
        return json.loads(response.read().decode("utf-8")), ""
    except HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        return None, str(getattr(exc, "reason", exc))
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass


def _payload_list(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _external_failure(provider: str, reason: str, error: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "available": False,
        "readonly": True,
        "reason": reason,
        "error": error,
        "summary": {"total": 0, "categories": {}},
        "items": [],
    }


def _cognee_item(raw: dict[str, Any], dataset_name: str) -> dict[str, Any]:
    extension = str(raw.get("extension") or "").strip().lstrip(".")
    mime_type = str(raw.get("mime_type") or "").strip()
    return {
        "id": str(raw.get("id") or raw.get("data_id") or raw.get("name") or ""),
        "content": str(raw.get("name") or raw.get("content") or raw.get("id") or ""),
        "category": dataset_name or "dataset",
        "tags": [value for value in [extension, mime_type] if value],
        "trust_score": 1.0,
        "retrieval_count": 0,
        "helpful_count": 0,
        "created_at": str(raw.get("created_at") or raw.get("createdAt") or ""),
        "updated_at": str(raw.get("updated_at") or raw.get("updatedAt") or ""),
    }


def cognee_api_external_view(limit: int = 100) -> dict[str, Any]:
    values = memory_provider_config.provider_config_values("cognee")
    endpoint = str(values.get("COGNEE_API_URL", {}).get("value") or "").strip()
    if not endpoint:
        return provider_summary_external_view("cognee")

    headers = {
        "Accept": "application/json",
        "User-Agent": "Hermes-HUD/read-only-memory-view",
    }
    api_key = _provider_secret("COGNEE_API_KEY")
    if api_key:
        headers["X-Api-Key"] = api_key

    datasets_payload, error = _request_json(
        _join_http_url(endpoint, "/api/v1/datasets"),
        headers=headers,
    )
    if error:
        return _external_failure("cognee", "cognee_api_failed", error)

    datasets = _payload_list(datasets_payload, "datasets", "data")
    configured_dataset = str(values.get("COGNEE_DATASET", {}).get("value") or "").strip()
    if configured_dataset:
        datasets = [
            dataset
            for dataset in datasets
            if configured_dataset in {str(dataset.get("id") or ""), str(dataset.get("name") or "")}
        ]
    datasets = datasets[:COGNEE_DATASET_SCAN_LIMIT]

    items: list[dict[str, Any]] = []
    categories: dict[str, int] = {}
    for dataset in datasets:
        dataset_id = str(dataset.get("id") or "").strip()
        if not dataset_id:
            continue
        dataset_name = str(dataset.get("name") or dataset_id)
        data_payload, error = _request_json(
            _join_http_url(endpoint, f"/api/v1/datasets/{quote(dataset_id, safe='')}/data"),
            headers=headers,
        )
        if error:
            return _external_failure("cognee", "cognee_api_failed", error)
        for raw in _payload_list(data_payload, "data", "items"):
            if len(items) >= limit:
                break
            items.append(_cognee_item(raw, dataset_name))
            categories[dataset_name] = categories.get(dataset_name, 0) + 1
        if len(items) >= limit:
            break

    return {
        "provider": "cognee",
        "available": True,
        "readonly": True,
        "reason": "cognee_api",
        "summary": {"total": len(items), "categories": categories},
        "items": items,
    }


def _memos_item(raw: dict[str, Any], fallback_category: str) -> dict[str, Any]:
    metadata = raw.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    category = str(
        raw.get("memory_type")
        or raw.get("type")
        or raw.get("category")
        or metadata.get("memory_type")
        or metadata.get("type")
        or metadata.get("category")
        or fallback_category
    )
    content_value = (
        raw.get("memory")
        or raw.get("memory_value")
        or raw.get("preference")
        or raw.get("tool_value")
        or raw.get("experience")
        or raw.get("content")
        or raw.get("text")
        or raw.get("summary")
        or metadata.get("memory")
        or metadata.get("memory_value")
        or metadata.get("preference")
        or ""
    )
    memory_key = str(raw.get("memory_key") or metadata.get("memory_key") or "").strip()
    content = str(content_value)
    if memory_key and content:
        content = f"{memory_key}: {content}"
    score_values = {**metadata, **raw}
    return {
        "id": str(
            raw.get("id")
            or raw.get("memory_id")
            or raw.get("mem_id")
            or memory_key
            or content
        ),
        "content": content,
        "category": category,
        "tags": _memory_tags(raw.get("tags") or metadata.get("tags")),
        "trust_score": _memory_trust_score(score_values),
        "retrieval_count": int(
            raw.get("retrieval_count")
            or raw.get("retrievalCount")
            or metadata.get("retrieval_count")
            or 0
        ),
        "helpful_count": int(
            raw.get("helpful_count")
            or raw.get("helpfulCount")
            or metadata.get("helpful_count")
            or 0
        ),
        "created_at": str(
            raw.get("created_at")
            or raw.get("createdAt")
            or raw.get("create_time")
            or metadata.get("created_at")
            or metadata.get("create_time")
            or ""
        ),
        "updated_at": str(
            raw.get("updated_at")
            or raw.get("updatedAt")
            or raw.get("update_time")
            or metadata.get("updated_at")
            or metadata.get("update_time")
            or ""
        ),
    }


def _memos_external_payload(payload: Any, reason: str, limit: int) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}

    groups = [
        ("memory_detail_list", "memory"),
        ("preference_detail_list", "preference"),
        ("tool_memory_detail_list", "tool"),
        ("skill_detail_list", "skill"),
        ("profile_detail_list", "profile"),
        ("event_detail_list", "event"),
        ("text_mem", "memory"),
        ("pref_mem", "preference"),
        ("tool_mem", "tool"),
        ("skill_mem", "skill"),
    ]
    items: list[dict[str, Any]] = []
    categories: dict[str, int] = {}
    grouped_total = 0

    for key, fallback_category in groups:
        entries = data.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            memories = entry.get("memories")
            if isinstance(memories, list):
                total_nodes = entry.get("total_nodes")
                grouped_total += int(total_nodes) if isinstance(total_nodes, int | float) else len(memories)
                raw_memories = memories
            else:
                raw_memories = [entry]
            for raw in raw_memories:
                if len(items) >= limit or not isinstance(raw, dict):
                    continue
                item = _memos_item(raw, fallback_category)
                items.append(item)
                category = item["category"] or fallback_category
                categories[category] = categories.get(category, 0) + 1

    reported_total = data.get("total")
    total = (
        int(reported_total)
        if isinstance(reported_total, int | float)
        else grouped_total or len(items)
    )
    return {
        "provider": "memos",
        "available": True,
        "readonly": True,
        "reason": reason,
        "summary": {"total": total, "categories": categories},
        "items": items,
    }


def memos_cloud_external_view(limit: int = 100) -> dict[str, Any]:
    values = memory_provider_config.provider_config_values("memos")
    namespace = str(values.get("MEMOS_NAMESPACE", {}).get("value") or "").strip()
    api_key = _provider_secret("MEMOS_API_KEY")
    if not api_key or not namespace:
        return provider_summary_external_view("memos")

    is_global = str(values.get("MEMOS_IS_GLOBAL", {}).get("value") or "").lower()
    endpoint = MEMOS_GLOBAL_BASE_URL if is_global in {"1", "true", "yes"} else MEMOS_CHINA_BASE_URL

    url = _join_http_url(endpoint, "/get/memory")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Token {api_key}",
        "User-Agent": "Hermes-HUD/read-only-memory-view",
    }
    items: list[dict[str, Any]] = []
    categories: dict[str, int] = {}
    reported_total = 0
    page = 1
    max_pages = max(1, (limit + 49) // 50)

    while page <= max_pages and len(items) < limit:
        size = min(50, limit - len(items))
        payload, error = _request_json(
            url,
            headers=headers,
            method="POST",
            payload={
                "user_id": namespace,
                "include_preference": True,
                "include_tool_memory": True,
                "page": page,
                "size": size,
            },
        )
        if error:
            return _external_failure("memos", "memos_cloud_failed", error)

        normalized = _memos_external_payload(payload, "memos_cloud", limit - len(items))
        page_items = normalized["items"]
        for item in page_items:
            items.append(item)
            category = item["category"] or "memory"
            categories[category] = categories.get(category, 0) + 1
        page_total = normalized["summary"]["total"]
        if isinstance(page_total, int):
            reported_total = max(reported_total, page_total)

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            data = payload if isinstance(payload, dict) else {}
        current = data.get("current")
        pages = data.get("pages")
        if isinstance(current, int | float) and isinstance(pages, int | float):
            if int(current) >= int(pages):
                break
        elif not page_items or len(page_items) < size or reported_total <= len(items):
            break
        page += 1

    return {
        "provider": "memos",
        "available": True,
        "readonly": True,
        "reason": "memos_cloud",
        "summary": {"total": max(reported_total, len(items)), "categories": categories},
        "items": items,
    }


def memos_self_hosted_external_view(limit: int = 100) -> dict[str, Any]:
    values = memory_provider_config.provider_config_values("memos")
    endpoint = str(values.get("MEMOS_BASE_URL", {}).get("value") or "").strip()
    namespace = str(values.get("MEMOS_NAMESPACE", {}).get("value") or "").strip()
    if not endpoint or not namespace:
        return provider_summary_external_view("memos")

    path = "/get_memory" if endpoint.rstrip("/").endswith("/product") else "/product/get_memory"
    payload, error = _request_json(
        _join_http_url(endpoint, path),
        headers={
            "Accept": "application/json",
            "User-Agent": "Hermes-HUD/read-only-memory-view",
        },
        method="POST",
        payload={
            "mem_cube_id": namespace,
            "include_preference": True,
            "include_tool_memory": True,
            "include_skill_memory": True,
            "page": 1,
            "page_size": limit,
        },
    )
    if error:
        return _external_failure("memos", "memos_self_hosted_failed", error)
    return _memos_external_payload(payload, "memos_self_hosted", limit)


def _agentmemory_item(raw: dict[str, Any]) -> dict[str, Any]:
    category = str(raw.get("type") or raw.get("category") or "memory")
    return {
        "id": str(raw.get("id") or raw.get("memory_id") or raw.get("title") or ""),
        "content": str(raw.get("content") or raw.get("text") or raw.get("summary") or ""),
        "category": category,
        "tags": _memory_tags(raw.get("concepts") or raw.get("tags")),
        "trust_score": _memory_trust_score(raw),
        "retrieval_count": int(raw.get("retrieval_count") or raw.get("retrievalCount") or 0),
        "helpful_count": int(raw.get("helpful_count") or raw.get("helpfulCount") or 0),
        "created_at": str(raw.get("createdAt") or raw.get("created_at") or ""),
        "updated_at": str(raw.get("updatedAt") or raw.get("updated_at") or ""),
    }


def _agentmemory_secret() -> str:
    return _provider_secret("AGENTMEMORY_SECRET")


def agentmemory_rest_external_view(limit: int = 100) -> dict[str, Any]:
    values = memory_provider_config.provider_config_values("agentmemory")
    endpoint = str(values.get("AGENTMEMORY_URL", {}).get("value") or "").strip()
    if not endpoint:
        return provider_summary_external_view("agentmemory")

    url = _join_http_url(endpoint, f"/agentmemory/memories?limit={limit}")
    headers = {
        "Accept": "application/json",
        "User-Agent": "Hermes-HUD/read-only-memory-view",
    }
    secret = _agentmemory_secret()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
        headers["X-AgentMemory-Secret"] = secret

    response = None
    try:
        response = urlopen(Request(url, headers=headers, method="GET"), timeout=3)
        payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return {
            "provider": "agentmemory",
            "available": False,
            "readonly": True,
            "reason": "agentmemory_rest_failed",
            "error": f"HTTP {exc.code}",
            "summary": {"total": 0, "categories": {}},
            "items": [],
        }
    except (URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return {
            "provider": "agentmemory",
            "available": False,
            "readonly": True,
            "reason": "agentmemory_rest_failed",
            "error": str(getattr(exc, "reason", exc)),
            "summary": {"total": 0, "categories": {}},
            "items": [],
        }
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    memories = payload.get("memories") if isinstance(payload, dict) else []
    if not isinstance(memories, list):
        memories = []
    items = [_agentmemory_item(item) for item in memories if isinstance(item, dict)]
    categories: dict[str, int] = {}
    for item in items:
        category = item["category"] or "memory"
        categories[category] = categories.get(category, 0) + 1
    total = payload.get("total") if isinstance(payload, dict) else None
    return {
        "provider": "agentmemory",
        "available": True,
        "readonly": True,
        "reason": "agentmemory_rest",
        "summary": {
            "total": int(total) if isinstance(total, int | float) else len(items),
            "categories": categories,
        },
        "items": items,
    }


def external_view(provider: str) -> dict[str, Any]:
    if provider == "holographic":
        return holographic_external_view()
    if provider == "cognee":
        values = memory_provider_config.provider_config_values(provider)
        mode = memory_provider_config.current_config_mode(MEMORY_PROVIDER_OPTIONS[provider], values)
        if mode == "docker_api":
            return cognee_api_external_view()
    if provider == "agentmemory":
        values = memory_provider_config.provider_config_values(provider)
        mode = memory_provider_config.current_config_mode(MEMORY_PROVIDER_OPTIONS[provider], values)
        if mode == "rest_server":
            return agentmemory_rest_external_view()
    if provider == "memos":
        values = memory_provider_config.provider_config_values(provider)
        mode = memory_provider_config.current_config_mode(MEMORY_PROVIDER_OPTIONS[provider], values)
        if mode == "cloud":
            return memos_cloud_external_view()
        if mode == "self_hosted":
            return memos_self_hosted_external_view()
    if provider in {"cognee", "agentmemory", "memos"}:
        return provider_summary_external_view(provider)
    return {
        "provider": provider,
        "available": False,
        "readonly": True,
        "reason": "provider_specific_api_not_configured",
        "items": [],
    }
