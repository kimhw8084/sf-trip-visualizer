import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from qa_loading import APPLICATION_READY, assert_loading_not_blocking, wait_for_application_ready  # noqa: E402


class FakePage:
    def __init__(self, state):
        self.state = state
        self.wait_expression = None

    def evaluate(self, expression):
        return self.state

    def wait_for_function(self, expression, timeout):
        self.wait_expression = (expression, timeout)


class LoadingCompletionTests(unittest.TestCase):
    def test_hidden_ready_screen_before_dom_removal_is_accepted(self):
        page = FakePage({"present": True, "ready": True, "blocking": False, "status": "ready"})
        state = wait_for_application_ready(page, timeout=1234)
        self.assertTrue(state["ready"])
        self.assertFalse(state["blocking"])
        self.assertIn("appReady", page.wait_expression[0])
        self.assertEqual(page.wait_expression[1], 1234)

    def test_visible_stuck_loading_screen_is_a_failure(self):
        page = FakePage({"present": True, "ready": False, "blocking": True, "status": "visible"})
        with self.assertRaises(AssertionError):
            assert_loading_not_blocking(page)

    def test_readiness_requires_product_ready_state_and_nonblocking_screen(self):
        self.assertIn("app.state.loadingStatus === 'ready'", APPLICATION_READY)
        self.assertIn("legacyProductReady", APPLICATION_READY)
        self.assertIn("app.state.mapVisualReady === true", APPLICATION_READY)
        self.assertIn("map.areTilesLoaded", APPLICATION_READY)
        self.assertIn("!map.isMoving", APPLICATION_READY)
        self.assertIn("!map.isZooming", APPLICATION_READY)
        self.assertIn("screen.classList.contains('ready')", APPLICATION_READY)
        self.assertIn("screen.getAttribute('aria-hidden') === 'true'", APPLICATION_READY)
        self.assertIn("getComputedStyle(screen).pointerEvents === 'none'", APPLICATION_READY)

    def test_map_first_full_no_longer_uses_fixed_loading_sleep_or_removal_only(self):
        source = (ROOT / "scripts/qa_map_first_full.py").read_text()
        self.assertIn("wait_for_application_ready", source)
        self.assertNotIn("page.wait_for_timeout(900)\n    report[\"checks\"][\"loading_completed\"]", source)
        self.assertNotIn("!document.getElementById('loadingScreen')", source)

    def test_map_visual_readiness_waits_for_resources_idle_and_stable_frames(self):
        source = (ROOT / "src/app_phase7.js").read_text()
        self.assertIn("function waitForMapVisualReady", source)
        self.assertIn("snapshot.localPending===0", source)
        self.assertIn("snapshot.tilesLoaded", source)
        self.assertIn("renderSeen", source)
        self.assertIn("renderedVersion===snapshot.resourceVersion", source)
        self.assertIn("idleSeen", source)
        self.assertIn("postIdleRenderSeen", source)
        self.assertIn("stableFrames>=3", source)


if __name__ == "__main__":
    unittest.main()
