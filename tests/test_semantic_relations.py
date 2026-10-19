"""Synthetic positive, negative and adversarial Sarathy-inspired graph checks."""
import copy
import unittest
from research.semantic_relations import build_relationship_graph, compare_relationship_graphs

CASE = {"record_id": "SYNTHETIC-991", "instruction": "Move the blue cup twice, first to shelf A.",
        "scene": "Blue cup on table, shelf A nearby.", "dialogue": [],
        "capabilities": "move(object, destination)"}


def task():
    return {"intended_goal": "Move the blue cup twice",
            "actions": [
                {"action_id": "a1", "capability_id": "move",
                 "arguments": {"object": {"type": "object", "value": "blue cup", "evidence": ["instruction"]},
                               "destination": {"type": "location", "value": "shelf A", "evidence": ["instruction"]}},
                 "constraints": []},
                {"action_id": "a2", "capability_id": "move",
                 "arguments": {"object": {"type": "object", "value": "blue cup", "evidence": ["scene"]},
                               "destination": {"type": "location", "value": "shelf A", "evidence": ["scene"]}},
                 "constraints": []}],
            "unresolved": [],
            "dependencies": [
                {"source": "/actions/0/arguments/object", "target": "/actions/1/arguments/object", "relation": "same_value"},
                {"source": "/actions/0", "target": "/actions/1", "relation": "before"}],
            "readiness": "ACTION_READY", "clarification_question": None}


class SarathyGraphTests(unittest.TestCase):
    def projection(self, value=None, **kw):
        return build_relationship_graph(task() if value is None else value, CASE, **kw)

    def test_projection_preserves_original_schema_and_unmodified_task(self):
        t = task()
        initial = copy.deepcopy(t)
        graph = self.projection(t)
        self.assertEqual(t, initial)
        self.assertEqual(len(graph["cpc"]["actions"]), 2)
        self.assertEqual(len(graph["cpc"]["dependencies"]), 2)
        self.assertEqual(len(graph["cpc"]["goal_action_links"]), 2)
        self.assertEqual(len(graph["spc"]["argument_referents"]), 4)
        self.assertEqual(graph["semantic_correctness"], "NOT_COMPUTED")

    def test_identical_graphs_match_without_claiming_semantic_correctness(self):
        ref = self.projection()
        report = compare_relationship_graphs(ref, self.projection())
        self.assertTrue(report["cpc_action_structure_equal"])
        self.assertTrue(report["cpc_goal_action_link_coverage"])
        self.assertTrue(report["spc_binding_structure_equal"])
        self.assertTrue(report["dependency_complete"])
        self.assertTrue(report["goal_literal_equal"])
        self.assertEqual(report["semantic_correctness"], "NOT_COMPUTED")

    def test_missing_dependency_detected(self):
        t = task()
        t["dependencies"].pop()
        report = compare_relationship_graphs(self.projection(), self.projection(t))
        self.assertFalse(report["dependency_complete"])
        self.assertEqual(report["missing_dependencies"][0]["relation"], "before")

    def test_distinct_referents_even_with_same_surface_word(self):
        ref_bind = {"/actions/0/arguments/object": "cup-001",
                    "/actions/1/arguments/object": "cup-001"}
        pred_bind = {"/actions/0/arguments/object": "cup-001",
                     "/actions/1/arguments/object": "cup-999"}
        ref = self.projection(referent_bindings=ref_bind)
        pred = self.projection(referent_bindings=pred_bind)
        report = compare_relationship_graphs(ref, pred)
        self.assertFalse(report["spc_binding_structure_equal"])
        self.assertTrue(report["dependency_complete"])
        self.assertTrue(report["requires_independent_semantic_review"])

    def test_explicit_alignment_changes_node_correspondence_not_goal_truth(self):
        graph = self.projection()
        report = compare_relationship_graphs(graph, graph, action_alignment={0: 1, 1: 0})
        self.assertFalse(report["action_order_identical"])
        self.assertFalse(report["dependency_complete"])

    def test_invalid_binding_paths_or_non_entity_types_rejected(self):
        for bindings in (
            {"/actions/99/arguments/object": "x"},
            {"/actions/0/arguments/missing": "x"},
            {"/actions/0": "object-A"},
            {"/actions/0/arguments/object": ""},
            {"/actions/00/arguments/object": "x"},
        ):
            with self.subTest(bindings=bindings), self.assertRaises(ValueError):
                self.projection(referent_bindings=bindings)

    def test_duplicate_relation_and_cycle_detected_without_changing_validation(self):
        t = task()
        t["dependencies"].append(copy.deepcopy(t["dependencies"][0]))
        t["dependencies"].extend([
            {"source": "/actions/0", "target": "/actions/1", "relation": "depends_on"},
            {"source": "/actions/1", "target": "/actions/0", "relation": "depends_on"}])
        projection = self.projection(t)
        codes = {entry["code"] for entry in projection["relationship_issues"]}
        self.assertIn("DUPLICATE_RELATION", codes)
        self.assertIn("CYCLIC_ACTION_RELATIONSHIP", codes)
        self.assertEqual(projection["semantic_correctness"], "NOT_COMPUTED")

    def test_depends_on_prerequisite_direction_avoids_false_cycles(self):
        t = task()
        # Action 1 is before action 2, and action 2 depends on action 1.
        # Both mean 1 precedes 2, not a cycle.
        t["dependencies"].append({"source": "/actions/1", "target": "/actions/0",
                                  "relation": "depends_on"})
        projection = self.projection(t)
        self.assertNotIn("CYCLIC_ACTION_RELATIONSHIP",
                         [entry["code"] for entry in projection["relationship_issues"]])

    def test_conflicting_human_provided_bindings_flagged(self):
        graph = self.projection(referent_bindings={
            "/actions/0/arguments/object": "instance-A",
            "/actions/1/arguments/object": "instance-B"})
        self.assertIn("CONFLICTING_REFERENT_BINDINGS",
                      [issue["code"] for issue in graph["relationship_issues"]])

    def test_bad_alignment_and_repeated_mapping_rejected(self):
        graph = self.projection()
        for mapping in ({0: 0, 1: 0}, {0: 5, 1: 1}, {0: 0}, {0: "0", 1: 1}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                compare_relationship_graphs(graph, graph, action_alignment=mapping)

    def test_invented_evidence_rejected_before_projection(self):
        t = task()
        t["actions"][0]["arguments"]["object"]["evidence"] = ["hidden_gold/0"]
        with self.assertRaises(ValueError):
            self.projection(t)


if __name__ == "__main__":
    unittest.main()
