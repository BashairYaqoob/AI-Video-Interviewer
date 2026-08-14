"""
graph.py

Milestone 4C — LangGraph interview state machine.

Flow: intro -> ask_question -> receive_answer (pauses/interrupts) ->
analyze_answer -> [follow_up loop | advance to next question | closing].

This graph controls interview flow and evidence collection ONLY — it does
not score the candidate (later milestone), and it is not yet wired into
the live realtime agent (also later — this is deliberately standalone and
testable for now).

Uses an in-memory checkpointer for now (MemorySaver). The brief requires
a SQLite checkpointer for real dropped-call resume — that swap happens
when this graph is integrated with the live agent, not in this milestone.
"""

from functools import partial

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.interview.state import InterviewState
from src.interview.nodes import (
    intro_node,
    ask_question_node,
    receive_answer_node,
    analyze_answer_node,
    ask_follow_up_node,
    advance_question_node,
    closing_node,
)
from src.interview.router import route_after_analysis
from src.interview.answer_analysis import analyze_answer as default_analyzer


def build_interview_graph(analyzer=None, checkpointer=None):
    """
    Builds and compiles the interview graph.

    Args:
        analyzer: callable(question, answer, jd, resume, github_evidence)
                  -> EvidenceRecord. Defaults to the real Gemini-based
                  analyzer. Tests should pass a fake/deterministic function.
        checkpointer: LangGraph checkpointer. Defaults to an in-memory
                      MemorySaver (fine for tests/local dev).
    """
    analyzer_fn = analyzer or default_analyzer
    checkpointer = checkpointer if checkpointer is not None else MemorySaver()

    builder = StateGraph(InterviewState)

    builder.add_node("intro", intro_node)
    builder.add_node("ask_question", ask_question_node)
    builder.add_node("receive_answer", receive_answer_node)
    builder.add_node("analyze_answer", partial(analyze_answer_node, analyzer=analyzer_fn))
    builder.add_node("ask_follow_up", ask_follow_up_node)
    builder.add_node("advance_question", advance_question_node)
    builder.add_node("closing", closing_node)

    builder.add_edge(START, "intro")
    builder.add_edge("intro", "ask_question")
    builder.add_edge("ask_question", "receive_answer")
    builder.add_edge("receive_answer", "analyze_answer")

    builder.add_conditional_edges(
        "analyze_answer",
        route_after_analysis,
        {
            "follow_up": "ask_follow_up",
            "advance_next": "advance_question",
            "closing": "closing",
        },
    )

    builder.add_edge("ask_follow_up", "receive_answer")
    builder.add_edge("advance_question", "ask_question")
    builder.add_edge("closing", END)

    return builder.compile(checkpointer=checkpointer)