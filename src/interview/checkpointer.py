"""
checkpointer.py

Milestone 6 — persistent SQLite-backed checkpointing for the realtime
interview graph.

Uses AsyncSqliteSaver (from the `langgraph-checkpoint-sqlite` package) so
the live LiveKit agent can persist and resume interview state natively
via async APIs (ainvoke / aget_state / aupdate_state) without blocking
the event loop on synchronous SQLite calls.

This checkpointer is used ONLY on the realtime path
(build_interview_graph(realtime_mode=True) in src/realtime/agent.py).
The default synchronous test suite (test_interview_graph.py) keeps using
the in-memory MemorySaver that graph.py falls back to when no
checkpointer is passed — AsyncSqliteSaver does not implement the
synchronous checkpointer interface, so a plain `graph.invoke(...)` call
against it will raise, by design. Anything exercising the realtime
graph's persistence should use the async tests in
tests/test_persistence_and_hitl.py instead.

VERSION NOTE: this was written against the async API surface of
langgraph-checkpoint-sqlite as of Milestone 5's stack (LangGraph +
LiveKit Agents + Gemini Realtime). It could not be verified against your
exact installed package versions in the environment this was written in
(no package registry access there) — run
`pip show langgraph-checkpoint-sqlite` and skim its `aio.py` if
`open_sqlite_checkpointer()` raises an AttributeError/ImportError, and
adjust the import path / setup() call below accordingly. This is called
out again in ARCHITECTURE.md.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Union

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

DEFAULT_DB_PATH = (
    Path(__file__).resolve().parent.parent.parent / "output" / "interview_checkpoints.sqlite"
)


@asynccontextmanager
async def open_sqlite_checkpointer(db_path: Union[Path, str] = DEFAULT_DB_PATH):
    """
    Async context manager yielding a ready-to-use AsyncSqliteSaver backed
    by a real file on disk, so interview state survives process restarts
    and dropped calls.

    Usage:
        async with open_sqlite_checkpointer() as checkpointer:
            graph = build_interview_graph(realtime_mode=True, checkpointer=checkpointer)
            ...

    Each interview thread (see thread_id derivation in
    src/realtime/agent.py) is just a row keyed by thread_id inside this
    one file — multiple concurrent interviews can safely share the same
    DB file; they never share a thread_id.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        # Defensive: some langgraph-checkpoint-sqlite versions create
        # tables automatically inside from_conn_string()'s __aenter__,
        # others require an explicit setup() call. setup() is a CREATE
        # TABLE IF NOT EXISTS under the hood, so calling it when it's
        # already been done is a harmless no-op — this just means we
        # don't have to know which version you're on.
        if hasattr(checkpointer, "setup"):
            await checkpointer.setup()
        yield checkpointer