from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .progress import ProgressEventProjector

TradingAgentsGraph = None


def _trading_agents_graph():
    graph_cls = globals().get("TradingAgentsGraph")
    if graph_cls is None:
        from tradingagents.graph.trading_graph import TradingAgentsGraph as graph_cls

        globals()["TradingAgentsGraph"] = graph_cls
    return graph_cls


@dataclass(frozen=True)
class AnalysisCommand:
    ticker: str
    trade_date: str
    asset_type: str
    analysts: tuple[str, ...]
    config: dict[str, Any]
    display_name: str | None = None
    english_name: str | None = None


@dataclass(frozen=True)
class AnalysisEvent:
    progress_percent: int
    message: str
    state_update: dict[str, Any] | None = None
    kind: str = "stage"


@dataclass(frozen=True)
class AnalysisResult:
    final_state: dict[str, Any]
    decision: str
    run_id: str | None = None
    run_dir: str | None = None


def run_analysis(
    command: AnalysisCommand,
    *,
    callbacks: tuple[Any, ...] | list[Any] = (),
    on_event: Callable[[AnalysisEvent], None] | None = None,
) -> AnalysisResult:
    graph = _trading_agents_graph()(
        selected_analysts=list(command.analysts),
        config=command.config,
        debug=False,
        callbacks=list(callbacks),
    )
    merged_state: dict[str, Any] = {}
    projector = ProgressEventProjector(command.analysts, command.config)

    def handle_chunk(chunk: dict[str, Any]) -> None:
        merged_state.update(chunk)
        if on_event is not None:
            for update in projector.consume(merged_state, chunk):
                on_event(
                    AnalysisEvent(
                        update.progress_percent,
                        update.message,
                        dict(chunk),
                        update.kind,
                    )
                )

    final_state, decision = graph.propagate(
        command.ticker,
        command.trade_date,
        asset_type=command.asset_type,
        on_chunk=handle_chunk,
        display_name=command.display_name,
        english_name=command.english_name,
    )
    last_run = getattr(graph, "last_run", None)
    return AnalysisResult(
        final_state=final_state,
        decision=str(decision),
        run_id=getattr(last_run, "run_id", None),
        run_dir=str(last_run.directory) if last_run is not None else None,
    )
