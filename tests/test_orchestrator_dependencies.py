from importlib import import_module
import sqlite3
from typing import TypedDict


def test_langgraph_sqlite_modules_import():
    assert import_module("langgraph.graph")
    assert import_module("langgraph.checkpoint.sqlite")


class DummyState(TypedDict):
    val: str


def test_langgraph_sqlite_persistence_roundtrip(tmp_path):
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import StateGraph, START, END

    db_path = tmp_path / "checkpoints.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)

    builder = StateGraph(DummyState)

    def step(state: DummyState) -> dict:
        return {"val": state["val"] + "_updated"}

    builder.add_node("step", step)
    builder.add_edge(START, "step")
    builder.add_edge("step", END)

    graph = builder.compile(checkpointer=saver)

    config = {"configurable": {"thread_id": "test-thread-1"}}
    result = graph.invoke({"val": "init"}, config=config)
    assert result["val"] == "init_updated"

    # Close and reopen SQLite to verify state survives and can be retrieved
    conn.close()

    conn2 = sqlite3.connect(db_path, check_same_thread=False)
    saver2 = SqliteSaver(conn2)
    graph2 = builder.compile(checkpointer=saver2)

    saved_state = graph2.get_state(config)
    assert saved_state.values["val"] == "init_updated"
    conn2.close()
