"""Synthetic-only local HTTP integration tests; never read protected cases."""
import copy
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unittest

from research.annotation_workbench import draft_envelope
from tests.test_reference_schema import example
from tools.serve_annotations import make_handler


class FakeStore:
    def __init__(self, root):
        self.root = root
        self.events = []
        self.state = {"record_id": "SYNTHETIC-771", "source": {
            "record_id": "SYNTHETIC-771", "command": "Move the blue cup to shelf A.",
            "scene_context": "A blue cup is on the desk. <untrusted>", "dialogue_history": [],
            "capability_context": "move(object, destination) moves an object to a location."},
            "approved_route": {"record_id": "SYNTHETIC-771", "terminal_strategy": "execute",
                               "strategy_sequence": ["execute"]},
            "status": "WAITING_FOR_PREPARATION", "reference": None, "revision": 0, "head": "first"}

    def show(self, case):
        if case != self.state["record_id"]:
            raise ValueError("invalid case")
        return copy.deepcopy(self.state)

    def list_cases(self):
        return [self.show(self.state["record_id"])]

    def prepare(self, case, ref, actor, *, provenance, expected_head):
        if expected_head != self.state["head"] or self.state["revision"]:
            raise ValueError("stale")
        self.events.append((actor, provenance))
        self.state.update(reference=ref, revision=1, head="second", status="CANDIDATE")
        return self.show(case)

    revise = prepare


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()
        self.store = FakeStore(self.root)
        self.token = "synthetic-test-token"
        handler = make_handler(self.store, port=0, drafts_dir=self.root / "drafts", token=self.token)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = server.server_port
        server.server_close()
        handler = make_handler(self.store, port=self.port, drafts_dir=self.root / "drafts", token=self.token)
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.worker = Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.temp.cleanup()

    def url(self, path, *, data=None, override_token=None, actor="", action="save", extra_headers=None):
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if extra_headers:
            headers.update(extra_headers)
        if data is not None:
            form = {"csrf": self.token if override_token is None else override_token,
                    "draft_json": data, "actor": actor, "action": action, "provenance": "human"}
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            request = Request(self.base + path, data=urlencode(form).encode(), headers=headers, method="POST")
        else:
            request = Request(self.base + path, headers=headers)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, response.read().decode()
        except HTTPError as exc:
            return exc.code, exc.read().decode()

    def valid_json(self):
        envelope = draft_envelope(self.store.show("SYNTHETIC-771"))
        reference, _, _ = example()
        reference["record_id"] = "SYNTHETIC-771"
        envelope["reference"] = reference
        return json.dumps(envelope)

    def test_html_escapes_source_text(self):
        status, body = self.url("/case/SYNTHETIC-771")
        self.assertEqual(status, 200)
        self.assertIn("&lt;untrusted&gt;", body)
        self.assertNotIn("<untrusted>", body)
        self.assertIn("UNVERIFIED_HUMAN_EDITABLE_DRAFT", body)
        self.assertIn("/latest", body)

    def test_save_only_draft_without_human_identity(self):
        status, body = self.url("/case/SYNTHETIC-771", data=self.valid_json())
        self.assertEqual(status, 200)
        self.assertIn("Unverified draft saved", body)
        self.assertFalse(self.store.events)
        self.assertTrue((self.root / "drafts/SYNTHETIC-771.json").exists())

    def test_submit_requires_actor_and_never_approves(self):
        value = self.valid_json()
        self.assertEqual(self.url("/case/SYNTHETIC-771", data=value, action="submit")[0], 422)
        status, body = self.url("/case/SYNTHETIC-771", data=value, actor="real-preparer", action="submit")
        self.assertEqual(status, 200)
        self.assertIn("Not approved or gold", body)
        self.assertEqual(self.store.events, [("real-preparer", "human")])
        self.assertEqual(self.store.state["status"], "CANDIDATE")
        self.assertEqual(self.url("/case/SYNTHETIC-771", data=value, actor="real-preparer", action="submit")[0], 422)
        self.assertEqual(self.url("/case/SYNTHETIC-771/latest")[0], 200)

    def test_csrf_and_origin_rejected(self):
        self.assertEqual(self.url("/case/SYNTHETIC-771", data=self.valid_json(), override_token="forged")[0], 403)
        self.assertEqual(self.url("/case/SYNTHETIC-771", data=self.valid_json(),
                                  extra_headers={"Origin": "https://evil.example"})[0], 403)
        self.assertFalse(self.store.events)

    def test_reject_forged_route_and_duplicate_json(self):
        value = json.loads(self.valid_json())
        value["reference"]["author_approved_route"] = "clarify"
        self.assertEqual(self.url("/case/SYNTHETIC-771", data=json.dumps(value))[0], 422)
        duplicate = self.valid_json().replace('"record_id": "SYNTHETIC-771",',
                    '"record_id": "SYNTHETIC-771", "record_id": "SYNTHETIC-771",', 1)
        self.assertEqual(self.url("/case/SYNTHETIC-771", data=duplicate)[0], 422)

    def test_empty_skeleton_is_not_gold(self):
        from research.annotation_workbench import validate_envelope
        state = self.store.show("SYNTHETIC-771")
        with self.assertRaises(ValueError):
            validate_envelope(draft_envelope(state), state)
        self.assertFalse(self.store.events)


if __name__ == "__main__":
    unittest.main()
