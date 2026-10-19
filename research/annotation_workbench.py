"""Local-only annotation form helpers. Never contacts models or declares gold."""
from __future__ import annotations

import html
import json

from research.input_contract import source_to_model_input
from research.reference_schema import reference_template, validate_reference

MAX_DRAFT_BYTES = 256 * 1024


def _escape(value):
    return html.escape(str(value), quote=True)


def starter_reference(case_id, approved_route):
    """Human-editable structural skeleton, with intentionally EMPTY semantic data."""
    result = reference_template(case_id, approved_route)
    clarify = approved_route["terminal_strategy"] == "clarify"
    result["reference_task"] = {
        "intended_goal": "", "actions": [{"action_id": "", "capability_id": "", "arguments": {}, "constraints": []}],
        "unresolved": [{"field": "", "reason": "", "critical": True}] if clarify else [],
        "dependencies": [], "readiness": "CLARIFY" if clarify else "ACTION_READY",
        "clarification_question": "" if clarify else None,
    }
    result["critical_unknowns"] = [{"field": "", "reason": ""}] if clarify else []
    result["dialogue_relevant"] = None
    result["explicit_linked_dependencies"] = None
    result["verification_evidence"] = None
    return result


def parse_envelope(body, state):
    """Fail closed on forged/stale draft envelopes; route is immutable."""
    if not isinstance(body, str) or len(body.encode("utf-8")) > MAX_DRAFT_BYTES:
        raise ValueError("Draft must be UTF-8 text under the size limit")
    from research.integrity import loads_json
    value = loads_json(body)
    case = state["record_id"]
    if (not isinstance(value, dict) or set(value) != {"document_type", "record_id", "expected_head", "reference"}
            or value["document_type"] != "UNVERIFIED_HUMAN_EDITABLE_DRAFT"
            or value["record_id"] != case or value["expected_head"] != state["head"]
            or not isinstance(value["reference"], dict)):
        raise ValueError("Draft envelope is invalid or stale; reload the latest case")
    ref = value["reference"]
    if (ref.get("record_id") != case
            or ref.get("author_approved_route") != state["approved_route"]["terminal_strategy"]
            or ref.get("author_approved_strategy_sequence") != state["approved_route"].get("strategy_sequence")):
        raise ValueError("Locked route, strategy sequence or case identity changed")
    return value


def draft_envelope(state):
    """Use the latest ledger content, falling back only to a blank skeleton."""
    reference = state["reference"] if state["reference"] is not None else starter_reference(
        state["record_id"], state["approved_route"])
    return {"document_type": "UNVERIFIED_HUMAN_EDITABLE_DRAFT", "record_id": state["record_id"],
            "expected_head": state["head"], "reference": reference}


def validate_envelope(envelope, state):
    clean = source_to_model_input(state["source"])
    return validate_reference(envelope["reference"], clean, state["approved_route"])


def case_page(state, *, draft_text, token, message=""):
    """All user-provided text is HTML-escaped. No external scripts/assets."""
    case = _escape(state["record_id"])
    source = state["source"]
    route = _escape(state["approved_route"]["terminal_strategy"])
    dialogue = "\n".join(source["dialogue_history"]) if source["dialogue_history"] else "[none]"
    inputs = [("Instruction", source["command"]), ("Scene", source["scene_context"]),
              ("Dialogue", dialogue), ("Capabilities", source["capability_context"])]
    cards = "".join(f'<section><h3>{_escape(label)}</h3><pre>{_escape(value)}</pre></section>' for label, value in inputs)
    notice = f'<p role="status">{_escape(message)}</p>' if message else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reference workbench {case}</title><style>
body{{font:16px system-ui;max-width:1500px;margin:24px auto;padding:0 18px;color:#171717}}
a{{color:#2159a6}} main{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
section{{margin:8px 0;padding:12px;border:1px solid #bbb;border-radius:6px}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;max-height:220px;overflow:auto}}
textarea{{width:100%;height:68vh;box-sizing:border-box;font:13px ui-monospace,monospace}}
textarea[name=notes]{{height:85px;display:block;margin:6px 0}}
button{{margin:8px 8px 8px 0;padding:9px 14px}}input{{padding:7px}}
@media(max-width:900px){{main{{grid-template-columns:1fr}}textarea{{height:50vh}}}}
</style></head><body><a href="/">All cases</a> · <strong>{case}</strong> · approved route: {route}
 · status: {_escape(state['status'])} · revision: {_escape(state['revision'])}
<h1>Semantic reference preparation</h1><p>Human annotation only. Empty fields are not valid evidence.
Do not invent commands, arguments, constraints or hypothetical answers.</p>{notice}
<p><a href="/case/{case}/latest">Load latest ledger revision (without overwriting saved draft)</a></p>
<main><div><h2>Locked source inputs</h2>{cards}</div><div><h2>Editable, unverified draft</h2>
<details><summary>Reference editing guide</summary><p>Fill the intended goal and ordered actions.
Each action needs a capability identifier, typed grounded arguments and any constraints.
Use source pointers such as <code>instruction</code>, <code>scene</code>,
<code>dialogue/0</code> and <code>capabilities</code>; the quoted evidence
claims must identify the exact supporting text.</p>
<p>For ambiguous cases, list critical unresolved fields, the clarification question
and separately simulated answer branches (maximum five turns). The initial
reference must not contain a future reply. Enter explicit human decisions on
dialogue relevance and linked dependencies. Leave unsupported facts unresolved,
never invent preferences or execution requirements.</p></details>
<form method="post" action="/case/{case}">
<input type="hidden" name="csrf" value="{_escape(token)}">
<textarea name="draft_json" spellcheck="false" aria-label="Draft JSON">{_escape(draft_text)}</textarea>
<p><label>Actual human actor (preparer, adopter, reviewer, approver) <input name="actor" autocomplete="off" maxlength="120"></label>
<label>Provenance <select name="provenance"><option value="human">Human-authored</option>
<option value="model_candidate">Model-assisted candidate</option></select></label></p>
<button name="action" value="save" type="submit">Save draft locally</button>
<button name="action" value="validate" type="submit">Validate structure</button>
<button name="action" value="submit" type="submit">Submit to review ledger</button>
<hr><label>Actual human review notes <textarea name="notes" aria-label="Human review notes"></textarea></label>
<button name="action" value="adopt" type="submit">Adopt model candidate</button>
<button name="action" value="verify_yes" type="submit">Verify reference</button>
<button name="action" value="verify_no" type="submit">Record disagreement</button>
<button name="action" value="approve" type="submit">Final approval</button>
</form><p>Saving edits only the local draft. Submitting requires an actual preparer identity,
validates the full reference and creates a tamper-evident ledger event. A separate person must verify it.
Review actions operate only on the exact current ledger reference, not unsaved edits.
A human reviewer must read the context and provide substantive notes. Do not impersonate a reviewer.</p>
</div></main></body></html>'''


def index_page(states):
    rows = []
    for state in states:
        case = _escape(state["record_id"])
        rows.append(f'<tr><td><a href="/case/{case}">{case}</a></td>'
                    f'<td>{_escape(state["approved_route"]["terminal_strategy"])}</td>'
                    f'<td>{_escape(state["status"])}</td></tr>')
    return ('''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Reference preparation queue</title><style>body{font:16px system-ui;max-width:950px;margin:30px auto}
td,th{padding:8px 20px;border-bottom:1px solid #aaa;text-align:left}</style>
<h1>Reference preparation queue</h1><p>Human annotation. No Gemini calls and no released gold.</p>
<table><thead><tr><th>Case</th><th>Locked route</th><th>Review status</th></tr></thead><tbody>'''
            + "".join(rows) + "</tbody></table></html>")
