"""Freeze the exact prompts and non-secret run settings before inference."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable

from .. import config


PROMPT_FILENAMES = (
    "local_summary.md",
    "phase_aggregate.md",
    "root_cause.md",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    _atomic_write_bytes(path, encoded)


def _config_snapshot() -> Dict[str, Any]:
    names = (
        "SCHEMA_VERSION",
        "PROMPT_VERSIONS",
        "LLM_SEND_THINKING_CONFIG",
        "LLM_THINKING_LOCAL",
        "LLM_THINKING_PHASE",
        "LLM_THINKING_ROOT",
        "LLM_REASONING_EFFORT_LOCAL",
        "LLM_REASONING_EFFORT_PHASE",
        "LLM_REASONING_EFFORT_ROOT",
        "LLM_TEMPERATURE_DEFAULT",
        "LLM_TEMPERATURE_ROOT",
        "LLM_MAX_TOKENS_LOCAL",
        "LLM_MAX_TOKENS_PHASE",
        "LLM_MAX_TOKENS_ROOT",
        "LLM_TIMEOUT_SECONDS",
        "LLM_MAX_RETRIES",
        "LLM_RETRY_BACKOFF_BASE",
        "SEG_TARGET_CHARS",
        "SEG_MAX_CHARS",
        "SEG_MIN_STEPS",
        "SEG_MIN_CHARS_FOR_SOFT_BOUNDARY",
        "SEG_MAX_STEPS",
        "SEG_OVERLAP_STEPS",
        "STEP_FULL_MAX_CHARS",
    )
    return {name: getattr(config, name, None) for name in names}


def _identity(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "created_at_utc"}


def freeze_run_snapshot(
    *,
    out_root: Path,
    benchmark: str,
    model: str,
    base_url: str,
    input_dir: Path,
    input_files: Iterable[Path],
) -> Dict[str, Any]:
    """Save exact prompt bytes and refuse to mix incompatible resumed outputs.

    The manifest intentionally contains no API key or other credential.
    """
    out_root = Path(out_root)
    snapshot_root = out_root / "run_snapshot"
    prompt_snapshot_dir = snapshot_root / "prompts"
    manifest_path = snapshot_root / "manifest.json"

    prompt_bytes: Dict[str, bytes] = {}
    prompt_entries: Dict[str, Dict[str, Any]] = {}
    for filename in PROMPT_FILENAMES:
        source = config.PROMPTS_DIR / filename
        data = source.read_bytes()
        prompt_bytes[filename] = data
        prompt_entries[filename] = {
            "sha256": _sha256(data),
            "bytes": len(data),
            "snapshot_path": f"prompts/{filename}",
        }

    file_names = sorted(Path(path).name for path in input_files)
    file_list_bytes = "\n".join(file_names).encode("utf-8")
    candidate: Dict[str, Any] = {
        "snapshot_schema_version": 1,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "benchmark": benchmark,
        "model": model,
        "base_url": base_url,
        "input_dir": str(Path(input_dir).resolve()),
        "input_count": len(file_names),
        "input_file_list_sha256": _sha256(file_list_bytes),
        "prompts": prompt_entries,
        "config": _config_snapshot(),
    }

    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        copied_hashes = {
            filename: _sha256((prompt_snapshot_dir / filename).read_bytes())
            for filename in PROMPT_FILENAMES
            if (prompt_snapshot_dir / filename).exists()
        }
        expected_hashes = {
            filename: entry["sha256"]
            for filename, entry in (existing.get("prompts") or {}).items()
        }
        if _identity(existing) != _identity(candidate) or copied_hashes != expected_hashes:
            raise RuntimeError(
                "run snapshot mismatch: refusing to mix outputs produced with "
                "different prompts, inputs, model, or settings"
            )
        return existing

    if snapshot_root.exists() and any(snapshot_root.iterdir()):
        raise RuntimeError(
            "run snapshot mismatch: snapshot directory exists without a complete manifest"
        )

    for filename, data in prompt_bytes.items():
        _atomic_write_bytes(prompt_snapshot_dir / filename, data)
    _atomic_write_json(manifest_path, candidate)
    return candidate
