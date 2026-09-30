"""What `mount_mcp` exposed, hid, and skipped. Never contains header values."""

from __future__ import annotations

from dataclasses import dataclass, field

from mcpmaker.policy import WRITE_REASON, Selection


@dataclass
class MountReport:
    path: str
    tools: list[tuple[str, str, str]] = field(default_factory=list)  # (tool, METHOD, path)
    hidden: list[tuple[str, str, str]] = field(default_factory=list)  # (METHOD, path, reason)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (operation_id, error)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_selection(cls, selection: Selection, *, path: str, skipped: list[tuple[str, str]]) -> MountReport:
        skipped_ids = {op_id for op_id, _ in skipped}
        tools = [
            (name, selection.operations[op_id].method, selection.operations[op_id].path)
            for op_id, name in selection.exposed.items()
            if op_id not in skipped_ids
        ]
        hidden = [(h.operation.method, h.operation.path, h.reason) for h in selection.hidden]
        warnings = list(selection.warnings) + [f"skipped {op_id}: {err}" for op_id, err in skipped]
        return cls(path=path, tools=tools, hidden=hidden, skipped=list(skipped), warnings=warnings)

    def format(self) -> str:
        head = f"mcpmaker: {len(self.tools)} tools exposed at {self.path}"
        writes_hidden = sum(1 for _, _, reason in self.hidden if reason == WRITE_REASON)
        if writes_hidden:
            head += f" ({writes_hidden} write routes hidden - pass include_writes=True or mark routes)"
        lines = [head]
        lines += [f"  - {name}  {method} {path}" for name, method, path in self.tools]
        lines += [f"  WARNING: {w}" for w in self.warnings]
        return "\n".join(lines)
