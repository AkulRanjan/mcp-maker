from mcpmaker.policy import (
    EXCLUDED_REASON,
    MCP_PATH_REASON,
    METHOD_REASON,
    WRITE_REASON,
    Operation,
    ensure_operation_ids,
    operations_from_spec,
    sanitize_name,
    select_operations,
)


def op(method="GET", path="/items", *, fn=None, summary="does a thing", **kw):
    return Operation(
        operation_id=kw.pop("operation_id", f"{method.lower()}{path.replace('/', '_')}"),
        method=method,
        path=path,
        summary=summary,
        function_name=fn,
        **kw,
    )


def reasons(sel):
    return {(h.operation.method, h.operation.path): h.reason for h in sel.hidden}


def test_get_exposed_and_writes_hidden_by_default():
    sel = select_operations([op("GET", fn="list_items"), op("POST", fn="create_item")])
    assert list(sel.exposed.values()) == ["list_items"]
    assert reasons(sel) == {("POST", "/items"): WRITE_REASON}


def test_include_writes_exposes_all_write_methods():
    ops = [op(m, fn=f"f_{m.lower()}") for m in ("POST", "PUT", "PATCH", "DELETE")]
    sel = select_operations(ops, include_writes=True)
    assert sorted(sel.exposed.values()) == ["f_delete", "f_patch", "f_post", "f_put"]


def test_x_mcp_true_opts_in_a_single_write():
    sel = select_operations([op("POST", fn="star", x_mcp=True), op("DELETE", fn="drop")])
    assert list(sel.exposed.values()) == ["star"]


def test_x_mcp_false_hides_a_get():
    sel = select_operations([op("GET", fn="secret", x_mcp=False)])
    assert sel.exposed == {}
    assert reasons(sel) == {("GET", "/items"): EXCLUDED_REASON}


def test_exclude_glob_matches_nested_paths():
    ops = [op(path="/admin/stats", fn="a"), op(path="/admin/users/{id}", fn="b"), op(path="/items", fn="c")]
    sel = select_operations(ops, exclude=["/admin/*"])
    assert list(sel.exposed.values()) == ["c"]


def test_exclude_beats_x_mcp_true():
    sel = select_operations([op("POST", path="/admin/reset", fn="reset", x_mcp=True)], exclude=["/admin/*"])
    assert sel.exposed == {}
    assert reasons(sel)[("POST", "/admin/reset")] == EXCLUDED_REASON


def test_mount_path_is_never_a_tool():
    sel = select_operations([op(path="/mcp", fn="m"), op(path="/mcp/x", fn="n")], mount_path="/mcp")
    assert sel.exposed == {}
    assert set(reasons(sel).values()) == {MCP_PATH_REASON}


def test_head_is_unsupported():
    sel = select_operations([op("HEAD", fn="h")])
    assert reasons(sel) == {("HEAD", "/items"): METHOD_REASON}


def test_function_name_preferred_then_operation_id():
    sel = select_operations([op(fn="nice_name"), op(path="/other", operation_id="customOp")])
    assert sorted(sel.exposed.values()) == ["customOp", "nice_name"]


def test_name_collision_is_deduped_with_warning():
    sel = select_operations([op(path="/a", fn="list_items"), op(path="/b", fn="list_items")])
    assert sorted(sel.exposed.values()) == ["list_items", "list_items_2"]
    assert any("collision" in w and "list_items_2" in w for w in sel.warnings)


def test_sanitize_name():
    assert sanitize_name("get items/{id}") == "get_items__id"
    assert sanitize_name("x" * 100) == "x" * 64
    assert sanitize_name("///") == "tool"


def test_undocumented_tools_warned():
    sel = select_operations([op(fn="bare", summary="")])
    assert any("no description" in w and "bare" in w for w in sel.warnings)


def test_too_many_tools_warned():
    ops = [op(path=f"/p{i}", fn=f"t{i}") for i in range(3)]
    sel = select_operations(ops, max_tools_warning=2)
    assert any("3 tools exposed" in w for w in sel.warnings)


def test_zero_tools_warning_points_at_include_writes():
    sel = select_operations([op("POST", fn="c")])
    assert any("0 tools exposed" in w and "include_writes=True" in w for w in sel.warnings)


def test_operations_from_spec_reads_fields_and_endpoint_names():
    spec = {
        "paths": {
            "/items": {
                "get": {"operationId": "list_items_items_get", "summary": "List", "description": "All items"},
                "post": {"operationId": "create", "x-mcp": True},
            }
        }
    }
    ops = operations_from_spec(spec, {("GET", "/items"): "list_items"})
    by_id = {o.operation_id: o for o in ops}
    assert by_id["list_items_items_get"].function_name == "list_items"
    assert by_id["list_items_items_get"].description == "All items"
    assert by_id["create"].method == "POST"
    assert by_id["create"].x_mcp is True
    assert by_id["create"].function_name is None


def test_ensure_operation_ids_fills_missing_without_mutating_input():
    spec = {"paths": {"/items/{id}": {"get": {"summary": "x"}}}}
    out = ensure_operation_ids(spec)
    assert out["paths"]["/items/{id}"]["get"]["operationId"] == "get__items__id"
    assert "operationId" not in spec["paths"]["/items/{id}"]["get"]
