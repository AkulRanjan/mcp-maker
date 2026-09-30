from mcpmaker.policy import Operation, select_operations
from mcpmaker.report import MountReport


def make_selection():
    ops = [
        Operation("list_op", "GET", "/items", summary="List", function_name="list_items"),
        Operation("get_op", "GET", "/items/{id}", summary="Get", function_name="get_item"),
        Operation("create_op", "POST", "/items", summary="Create", function_name="create_item"),
    ]
    return select_operations(ops)


def test_from_selection_lists_tools_and_hidden():
    report = MountReport.from_selection(make_selection(), path="/mcp", skipped=[])
    assert report.tools == [("list_items", "GET", "/items"), ("get_item", "GET", "/items/{id}")]
    assert report.hidden[0][:2] == ("POST", "/items")


def test_skipped_operations_are_removed_and_warned():
    report = MountReport.from_selection(make_selection(), path="/mcp", skipped=[("get_op", "ValueError: bad schema")])
    assert [t[0] for t in report.tools] == ["list_items"]
    assert report.skipped == [("get_op", "ValueError: bad schema")]
    assert any("get_op" in w and "bad schema" in w for w in report.warnings)


def test_format_summarises_counts_and_hidden_writes():
    text = MountReport.from_selection(make_selection(), path="/mcp", skipped=[]).format()
    first = text.splitlines()[0]
    assert first.startswith("mcpmaker: 2 tools exposed at /mcp")
    assert "1 write routes hidden" in first
    assert "list_items" in text
    text.encode("ascii")  # safe for legacy Windows consoles
