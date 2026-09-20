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
    """The checked-in requests still describe the real builder, and the recorded
    live bodies replay through the parsers the live path uses.

    The directories were born constructed-and-never-sent and were later replaced
    by one authorized live run, so every assertion here is driven by each
    fixture's own `metadata.json`: a constructed fixture must still say so, and a
    live one must carry a real status, a real time, a response body, and a
    `request.json` that matches the builder for the ids it records.
    """

    OPERATIONS = (
        "updateFeatures",
        "deletePartStudioFeature",
        "updateRollback",
        "updatePartStudioFeature",
        "getPartStudioFeatures",
    )

    def _metadata(self, operation_id: str) -> dict:
        path = FIXTURES / operation_id / "metadata.json"
        self.assertTrue(path.is_file(), f"missing fixture metadata {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _request_ids(self, operation_id: str, metadata: dict) -> tuple[dict, str | None]:
        """The ids the recorded request addresses: the live target when the call
        was really sent, the placeholders while a fixture is still constructed."""
        if metadata["liveExecuted"]:
            target = metadata["target"]
            named = {
                "document_id": target["document_id"],
                "workspace_id": target["workspace_id"],
                "element_id": target["element_id"],
            }
            return dict(named), target.get("featureId")
        return dict(IDS), "FEATID_A"

    def _current(self, operation_id: str, metadata: dict) -> tuple:
        """The request the shared builder produces for this fixture's ids:
        `(method, path, body, query)`."""
        named, feature_id = self._request_ids(operation_id, metadata)
        if operation_id == "getPartStudioFeatures":
            return (
                "GET", feature_list.feature_list_path(**named), None,
                {"rollbackBarIndex": -1},
            )
        if operation_id == "updateRollback":
            return (
                "POST", feature_list.rollback_path(**named),
                feature_list.rollback_body(feature_list.ROLLBACK_END), None,
            )
        if operation_id == "updateFeatures":
            return (
                "POST", feature_list.updates_path(**named),
                feature_list.suppression_body([feature_id], True), None,
            )
        path = feature_list.feature_path(**named, feature_id=feature_id)
        if operation_id == "deletePartStudioFeature":
            return ("DELETE", path, None, None)
        return (
            "POST", path,
            feature_list.feature_definition_call(
                self._replace_feature(operation_id, metadata, feature_id)
            ),
            None,
        )

    def _replace_feature(self, operation_id: str, metadata: dict, feature_id: str) -> dict:
        """`updatePartStudioFeature` was sent the definition read back from the
        Feature List, so the expectation is rebuilt from the recorded read."""
        if not metadata["liveExecuted"]:
            return {
                "btType": feature_list.FEATURE,
                "featureId": "FEATID_A",
                "name": "Renamed in place",
                "suppressed": False,
            }
        listing = json.loads(
            (FIXTURES / "getPartStudioFeatures" / "response.json").read_text(encoding="utf-8")
        )
        source = next(f for f in listing["features"] if f["featureId"] == feature_id)
        return feature_list.feature(
            feature_id,
            name=f"{source['name']} (P3 rename)",
            feature_type=source["featureType"],
            namespace=source["namespace"],
            parameters=source["parameters"],
        )

    def test_each_fixture_request_still_matches_the_builder(self) -> None:
        client = FakeClient()
        for operation_id in self.OPERATIONS:
            with self.subTest(operation=operation_id):
                metadata = self._metadata(operation_id)
                fixture = FIXTURES / operation_id / "request.json"
                self.assertTrue(fixture.is_file(), f"missing fixture {fixture}")
                recorded = json.loads(fixture.read_text(encoding="utf-8"))
                method, path, body, query = self._current(operation_id, metadata)
                expected = client.describe(method, path, body, query=query)
                self.assertEqual(
                    recorded, expected,
                    f"{operation_id}/request.json drifted; rewrite it with:\n"
                    + json.dumps(expected, indent=2, ensure_ascii=False),
                )
                self.assertEqual(recorded["headers"]["Authorization"], "<REDACTED>")

    def test_every_live_fixture_records_what_the_run_received(self) -> None:
        for operation_id in self.OPERATIONS:
            with self.subTest(operation=operation_id):
                directory = FIXTURES / operation_id
                metadata = self._metadata(operation_id)
                self.assertEqual(metadata["operationId"], operation_id)
                self.assertEqual(
                    metadata["responseSchema"],
                    response_schema_name(operation(operation_id)[2]),
                )
                if not metadata["liveExecuted"]:
                    self.assertIsNone(metadata["status"])
                    self.assertIn("no request was sent", metadata["responseHeaders"])
                    self.assertFalse(
                        (directory / "response.json").exists(),
                        f"{operation_id} has a response.json but no live call was ever made",
                    )
                    continue
                # Live: the run's own record must be internally consistent.
                self.assertIsInstance(metadata["status"], int)
                self.assertTrue(200 <= metadata["status"] < 300, metadata["status"])
                self.assertRegex(metadata["executedAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
                self.assertTrue(metadata["target"]["element_id"])
                self.assertTrue((directory / "response.json").is_file())
                recorded = json.loads((directory / "request.json").read_text(encoding="utf-8"))
                self.assertEqual(recorded["headers"]["Authorization"], "<REDACTED>")
                self.assertNotIn("accessKey", json.dumps(recorded))
                self.assertNotIn("secretKey", json.dumps(recorded))
        self.assertTrue((FIXTURES / "README.md").is_file())


class RefusalShapeTest(unittest.TestCase):
    """The one recorded refusal, and the property it exists to pin.

    The four success fixtures say nothing about failure. This directory holds a
    real 404 for a feature id that cannot exist, so the refusal envelope is
    evidence rather than an assumption — and so that "an error body is not a
    success" can be asserted instead of trusted.
    """

    DIRECTORY = FIXTURES / "refusal-deletePartStudioFeature"

    def _metadata(self) -> dict:
        return json.loads((self.DIRECTORY / "metadata.json").read_text(encoding="utf-8"))

    def test_the_refusal_is_recorded_with_its_real_shape(self) -> None:
        metadata = self._metadata()
        self.assertIs(metadata["liveExecuted"], True)
        self.assertEqual(metadata["operationId"], "deletePartStudioFeature")
        self.assertTrue(400 <= metadata["status"] < 500, metadata["status"])
        self.assertEqual(metadata["ledgerStatus"], metadata["status"])
        self.assertRegex(metadata["executedAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        body = json.loads((self.DIRECTORY / "response.json").read_text(encoding="utf-8"))
        # The shared error envelope, verbatim: this is what a caller has to
        # recognise, and it is not the operation's declared response schema.
        self.assertEqual(set(body), {"moreInfoUrl", "message", "status", "code"})
        self.assertEqual(body["message"], "Feature not found")
        self.assertEqual(body["status"], metadata["status"])
        self.assertIsInstance(body["code"], int)
        self.assertIsNone(metadata["responseSchema"])
        self.assertIn("error envelope", metadata["responseSchemaNote"])
        request = json.loads((self.DIRECTORY / "request.json").read_text(encoding="utf-8"))
        self.assertEqual(request["method"], "DELETE")
        self.assertEqual(request["headers"]["Authorization"], "<REDACTED>")

    def test_the_refusal_was_free_of_quota(self) -> None:
        """4xx does not count toward the annual limit — measured, not assumed."""
        self.assertEqual(self._metadata()["quotaConsumed"], 0)

    def test_the_success_parser_cannot_mistake_an_error_for_a_success(self) -> None:
        body = json.loads((self.DIRECTORY / "response.json").read_text(encoding="utf-8"))
        summary = feature_list.summarize_feature_api_base(body)
        self.assertEqual(
            set(summary),
            {"btType", "sourceMicroversion", "serializationVersion", "libraryVersion"},
        )
        self.assertTrue(all(value is None for value in summary.values()))

    def test_every_fixture_directory_states_what_it_is(self) -> None:
        """A directory without metadata, or a response with no metadata saying it
        is live, would be an unexplained artifact in the fixture tree."""
        for directory in sorted(p for p in FIXTURES.iterdir() if p.is_dir()):
            with self.subTest(directory=directory.name):
                metadata_path = directory / "metadata.json"
                self.assertTrue(metadata_path.is_file(), directory.name)
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertIn("liveExecuted", metadata)
                self.assertIn("purpose", metadata)
                self.assertIn("testPurpose", metadata)
                if (directory / "response.json").is_file():
                    self.assertIs(metadata["liveExecuted"], True)


class LiveReplayTest(unittest.TestCase):
    """The real server bodies, replayed through the real parsers.

    This is the payoff of the authorized run: the parsers are no longer only
    checked against a spec-derived instance, they are checked against what
    Onshape actually answered.
    """

    def _body(self, operation_id: str) -> dict:
        return json.loads(
            (FIXTURES / operation_id / "response.json").read_text(encoding="utf-8")
        )

    def test_the_read_returns_the_fields_a_replace_call_must_be_fed(self) -> None:
        body = self._body("getPartStudioFeatures")
        self.assertEqual(body["btType"], "BTFeatureListResponse-2457")
        self.assertIs(body["isComplete"], True)
        self.assertIsInstance(body["rollbackIndex"], int)
        # The recorded request carries rollbackBarIndex=-1 because that is the
        # call that returned the list; a follow-up probe showed the argument does
        # not filter the response (see this directory's README). The URL is pinned
        # so a re-recorded fixture cannot silently drop the query.
        request = json.loads(
            (FIXTURES / "getPartStudioFeatures" / "request.json").read_text(encoding="utf-8")
        )
        self.assertIn("rollbackBarIndex=-1", request["url"])
        feature = body["features"][0]
        for key in ("featureId", "featureType", "namespace", "parameters", "btType"):
            self.assertIn(key, feature)
        self.assertEqual(feature["btType"], feature_list.FEATURE)
        self.assertEqual(feature["featureType"], "spiralRidge")
        # The namespace is the Feature Studio that owns the definition, which is
        # what makes the row a custom feature rather than a standard one.
        self.assertRegex(feature["namespace"], r"^e[0-9a-f]{20,24}::m[0-9a-f]{20,26}$")
        # The state map covers the feature, which is how the live path can tell
        # a computed row from a broken one without a second request.
        self.assertEqual(
            body["featureStates"][feature["featureId"]]["featureStatus"], "OK",
        )

    def test_suppression_replays_to_a_suppressed_feature(self) -> None:
        summary = feature_list.summarize_update_features(self._body("updateFeatures"))
        self.assertEqual(summary["featureCount"], 1)
        self.assertIs(summary["features"][0]["suppressed"], True)
        self.assertEqual(summary["features"][0]["featureType"], "spiralRidge")
        self.assertEqual(
            [item["featureId"] for item in summary["featureStates"]],
            [summary["features"][0]["featureId"]],
        )
        self.assertEqual(summary["featureStates"][0]["featureStatus"], "OK")

    def test_the_in_place_replace_replays_to_an_ok_renamed_feature(self) -> None:
        body = self._body("updatePartStudioFeature")
        summary = feature_list.summarize_feature_definition(body)
        self.assertEqual(summary["featureStatus"], "OK")
        self.assertIs(summary["inactive"], False)
        self.assertEqual(summary["featureType"], "spiralRidge")
        self.assertTrue(summary["feature"]["name"].endswith("(P3 rename)"))
        self.assertEqual(
            summary["feature"]["featureId"], body["feature"]["featureId"],
        )

    def test_rollback_replays_to_a_real_position_and_microversion(self) -> None:
        summary = feature_list.summarize_rollback(self._body("updateRollback"))
        self.assertEqual(summary["rollbackIndex"], 1)
        self.assertTrue(summary["sourceMicroversion"])
        # `-1` was sent and the server answered with the resolved position: the
        # response reports where the bar ended up, not the sentinel that was sent.
        self.assertEqual(summary["microversionId"], self._body("updateRollback")["microversionId"]["theId"])

    def test_the_add_endpoint_returns_the_feature_it_created(self) -> None:
        """`addPartStudioFeature` is the endpoint `operations.instantiate_feature`
        has always targeted; this is its only live evidence."""
        body = self._body("addPartStudioFeature")
        summary = feature_list.summarize_feature_definition(body)
        self.assertEqual(summary["featureStatus"], "OK")
        self.assertIs(summary["inactive"], False)
        # It resolved the definition the request named, not some other one.
        self.assertEqual(summary["featureType"], "spiralRidge")
        request = json.loads(
            (FIXTURES / "addPartStudioFeature" / "request.json").read_text(encoding="utf-8")
        )
        sent = request["body"]["feature"]
        self.assertEqual(summary["namespace"], sent["namespace"])
        self.assertEqual(summary["featureId"], body["feature"]["featureId"])
        self.assertNotEqual(summary["featureId"], "")
        # The spec takes no parameters, so an empty array is the correct body --
        # which is also why the in-place replace could round-trip one.
        self.assertEqual(sent["parameters"], [])

    def test_delete_replays_to_the_versioning_envelope(self) -> None:
        summary = feature_list.summarize_feature_api_base(self._body("deletePartStudioFeature"))
        self.assertEqual(summary["btType"], "BTFeatureApiBase-1430")
        self.assertTrue(summary["sourceMicroversion"])
        self.assertTrue(summary["serializationVersion"])



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
