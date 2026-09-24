import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from public_asset_rights import audit_tree, evidence_tree_label, load_contract, load_json, render_attribution, write_notices


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_contract() -> dict:
    return {
        "schema_version": 1,
        "project": "sf-trip-visualizer",
        "decision_vocabulary": ["approved", "excluded", "verify-required"],
        "input_sha256": {},
        "private_only_paths": ["private/**"],
        "asset_families": [{
            "id": "fixture", "asset_class": "fixture", "paths": ["index.html"],
            "provenance": "fixture", "license_or_permission": "fixture", "attribution_text": "fixture",
            "derivative_obligations": "fixture", "evidence_status": "first-party-generated",
            "public_distribution_decision": "approved",
        }],
        "photo_assets": [],
        "path_rules": [
            {"id": "index", "modes": ["pages"], "paths": ["index.html"], "asset_class": "fixture", "decision": "approved"},
            {"id": "attribution", "modes": ["pages"], "paths": ["ATTRIBUTION.md"], "asset_class": "notice", "decision": "approved"},
            {"id": "third-party", "modes": ["pages"], "paths": ["THIRD_PARTY_NOTICES.md"], "asset_class": "notice", "decision": "approved"},
            {"id": "contract", "modes": ["pages"], "paths": [".public-asset-rights.json"], "asset_class": "notice", "decision": "approved"},
        ],
        "hash_bindings": [],
        "required_paths": {"pages": ["index.html", "ATTRIBUTION.md", "THIRD_PARTY_NOTICES.md", ".public-asset-rights.json"]},
    }


class PublicAssetRightsTests(unittest.TestCase):
    def make_tree(self, contract=None):
        contract = contract or fixture_contract()
        temporary = tempfile.TemporaryDirectory(prefix="rights-gate-test-")
        tree = Path(temporary.name)
        (tree / "index.html").write_text("<!doctype html><title>fixture</title>")
        write_notices(tree, contract, {"assets": []}, "pages")
        self.addCleanup(temporary.cleanup)
        return tree, contract

    def test_all_approved_public_tree_passes(self):
        tree, contract = self.make_tree()
        result = audit_tree(tree, contract=contract, manifest={"assets": []}, mode="pages", require_provenance=False)
        self.assertEqual(result["status"], "PASS", result)

    def test_unregistered_shipped_file_fails(self):
        tree, contract = self.make_tree()
        (tree / "unexpected.bin").write_bytes(b"not registered")
        result = audit_tree(tree, contract=contract, manifest={"assets": []}, mode="pages", require_provenance=False)
        self.assertIn("unregistered shipped file: unexpected.bin", result["failures"])

    def test_verify_required_decision_fails(self):
        contract = fixture_contract()
        contract["path_rules"][0]["decision"] = "verify-required"
        tree, contract = self.make_tree(contract)
        result = audit_tree(tree, contract=contract, manifest={"assets": []}, mode="pages", require_provenance=False)
        self.assertTrue(any("not approved" in failure for failure in result["failures"]))

    def test_missing_required_attribution_fails(self):
        tree, contract = self.make_tree()
        (tree / "ATTRIBUTION.md").unlink()
        result = audit_tree(tree, contract=contract, manifest={"assets": []}, mode="pages", require_provenance=False)
        self.assertTrue(any("required public asset/notice missing: ATTRIBUTION.md" in failure for failure in result["failures"]))

    def test_private_only_asset_absent_passes(self):
        tree, contract = self.make_tree()
        result = audit_tree(tree, contract=contract, manifest={"assets": []}, mode="pages", require_provenance=False)
        self.assertEqual(result["status"], "PASS")

    def test_hash_binding_mismatch_fails_closed(self):
        tree, contract = self.make_tree()
        contract["hash_bindings"] = [{"path": "index.html", "sha256": "0" * 64, "modes": ["pages"]}]
        result = audit_tree(tree, contract=contract, manifest={"assets": []}, mode="pages", require_provenance=False)
        self.assertTrue(any("hash-bound public asset mismatch: index.html" in failure for failure in result["failures"]))

    def test_replacements_preserve_place_role_and_integrity_bindings(self):
        manifest = load_json(ROOT / "manifests/asset_manifest.json")
        contract = load_contract()
        self.assertEqual(len(manifest["assets"]), 117)
        self.assertEqual(len(contract["photo_assets"]), 117)
        self.assertEqual(len({item["sha256"] for item in manifest["assets"]}), 117)
        self.assertEqual(len(contract["initially_ambiguous_replacements"]), 12)
        roles = {(item["place_key"], item["role"]) for item in manifest["assets"]}
        self.assertEqual(len(roles), 117)
        retired = {"academy", "bay_lights", "bixby", "coit", "exploratorium", "mariposa", "musee"}
        self.assertFalse(retired & {item["place_key"] for item in manifest["assets"]})
        self.assertFalse(any(any(f"{place}__" in path for place in retired) for row in contract["asset_families"] for path in row.get("paths", [])))
        self.assertFalse(any(any(f"{place}__" in path for place in retired) for rule in contract["path_rules"] for path in rule.get("paths", [])))
        for item in manifest["assets"]:
            rights = next(row for row in contract["photo_assets"] if row["id"] == f'{item["place_key"]}/{item["role"]}')
            self.assertEqual(rights["public_paths"], [item["local_thumb_path"], item["local_medium_path"]])
            self.assertEqual(rights["hashes"][item["local_thumb_path"]], item["thumb_sha256"])
            self.assertEqual(rights["hashes"][item["local_medium_path"]], item["medium_sha256"])
            self.assertTrue((ROOT / item["local_thumb_path"]).is_file())
            self.assertTrue((ROOT / item["local_medium_path"]).is_file())

    def test_generated_attribution_is_deterministic(self):
        contract = load_contract()
        first = render_attribution(contract)
        second = render_attribution(copy.deepcopy(contract))
        self.assertEqual(first, second)
        self.assertNotIn("exploratorium/", first)
        self.assertNotIn("musee/", first)
        self.assertNotIn("academy/", first)
        self.assertNotIn("bay_lights/", first)
        self.assertNotIn("bixby/", first)
        self.assertNotIn("coit/", first)
        self.assertNotIn("mariposa/", first)
        self.assertIn("CC BY-SA 3.0", first)

    def test_evidence_tree_label_redacts_external_operator_path(self):
        self.assertEqual(evidence_tree_label(Path("/Users/operator/private-tree")), "<candidate-tree>")


if __name__ == "__main__":
    unittest.main()
