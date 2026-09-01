"""Local analysis-run store: files for one report, SQLite for the catalog.

Layout::

    {run_store_dir}/{run_id}/
        manifest.json
        decision.json
        complete_report.md
        state.json
        events.jsonl
        1_analysts/ ...

    {run_store_dir.parent}/runs.sqlite
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tradingagents.agents.utils.rating import parse_rating
from tradingagents.reporting import write_report_tree

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    status TEXT NOT NULL,
    rating TEXT,
    created_at TEXT NOT NULL,
    directory TEXT NOT NULL,
    llm_provider TEXT,
    deep_think_llm TEXT,
    quick_think_llm TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_ticker_date ON runs (ticker, trade_date);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs (created_at);
"""

_RUN_COLUMNS = (
    "run_id, ticker, trade_date, status, rating, created_at, directory, "
    "llm_provider, deep_think_llm, quick_think_llm, progress_percent, "
    "current_step, error, cancel_requested, analysts, output_language, finished_at"
)

_EXTRA_COLUMNS = (
    ("progress_percent", "INTEGER"),
    ("current_step", "TEXT"),
    ("error", "TEXT"),
    ("cancel_requested", "INTEGER DEFAULT 0"),
    ("analysts", "TEXT"),
    ("output_language", "TEXT"),
    ("finished_at", "TEXT"),
)


@dataclass(frozen=True)
class PersistedRun:
    run_id: str
    directory: Path
    manifest: dict[str, Any]


def persist_completed_run(
    *,
    config: dict[str, Any],
    ticker: str,
    trade_date: str,
    final_state: dict[str, Any],
    state_snapshot: dict[str, Any],
    analysts: tuple[str, ...] = (),
    run_id: str | None = None,
) -> PersistedRun | None:
    """Write a completed run to disk and upsert the SQLite catalog row.

    Missing or false ``run_store_enabled`` skips all file I/O. The hosted API
    path forces this off so workers do not write tenant reports to local disk.
    """
    if not config.get("run_store_enabled"):
        return None
    store_dir = config.get("run_store_dir")
    if not store_dir:
        return None

    run_id = run_id or config.get("run_store_run_id") or uuid.uuid4().hex
    if not _safe_run_id(str(run_id)):
        return None
    directory = Path(store_dir).expanduser() / run_id
    directory.mkdir(parents=True, exist_ok=True)

    write_report_tree(final_state, ticker, directory)
    _write_json(directory / "state.json", state_snapshot)
    _write_json(directory / "decision.json", final_state.get("decision_brief"))

    now = datetime.now(timezone.utc).isoformat()
    existing = get_run(config, str(run_id))
    created_at = (existing or {}).get("created_at") or now
    rating = parse_rating(str(final_state.get("final_trade_decision") or ""))
    manifest = {
        "run_id": run_id,
        "ticker": ticker,
        "trade_date": str(trade_date),
        "status": "succeeded",
        "rating": rating,
        "created_at": created_at,
        "analysts": list(analysts),
        "llm_provider": config.get("llm_provider"),
        "deep_think_llm": config.get("deep_think_llm"),
        "quick_think_llm": config.get("quick_think_llm"),
        "output_language": config.get("output_language"),
        "progress_percent": 100,
        "current_step": "Completed",
        "error": None,
        "cancel_requested": 0,
        "finished_at": now,
    }
    _write_json(directory / "manifest.json", manifest)

    index_path = _index_path(config, Path(store_dir).expanduser())
    _upsert_index(index_path, manifest, directory)
    return PersistedRun(run_id=run_id, directory=directory, manifest=manifest)


def begin_run(
    *,
    config: dict[str, Any],
    ticker: str,
    trade_date: str,
    analysts: tuple[str, ...] = (),
) -> PersistedRun | None:
    """Insert a ``running`` catalog row and create the run directory."""
    if not config.get("run_store_enabled"):
        return None
    store_dir = config.get("run_store_dir")
    if not store_dir:
        return None
    run_id = uuid.uuid4().hex
    directory = Path(store_dir).expanduser() / run_id
    directory.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "run_id": run_id,
        "ticker": ticker,
        "trade_date": str(trade_date),
        "status": "running",
        "rating": None,
        "created_at": created_at,
        "analysts": list(analysts),
        "llm_provider": config.get("llm_provider"),
        "deep_think_llm": config.get("deep_think_llm"),
        "quick_think_llm": config.get("quick_think_llm"),
        "output_language": config.get("output_language"),
        "progress_percent": 0,
        "current_step": "Queued",
        "error": None,
        "cancel_requested": 0,
        "finished_at": None,
    }
    _write_json(directory / "manifest.json", manifest)
    (directory / "events.jsonl").touch()
    _upsert_index(_index_path(config, Path(store_dir).expanduser()), manifest, directory)
    return PersistedRun(run_id=run_id, directory=directory, manifest=manifest)


def get_run(config: dict[str, Any], run_id: str) -> dict[str, Any] | None:
    """Return the catalog row for ``run_id``, or None if missing."""
    if not _safe_run_id(run_id):
        return None
    conn = _connect(config)
    if conn is None:
        return None
    try:
        row = conn.execute(
            f"SELECT {_RUN_COLUMNS} FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    finally:
        conn.close()
    return _row_dict(row) if row else None


def list_runs(
    config: dict[str, Any],
    *,
    ticker: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List recent catalog rows, newest first."""
    conn = _connect(config)
    if conn is None:
        return []
    limit = max(1, min(int(limit), 500))
    clauses = []
    params: list[Any] = []
    if ticker:
        clauses.append("ticker = ?")
        params.append(ticker)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    try:
        rows = conn.execute(
            f"SELECT {_RUN_COLUMNS} FROM runs {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
    finally:
        conn.close()
    return [_row_dict(row) for row in rows]


def update_run_progress(
    config: dict[str, Any],
    run_id: str,
    *,
    progress_percent: int,
    current_step: str,
    kind: str = "stage",
) -> None:
    """Record a progress event on a running analysis."""
    row = get_run(config, run_id)
    if row is None or row.get("status") not in {"queued", "running"}:
        return
    now = datetime.now(timezone.utc).isoformat()
    _patch_run(
        config,
        run_id,
        {
            "progress_percent": int(progress_percent),
            "current_step": current_step,
            "status": "running",
        },
    )
    _append_event(
        Path(row["directory"]),
        {
            "time": now,
            "progress_percent": int(progress_percent),
            "message": current_step,
            "kind": kind,
        },
    )


def list_run_events(config: dict[str, Any], run_id: str) -> list[dict[str, Any]]:
    row = get_run(config, run_id)
    if row is None:
        return []
    path = Path(row["directory"]) / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def request_cancel(config: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Ask a running job to stop. Returns ``{id, status}`` or raises ValueError."""
    row = get_run(config, run_id)
    if row is None:
        raise ValueError("analysis not found")
    status = row.get("status")
    if status in {"succeeded", "failed", "cancelled"}:
        raise ValueError(f"analysis cannot be cancelled from status {status}")
    if status == "queued":
        now = datetime.now(timezone.utc).isoformat()
        _patch_run(
            config,
            run_id,
            {
                "status": "cancelled",
                "cancel_requested": 1,
                "current_step": "Cancelled",
                "finished_at": now,
            },
        )
        return {"id": run_id, "status": "cancelled"}
    _patch_run(config, run_id, {"cancel_requested": 1})
    return {"id": run_id, "status": "cancel_requested"}


def is_cancel_requested(config: dict[str, Any], run_id: str) -> bool:
    row = get_run(config, run_id)
    return bool(row and row.get("cancel_requested"))


def mark_run_failed(
    config: dict[str, Any],
    run_id: str,
    *,
    error: str,
    cancelled: bool = False,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    _patch_run(
        config,
        run_id,
        {
            "status": "cancelled" if cancelled else "failed",
            "error": error,
            "finished_at": now,
            "current_step": "Cancelled" if cancelled else "Failed",
        },
    )


def load_run_report(config: dict[str, Any], run_id: str) -> dict[str, Any] | None:
    """Decision card and report sections from a completed run directory."""
    row = get_run(config, run_id)
    if row is None:
        return None
    directory = Path(row["directory"])
    state = _read_json(directory / "state.json") or {}
    decision = _read_json(directory / "decision.json")
    manifest = _read_json(directory / "manifest.json") or {}
    return {
        "id": run_id,
        "status": row.get("status"),
        "ticker": row.get("ticker"),
        "trade_date": row.get("trade_date"),
        "decision": state.get("final_trade_decision") or row.get("rating"),
        "reports": report_sections_from_state(state),
        "decision_brief": decision if decision is not None else state.get("decision_brief"),
        "output_language": row.get("output_language") or manifest.get("output_language"),
        "quick_think_llm": row.get("quick_think_llm"),
        "deep_think_llm": row.get("deep_think_llm"),
        "run_dir": str(directory),
    }


def report_sections_from_state(final_state: dict[str, Any]) -> dict[str, Any]:
    """Map graph state fields to the desk-style ``reports`` object."""
    reports: dict[str, Any] = {}
    for key in (
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "investment_plan",
        "trader_investment_plan",
        "final_trade_decision",
    ):
        value = final_state.get(key)
        if value:
            reports["research_team_decision" if key == "investment_plan" else key] = value
    research = final_state.get("investment_debate_state") or {}
    if research.get("bull_history"):
        reports["bull_researcher"] = research["bull_history"]
    if research.get("bear_history"):
        reports["bear_researcher"] = research["bear_history"]
    if research.get("judge_decision") and "research_team_decision" not in reports:
        reports["research_team_decision"] = research["judge_decision"]
    risk = final_state.get("risk_debate_state") or {}
    if risk.get("aggressive_history"):
        reports["risky_analyst"] = risk["aggressive_history"]
    if risk.get("conservative_history"):
        reports["safe_analyst"] = risk["conservative_history"]
    if risk.get("neutral_history"):
        reports["neutral_analyst"] = risk["neutral_history"]
    judge = risk.get("judge_decision")
    if judge and reports.get("final_trade_decision") != judge:
        reports["risk_management_decision"] = judge
    return reports


def _safe_run_id(run_id: str) -> bool:
    return isinstance(run_id, str) and run_id.isalnum() and 8 <= len(run_id) <= 64


def _index_path(config: dict[str, Any], store_dir: Path) -> Path:
    explicit = config.get("run_store_index")
    if explicit:
        return Path(explicit).expanduser()
    return store_dir.parent / "runs.sqlite"


def _connect(config: dict[str, Any]) -> sqlite3.Connection | None:
    store_dir = config.get("run_store_dir")
    if not store_dir:
        return None
    path = _index_path(config, Path(store_dir).expanduser())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    _ensure_columns(conn)
    return conn


def _ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    for name, decl in _EXTRA_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {decl}")
    conn.commit()


def _upsert_index(index_path: Path, manifest: dict[str, Any], directory: Path) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(index_path), timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        _ensure_columns(conn)
        analysts = manifest.get("analysts")
        if isinstance(analysts, (list, tuple)):
            analysts = json.dumps(list(analysts))
        conn.execute(
            """
            INSERT INTO runs (
                run_id, ticker, trade_date, status, rating, created_at,
                directory, llm_provider, deep_think_llm, quick_think_llm,
                progress_percent, current_step, error, cancel_requested,
                analysts, output_language, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                ticker = excluded.ticker,
                trade_date = excluded.trade_date,
                status = excluded.status,
                rating = excluded.rating,
                directory = excluded.directory,
                llm_provider = excluded.llm_provider,
                deep_think_llm = excluded.deep_think_llm,
                quick_think_llm = excluded.quick_think_llm,
                progress_percent = excluded.progress_percent,
                current_step = excluded.current_step,
                error = excluded.error,
                cancel_requested = excluded.cancel_requested,
                analysts = excluded.analysts,
                output_language = excluded.output_language,
                finished_at = excluded.finished_at
            """,
            (
                manifest["run_id"],
                manifest["ticker"],
                manifest["trade_date"],
                manifest["status"],
                manifest.get("rating"),
                manifest["created_at"],
                str(directory),
                manifest.get("llm_provider"),
                manifest.get("deep_think_llm"),
                manifest.get("quick_think_llm"),
                manifest.get("progress_percent"),
                manifest.get("current_step"),
                manifest.get("error"),
                int(manifest.get("cancel_requested") or 0),
                analysts,
                manifest.get("output_language"),
                manifest.get("finished_at"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _patch_run(config: dict[str, Any], run_id: str, fields: dict[str, Any]) -> None:
    conn = _connect(config)
    if conn is None:
        return
    assignments = []
    params: list[Any] = []
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        params.append(value)
    params.append(run_id)
    try:
        conn.execute(
            f"UPDATE runs SET {', '.join(assignments)} WHERE run_id = ?",
            params,
        )
        conn.commit()
        row = conn.execute(
            f"SELECT {_RUN_COLUMNS} FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return
    directory = Path(row["directory"])
    manifest_path = directory / "manifest.json"
    manifest = _read_json(manifest_path) or {}
    manifest.update(_row_dict(row))
    _write_json(manifest_path, manifest)


def _append_event(directory: Path, event: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    analysts = data.get("analysts")
    if isinstance(analysts, str) and analysts.startswith("["):
        with contextlib.suppress(json.JSONDecodeError):
            data["analysts"] = json.loads(analysts)
    return data


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
