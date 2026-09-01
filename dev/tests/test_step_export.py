from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from onshape_rest_api_mode.step_export import (
    build_step_export_body,
    build_step_export_plan,
    export_step,
)


class FakeClient:
    base_url = "https://cad.onshape.com"

    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = []

    def describe(self, method, path, body=None, query=None):
        return {
            "method": method,
            "url": self.base_url + path,
            "headers": {"Authorization": "<REDACTED>"},
            "body": body,
        }

    def request(self, method, path, body=None, query=None, timeout=180, retry_get=True):
        self.calls.append({
            "method": method,
            "path": path,
            "body": body,
            "retry_get": retry_get,
        })
        if not self.responses:
            raise AssertionError("unexpected request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class StepExportTest(unittest.TestCase):
    def _ids(self):
        return {
            "document_id": "doc1",
            "wv": "w",
            "wvid": "workspace1",
            "element_id": "element1",
        }

    def test_body_is_canonical_fdm_step_export(self):
        body = build_step_export_body()
        self.assertEqual(body["stepVersionString"], "AP242")
        self.assertEqual(body["stepUnit"], "MILLIMETER")
        self.assertTrue(body["grouping"])
        self.assertFalse(body["storeInDocument"])
        self.assertFalse(body["triggerAutoDownload"])
        with self.assertRaisesRegex(ValueError, "simple .step filename"):
            build_step_export_body(destination_name="../escape.step")

    def test_dry_run_has_bounded_post_poll_download_plan(self):
        plan = build_step_export_plan(**self._ids(), max_polls=3, client=FakeClient())
        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["estimatedRequests"], 5)
        self.assertEqual(plan["requests"][0]["method"], "POST")
        self.assertTrue(plan["requests"][0]["url"].endswith("/export/step"))
        self.assertEqual(plan["requests"][1]["maxExecutions"], 3)
        self.assertFalse(plan["requests"][1]["implicitRetry"])
        self.assertEqual(plan["requests"][2]["maxExecutions"], 1)
        self.assertNotIn("doc1", str(plan["requests"][0]["headers"]))

    def test_resume_plan_never_repeats_post(self):
        plan = build_step_export_plan(
            **self._ids(),
            translation_id="translation1",
            max_polls=2,
            client=FakeClient(),
        )
        self.assertTrue(plan["resume"])
        self.assertEqual(plan["estimatedRequests"], 3)
        self.assertEqual([request["method"] for request in plan["requests"]], ["GET", "GET"])
        self.assertTrue(plan["requests"][0]["url"].endswith("/translations/translation1"))

    def test_export_posts_once_polls_once_downloads_once(self):
        client = FakeClient([
            {"id": "translation1", "requestState": "ACTIVE"},
            {
                "id": "translation1",
                "requestState": "DONE",
                "documentId": "doc1",
                "resultExternalDataIds": ["external1"],
            },
            b"ISO-10303-21;\nEND-ISO-10303-21;\n",
        ])
        sleeps = []
        with tempfile.TemporaryDirectory() as tmp:
            result = export_step(
                **self._ids(),
                max_polls=2,
                poll_interval_seconds=5,
                client=client,
                output_root=Path(tmp),
                sleeper=sleeps.append,
            )
            step_path = Path(result["step"]["path"])
            self.assertTrue(step_path.is_file())
            self.assertEqual(step_path.parent.name, "translation1")
            step_manifest = json.loads(Path(result["stepManifestPath"]).read_text(encoding="utf-8"))
        self.assertTrue(result["exported"])
        self.assertEqual(step_manifest["translationId"], "translation1")
        self.assertEqual(step_manifest["artifact"]["path"], "model.step")
        self.assertEqual(step_manifest["artifact"]["sha256"], result["step"]["sha256"])
        self.assertEqual(result["requestsConsumed"], 3)
        self.assertEqual(result["step"]["units"], "mm")
        self.assertEqual(sleeps, [5])
        self.assertEqual([call["method"] for call in client.calls], ["POST", "GET", "GET"])
        self.assertTrue(client.calls[1]["retry_get"] is False)
        self.assertTrue(client.calls[2]["retry_get"] is False)

    def test_poll_budget_returns_resumable_state_without_reposting(self):
        client = FakeClient([
            {"requestState": "ACTIVE"},
            {"requestState": "ACTIVE"},
        ])
        result = export_step(
            **self._ids(),
            translation_id="translation1",
            max_polls=2,
            poll_interval_seconds=5,
            client=client,
            sleeper=lambda _: None,
        )
        self.assertFalse(result["exported"])
        self.assertTrue(result["resumable"])
        self.assertEqual(result["translationId"], "translation1")
        self.assertEqual([call["method"] for call in client.calls], ["GET", "GET"])

    def test_failed_or_ambiguous_translation_fails_closed(self):
        failed = FakeClient([{"requestState": "FAILED", "failureReason": "fixture"}])
        with self.assertRaisesRegex(RuntimeError, "fixture"):
            export_step(
                **self._ids(),
                translation_id="translation1",
                max_polls=1,
                poll_interval_seconds=5,
                client=failed,
                sleeper=lambda _: None,
            )
        ambiguous = FakeClient([{"requestState": "DONE", "resultExternalDataIds": []}])
        with self.assertRaisesRegex(ValueError, "exactly one"):
            export_step(
                **self._ids(),
                translation_id="translation1",
                max_polls=1,
                poll_interval_seconds=5,
                client=ambiguous,
                sleeper=lambda _: None,
            )


if __name__ == "__main__":
    unittest.main()
