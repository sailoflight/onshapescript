"""Offline proof for the Part Studio Feature List CRUD operations.

Nothing here touches the network or a live Onshape account. Three independent
kinds of evidence are combined so that a passing run means something:

1. the built request paths match the templates in the vendored OpenAPI, keyed by
   the same `operationId`;
2. the response parsers read exactly the fields those schemas declare, verified
   against a spec-derived instance rather than a hand-written body;
3. the checked-in `request.json` fixtures still equal the current builder output,
   and say plainly that they were never sent.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from onshape_rest_api_mode import feature_list, operations

ROOT = Path(__file__).resolve().parents[2]
API_SPEC = ROOT / "onshape_docs" / "reference" / "raw" / "onshape-api" / "openapi.json"
FIXTURES = ROOT / "dev" / "tests" / "fixtures" / "onshape" / "feature-list"
IDS = {"document_id": "DOCID", "workspace_id": "WKSID", "element_id": "PSID"}
STATE = {"documentId": "DOCID", "workspaceId": "WKSID", "partStudioId": "PSID"}
API_PREFIX = "/api/v9"


class FakeClient:
    """Records every request; answers `describe` exactly like the real client.

    `request` raises unless a queued response exists, so a test that forgot to
    queue one fails instead of silently sending something.
    """

    base_url = "https://cad.onshape.com"

    def __init__(self, responses=()):
        self.state = dict(STATE)
        self.responses = list(responses)
        self.calls = []

    def describe(self, method, path, body=None, query=None):
        headers = {
            "Authorization": "<REDACTED>",
            "Accept": "application/json;charset=UTF-8; qs=0.09",
        }
        if body is not None:
            headers["Content-Type"] = "application/json;charset=UTF-8; qs=0.09"
        url = self.base_url + path
        if query:
            url += "?" + "&".join(f"{k}={v}" for k, v in query.items())
        return {"method": method, "url": url, "headers": headers, "body": body}

    def request(self, method, path, body=None, query=None, timeout=180, retry_get=True):
        self.calls.append({
            "method": method,
            "path": path,
            "body": body,
            "timeout": timeout,
            "retry_get": retry_get,
        })
        if not self.responses:
            raise AssertionError("unexpected request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


_spec_cache: dict | None = None


def spec() -> dict:
    global _spec_cache
    if _spec_cache is None:
        _spec_cache = json.loads(API_SPEC.read_text(encoding="utf-8"))
    return _spec_cache


def operation(operation_id: str) -> tuple[str, str, dict]:
    for path, methods in spec()["paths"].items():
        for method, op in methods.items():
            if op.get("operationId") == operation_id:
                return method.upper(), path, op
    raise AssertionError(f"{operation_id} is not in the vendored spec")


def response_schema_name(op: dict) -> str:
    """The single response schema the parser targets, e.g. BTUpdateFeaturesCall."""
    responses = op.get("responses") or {}
    for response in responses.values():
        for media in (response.get("content") or {}).values():
            ref = (media.get("schema") or {}).get("$ref")
            if ref:
                return ref.rsplit("/", 1)[-1]
    raise AssertionError("response has no schema reference")


def _resolve(node: dict) -> dict:
    if "$ref" in node:
        return spec()["components"]["schemas"][node["$ref"].rsplit("/", 1)[-1]]
    return node


def spec_instance(schema_name: str) -> dict:
    """A minimal instance built ONLY from the schema's declared properties.

    This is what makes the parser tests meaningful: the expected body shape comes
    from the vendored spec, not from the parser author's memory.
    """
    schema = spec()["components"]["schemas"][schema_name]
    instance: dict = {}
    for prop, node in (schema.get("properties") or {}).items():
        node = _resolve(node)
        kind = node.get("type")
        if kind == "string":
            instance[prop] = f"<{prop}>"
        elif kind == "integer":
            instance[prop] = 0
        elif kind == "boolean":
            instance[prop] = False
        elif kind == "array":
            instance[prop] = []
        elif kind == "object":
            instance[prop] = {}
        else:
            instance[prop] = None
    return instance


def declared_properties(schema_name: str) -> set[str]:
    schema = spec()["components"]["schemas"][schema_name]
    return set((schema.get("properties") or {}).keys())


def declared_properties_deep(schema_name: str) -> set[str]:
    """Declared fields of a response schema plus those of its direct sub-objects,
    because a summary may legitimately lift `featureState.featureStatus`."""
    schema = spec()["components"]["schemas"][schema_name]
    declared = set((schema.get("properties") or {}).keys())
    for node in (schema.get("properties") or {}).values():
        if "$ref" in node:
            declared |= declared_properties(node["$ref"].rsplit("/", 1)[-1])
    return declared


class SpecAgreementTest(unittest.TestCase):
    """The built request must be the documented request."""

    def test_every_built_path_matches_the_vendored_spec_template(self) -> None:
        cases = {
            "updatePartStudioFeature": (
                feature_list.feature_path(**IDS, feature_id="FEATID_A"),
                {"did": "DOCID", "wid": "WKSID", "eid": "PSID", "fid": "FEATID_A"},
            ),
            "deletePartStudioFeature": (
                feature_list.feature_path(**IDS, feature_id="FEATID_A"),
                {"did": "DOCID", "wid": "WKSID", "eid": "PSID", "fid": "FEATID_A"},
            ),
            "updateRollback": (feature_list.rollback_path(**IDS), {
                "did": "DOCID", "wid": "WKSID", "eid": "PSID",
            }),
            "updateFeatures": (feature_list.updates_path(**IDS), {
                "did": "DOCID", "wid": "WKSID", "eid": "PSID",
            }),
        }
        for operation_id, (built, values) in cases.items():
            with self.subTest(operation=operation_id):
                _method, template, _op = operation(operation_id)
                expected = template
                for key, value in values.items():
                    expected = expected.replace("{" + key + "}", value)
                self.assertTrue(
                    built.startswith(API_PREFIX),
                    f"{built} must carry the versioned prefix the live features path uses",
                )
                self.assertEqual(built[len(API_PREFIX):], expected)

    def test_methods_match_the_spec(self) -> None:
        self.assertEqual(operation("updatePartStudioFeature")[0], "POST")
        self.assertEqual(operation("deletePartStudioFeature")[0], "DELETE")
        self.assertEqual(operation("updateRollback")[0], "POST")
        self.assertEqual(operation("updateFeatures")[0], "POST")

    def test_rollback_body_follows_the_prose_not_the_string_schema(self) -> None:
        """`updateRollback` declares its body as a bare `string`, which cannot be
        right for a position. The spec's own description carries the real shape,
        so the deviation is deliberate and this test pins the evidence."""
        _method, _path, op = operation("updateRollback")
        schema = op["requestBody"]["content"]
        declared = next(iter(schema.values()))["schema"]
        self.assertEqual(declared, {"type": "string"})
        description = op["description"]
        self.assertIn('{ "rollbackIndex": integer }', description)
        self.assertIn("Set to `-1`", description)
        self.assertEqual(feature_list.rollback_body(-1), {"rollbackIndex": -1})
        self.assertEqual(feature_list.rollback_body(2), {"rollbackIndex": 2})

    def test_update_features_is_the_suppression_endpoint(self) -> None:
        _method, _path, op = operation("updateFeatures")
        self.assertIn("update feature suppression attributes", op["description"])
        self.assertIn(
            "updateSuppressionAttributes",
            spec()["components"]["schemas"]["BTUpdateFeaturesCall-1748"]["properties"],
        )


class PathTest(unittest.TestCase):
    def test_paths_are_scoped_to_the_part_studio(self) -> None:
        self.assertEqual(
            feature_list.feature_list_path("d1", "w1", "e1"),
            "/api/v9/partstudios/d/d1/w/w1/e/e1/features",
        )
        self.assertEqual(
            feature_list.feature_path("d1", "w1", "e1", "f1"),
            "/api/v9/partstudios/d/d1/w/w1/e/e1/features/featureid/f1",
        )
        self.assertEqual(
            feature_list.rollback_path("d1", "w1", "e1"),
            "/api/v9/partstudios/d/d1/w/w1/e/e1/features/rollback",
        )
        self.assertEqual(
            feature_list.updates_path("d1", "w1", "e1"),
            "/api/v9/partstudios/d/d1/w/w1/e/e1/features/updates",
        )

    def test_empty_or_unsafe_segments_are_rejected(self) -> None:
        for bad in ("", "   ", None, 7):
            with self.subTest(value=bad):
                with self.assertRaisesRegex(ValueError, "non-empty string"):
                    feature_list.feature_path("d1", "w1", "e1", bad)
        with self.assertRaisesRegex(ValueError, "must not contain"):
            feature_list.feature_path("d1", "w1", "e1", "a/b")
        with self.assertRaisesRegex(ValueError, "document_id"):
            feature_list.feature_list_path("", "w1", "e1")


class RollbackIndexTest(unittest.TestCase):
    def test_accepts_positions_and_the_documented_end_sentinel(self) -> None:
        self.assertEqual(feature_list.validate_rollback_index(0), 0)
        self.assertEqual(feature_list.validate_rollback_index(17), 17)
        self.assertEqual(feature_list.validate_rollback_index(-1), -1)

    def test_rejects_values_that_are_not_positions(self) -> None:
        for bad in (True, False, "2", 2.0, None, [2]):
            with self.subTest(value=bad):
                with self.assertRaisesRegex(ValueError, "integer"):
                    feature_list.validate_rollback_index(bad)
        with self.assertRaisesRegex(ValueError, ">= -1"):
            feature_list.validate_rollback_index(-2)


class SuppressionBodyTest(unittest.TestCase):
    def test_one_call_covers_the_whole_list_and_flips_the_required_flag(self) -> None:
        body = feature_list.suppression_body(["A", "B", "C"], True)
        self.assertEqual(body["btType"], "BTUpdateFeaturesCall-1748")
        self.assertTrue(body["updateSuppressionAttributes"])
        self.assertEqual([f["featureId"] for f in body["features"]], ["A", "B", "C"])
        for item in body["features"]:
            self.assertEqual(item["btType"], "BTMFeature-134")
            self.assertTrue(item["suppressed"])
            # Nothing but identity + the flag: updateFeatures leaves omitted
            # fields alone, so a bloat-free body cannot clobber parameters.
            self.assertEqual(set(item), {"btType", "featureId", "suppressed"})

    def test_unsuppress_is_the_same_call_with_the_flag_off(self) -> None:
        body = feature_list.suppression_body(["A"], False)
        self.assertFalse(body["features"][0]["suppressed"])
        self.assertTrue(body["updateSuppressionAttributes"])

    def test_bad_lists_are_rejected_before_anything_is_sent(self) -> None:
        cases = {
            "feature_ids must be a list": "A",
            "at least one": [],
            "duplicate": ["A", "A"],
            "non-empty string": [""],
        }
        for message, value in cases.items():
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, message):
                    feature_list.suppression_body(value, True)
        with self.assertRaisesRegex(ValueError, "boolean"):
            feature_list.suppression_body(["A"], "yes")


class BodyBuilderTest(unittest.TestCase):
    def test_feature_omits_unsupplied_keys(self) -> None:
        self.assertEqual(
            feature_list.feature("f1"),
            {"btType": "BTMFeature-134", "featureId": "f1"},
        )
        full = feature_list.feature(
            "f1", suppressed=True, name="Extrude 1", namespace="e1::m2",
            feature_type="extrude", parameters=[{"parameterId": "depth"}],
        )
        self.assertEqual(full["suppressed"], True)
        self.assertEqual(full["parameters"], [{"parameterId": "depth"}])
        with self.assertRaisesRegex(ValueError, "suppressed must be a boolean"):
            feature_list.feature("f1", suppressed="yes")

    def test_update_features_body_requires_typed_features(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            feature_list.update_features_body([])
        with self.assertRaisesRegex(ValueError, "btType"):
            feature_list.update_features_body([{"featureId": "f1"}])
        body = feature_list.update_features_body([feature_list.feature("f1")])
        self.assertFalse(body["updateSuppressionAttributes"])
        body = feature_list.update_features_body(
            [feature_list.feature("f1")], update_suppression_attributes=True,
            source_microversion="m1",
        )
        self.assertTrue(body["updateSuppressionAttributes"])
        self.assertEqual(body["sourceMicroversion"], "m1")

    def test_definition_call_envelope_is_shared_with_the_add_path(self) -> None:
        body = feature_list.feature_definition_call(feature_list.feature("f1"))
        self.assertEqual(body["btType"], "BTFeatureDefinitionCall-1406")
        self.assertEqual(body["feature"]["btType"], "BTMFeature-134")
        with self.assertRaisesRegex(ValueError, "must be an object"):
            feature_list.feature_definition_call("f1")
        # The instantiate ("add") path must use the same envelope, or add and
        # update could disagree about BTFeatureDefinitionCall-1406.
        add = operations._instantiate_body({"depth": 1}, "e1::m2")
        self.assertEqual(add["btType"], feature_list.FEATURE_DEFINITION_CALL)
        self.assertEqual(add["feature"]["btType"], feature_list.FEATURE)


class DryRunTest(unittest.TestCase):
    def _client(self) -> FakeClient:
        client = FakeClient()
        client.request = mock.Mock(side_effect=AssertionError("dry run must not request"))
        return client

    def test_suppress_plans_exactly_one_call(self) -> None:
        plan = operations.update_feature_list(
            "suppress", feature_ids=["A", "B"], client=self._client(), dry_run=True,
        )
        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["estimatedRequests"], 1)
        request = plan["requests"][0]
        self.assertEqual(request["method"], "POST")
        self.assertTrue(request["url"].endswith("/features/updates"))
        self.assertTrue(request["headers"]["Authorization"] == "<REDACTED>")
        self.assertEqual([f["featureId"] for f in request["body"]["features"]], ["A", "B"])
        self.assertIn("updateSuppressionAttributes", request["note"])

    def test_unsuppress_plans_the_same_endpoint(self) -> None:
        plan = operations.update_feature_list(
            "unsuppress", feature_ids=["A"], client=self._client(), dry_run=True,
        )
        self.assertEqual(plan["requests"][0]["body"]["features"][0]["suppressed"], False)

    def test_rollback_plans_the_documented_body(self) -> None:
        plan = operations.update_feature_list(
            "rollback", rollback_index=-1, client=self._client(), dry_run=True,
        )
        self.assertEqual(plan["requests"][0]["body"], {"rollbackIndex": -1})
        self.assertTrue(plan["requests"][0]["url"].endswith("/features/rollback"))
        self.assertIn("end of the list", plan["requests"][0]["note"])

    def test_delete_plans_one_delete_without_a_body(self) -> None:
        plan = operations.update_feature_list(
            "delete", feature_id="F1", client=self._client(), dry_run=True,
        )
        request = plan["requests"][0]
        self.assertEqual(request["method"], "DELETE")
        self.assertTrue(request["url"].endswith("/features/featureid/F1"))
        self.assertIsNone(request["body"])
        self.assertNotIn("Content-Type", request["headers"])

    def test_replace_plans_a_full_definition_post(self) -> None:
        definition = feature_list.feature("F1", name="Renamed")
        plan = operations.update_feature_list(
            "replace", feature_id="F1", feature_definition=definition,
            client=self._client(), dry_run=True,
        )
        request = plan["requests"][0]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["body"]["feature"], definition)
        self.assertIn("NOT preserved", request["note"])

    def test_unknown_action_and_missing_arguments_are_refused(self) -> None:
        client = self._client()
        with self.assertRaisesRegex(ValueError, "action must be one of"):
            operations.update_feature_list("suppres", client=client, dry_run=True)
        with self.assertRaisesRegex(ValueError, "feature_id is required"):
            operations.update_feature_list("delete", client=client, dry_run=True)
        with self.assertRaisesRegex(ValueError, "feature_definition must"):
            operations.update_feature_list(
                "replace", feature_id="F1", client=client, dry_run=True,
            )
        with self.assertRaisesRegex(ValueError, "must carry featureId"):
            operations.update_feature_list(
                "replace", feature_id="F1", feature_definition={}, client=client, dry_run=True,
            )
        with self.assertRaisesRegex(ValueError, "must equal feature_id"):
            operations.update_feature_list(
                "replace", feature_id="F1",
                feature_definition=feature_list.feature("F2"),
                client=client, dry_run=True,
            )

    def test_part_studio_id_falls_back_to_state_without_walking_the_document(self) -> None:
        client = self._client()
        plan = operations.update_feature_list(
            "rollback", rollback_index=1, client=client, dry_run=True,
        )
        self.assertIn("/e/PSID/", plan["requests"][0]["url"])
        client.request.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "No Part Studio id available"):
            operations.update_feature_list(
                "rollback", rollback_index=1, part_studio_id=None,
                client=_NoStateClient(), dry_run=True,
            )


class _NoStateClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.state = {"documentId": "DOCID", "workspaceId": "WKSID"}


class LiveExecutionTest(unittest.TestCase):
    """What the live path sends and how it reads the answer back."""

    def test_suppress_sends_one_post_and_reports_the_new_states(self) -> None:
        client = FakeClient([{
            "btType": "BTUpdateFeaturesResponse-1333",
            "features": [
                {
                    "btType": "BTMFeature-134",
                    "featureId": "A",
                    "name": "Extrude 1",
                    "featureType": "extrude",
                    "namespace": "",
                    "suppressed": True,
                    "suppressionConfigured": True,
                    "suppressionState": {"btType": "BTMSuppressionStateConfigured-2598"},
                },
            ],
            "featureStates": {"A": {"btType": "BTFeatureState-1688", "featureStatus": "OK", "inactive": False}},
            "sourceMicroversion": "m2",
        }])
        result = operations.update_feature_list("suppress", feature_ids=["A"], client=client)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["method"], "POST")
        self.assertEqual(client.calls[0]["retry_get"], True)  # never a GET: single attempt
        self.assertEqual(result["action"], "suppress")
        self.assertEqual(result["requestCount"], 1)
        response = result["results"][0]["response"]
        self.assertEqual(response["features"][0]["suppressed"], True)
        self.assertEqual(response["features"][0]["suppressionKind"], "BTMSuppressionStateConfigured-2598")
        self.assertEqual(response["featureStates"], [{"featureId": "A", "featureStatus": "OK", "inactive": False}])
        self.assertEqual(response["sourceMicroversion"], "m2")
        self.assertIn("confirm the cloud state", result["verifyWith"])

    def test_rollback_and_delete_read_their_own_response_shapes(self) -> None:
        client = FakeClient([
            {"rollbackIndex": -1, "sourceMicroversion": "m3", "microversionId": {"theId": "mv3"}},
            {"btType": "BTFeatureApiBase-1430", "sourceMicroversion": "m4", "serializationVersion": "s1", "libraryVersion": 1},
        ])
        rolled = operations.update_feature_list("rollback", rollback_index=-1, client=client)
        self.assertEqual(rolled["results"][0]["response"], {
            "rollbackIndex": -1, "sourceMicroversion": "m3", "microversionId": "mv3",
        })
        deleted = operations.update_feature_list("delete", feature_id="A", client=client)
        self.assertEqual(deleted["results"][0]["response"]["sourceMicroversion"], "m4")
        self.assertEqual([call["method"] for call in client.calls], ["POST", "DELETE"])

    def test_replace_treats_a_non_ok_regeneration_as_a_failure(self) -> None:
        definition = feature_list.feature("A", name="Broken")
        client = FakeClient([{
            "feature": {"featureId": "A", "featureType": "extrude", "namespace": "e1::m1"},
            "featureState": {"featureStatus": "ERROR", "inactive": False},
            "sourceMicroversion": "m5",
        }])
        with self.assertRaisesRegex(RuntimeError, "did not regenerate cleanly: status ERROR"):
            operations.update_feature_list(
                "replace", feature_id="A", feature_definition=definition, client=client,
            )
        self.assertEqual(len(client.calls), 1)  # reported, never retried

    def test_replace_accepts_an_ok_regeneration(self) -> None:
        definition = feature_list.feature("A", name="Fine")
        client = FakeClient([{
            "feature": {"featureId": "A", "featureType": "extrude", "namespace": "e1::m1"},
            "featureState": {"featureStatus": "OK", "inactive": False},
            "sourceMicroversion": "m6",
        }])
        result = operations.update_feature_list(
            "replace", feature_id="A", feature_definition=definition, client=client,
        )
        response = result["results"][0]["response"]
        self.assertEqual(response["featureStatus"], "OK")
        self.assertEqual(response["feature"]["featureId"], "A")
        self.assertEqual(response["feature"]["suppressed"], None)


class ParserAgreementTest(unittest.TestCase):
    """Each parser reads exactly the fields its response schema declares."""

    CASES = {
        "updateFeatures": (
            feature_list.summarize_update_features,
            "BTUpdateFeaturesResponse-1333",
            {"features", "featureCount", "featureStates", "sourceMicroversion"},
        ),
        "updatePartStudioFeature": (
            feature_list.summarize_feature_definition,
            "BTFeatureDefinitionResponse-1617",
            {
                "featureStatus", "inactive", "featureId", "featureType", "namespace",
                "sourceMicroversion", "feature",
            },
        ),
        "updateRollback": (
            feature_list.summarize_rollback,
            "BTSetFeatureRollbackResponse-1042",
            {"rollbackIndex", "sourceMicroversion", "microversionId"},
        ),
        "deletePartStudioFeature": (
            feature_list.summarize_feature_api_base,
            "BTFeatureApiBase-1430",
            {"btType", "sourceMicroversion", "serializationVersion", "libraryVersion"},
        ),
    }

    def test_fixture_response_schema_is_the_one_the_parser_targets(self) -> None:
        for operation_id, (_parser, schema_name, _keys) in self.CASES.items():
            with self.subTest(operation=operation_id):
                _method, _path, op = operation(operation_id)
                self.assertEqual(response_schema_name(op), schema_name)

    def test_parsers_consume_only_declared_fields(self) -> None:
        for operation_id, (parser, schema_name, expected_keys) in self.CASES.items():
            with self.subTest(operation=operation_id):
                declared = declared_properties_deep(schema_name)
                self.assertTrue(
                    expected_keys <= declared | {"featureCount"},
                    f"{operation_id}: parser claims fields the schema does not declare: "
                    f"{sorted(expected_keys - declared - {'featureCount'})}",
                )
                parsed = parser(spec_instance(schema_name))
                self.assertEqual(set(parsed), expected_keys)

    def test_parsers_survive_empty_and_malformed_bodies(self) -> None:
        def empty(value) -> bool:
            if isinstance(value, dict):
                return all(empty(item) for item in value.values())
            return value in (None, [], 0)

        for operation_id, (parser, _schema, expected_keys) in self.CASES.items():
            for body in ({}, None, [], "text", 0):
                with self.subTest(operation=operation_id, body=body):
                    parsed = parser(body)
                    self.assertEqual(set(parsed), expected_keys)
                    self.assertTrue(all(empty(value) for value in parsed.values()))

    def test_feature_states_map_is_normalised_to_a_sorted_list(self) -> None:
        parsed = feature_list.summarize_update_features({
            "features": [],
            "featureStates": {"B": {"featureStatus": "ERROR"}, "A": {"inactive": True}},
        })
        self.assertEqual(
            [item["featureId"] for item in parsed["featureStates"]], ["A", "B"],
        )
        # An undeclared list shape must not explode the summary.
        self.assertEqual(feature_list.summarize_update_features({"featureStates": [1, 2]})["featureStates"], [])

    def test_suppression_kind_surfaces_the_parent_suppressed_case(self) -> None:
        summary = feature_list.summarize_feature({
            "featureId": "A",
            "suppressed": False,
            "suppressionState": {"btType": "BTMSuppressionStateParentSuppressed-5404"},
        })
        self.assertEqual(summary["suppressionKind"], "BTMSuppressionStateParentSuppressed-5404")
        self.assertFalse(summary["suppressed"])


class FixtureTest(unittest.TestCase):
    """The checked-in constructed requests still describe the real builder."""

    def _current(self) -> dict[str, dict]:
        def build(feature_id="FEATID_A"):
            return feature_list.feature_path(**IDS, feature_id=feature_id)
        return {
            "updateFeatures": ("POST", feature_list.updates_path(**IDS),
                               feature_list.suppression_body(["FEATID_A", "FEATID_B"], True)),
            "deletePartStudioFeature": ("DELETE", build(), None),
            "updateRollback": ("POST", feature_list.rollback_path(**IDS),
                               feature_list.rollback_body(feature_list.ROLLBACK_END)),
            "updatePartStudioFeature": (
                "POST", build(),
                feature_list.feature_definition_call({
                    "btType": feature_list.FEATURE,
                    "featureId": "FEATID_A",
                    "name": "Renamed in place",
                    "suppressed": False,
                }),
            ),
        }

    def test_each_fixture_request_still_matches_the_builder(self) -> None:
        client = FakeClient()
        for operation_id, (method, path, body) in self._current().items():
            with self.subTest(operation=operation_id):
                fixture = FIXTURES / operation_id / "request.json"
                self.assertTrue(fixture.is_file(), f"missing fixture {fixture}")
                recorded = json.loads(fixture.read_text(encoding="utf-8"))
                expected = client.describe(method, path, body)
                self.assertEqual(
                    recorded, expected,
                    f"{operation_id}/request.json drifted; rewrite it with:\n"
                    + json.dumps(expected, indent=2, ensure_ascii=False),
                )
                self.assertEqual(recorded["headers"]["Authorization"], "<REDACTED>")

    def test_fixtures_state_plainly_that_nothing_was_sent(self) -> None:
        for operation_id in self._current():
            with self.subTest(operation=operation_id):
                directory = FIXTURES / operation_id
                metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
                self.assertIs(metadata["liveExecuted"], False)
                self.assertIsNone(metadata["status"])
                self.assertEqual(metadata["operationId"], operation_id)
                self.assertIn("no request was sent", metadata["responseHeaders"])
                self.assertEqual(
                    metadata["responseSchema"],
                    response_schema_name(operation(operation_id)[2]),
                )
                # A response body nobody received would be fabricated evidence.
                self.assertFalse(
                    (directory / "response.json").exists(),
                    f"{operation_id} has a response.json but no live call was ever made",
                )
        self.assertTrue((FIXTURES / "README.md").is_file())


class McpToolTest(unittest.TestCase):
    """The tool that makes all of the above reachable."""

    def _tool(self) -> dict:
        from mcp_main.win.mcp import server
        return next(t for t in server.TOOLS if t["name"] == "onshape_update_feature_list")

    def test_declared_cost_is_one_live_mutating_request(self) -> None:
        tool = self._tool()
        declared = tool["cost"]
        for key, value in {
            "network": "live",
            "estimated_requests": 1,
            "max_requests": 1,
            "mutating": True,
            "cacheable": False,
        }.items():
            self.assertEqual(declared[key], value, key)
        # Every action is planned as exactly one request, which is the property
        # the declared cost depends on.
        self.assertEqual(tool["annotations"]["destructiveHint"], True)
        self.assertEqual(
            tool["inputSchema"]["properties"]["action"]["enum"],
            list(operations.FEATURE_LIST_ACTIONS),
        )
        self.assertIn("confirm_mutation", tool["inputSchema"]["required"])

    def test_handler_requires_confirmation_before_planning(self) -> None:
        from mcp_main.win.mcp import server
        with self.assertRaisesRegex(ValueError, "confirm_mutation must be true"):
            server._update_feature_list({"action": "rollback", "rollback_index": 1})

    def test_handler_dry_run_calls_the_operation_without_a_quota_gate(self) -> None:
        from mcp_main.win.mcp import server
        with mock.patch.object(server, "update_feature_list") as call, \
                mock.patch.object(server, "_require_live") as gate:
            call.return_value = {"dryRun": True, "estimatedRequests": 1}
            result = server._update_feature_list({
                "confirm_mutation": True,
                "action": "rollback",
                "rollback_index": -1,
                "dry_run": True,
            })
        self.assertTrue(result["dryRun"])
        gate.assert_not_called()
        self.assertTrue(call.call_args.kwargs["dry_run"])

    def test_handler_live_gates_on_the_estimate_the_plan_reports(self) -> None:
        from mcp_main.win.mcp import server
        with mock.patch.object(server, "update_feature_list") as call, \
                mock.patch.object(server, "_require_live") as gate:
            call.side_effect = [
                {"dryRun": True, "estimatedRequests": 1},
                {"action": "delete", "requestCount": 1},
            ]
            result = server._update_feature_list({
                "confirm_mutation": True, "action": "delete", "feature_id": "F1",
            })
        self.assertEqual(result["requestCount"], 1)
        gate.assert_called_once_with(1, "update_feature_list (delete)")
        self.assertEqual(call.call_count, 2)
        self.assertTrue(call.call_args_list[0].kwargs["dry_run"])
        self.assertNotIn("dry_run", call.call_args_list[1].kwargs)

    def test_handler_never_gates_when_the_plan_is_invalid(self) -> None:
        from mcp_main.win.mcp import server
        with mock.patch.object(server, "update_feature_list") as call, \
                mock.patch.object(server, "_require_live") as gate:
            call.side_effect = ValueError("feature_id is required for action 'delete'")
            with self.assertRaisesRegex(ValueError, "feature_id is required"):
                server._update_feature_list({
                    "confirm_mutation": True, "action": "delete",
                })
        gate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
