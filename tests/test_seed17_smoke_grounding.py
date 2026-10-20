"""Invented smoke qualification: unavailable answers must never be asserted."""
import unittest
from research.seed17_gate import synthetic_smoke_grounding_valid
from research.seed17_smoke_fixture import fixture


class SmokeGroundingTests(unittest.TestCase):
    def setUp(self):
        _, release = fixture()
        self.steps = release["rows"][0]["reference"]["hypothetical_answer_branches"][0]["turns"]

    def rows(self):
        result = []
        for turn in range(3):
            arguments = {"object": {"type": "string", "value": "blue cup", "evidence": ["scene"]}}
            for step in self.steps[:turn]:
                arguments[step["field"]] = {"type": "string", "value": step["answer"], "evidence": ["dialogue"]}
            result.append({"turn": turn, "task": {"actions": [{"action_id": "a1", "capability_id": "move",
                "arguments": arguments, "constraints": []}], "unresolved": [
                {"field": step["field"], "critical": True, "reason": "Not yet supplied"} for step in self.steps[turn:]]}})
        return result

    def test_correct_partial_tasks_and_empty_early_actions_qualify(self):
        rows = self.rows()
        self.assertTrue(synthetic_smoke_grounding_valid(rows, self.steps))
        rows[0]["task"]["actions"] = []
        rows[1]["task"]["actions"] = []
        self.assertTrue(synthetic_smoke_grounding_valid(rows, self.steps))

    def test_fabricated_defaults_and_premature_visible_option_fail(self):
        for turn, field, value in ((0,"time","now"),(0,"destination","Shelf A"),(1,"time","09:00")):
            rows = self.rows()
            rows[turn]["task"]["actions"][0]["arguments"][field] = {
                "type":"string", "value":value, "evidence":["scene"]}
            self.assertFalse(synthetic_smoke_grounding_valid(rows, self.steps))

    def test_released_value_must_match_answer_and_cite_dialogue(self):
        for turn, field, value, evidence in ((1,"destination","Shelf B",["dialogue"]),
                (2,"time","now",["dialogue"]),(1,"destination","Shelf A",["scene"]),
                (2,"time","09:00","dialogue")):
            rows = self.rows()
            rows[turn]["task"]["actions"][0]["arguments"][field].update(value=value,evidence=evidence)
            self.assertFalse(synthetic_smoke_grounding_valid(rows, self.steps))

    def test_critical_unresolved_field_cannot_be_asserted_after_release(self):
        rows = self.rows()
        rows[1]["task"]["unresolved"].append({"field":"destination","critical":True})
        self.assertFalse(synthetic_smoke_grounding_valid(rows, self.steps))

    def test_unknown_capability_argument_object_type_or_duplicate_action_fail(self):
        changes = [lambda a: a.update(capability_id="clarify"),
            lambda a: a["arguments"].update(speed={"type":"string","value":"fast","evidence":["scene"]}),
            lambda a: a["arguments"]["object"].update(value="red cup"),
            lambda a: a["arguments"]["object"].update(type="object")]
        for change in changes:
            rows = self.rows(); change(rows[0]["task"]["actions"][0])
            self.assertFalse(synthetic_smoke_grounding_valid(rows, self.steps))
        rows = self.rows()
        rows[0]["task"]["actions"] *= 2
        self.assertFalse(synthetic_smoke_grounding_valid(rows, self.steps))

    def test_malformed_shapes_fail_closed_without_exceptions(self):
        for rows in (None, {}, [], [{"turn":0}], self.rows()[:2]):
            self.assertFalse(synthetic_smoke_grounding_valid(rows, self.steps))
        for value in (None, [], "bad", {"unknown":"bad"}):
            rows = self.rows(); rows[0]["task"]["actions"][0]["arguments"]["object"] = value
            self.assertFalse(synthetic_smoke_grounding_valid(rows, self.steps))
        for steps in (None, {}, [], [{"field":"time"}]):
            self.assertFalse(synthetic_smoke_grounding_valid(self.rows(), steps))


if __name__ == "__main__":
    unittest.main()
