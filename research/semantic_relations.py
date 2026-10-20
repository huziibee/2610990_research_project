"""Evaluator-side CPC/SPC-inspired relationship diagnostics (Sarathy et al.).

Not Sarathy's DIARC semantic parser or information structure. Outputs are
structural comparison candidates only; no semantic correctness is inferred.
Never import into model prompts or modify the primary task schema.
"""
from __future__ import annotations
import json
from research.task_schema import _pointer, validate_task

RELATIONS = frozenset(("same_value", "before", "depends_on"))


def _reference_slot(path):
    """Extract a canonical action/argument address from a validated JSON pointer."""
    parts = path.split("/")
    if (len(parts) == 3 and parts[:2] == ["", "actions"] and parts[2].isdecimal()):
        return ("action", int(parts[2]), None)
    if (len(parts) == 5 and parts[:2] == ["", "actions"] and parts[2].isdecimal()
            and parts[3] == "arguments" and parts[4]):
        field = parts[4].replace("~1", "/").replace("~0", "~")
        return ("argument", int(parts[2]), field)
    raise ValueError("Relationship endpoints must name whole actions or typed arguments")


def _canonical_id(kind, value):
    return json.dumps([kind, value], ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def build_relationship_graph(task, model_input, *, referent_bindings=None, capability_catalog=None):
    """Project an existing validated task into separate CPC/SPC-inspired graphs.

    referent_bindings maps existing argument JSON pointers to externally
    *reviewed* referent IDs. Unprovided bindings stay literal and unverified.
    This is a projection, not entity resolution or semantic parsing.
    """
    # This evaluator must receive contradictory/cyclic edges so it can report
    # them as measured issues. Keep schema and pointer checks, but leave
    # dependency-consistency scoring to the graph diagnostics below.
    validate_task(task, model_input, capability_catalog=capability_catalog,
                  check_dependency_consistency=False)
    bindings = {} if referent_bindings is None else referent_bindings
    if not isinstance(bindings, dict):
        raise ValueError("Referent bindings must be a dictionary")
    for path, referent in bindings.items():
        if not isinstance(path, str) or not isinstance(referent, str) or not referent.strip():
            raise ValueError("Referent bindings require nonempty canonical entity IDs")
        addr = _reference_slot(path)
        if addr[0] != "argument":
            raise ValueError("Referent bindings must target argument objects")
        value = _pointer(task, path)
        if not isinstance(value, dict) or not {"type", "value", "evidence"} <= set(value):
            raise ValueError("Referent binding target must be a typed task argument")
        if value["type"] not in ("object", "location"):
            raise ValueError("Only object/location arguments receive external referent IDs")
    actions = []
    supplemental = []
    for index, action in enumerate(task["actions"]):
        slots = []
        for name, arg in sorted(action["arguments"].items()):
            path = "/actions/" + str(index) + "/arguments/" + name.replace("~", "~0").replace("/", "~1")
            supplied = path in bindings
            canonical = (bindings[path] if supplied else
                         _canonical_id(arg["type"], arg["value"]))
            slots.append({"field": name, "type": arg["type"], "referent": canonical})
            supplemental.append({"action": index, "field": name, "type": arg["type"],
                                 "referent": canonical, "externally_bound": supplied})
        actions.append({"index": index, "capability": action["capability_id"],
                        "arguments": slots, "constraints": sorted(action["constraints"])})
    relations = []
    for dep in task["dependencies"]:
        source = _reference_slot(dep["source"])
        target = _reference_slot(dep["target"])
        if dep["relation"] not in RELATIONS:
            raise ValueError("Invalid relationship")
        if dep["relation"] == "same_value" and (source[0] != "argument" or target[0] != "argument"):
            raise ValueError("same_value requires argument endpoints")
        if dep["relation"] == "before" and (source[0] != "action" or target[0] != "action"):
            raise ValueError("before requires action endpoints")
        relations.append({"relation": dep["relation"], "source": source, "target": target})
    # Diagnostic checks are separate from model-output validity and never
    # turn unverified referent labels into ground truth.
    relationship_issues = []
    seen_relations = set()
    directed_edges = []
    slot_lookup = {(slot["action"], slot["field"]): slot["referent"] for slot in supplemental}
    for relation in relations:
        key = (relation["relation"], relation["source"], relation["target"])
        if key in seen_relations:
            relationship_issues.append({"code": "DUPLICATE_RELATION", "relation": relation["relation"]})
        seen_relations.add(key)
        if relation["relation"] == "same_value":
            lhs = (relation["source"][1], relation["source"][2])
            rhs = (relation["target"][1], relation["target"][2])
            if slot_lookup[lhs] != slot_lookup[rhs]:
                relationship_issues.append({"code": "CONFLICTING_REFERENT_BINDINGS",
                                            "relation": "same_value"})
        elif relation["source"][0] == relation["target"][0] == "action":
            # 'A depends_on B' means B must precede A, while 'A before B'
            # means A must precede B. Normalize both to precedence arrows.
            left, right = relation["source"][1], relation["target"][1]
            directed_edges.append((right, left) if relation["relation"] == "depends_on"
                                  else (left, right))
    adjacency = {i: set() for i in range(len(actions))}
    for left, right in directed_edges:
        adjacency[left].add(right)
    visiting, completed = set(), set()
    def cyclic(node):
        if node in visiting:
            return True
        if node in completed:
            return False
        visiting.add(node)
        if any(cyclic(next_node) for next_node in adjacency[node]):
            return True
        visiting.remove(node)
        completed.add(node)
        return False
    if any(cyclic(i) for i in adjacency if i not in completed):
        relationship_issues.append({"code": "CYCLIC_ACTION_RELATIONSHIP"})
    # A repeated referent ID denotes a shared binding, not proven object identity.
    return {"diagnostic_kind": "SARATHY_INSPIRED_STRUCTURAL_PROJECTION",
            "semantic_correctness": "NOT_COMPUTED",
            "cpc": {"goal_literal": task["intended_goal"], "actions": actions,
                    "goal_action_links": [{"source": "goal", "target_action": i,
                                           "relation": "PROPOSED_REALIZATION"}
                                          for i in range(len(actions))],
                    "dependencies": sorted(relations, key=lambda r: str(r))},
            "spc": {"argument_referents": supplemental},
            "unresolved_fields": sorted(item["field"] for item in task["unresolved"] if item["critical"]),
            "external_binding_count": len(bindings),
            "relationship_issues": relationship_issues,
            "automated_reference_resolution": False,
            "requires_independent_semantic_review": True}


def compare_relationship_graphs(reference, prediction, *, action_alignment=None):
    """Compare projections using explicit action alignment; never claim intent truth.

    An action alignment maps predicted integer positions to reference positions.
    Its provenance must be adjudicated independently. Otherwise positions are
    compared literally. Ordering is a separate diagnostic.
    """
    ref, pred = reference["cpc"], prediction["cpc"]
    if reference.get("diagnostic_kind") != "SARATHY_INSPIRED_STRUCTURAL_PROJECTION" or prediction.get("diagnostic_kind") != "SARATHY_INSPIRED_STRUCTURAL_PROJECTION":
        raise ValueError("Only validated structural projections may be compared")
    num_ref, num_pred = len(ref["actions"]), len(pred["actions"])
    mapping = ({index: index for index in range(num_pred)} if action_alignment is None
               else action_alignment)
    if (not isinstance(mapping, dict) or set(mapping) != set(range(num_pred))
            or any(type(k) is not int or type(v) is not int for k, v in mapping.items())
            or len(set(mapping.values())) != len(mapping)
            or any(v < 0 or v >= num_ref for v in mapping.values())):
        raise ValueError("Alignment must be an injective mapping of all predicted action positions")
    ref_actions = {row["index"]: row for row in ref["actions"]}
    aligned = []
    for row in pred["actions"]:
        new = dict(row)
        new["index"] = mapping[row["index"]]
        aligned.append(new)
    missing_actions = [row for idx, row in ref_actions.items() if row not in aligned]
    extra_actions = [row for row in aligned if row not in ref_actions.values()]
    def mapped_relation(row):
        result = dict(row)
        result["source"] = (row["source"][0], mapping[row["source"][1]], row["source"][2])
        result["target"] = (row["target"][0], mapping[row["target"][1]], row["target"][2])
        return result
    pred_relations = [mapped_relation(row) for row in pred["dependencies"]]
    ref_relations = ref["dependencies"]
    def diff(a, b):
        return [item for item in a if item not in b]
    mapped_goal_links = [{**link, "target_action": mapping[link["target_action"]]}
                         for link in pred["goal_action_links"]]
    goal_link_coverage = all(link in mapped_goal_links for link in ref["goal_action_links"])
    ref_slots = {(s["action"], s["field"], s["type"], s["referent"])
                 for s in reference["spc"]["argument_referents"]}
    pred_slots = {(mapping[s["action"]], s["field"], s["type"], s["referent"])
                  for s in prediction["spc"]["argument_referents"]}
    return {"status": "STRUCTURAL_DIAGNOSTIC_NOT_SEMANTIC_SCORE",
            "goal_literal_equal": ref["goal_literal"] == pred["goal_literal"],
            "cpc_action_structure_equal": not missing_actions and not extra_actions,
            "cpc_goal_action_link_coverage": goal_link_coverage,
            "action_order_identical": list(mapping.values()) == list(range(num_pred)),
            "spc_binding_structure_equal": ref_slots == pred_slots,
            "dependency_complete": not diff(ref_relations, pred_relations),
            "missing_dependencies": diff(ref_relations, pred_relations),
            "extra_dependencies": diff(pred_relations, ref_relations),
            "missing_actions": missing_actions, "extra_actions": extra_actions,
            "unresolved_fields_equal": reference["unresolved_fields"] == prediction["unresolved_fields"],
            "semantic_correctness": "NOT_COMPUTED",
            "requires_independent_semantic_review": True}
