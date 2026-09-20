"""Shared semantic readiness checks for the map-first browser suites."""

from __future__ import annotations


LOADING_SCREEN_STATE = """() => {
  const screen = document.getElementById('loadingScreen');
  if (!screen) return {present:false, ready:true, blocking:false, status:'absent'};
  const style = getComputedStyle(screen);
  const ready = screen.classList.contains('ready')
    && screen.getAttribute('aria-hidden') === 'true'
    && style.visibility === 'hidden'
    && style.pointerEvents === 'none';
  const rect = screen.getBoundingClientRect();
  const visible = style.display !== 'none'
    && style.visibility !== 'hidden'
    && Number(style.opacity) > 0
    && rect.width > 0
    && rect.height > 0;
  const blocking = visible && style.pointerEvents !== 'none'
    && screen.getAttribute('aria-hidden') !== 'true';
  return {
    present:true,
    ready,
    blocking,
    status: screen.classList.contains('failed') ? 'failed' : screen.classList.contains('ready') ? 'ready' : 'visible',
    ariaHidden: screen.getAttribute('aria-hidden'),
    visibility: style.visibility,
    pointerEvents: style.pointerEvents,
    opacity: Number(style.opacity),
  };
}"""


APPLICATION_READY = """() => {
  const app = window.__tripApp;
  const map = app?.map?.();
  const screen = document.getElementById('loadingScreen');
  const screenReady = !screen || (
    screen.classList.contains('ready')
    && screen.getAttribute('aria-hidden') === 'true'
    && getComputedStyle(screen).visibility === 'hidden'
    && getComputedStyle(screen).pointerEvents === 'none'
  );
  const explicitProductReady = app?.state?.appReady === true
    && app.state.loadingStatus === 'ready';
  const legacyProductReady = app?.state?.appReady === undefined
    && app.state.localAssets?.status === 'ready'
    && app.state.provider === 'vector'
    && app.state.providerHealth?.vector === 'ready';
  return Boolean(
    (explicitProductReady || legacyProductReady)
    && app.state.provider === 'vector'
    && app.state.providerHealth?.vector === 'ready'
    && app.state.localAssets?.status === 'ready'
    && (app.state.mapVisualReady === true || app.state.mapVisualReady === undefined)
    && map?.isStyleLoaded?.()
    && (typeof map.areTilesLoaded !== 'function' || map.areTilesLoaded())
    && !map.isMoving?.()
    && !map.isZooming?.()
    && document.querySelectorAll('.maplibregl-canvas').length === 1
    && document.querySelectorAll('.photo-marker').length === window.TRIP_DATA.markers.filter(app.markerVisible).length
    && document.querySelectorAll('[data-timeline]').length === window.TRIP_DATA.timeline.filter(app.timelineVisible).length
    && screenReady
  );
}"""


def loading_screen_state(page) -> dict:
    return page.evaluate(LOADING_SCREEN_STATE)


def assert_loading_not_blocking(page) -> dict:
    state = loading_screen_state(page)
    if state.get("blocking"):
        raise AssertionError(f"loading screen remains visibly blocking after app readiness: {state}")
    return state


def wait_for_application_ready(page, timeout: int = 30000) -> dict:
    """Wait for app readiness and accept either hidden-ready or removed loading DOM."""

    page.wait_for_function(APPLICATION_READY, timeout=timeout)
    return assert_loading_not_blocking(page)
