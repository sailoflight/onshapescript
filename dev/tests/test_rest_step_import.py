"""Offline gates for the STEP import leg (plan-first, no live call).

Three things this file actually guards:

1. **No invented request fields.** Every key the planner would send, and every key
   it declares *unsent*, must exist in the vendored OpenAPI schema
   (``BTBTranslationRequestParams``), so the plan cannot drift away from the API
   it claims to implement.
2. **The refusal is explicit.** An import that cannot be transported must return a
   refusal naming the missing transport; an empty success would be the one outcome
   nobody could audit.
3. **No network.** The fake client turns any ``request()`` call into an assertion
   failure, so a "plan" that quietly sent something cannot pass this file.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from onshape_rest_api_mode import step_import  # noqa: E402

OPENAPI = ROOT / "onshape_docs" / "reference" / "raw" / "onshape-api" / "openapi.json"


@lru_cache(maxsize=1)
def _translation_schema_properties() -> set[str]:
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    schemas = spec.get("components", {}).get("schemas", {})
    schema = schemas.get("BTBTranslationRequestParams")
    if not isinstance(schema, dict):
        raise AssertionError("vendored OpenAPI no longer documents BTBTranslationRequestParams")
    return set(schema.get("properties", {}))


class _FakeClient:
    """Records the describe calls a plan made and fails on any request."""

    def __init__(self) -> None:
        self.describe_calls: list[tuple[str, str]] = []
        self.request_calls = 0

    def describe(self, method, path, body=None, query=None):
        self.describe_calls.append((method, path))
        url = "https://cad.onshape.com" + path
        headers = {"Authorization": "<REDACTED>", "Accept": "application/json;charset=UTF-8; qs=0.09"}
        return {"method": method, "url": url, "headers": headers, "body": body}

    def request(self, *args, **kwargs):  # pragma: no cover - must never run
        self.request_calls += 1
        raise AssertionError("the import leg must not send anything")


def _plan(**overrides):
    kwargs = dict(document_id="did123", workspace_id="wid456", filename="model.step")
    kwargs.update(overrides)
    return step_import.build_step_import_plan(client=_FakeClient(), **kwargs)


class SchemaCrossCheckTest(unittest.TestCase):
    def test_every_sent_field_is_documented(self):
        body = step_import.build_step_import_body(
            filename="model.step", location_element_id="eid1", location_position=0
        )
        undocumented = set(body) - _translation_schema_properties()
        self.assertEqual(undocumented, set(), f"undocumented request fields: {sorted(undocumented)}")

    def test_every_declared_unsent_field_is_documented(self):
        undocumented = set(step_import.UNSENT_FIELDS) - _translation_schema_properties()
        self.assertEqual(undocumented, set(), f"unsent list names non-schema fields: {sorted(undocumented)}")

    def test_unsent_fields_are_never_sent(self):
        body = step_import.build_step_import_body(filename="model.step")
        self.assertEqual(set(body) & set(step_import.UNSENT_FIELDS), set())

    def test_internal_fields_are_the_schemas_internal_visibility_list(self):
        spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
        schema = spec["components"]["schemas"]["BTBTranslationRequestParams"]
        internal = set(schema.get("x-BTVisibility-properties", {}))
        self.assertLessEqual(set(step_import.INTERNAL_FIELDS), internal)
        body = step_import.build_step_import_body(filename="model.step")
        self.assertEqual(set(body) & set(step_import.INTERNAL_FIELDS), set())


class BodyTest(unittest.TestCase):
    def test_defaults_match_the_contract_the_peers_agreed(self):
        body = step_import.build_step_import_body(filename="model.step")
        self.assertEqual(body["formatName"], "STEP")
        self.assertEqual(body["unit"], "MILLIMETER")
        self.assertTrue(body["storeInDocument"])
        self.assertTrue(body["translate"])
        self.assertFalse(body["yAxisIsUp"])
        self.assertFalse(body["flattenAssemblies"])
        self.assertFalse(body["onePartPerDoc"])
        self.assertFalse(body["allowFaultyParts"])
        self.assertNotIn("locationElementId", body)
        self.assertNotIn("locationPosition", body)

    def test_location_fields_only_when_asked(self):
        body = step_import.build_step_import_body(
            filename="model.step", location_element_id="eid9", location_position=2
        )
        self.assertEqual(body["locationElementId"], "eid9")
        self.assertEqual(body["locationPosition"], 2)

    def test_filename_must_be_a_simple_step_file(self):
        for bad in ("model", "model.stl", "a/b.step", "../model.step", "", "model.step.exe"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    step_import.build_step_import_body(filename=bad)

    def test_filename_accepts_uppercase_extension(self):
        body = step_import.build_step_import_body(filename="MODEL.STEP")
        self.assertEqual(body["formatName"], "STEP")

    def test_format_and_unit_are_enumerated(self):
        with self.assertRaises(ValueError):
            step_import.build_step_import_body(filename="model.step", format_name="IGES")
        with self.assertRaises(ValueError):
            step_import.build_step_import_body(filename="model.step", unit="PARSEC")

    def test_identifiers_and_positions_are_validated(self):
        with self.assertRaises(ValueError):
            step_import.build_step_import_body(filename="model.step", location_element_id="has space")
        with self.assertRaises(ValueError):
            step_import.build_step_import_body(filename="model.step", location_position=-1)


class PlanTest(unittest.TestCase):
    def test_plan_says_the_transport_is_missing(self):
        plan = _plan()
        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["operation"], "step-import")
        self.assertEqual(plan["transport"], "multipart/form-data")
        live = plan["liveExecution"]
        self.assertFalse(live["available"])
        self.assertEqual(live["reason"], "multipart_transport_unavailable")
        self.assertEqual(len(live["options"]), 2)
        self.assertTrue(any("multipart" in option for option in live["options"]))
        self.assertTrue(any("browser" in option for option in live["options"]))

    def test_request_inventory_and_budget(self):
        plan = _plan(max_polls=2)
        self.assertEqual(plan["estimatedRequests"], 4)
        self.assertEqual(plan["maxRequests"], 4)
        post, poll, verify = plan["requests"]
        self.assertEqual(post["method"], "POST")
        self.assertEqual(post["url"].rsplit("/", 2)[-2:], ["w", "wid456"])
        self.assertEqual(post["contentType"], "multipart/form-data")
        self.assertEqual(post["maxExecutions"], 1)
        self.assertFalse(post["implicitRetry"])
        self.assertEqual(poll["method"], "GET")
        self.assertEqual(poll["maxExecutions"], 2)
        self.assertIn("<translationId from POST>", poll["url"])
        self.assertEqual(verify["method"], "GET")
        self.assertIn("/elements", verify["url"])
        self.assertEqual(plan["pollPolicy"]["states"], ["ACTIVE", "DONE", "FAILED"])
        self.assertFalse(plan["pollPolicy"]["getRetry"])
        self.assertFalse(plan["pollPolicy"]["repeatPost"])

    def test_parts_carry_the_binary_file_first(self):
        plan = _plan()
        parts = plan["requests"][0]["bodyParts"]
        self.assertEqual(parts[0], {
            "name": "file",
            "kind": "binary",
            "filename": "model.step",
            "contentType": "model/step",
        })
        text = {p["name"]: p["value"] for p in parts[1:]}
        self.assertEqual(text["formatName"], "STEP")
        self.assertEqual(text["unit"], "MILLIMETER")
        self.assertEqual(set(text), set(plan["requests"][0]["body"]))
        self.assertEqual([p["name"] for p in parts[1:]], sorted(text))

    def test_credentials_are_never_in_the_plan(self):
        plan = _plan()
        blob = json.dumps(plan)
        self.assertIn("<REDACTED>", plan["requests"][0]["headers"]["Authorization"])
        for forbidden in ("Bearer ", "accessKey", "secretKey", "Basic "):
            self.assertNotIn(forbidden, blob)

    def test_declarations_are_the_receivers(self):
        plan = _plan(unit="MILLIMETER", y_axis_is_up=True, one_part_per_doc=True)
        declarations = plan["declarations"]
        self.assertEqual(declarations["unit"], "MILLIMETER")
        self.assertEqual(declarations["declaredBy"], "receiver")
        self.assertTrue(declarations["yAxisIsUp"])
        self.assertTrue(declarations["onePartPerDoc"])

    def test_source_facts_are_measured_locally_without_claiming_stability(self):
        payload = b"ISO-10303-21;\nEND-ISO-10303-21;\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.step"
            path.write_bytes(payload)
            plan = _plan(source_path=path)
        source = plan["artifactContract"]["source"]
        self.assertEqual(source["byteCount"], len(payload))
        self.assertEqual(source["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertFalse(source["sha256Stable"])
        self.assertIn("download integrity", source["sha256Note"])

    def test_missing_or_wrong_suffix_source_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.step"
            with self.assertRaises(FileNotFoundError):
                _plan(source_path=missing)
            wrong = Path(tmp) / "model.stl"
            wrong.write_bytes(b"solid\n")
            with self.assertRaises(ValueError):
                _plan(source_path=wrong)

    def test_plan_is_json_serializable(self):
        json.dumps(_plan(max_polls=1, location_element_id="eid1", location_position=0))

    def test_bounds_and_identifier_rules(self):
        for bad in (0, 6):
            with self.subTest(max_polls=bad):
                with self.assertRaises(ValueError):
                    _plan(max_polls=bad)
        with self.assertRaises(ValueError):
            _plan(media_type="step")
        with self.assertRaises(ValueError):
            _plan(document_id="not an id")
        with self.assertRaises(ValueError):
            _plan(workspace_id="")

    def test_unsent_fields_are_reported_with_reasons(self):
        plan = _plan()
        self.assertIn("uploadId", plan["unverifiedFields"])
        self.assertTrue(all(plan["unverifiedFields"].values()))


class ImportTest(unittest.TestCase):
    def test_default_is_a_plan(self):
        result = step_import.import_step(
            document_id="did123", workspace_id="wid456", filename="model.step", client=_FakeClient()
        )
        self.assertTrue(result["dryRun"])

    def test_live_attempt_refuses_and_sends_nothing(self):
        client = _FakeClient()
        result = step_import.import_step(
            document_id="did123",
            workspace_id="wid456",
            filename="model.step",
            dry_run=False,
            client=client,
        )
        self.assertFalse(result["imported"])
        self.assertEqual(result["requestsConsumed"], 0)
        self.assertEqual(result["reason"], "multipart_transport_unavailable")
        self.assertEqual(result["requiredTransport"], "multipart/form-data")
        self.assertIn("plan", result)
        self.assertEqual(client.request_calls, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
