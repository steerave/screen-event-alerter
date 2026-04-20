# Last War Alert Watcher — Implementation Plan (Revised)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight Windows background watcher that detects known event icons in the Last War game window and fires local (sound + toast) and optional Slack alerts on a confirmed rising edge only.

**Architecture:** Five focused modules (WindowFinder, ScreenCapture, Detector, AlertManager, watcher main loop) plus a calibration probe. Multi-template matching via OpenCV in grayscale. Rising-edge state machine per event prevents re-alerting on a persistent icon. YAML config drives all events, ROIs, template lists, consecutive-hit requirements, thresholds, and cooldowns. DPI awareness set at startup.

**Tech Stack:** Python 3.11+, pywin32, mss, opencv-python, numpy, PyYAML, python-dotenv, requests, win10toast, pytest

---

## Explicit Limitations (v1)

These are known constraints of the chosen architecture. They are not bugs — they are design tradeoffs. Understand them before deploying.

### 1. Game window must be visible and unobstructed
v1 uses screen capture of the on-screen client area via mss (the Windows desktop compositor). If another window overlaps the watched region, mss will capture whatever is on top — not the game. This means:

- Keep the Last War watched region free of overlapping windows while the watcher is running
- A Slack notification panel, a browser tooltip, or another app window sliding over that region will cause either missed detections (obscured) or false positives (captured wrong content)
- This is a fundamental limitation of compositor-based capture, not a bug

**Future path to fix this:** DirectX DXGI Desktop Duplication API or PrintWindow with PW_RENDERFULLCONTENT flag can capture window content even when occluded, but requires different capture code and does not work on all GPU/driver configurations. Out of scope for v1.

### 2. Window size must remain fixed
ROI pixel coordinates and all template images are tied to a specific window resolution. If the window is resized:
- All ROI coordinates become wrong (different pixel positions)
- All templates fail to match (different icon scale)
- Detection fails silently — no error, just no alerts

This is a hard constraint. Fix the window to one size, set `window_width` and `window_height` in config, and do not resize.

### 3. Window moving is fine; resizing is not
The watcher dynamically locates the window on every poll using its HWND. The window can be dragged anywhere on the desktop without breaking detection. Only its size must stay fixed.

### 4. Templates must match the current game version
Game updates may change icon artwork. If the game updates and the event icon changes appearance, templates must be recaptured. The watcher will fail silently (no matches) until templates are updated.

### 5. Cooldown state resets on restart
Cooldowns are in-memory only. If the watcher is stopped and restarted, all cooldowns reset. This means a detection that fired just before restart may fire again immediately after restart. Acceptable for v1.

### 6. Multiple matching windows
If more than one visible window contains the title substring (e.g., two Last War instances), the watcher uses the first match and logs a warning. This is unlikely in practice but worth knowing.

---

## Updated Architecture Summary

```
config.yaml
  window_title          # partial match string
  window_width          # expected client width — validated at startup
  window_height         # expected client height — validated at startup
  poll_fps              # default: 2
  debug_mode            # bool

  events:
    - name
      detection_mode    # "template" only in v1; hook for future modes
      templates         # list of template image paths (multiple supported)
      roi               # x, y, w, h (window-relative pixels)
      threshold         # confidence threshold per event
      consecutive_hits_required   # frames above threshold before alert fires
      cooldown_seconds  # anti-spam guard after alert fires
      blank_prefilter   # bool: skip matchTemplate if ROI is dark (optional)
      alert_sound       # bool
      alert_toast       # bool
      alert_slack       # bool
      slack_message     # string
```

```
State per event (in-memory, EventState dataclass):
  consecutive_hits: int       # frames continuously above threshold
  is_confirmed_present: bool  # True once consecutive_hits_required reached
  last_alert_time: float      # timestamp of most recent fired alert
  consecutive_errors: int     # count of consecutive capture/detect failures

Rising-edge logic per poll:
  if confidence >= threshold:
    consecutive_hits += 1
  else:
    consecutive_hits = 0
    is_confirmed_present = False   # icon gone — next confirmed detection is a new rising edge

  if consecutive_hits >= required AND NOT is_confirmed_present:
    is_confirmed_present = True
    if time since last_alert_time >= cooldown_seconds:
      FIRE ALERT
      last_alert_time = now
```

```
Main loop:
  1. DPI awareness set once at startup
  2. Find game window by partial title → log exact matched title → warn if >1 match
  3. If not found: log (rate-limited to once/minute), sleep, retry
  4. If minimized: sleep, retry
  5. Validate client size; warn once if mismatch from config
  6. Get client rect
  7. For each event:
     a. Capture ROI → numpy array (in memory only)
     b. Optional blank prefilter (if blank_prefilter: true)
     c. Detector.match() → DetectionResult(score, template_path, location)
     d. Update EventState via rising-edge state machine
     e. If alert fires: sound → toast → Slack (async) → optional debug screenshot
     f. Exceptions in any step: log and continue; count consecutive errors; warn at threshold
  8. Sleep to maintain poll_fps
```

---

## Updated Config Shape

```yaml
# Last War Alert Watcher — Configuration

window_title: "Last War"

# Hard requirement: do not resize the game window after setting these.
window_width: 1280
window_height: 720

# Default: 2 FPS (500ms worst-case detection lag).
# Rationale: Last War alert indicators persist for several seconds. 2 FPS is
# sufficient, minimizes CPU baseline, and keeps this tool imperceptible during
# normal desktop use. Increase to 5 only if you observe brief events that
# disappear in under 1 second.
poll_fps: 2

# true: print confidence scores every poll and save screenshots on detection
debug_mode: false

events:
  - name: "dig_event"

    # Detection mode: only "template" is implemented in v1.
    # Reserved for future modes: baseline_diff, hybrid.
    detection_mode: template

    # Multiple templates: the detector scores all and uses the best match.
    # Use multiple templates when the same event looks different across game
    # states (base view vs. world view, different map backgrounds, etc.).
    templates:
      - "templates/dig_event_base.png"
      # - "templates/dig_event_world.png"  # add more as needed

    roi:
      # Window-relative pixel coordinates (relative to game window client area).
      # PLACEHOLDER — update after running calibrate.py.
      x: 100
      y: 400
      w: 100
      h: 100

    # Confidence threshold 0.0–1.0. Tune after calibration.
    # Rule of thumb: set to (lowest positive-state score observed) minus 0.10.
    threshold: 0.85

    # Number of consecutive frames above threshold before the alert fires.
    # Prevents single-frame false positives. Default: 2.
    # At 2 FPS: 2 hits = event must be visible for ~500ms before alerting.
    # At 5 FPS: 2 hits = ~400ms. Set to 1 only if you need maximum speed and
    # accept a slightly higher false positive rate.
    consecutive_hits_required: 2

    # Seconds before this event can fire again. Secondary anti-spam guard.
    # Rising-edge detection is the primary guard (icon must disappear and
    # reappear for a new alert to fire, even if cooldown has passed).
    cooldown_seconds: 60

    # Optional: skip matchTemplate if the ROI mean brightness is below 10.
    # Helps when the game window is obscured or minimized. Can hurt if the
    # event icon appears against a very dark background — disable in that case.
    blank_prefilter: true

    alert_sound: true
    alert_toast: true
    alert_slack: false
    slack_message: "Dig event detected in Last War"
```

---

## Revised Detector Design

### Grayscale matching (default)
Template matching runs in grayscale by default. Grayscale matching:
- Is more robust to lighting and color-tint variations between game states
- Runs faster (one channel vs. three)
- Is simpler to threshold

Color matching is available if needed (e.g., if the icon color is the primary distinguishing feature from background noise). The `Detector` class accepts a `grayscale: bool = True` parameter.

### Multiple templates
Each event has a list of templates. On every call to `match()`, the detector scores all templates against the frame and returns the best result. This handles visual variants of the same event (different backgrounds, zoom levels, etc.) without separate event entries.

### DetectionResult return type
```python
@dataclass
class DetectionResult:
    score: float             # best confidence across all templates, 0.0–1.0
    template_path: str       # which template produced the best score
    location: tuple[int, int]  # (x, y) of the best match in the frame
```

This allows the watcher loop and calibration tool to log which template matched, and enables future debug overlays.

### Blank-frame prefilter (optional)
`Detector.is_blank(frame, min_brightness=10.0)` checks mean pixel brightness.

**When it helps:** Captures from a minimized or obscured window often return black frames. Skipping matchTemplate on these avoids wasted compute and spurious low-confidence scores.

**When it hurts:** If the event icon appears against a very dark game background (e.g., nighttime world view), a legitimate positive frame may be falsely classified as blank. In that case, set `blank_prefilter: false` for that event in config.

The prefilter is per-event via the `blank_prefilter` config key. It is not applied globally.

---

## Revised Watcher-Loop Logic (pseudocode)

```python
# Startup
set_dpi_aware()
load_dotenv()
config = load_config("config.yaml")
events = load_events(config)          # loads all templates, validates files
event_states = {e.name: EventState() for e in events}
finder = WindowFinder()
capture = ScreenCapture()
alert_mgr = AlertManager()
last_not_found_log = 0.0
last_warned_size = None

# Main loop
while True:
    loop_start = time.time()

    # Window lookup
    hwnd, matched_title = finder.find(config.window_title)  # returns (hwnd, title) or (None, None)
    if hwnd is None:
        if time.time() - last_not_found_log > 60:
            log.warning(f"Window '{config.window_title}' not found")
            last_not_found_log = time.time()
        sleep_remainder(loop_start, poll_interval)
        continue

    if finder.is_minimized(hwnd):
        sleep_remainder(loop_start, poll_interval)
        continue

    # Size validation
    w, h = finder.get_client_size(hwnd)
    if (w, h) != (config.window_width, config.window_height):
        if (w, h) != last_warned_size:
            log.warning(f"Size mismatch: expected {config.window_width}x{config.window_height}, got {w}x{h}")
            last_warned_size = (w, h)
    else:
        last_warned_size = None

    client_rect = finder.get_client_rect(hwnd)

    # Per-event detection
    for evt in events:
        state = event_states[evt.name]

        # Capture
        try:
            frame = capture.capture_roi(client_rect, evt.roi)
        except Exception as e:
            log.error(f"{evt.name}: capture failed: {e}")
            state.consecutive_errors += 1
            _warn_if_errors(state, evt.name, log)
            continue

        # Optional blank prefilter
        if evt.blank_prefilter and Detector.is_blank(frame):
            log.debug(f"{evt.name}: blank frame, skipping")
            continue

        # Detection
        try:
            result = detector_for(evt).match(frame)
        except Exception as e:
            log.error(f"{evt.name}: detection failed: {e}")
            state.consecutive_errors += 1
            _warn_if_errors(state, evt.name, log)
            continue

        state.consecutive_errors = 0
        above = result.score >= evt.threshold

        # Rising-edge state machine
        if above:
            state.consecutive_hits += 1
        else:
            state.consecutive_hits = 0
            state.is_confirmed_present = False

        log.debug(f"{evt.name}: score={result.score:.3f} hits={state.consecutive_hits} template={result.template_path}")

        newly_confirmed = (state.consecutive_hits >= evt.consecutive_hits_required)
        if newly_confirmed and not state.is_confirmed_present:
            state.is_confirmed_present = True
            elapsed = time.time() - state.last_alert_time
            if elapsed >= evt.cooldown_seconds:
                log.info(f"DETECTED: {evt.name} score={result.score:.3f} template={result.template_path}")
                state.last_alert_time = time.time()

                try:
                    if evt.alert_sound:
                        alert_mgr.fire_sound()
                except Exception as e:
                    log.warning(f"Sound alert failed: {e}")

                try:
                    if evt.alert_toast:
                        alert_mgr.fire_toast("Last War Alert", evt.slack_message)
                except Exception as e:
                    log.warning(f"Toast alert failed: {e}")

                if evt.alert_slack and slack_url:
                    alert_mgr.fire_slack(slack_url, evt.slack_message)  # already async

                if config.debug_mode:
                    try:
                        alert_mgr.save_debug_screenshot(frame, evt.name)
                    except Exception as e:
                        log.warning(f"Debug screenshot failed: {e}")

    sleep_remainder(loop_start, poll_interval)
```

`_warn_if_errors` logs a warning when `consecutive_errors` reaches 5, then every 10 after that, to avoid log spam.

---

## File Map

| File | Purpose |
|---|---|
| `window_finder.py` | Locate window by partial title; return (hwnd, matched_title); warn on multiple matches |
| `screen_capture.py` | Translate window-relative ROI to screen coords; capture via mss |
| `detector.py` | Load template list; grayscale match; return DetectionResult |
| `alert_manager.py` | Cooldown tracking; fire sound, toast, Slack; save debug screenshots |
| `event_state.py` | EventState dataclass; rising-edge state machine logic |
| `watcher.py` | Main loop: orchestrate all components at target FPS |
| `calibrate.py` | Phase 1 probe: live confidence scores + optional ROI crop saving |
| `config.yaml` | All runtime settings |
| `.env.template` | Documents SLACK_WEBHOOK_URL |
| `requirements.txt` | All dependencies |
| `tests/test_window_finder.py` | Unit tests for WindowFinder |
| `tests/test_screen_capture.py` | Unit tests for ScreenCapture |
| `tests/test_detector.py` | Unit tests for Detector + DetectionResult |
| `tests/test_alert_manager.py` | Unit tests for AlertManager |
| `tests/test_event_state.py` | Unit tests for rising-edge state machine |
| `tests/test_detector_real_images.py` | Offline regression tests using real game screenshots |

---

## Revised Test Strategy

### Unit tests (mocked, run without the game)
- `test_window_finder.py`: find by substring, case-insensitivity, invisible windows, multiple matches warning, minimized detection, client rect math
- `test_screen_capture.py`: coordinate translation, alpha channel stripping, return type
- `test_detector.py`: multi-template loading, DetectionResult fields, grayscale matching, FileNotFoundError, blank-frame detection
- `test_alert_manager.py`: cooldown logic, sound call, toast call, Slack async POST, error resilience, debug screenshot creation
- `test_event_state.py`: rising-edge triggers alert, persistent icon does NOT re-alert, icon disappears then reappears triggers new alert, cooldown blocks alert after rising edge, consecutive error counting

### Offline regression tests (real images, no game required)
`tests/test_detector_real_images.py` — runs against actual project screenshots.

These tests:
1. Skip automatically if reference images are not found (marked with `pytest.mark.skipif`)
2. Load `SS - Dig.png` (positive reference) and run template matching across the full image
3. Assert that best match score > configured threshold
4. Load `SS - No Dig.png` (negative reference) and run template matching across the full image
5. Assert that best match score < configured threshold
6. If multiple templates are configured, assert at least one scores above threshold on the positive image

These tests are the most important validation in the project. They fail fast if:
- The template crop was done incorrectly
- The threshold is calibrated too high or too low
- A game update changed the icon appearance

Run them after every template recapture or threshold change.

---

## Revised Calibration Strategy

`calibrate.py` supports two modes:

### Interactive mode (default)
```bash
python calibrate.py
```
- Polls the live game window at configured FPS
- Prints a live updating line per event: `score  [HIT]  best_template`
- Useful for finding the right ROI and observing score range

Example output:
```
       dig_event (dig_event_base.png)   dig_event (dig_event_world.png)
          0.312                                  0.287
          0.891  HIT                             0.743
```

### Crop-saving mode
```bash
python calibrate.py --save-crops
```
- Same as interactive mode, but additionally:
  - When a frame scores above `threshold * 0.8` (near-positive), saves the ROI crop to `debug_crops/POSITIVE_<event>_<timestamp>.png`
  - When a frame scores below `threshold * 0.3` (clearly negative), saves to `debug_crops/NEGATIVE_<event>_<timestamp>.png`
  - Caps at 5 positive and 5 negative crops per event (avoids filling disk)
- These crops let you visually confirm the ROI is covering the right area

### Calibration workflow
1. Run `python calibrate.py` with the game in normal state (no event) — observe baseline scores
2. Trigger the event in game — observe peak scores
3. Set `threshold` to (peak score) − 0.10, with a floor above the highest baseline score
4. Verify gap is at least 0.20 between baseline and peak
5. If gap is too small: re-crop the template tighter, or adjust the ROI
6. Run `python calibrate.py --save-crops`, collect positive and negative samples
7. Run `pytest tests/test_detector_real_images.py` to formally validate

---

## Performance Notes

At `poll_fps: 2` with a 100×100 ROI:
- mss capture: < 1ms
- matchTemplate (grayscale, 100×100 frame, 30×30 template): < 1ms
- Total per-poll CPU time: ~3ms
- Across 2 polls/second: ~6ms of CPU per second → effectively 0% of a single core

No continuous disk writes in normal operation. Debug screenshots write only on confirmed detections. There is no background thread actively working between polls.

The primary practical risk is window visibility (another app overlapping the watched region), not CPU or memory pressure.

Toast notifications use `threaded=True` in win10toast and are non-blocking. Slack is dispatched to a daemon thread and returns immediately. Sound (winsound.Beep) is synchronous but completes in ~300ms; it fires first and does not block the poll loop beyond that.

---

## Honest Risks and Open Questions

| Risk | Severity | Status |
|---|---|---|
| Another window covers the watched region | High | Known limitation. Document and accept for v1. |
| Game update changes icon appearance | Medium | User must recapture templates. Fast to fix. |
| Window title doesn't match substring | Medium | Log the exact title on startup so user can correct. |
| Template crop too loose → false positives | Medium | Offline regression tests catch this. |
| Template crop too tight → misses | Medium | Calibration workflow catches this. |
| blank_prefilter masks dark-background icons | Low | Per-event config to disable. |
| win10toast incompatible with some Windows 11 builds | Low | Non-fatal. Sound alert still fires. |
| Multiple windows matching title | Low | First match used, warning logged. |
| mss returns blank for some GPU configurations | Low | Test on real game in Phase 1 before proceeding. |
| Cooldown reset on restart causes double-alert | Low | Acceptable for v1. |

---

## Phased Implementation Plan

### Phase 1: Proof of detection (gate — must pass before proceeding)
- Project scaffold, git init (GitHub setup optional/private)
- WindowFinder + tests
- ScreenCapture + tests
- Detector with multi-template + grayscale + DetectionResult + tests
- EventState + rising-edge state machine + tests
- `calibrate.py` with live scores and crop-saving mode
- Crop template from `SS - Dig.png`, run calibrate against real game
- Offline regression tests (`test_detector_real_images.py`) — must pass
- **Gate:** positive score > threshold, negative score < threshold, gap > 0.20

### Phase 2: Local alerting + main watcher
- AlertManager + tests
- `watcher.py` with full rising-edge loop, exception handling, rate-limited logging
- End-to-end test: run watcher, trigger event, confirm sound + toast fire once on rising edge
- Confirm persistent icon does not re-alert while visible (only cooldown after disappear+reappear)

### Phase 3: Config-driven + robustness
- YAML config for all parameters (templates list, consecutive_hits_required, blank_prefilter)
- Window size validation + warning
- Window title logging (exact match) + multiple-match warning
- DPI awareness at startup
- Exception handling in loop with consecutive error counter + warning

### Phase 4: Slack integration
- SLACK_WEBHOOK_URL from `.env`
- Async dispatch, graceful network failure handling

### Phase 5: Docs + regression test suite locked in
- README with limitations section (visibility constraint, window size, template maintenance)
- CHANGELOG
- All tests passing
- Regression tests committed with reference screenshots

---

## Implementation Tasks (detailed, with code)

---

### Task 1: Project Scaffolding

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `.env.template`
- Create: `config.yaml`
- Create: `templates/.gitkeep`
- Create: `debug_crops/.gitkeep`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create .gitignore**

```
# Secrets
.env
.env.*

# Runtime output — never commit these
debug_screenshots/
debug_crops/

# Logs & cache
logs/
*.log
.claude/settings.local.json

# Python
__pycache__/
*.py[cod]
.venv/
venv/
```

- [ ] **Step 2: Create requirements.txt**

```
pywin32
mss
opencv-python
numpy
PyYAML
python-dotenv
requests
win10toast
pytest
pytest-mock
```

- [ ] **Step 3: Create .env.template**

```
# Copy this file to .env and fill in your values.
# Never commit .env to git.

SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

- [ ] **Step 4: Create config.yaml**

```yaml
window_title: "Last War"
window_width: 1280
window_height: 720
poll_fps: 2
debug_mode: false

events:
  - name: "dig_event"
    detection_mode: template
    templates:
      - "templates/dig_event.png"
    roi:
      x: 100
      y: 400
      w: 100
      h: 100
    threshold: 0.85
    consecutive_hits_required: 2
    cooldown_seconds: 60
    blank_prefilter: true
    alert_sound: true
    alert_toast: true
    alert_slack: false
    slack_message: "Dig event detected in Last War"
```

- [ ] **Step 5: Create placeholder files**

Create empty files at `templates/.gitkeep`, `debug_crops/.gitkeep`, and `tests/__init__.py`.

- [ ] **Step 6: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: no errors. Confirm: `python -c "import cv2, mss, win32gui, yaml; print('OK')"`.

- [ ] **Step 7: Initialize git**

```bash
git init
git branch -M main
git add .gitignore requirements.txt .env.template config.yaml templates/.gitkeep debug_crops/.gitkeep tests/__init__.py docs/
git commit -m "feat: initial project scaffold

Co-Authored-By: Claude <noreply@anthropic.com>"
```

Note: GitHub repo creation is optional. If desired, run:
```bash
gh repo create lastwar-alert-system --private --source=. --remote=origin
git push -u origin main
```

---

### Task 2: WindowFinder

**Files:**
- Create: `window_finder.py`
- Create: `tests/test_window_finder.py`

- [ ] **Step 1: Write failing tests**

`tests/test_window_finder.py`:
```python
from unittest.mock import patch, call
from window_finder import WindowFinder


class TestWindowFinder:
    def _enum_once(self, hwnd):
        def fake_enum(callback, extra):
            callback(hwnd, None)
        return fake_enum

    def _enum_many(self, hwnds):
        def fake_enum(callback, extra):
            for hwnd in hwnds:
                callback(hwnd, None)
        return fake_enum

    def test_find_returns_hwnd_and_title_when_match(self):
        finder = WindowFinder()
        with patch("win32gui.EnumWindows", side_effect=self._enum_once(42)), \
             patch("win32gui.IsWindowVisible", return_value=True), \
             patch("win32gui.GetWindowText", return_value="Last War: Survival"):
            hwnd, title = finder.find("Last War")
        assert hwnd == 42
        assert title == "Last War: Survival"

    def test_find_returns_none_when_no_match(self):
        finder = WindowFinder()
        with patch("win32gui.EnumWindows", side_effect=self._enum_once(42)), \
             patch("win32gui.IsWindowVisible", return_value=True), \
             patch("win32gui.GetWindowText", return_value="Notepad"):
            hwnd, title = finder.find("Last War")
        assert hwnd is None
        assert title is None

    def test_find_ignores_invisible_windows(self):
        finder = WindowFinder()
        with patch("win32gui.EnumWindows", side_effect=self._enum_once(42)), \
             patch("win32gui.IsWindowVisible", return_value=False), \
             patch("win32gui.GetWindowText", return_value="Last War"):
            hwnd, title = finder.find("Last War")
        assert hwnd is None

    def test_find_is_case_insensitive(self):
        finder = WindowFinder()
        with patch("win32gui.EnumWindows", side_effect=self._enum_once(99)), \
             patch("win32gui.IsWindowVisible", return_value=True), \
             patch("win32gui.GetWindowText", return_value="LAST WAR"):
            hwnd, title = finder.find("last war")
        assert hwnd == 99

    def test_find_returns_first_match_when_multiple_exist(self):
        finder = WindowFinder()
        titles = {10: "Last War Instance 1", 20: "Last War Instance 2"}
        def fake_enum(callback, extra):
            callback(10, None)
            callback(20, None)
        with patch("win32gui.EnumWindows", side_effect=fake_enum), \
             patch("win32gui.IsWindowVisible", return_value=True), \
             patch("win32gui.GetWindowText", side_effect=lambda h: titles[h]):
            hwnd, title = finder.find("Last War")
        assert hwnd == 10

    def test_find_reports_multiple_match_count(self):
        finder = WindowFinder()
        titles = {10: "Last War A", 20: "Last War B"}
        def fake_enum(callback, extra):
            callback(10, None)
            callback(20, None)
        with patch("win32gui.EnumWindows", side_effect=fake_enum), \
             patch("win32gui.IsWindowVisible", return_value=True), \
             patch("win32gui.GetWindowText", side_effect=lambda h: titles[h]):
            hwnd, title = finder.find("Last War")
        assert finder.last_match_count == 2

    def test_is_minimized_true_when_iconic(self):
        finder = WindowFinder()
        with patch("win32gui.IsIconic", return_value=True):
            assert finder.is_minimized(42) is True

    def test_is_minimized_false_when_not_iconic(self):
        finder = WindowFinder()
        with patch("win32gui.IsIconic", return_value=False):
            assert finder.is_minimized(42) is False

    def test_get_client_size_returns_width_and_height(self):
        finder = WindowFinder()
        with patch("win32gui.GetClientRect", return_value=(0, 0, 1280, 720)):
            w, h = finder.get_client_size(42)
        assert w == 1280
        assert h == 720

    def test_get_client_rect_combines_origin_and_size(self):
        finder = WindowFinder()
        finder.get_client_size = lambda hwnd: (1280, 720)
        finder._client_to_screen = lambda hwnd: (10, 30)
        rect = finder.get_client_rect(42)
        assert rect == (10, 30, 1290, 750)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_window_finder.py -v
```

Expected: `ModuleNotFoundError: No module named 'window_finder'` or import error.

- [ ] **Step 3: Write window_finder.py**

```python
import ctypes
import ctypes.wintypes

import win32gui


class WindowFinder:
    def __init__(self):
        self.last_match_count: int = 0

    def find(self, title_substring: str) -> tuple[int | None, str | None]:
        """
        Returns (hwnd, exact_title) for the first visible matching window,
        or (None, None) if not found. Sets self.last_match_count.
        """
        found: list[tuple[int, str]] = []

        def callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if title_substring.lower() in title.lower():
                found.append((hwnd, title))

        win32gui.EnumWindows(callback, None)
        self.last_match_count = len(found)
        if not found:
            return None, None
        return found[0]

    def is_minimized(self, hwnd: int) -> bool:
        return bool(win32gui.IsIconic(hwnd))

    def get_client_size(self, hwnd: int) -> tuple[int, int]:
        rect = win32gui.GetClientRect(hwnd)
        return (rect[2], rect[3])

    def get_client_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        w, h = self.get_client_size(hwnd)
        left, top = self._client_to_screen(hwnd)
        return (left, top, left + w, top + h)

    def _client_to_screen(self, hwnd: int) -> tuple[int, int]:
        pt = ctypes.wintypes.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
        return (pt.x, pt.y)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_window_finder.py -v
```

Expected: 10 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add window_finder.py tests/test_window_finder.py
git commit -m "feat: add WindowFinder with partial title match, multiple-match tracking

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: ScreenCapture

**Files:**
- Create: `screen_capture.py`
- Create: `tests/test_screen_capture.py`

- [ ] **Step 1: Write failing tests**

`tests/test_screen_capture.py`:
```python
import numpy as np
from unittest.mock import patch, MagicMock
from screen_capture import ScreenCapture


class TestScreenCapture:
    def test_capture_roi_translates_window_relative_coords(self):
        captured_monitor = {}

        def fake_grab(monitor):
            captured_monitor.update(monitor)
            return np.zeros((monitor["height"], monitor["width"], 4), dtype=np.uint8)

        with patch("mss.mss") as mock_mss_cls:
            mock_mss_cls.return_value = MagicMock()
            cap = ScreenCapture()
            cap._sct.grab = fake_grab
            cap.capture_roi((100, 200, 1380, 920), {"x": 50, "y": 30, "w": 80, "h": 60})

        assert captured_monitor["left"] == 150    # 100 + 50
        assert captured_monitor["top"] == 230     # 200 + 30
        assert captured_monitor["width"] == 80
        assert captured_monitor["height"] == 60

    def test_capture_roi_strips_alpha_channel(self):
        def fake_grab(monitor):
            return np.zeros((monitor["height"], monitor["width"], 4), dtype=np.uint8)

        with patch("mss.mss") as mock_mss_cls:
            mock_mss_cls.return_value = MagicMock()
            cap = ScreenCapture()
            cap._sct.grab = fake_grab
            result = cap.capture_roi((0, 0, 1280, 720), {"x": 10, "y": 10, "w": 50, "h": 40})

        assert result.shape == (40, 50, 3)

    def test_capture_roi_returns_uint8_numpy_array(self):
        def fake_grab(monitor):
            return np.zeros((monitor["height"], monitor["width"], 4), dtype=np.uint8)

        with patch("mss.mss") as mock_mss_cls:
            mock_mss_cls.return_value = MagicMock()
            cap = ScreenCapture()
            cap._sct.grab = fake_grab
            result = cap.capture_roi((0, 0, 1280, 720), {"x": 0, "y": 0, "w": 100, "h": 100})

        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_screen_capture.py -v
```

Expected: `ModuleNotFoundError: No module named 'screen_capture'`

- [ ] **Step 3: Write screen_capture.py**

```python
import mss
import numpy as np


class ScreenCapture:
    def __init__(self):
        self._sct = mss.mss()

    def capture_roi(
        self,
        client_rect: tuple[int, int, int, int],
        roi: dict,
    ) -> np.ndarray:
        """
        client_rect: (left, top, right, bottom) of the game window client area
                     in screen coordinates.
        roi: dict with x, y, w, h relative to the client area top-left.
        Returns a BGR numpy array (alpha channel stripped).
        """
        monitor = {
            "top": client_rect[1] + roi["y"],
            "left": client_rect[0] + roi["x"],
            "width": roi["w"],
            "height": roi["h"],
        }
        screenshot = self._sct.grab(monitor)
        img = np.array(screenshot)
        return img[:, :, :3]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_screen_capture.py -v
```

Expected: 3 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add screen_capture.py tests/test_screen_capture.py
git commit -m "feat: add ScreenCapture with window-relative ROI translation

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Detector

**Files:**
- Create: `detector.py`
- Create: `tests/test_detector.py`

- [ ] **Step 1: Write failing tests**

`tests/test_detector.py`:
```python
import os
import tempfile

import cv2
import numpy as np
import pytest

from detector import Detector, DetectionResult


class TestDetector:
    def _write_template(self, color: tuple, size: tuple = (20, 20)) -> str:
        img = np.full((size[1], size[0], 3), color, dtype=np.uint8)
        path = tempfile.mktemp(suffix=".png")
        cv2.imwrite(path, img)
        return path

    def test_match_returns_detection_result(self):
        path = self._write_template(color=(0, 200, 0))
        try:
            detector = Detector([path])
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            result = detector.match(frame)
            assert isinstance(result, DetectionResult)
            assert isinstance(result.score, float)
            assert isinstance(result.template_path, str)
            assert isinstance(result.location, tuple) and len(result.location) == 2
        finally:
            os.unlink(path)

    def test_match_returns_high_confidence_when_template_present(self):
        path = self._write_template(color=(0, 200, 0), size=(20, 20))
        try:
            detector = Detector([path])
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[10:30, 10:30] = (0, 200, 0)
            result = detector.match(frame)
            assert result.score > 0.95
            assert result.template_path == path
        finally:
            os.unlink(path)

    def test_match_returns_low_confidence_when_template_absent(self):
        path = self._write_template(color=(0, 200, 0))
        try:
            detector = Detector([path])
            frame = np.full((100, 100, 3), 128, dtype=np.uint8)
            result = detector.match(frame)
            assert result.score < 0.5
        finally:
            os.unlink(path)

    def test_match_returns_zero_when_frame_smaller_than_template(self):
        path = self._write_template(color=(0, 200, 0), size=(50, 50))
        try:
            detector = Detector([path])
            frame = np.zeros((20, 20, 3), dtype=np.uint8)
            result = detector.match(frame)
            assert result.score == 0.0
        finally:
            os.unlink(path)

    def test_match_picks_best_score_across_multiple_templates(self):
        path_good = self._write_template(color=(0, 200, 0), size=(20, 20))
        path_bad = self._write_template(color=(200, 0, 0), size=(20, 20))
        try:
            detector = Detector([path_bad, path_good])
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[10:30, 10:30] = (0, 200, 0)    # matches path_good only
            result = detector.match(frame)
            assert result.score > 0.95
            assert result.template_path == path_good
        finally:
            os.unlink(path_good)
            os.unlink(path_bad)

    def test_raises_file_not_found_for_missing_template(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            Detector(["nonexistent_xyz.png"])

    def test_raises_value_error_for_empty_template_list(self):
        with pytest.raises(ValueError, match="at least one"):
            Detector([])

    def test_is_blank_true_for_dark_frame(self):
        assert Detector.is_blank(np.zeros((100, 100, 3), dtype=np.uint8)) is True

    def test_is_blank_false_for_bright_frame(self):
        assert Detector.is_blank(np.full((100, 100, 3), 128, dtype=np.uint8)) is False

    def test_is_blank_respects_custom_threshold(self):
        mid = np.full((10, 10, 3), 20, dtype=np.uint8)
        assert Detector.is_blank(mid, min_brightness=30.0) is True
        assert Detector.is_blank(mid, min_brightness=10.0) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_detector.py -v
```

Expected: `ModuleNotFoundError: No module named 'detector'`

- [ ] **Step 3: Write detector.py**

```python
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class DetectionResult:
    score: float
    template_path: str
    location: tuple[int, int]


class Detector:
    def __init__(self, template_paths: list[str], grayscale: bool = True):
        if not template_paths:
            raise ValueError("Detector requires at least one template path.")
        self._grayscale = grayscale
        self._templates: list[tuple[str, np.ndarray]] = []
        for path in template_paths:
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is None:
                raise FileNotFoundError(f"Template not found: {path}")
            if grayscale:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            self._templates.append((path, img))

    def match(self, frame: np.ndarray) -> DetectionResult:
        if self._grayscale:
            frame_to_match = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            frame_to_match = frame

        best = DetectionResult(score=0.0, template_path="", location=(0, 0))

        for path, template in self._templates:
            th, tw = template.shape[:2]
            fh, fw = frame_to_match.shape[:2]
            if fh < th or fw < tw:
                continue
            result = cv2.matchTemplate(frame_to_match, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if float(max_val) > best.score:
                best = DetectionResult(
                    score=float(max_val),
                    template_path=path,
                    location=(max_loc[0], max_loc[1]),
                )

        return best

    @staticmethod
    def is_blank(frame: np.ndarray, min_brightness: float = 10.0) -> bool:
        return float(np.mean(frame)) < min_brightness
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_detector.py -v
```

Expected: 10 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add detector.py tests/test_detector.py
git commit -m "feat: add Detector with multi-template grayscale matching and DetectionResult

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: EventState and Rising-Edge Logic

**Files:**
- Create: `event_state.py`
- Create: `tests/test_event_state.py`

- [ ] **Step 1: Write failing tests**

`tests/test_event_state.py`:
```python
import time
from event_state import EventState


class TestEventState:
    def test_initial_state_is_absent(self):
        state = EventState()
        assert state.consecutive_hits == 0
        assert state.is_confirmed_present is False

    def test_update_above_threshold_increments_hits(self):
        state = EventState()
        state.update(above_threshold=True)
        assert state.consecutive_hits == 1
        assert state.is_confirmed_present is False

    def test_update_below_threshold_resets_hits_and_presence(self):
        state = EventState()
        state.consecutive_hits = 3
        state.is_confirmed_present = True
        state.update(above_threshold=False)
        assert state.consecutive_hits == 0
        assert state.is_confirmed_present is False

    def test_rising_edge_fires_when_hits_reach_required(self):
        state = EventState()
        state.update(above_threshold=True)   # hit 1
        fired = state.update(above_threshold=True, consecutive_hits_required=2)  # hit 2
        assert fired is True
        assert state.is_confirmed_present is True

    def test_rising_edge_does_not_fire_again_while_icon_stays_present(self):
        state = EventState()
        state.update(above_threshold=True)
        state.update(above_threshold=True, consecutive_hits_required=2)  # fires once
        fired_again = state.update(above_threshold=True, consecutive_hits_required=2)
        assert fired_again is False

    def test_rising_edge_fires_again_after_icon_disappears_and_returns(self):
        state = EventState()
        # First detection
        state.update(above_threshold=True)
        state.update(above_threshold=True, consecutive_hits_required=2)
        # Icon disappears
        state.update(above_threshold=False)
        assert state.is_confirmed_present is False
        # Icon returns
        state.update(above_threshold=True)
        fired = state.update(above_threshold=True, consecutive_hits_required=2)
        assert fired is True

    def test_rising_edge_blocked_by_cooldown(self):
        state = EventState()
        state.last_alert_time = time.time()   # just alerted
        state.update(above_threshold=True)
        fired = state.update(above_threshold=True, consecutive_hits_required=2, cooldown_seconds=60)
        assert fired is False

    def test_rising_edge_fires_after_cooldown_expires(self):
        state = EventState()
        state.last_alert_time = time.time() - 61   # cooldown elapsed
        state.update(above_threshold=True)
        fired = state.update(above_threshold=True, consecutive_hits_required=2, cooldown_seconds=60)
        assert fired is True

    def test_consecutive_error_tracking(self):
        state = EventState()
        state.consecutive_errors = 4
        state.increment_error()
        assert state.consecutive_errors == 5
        state.clear_errors()
        assert state.consecutive_errors == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_event_state.py -v
```

Expected: `ModuleNotFoundError: No module named 'event_state'`

- [ ] **Step 3: Write event_state.py**

```python
import time


class EventState:
    def __init__(self):
        self.consecutive_hits: int = 0
        self.is_confirmed_present: bool = False
        self.last_alert_time: float = 0.0
        self.consecutive_errors: int = 0

    def update(
        self,
        above_threshold: bool,
        consecutive_hits_required: int = 1,
        cooldown_seconds: int = 0,
    ) -> bool:
        """
        Advance the state machine. Returns True if a rising-edge alert should fire,
        False otherwise.
        """
        if above_threshold:
            self.consecutive_hits += 1
        else:
            self.consecutive_hits = 0
            self.is_confirmed_present = False
            return False

        newly_confirmed = self.consecutive_hits >= consecutive_hits_required
        if not newly_confirmed or self.is_confirmed_present:
            return False

        self.is_confirmed_present = True
        elapsed = time.time() - self.last_alert_time
        if elapsed < cooldown_seconds:
            return False

        self.last_alert_time = time.time()
        return True

    def increment_error(self) -> None:
        self.consecutive_errors += 1

    def clear_errors(self) -> None:
        self.consecutive_errors = 0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_event_state.py -v
```

Expected: 9 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add event_state.py tests/test_event_state.py
git commit -m "feat: add EventState rising-edge state machine

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: AlertManager

**Files:**
- Create: `alert_manager.py`
- Create: `tests/test_alert_manager.py`

- [ ] **Step 1: Write failing tests**

`tests/test_alert_manager.py`:
```python
import time

import numpy as np
from unittest.mock import patch, MagicMock

from alert_manager import AlertManager


class TestAlertManager:
    def test_fire_sound_calls_winsound_beep(self):
        mgr = AlertManager()
        with patch("winsound.Beep") as mock_beep:
            mgr.fire_sound()
            mock_beep.assert_called_once_with(1000, 300)

    def test_fire_sound_does_not_raise_on_failure(self):
        mgr = AlertManager()
        with patch("winsound.Beep", side_effect=Exception("audio error")):
            mgr.fire_sound()   # should not raise

    def test_fire_toast_does_not_raise_when_unavailable(self):
        mgr = AlertManager()
        with patch("alert_manager._TOAST_AVAILABLE", False):
            mgr.fire_toast("Title", "Message")

    def test_fire_toast_calls_show_toast_when_available(self):
        mgr = AlertManager()
        mock_notifier = MagicMock()
        with patch("alert_manager._TOAST_AVAILABLE", True), \
             patch("alert_manager.ToastNotifier", return_value=mock_notifier):
            mgr.fire_toast("Last War Alert", "Test message")
        mock_notifier.show_toast.assert_called_once_with(
            "Last War Alert", "Test message", duration=5, threaded=True
        )

    def test_fire_toast_does_not_raise_on_notifier_failure(self):
        mgr = AlertManager()
        with patch("alert_manager._TOAST_AVAILABLE", True), \
             patch("alert_manager.ToastNotifier", side_effect=Exception("toast error")):
            mgr.fire_toast("Title", "Message")   # should not raise

    def test_fire_slack_posts_to_webhook_asynchronously(self):
        mgr = AlertManager()
        with patch("requests.post") as mock_post:
            mgr.fire_slack("https://hooks.slack.com/fake", "Alert")
            time.sleep(0.2)
            mock_post.assert_called_once_with(
                "https://hooks.slack.com/fake",
                json={"text": "Alert"},
                timeout=10,
            )

    def test_fire_slack_does_not_raise_on_network_error(self):
        mgr = AlertManager()
        with patch("requests.post", side_effect=Exception("network down")):
            mgr.fire_slack("https://hooks.slack.com/fake", "Alert")
            time.sleep(0.2)

    def test_save_debug_screenshot_creates_file_with_event_name(self, tmp_path):
        mgr = AlertManager(debug_dir=str(tmp_path))
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mgr.save_debug_screenshot(frame, "dig_event")
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert "dig_event" in files[0].name
        assert files[0].suffix == ".png"

    def test_save_debug_screenshot_does_not_raise_on_write_failure(self, tmp_path):
        mgr = AlertManager(debug_dir=str(tmp_path))
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        with patch("cv2.imwrite", return_value=False):
            mgr.save_debug_screenshot(frame, "dig_event")   # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_alert_manager.py -v
```

Expected: `ModuleNotFoundError: No module named 'alert_manager'`

- [ ] **Step 3: Write alert_manager.py**

```python
import os
import threading
from datetime import datetime

import cv2
import numpy as np
import requests
import winsound

try:
    from win10toast import ToastNotifier
    _TOAST_AVAILABLE = True
except ImportError:
    _TOAST_AVAILABLE = False


class AlertManager:
    def __init__(self, debug_dir: str = "debug_screenshots"):
        self._debug_dir = debug_dir

    def fire_sound(self) -> None:
        try:
            winsound.Beep(1000, 300)
        except Exception:
            pass

    def fire_toast(self, title: str, message: str) -> None:
        if not _TOAST_AVAILABLE:
            return
        try:
            notifier = ToastNotifier()
            notifier.show_toast(title, message, duration=5, threaded=True)
        except Exception:
            pass

    def fire_slack(self, webhook_url: str, message: str) -> None:
        def _send():
            try:
                requests.post(webhook_url, json={"text": message}, timeout=10)
            except Exception:
                pass

        threading.Thread(target=_send, daemon=True).start()

    def save_debug_screenshot(self, frame: np.ndarray, event_name: str) -> None:
        try:
            os.makedirs(self._debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = os.path.join(self._debug_dir, f"{event_name}_{timestamp}.png")
            cv2.imwrite(filename, frame)
        except Exception:
            pass
```

- [ ] **Step 4: Run the full test suite so far**

```bash
pytest tests/ -v
```

Expected: all tests PASSED (window_finder, screen_capture, detector, event_state, alert_manager).

- [ ] **Step 5: Commit**

```bash
git add alert_manager.py tests/test_alert_manager.py
git commit -m "feat: add AlertManager with sound, toast, Slack, and debug screenshot

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: Offline Regression Tests (Phase 1 Gate — Part 1)

**Files:**
- Create: `tests/test_detector_real_images.py`

These tests use the actual game screenshots from the project root. They are the most important correctness validation in the project. They skip automatically if template files or reference screenshots are not yet present.

- [ ] **Step 1: Crop template from reference screenshot**

Open `SS - Dig.png` in any image editor. Crop the dig event icon tightly (as little background as possible). Save as `templates/dig_event.png`.

- [ ] **Step 2: Write regression tests**

`tests/test_detector_real_images.py`:
```python
"""
Offline regression tests using real game screenshots.

These tests validate that:
  1. The template scores above threshold on the positive reference screenshot.
  2. The template scores below threshold on the negative reference screenshot.

They skip automatically if reference images or templates are not present.
Run these tests after every template recapture or threshold change.
"""

import os

import cv2
import pytest

from detector import Detector

POSITIVE_REF = "SS - Dig.png"
NEGATIVE_REF = "SS - No Dig.png"
TEMPLATE_PATH = "templates/dig_event.png"
THRESHOLD = 0.85


@pytest.mark.skipif(
    not os.path.exists(POSITIVE_REF) or not os.path.exists(TEMPLATE_PATH),
    reason="Reference screenshot or template not found",
)
def test_template_scores_above_threshold_on_positive_screenshot():
    detector = Detector([TEMPLATE_PATH])
    frame = cv2.imread(POSITIVE_REF, cv2.IMREAD_COLOR)
    assert frame is not None, f"Could not load {POSITIVE_REF}"
    result = detector.match(frame)
    assert result.score >= THRESHOLD, (
        f"Expected score >= {THRESHOLD} on positive ref, got {result.score:.3f}. "
        "Re-crop the template or re-tune the threshold."
    )


@pytest.mark.skipif(
    not os.path.exists(NEGATIVE_REF) or not os.path.exists(TEMPLATE_PATH),
    reason="Reference screenshot or template not found",
)
def test_template_scores_below_threshold_on_negative_screenshot():
    detector = Detector([TEMPLATE_PATH])
    frame = cv2.imread(NEGATIVE_REF, cv2.IMREAD_COLOR)
    assert frame is not None, f"Could not load {NEGATIVE_REF}"
    result = detector.match(frame)
    assert result.score < THRESHOLD, (
        f"Expected score < {THRESHOLD} on negative ref, got {result.score:.3f}. "
        "Template may be too generic — re-crop more tightly."
    )


@pytest.mark.skipif(
    not os.path.exists(POSITIVE_REF) or not os.path.exists(TEMPLATE_PATH),
    reason="Reference screenshot or template not found",
)
def test_score_gap_between_positive_and_negative_is_sufficient():
    """Gap must be at least 0.20 to give reliable threshold headroom."""
    detector = Detector([TEMPLATE_PATH])

    pos_frame = cv2.imread(POSITIVE_REF, cv2.IMREAD_COLOR)
    neg_frame = cv2.imread(NEGATIVE_REF, cv2.IMREAD_COLOR)

    pos_score = detector.match(pos_frame).score
    neg_score = detector.match(neg_frame).score
    gap = pos_score - neg_score

    assert gap >= 0.20, (
        f"Score gap too small: positive={pos_score:.3f}, negative={neg_score:.3f}, "
        f"gap={gap:.3f}. Need >= 0.20. Re-crop template or adjust ROI."
    )
```

- [ ] **Step 3: Run regression tests**

```bash
pytest tests/test_detector_real_images.py -v
```

If tests are skipped: the template crop (`templates/dig_event.png`) is not done yet — go back and crop it.

If tests fail: the template crop is too loose, wrong icon, or threshold is miscalibrated. Re-crop and re-run.

**Do not proceed to Task 8 until all three regression tests PASS.**

- [ ] **Step 4: Commit**

```bash
git add tests/test_detector_real_images.py templates/dig_event.png
git commit -m "test: add offline regression tests; add dig_event template

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: Calibration Probe (Phase 1 Gate — Part 2)

**Files:**
- Create: `calibrate.py`

- [ ] **Step 1: Write calibrate.py**

```python
"""
Calibration probe — prints live confidence scores; optionally saves ROI crops.

Usage:
    python calibrate.py               # live scoring only
    python calibrate.py --save-crops  # also save positive/negative ROI crops

Crops are saved to debug_crops/ and are useful for visual debugging.
Caps at 5 positive and 5 negative crops per event to avoid filling disk.
"""

import argparse
import ctypes
import os
import sys
import time
from datetime import datetime

import cv2
import yaml

from detector import Detector
from screen_capture import ScreenCapture
from window_finder import WindowFinder


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def save_crop(frame, label: str, event_name: str, debug_dir: str) -> None:
    os.makedirs(debug_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(debug_dir, f"{label}_{event_name}_{ts}.png")
    cv2.imwrite(path, frame)


def main() -> None:
    set_dpi_aware()

    parser = argparse.ArgumentParser()
    parser.add_argument("--save-crops", action="store_true")
    args = parser.parse_args()

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    window_title: str = config["window_title"]
    poll_fps: int = config.get("poll_fps", 2)
    poll_interval = 1.0 / poll_fps
    debug_dir = "debug_crops"

    events = config.get("events", [])
    if not events:
        print("No events in config.yaml.")
        sys.exit(1)

    detectors: list[tuple[dict, Detector]] = []
    for evt in events:
        try:
            detectors.append((evt, Detector(evt["templates"])))
            print(f"Loaded {len(evt['templates'])} template(s) for '{evt['name']}'")
        except (FileNotFoundError, ValueError) as e:
            print(f"WARNING: {e} — skipping '{evt['name']}'")

    if not detectors:
        print("No templates loaded.")
        sys.exit(1)

    # Crop counters per event
    pos_counts = {d[0]["name"]: 0 for d in detectors}
    neg_counts = {d[0]["name"]: 0 for d in detectors}
    CROP_CAP = 5

    finder = WindowFinder()
    capture = ScreenCapture()

    print(f"\nCalibration mode — polling '{window_title}' at {poll_fps} FPS")
    if args.save_crops:
        print(f"Saving crops to {debug_dir}/ (max {CROP_CAP} pos + {CROP_CAP} neg per event)")
    print("Press Ctrl+C to stop.\n")

    col_headers = "  ".join(f"{d[0]['name']:>28}" for d in detectors)
    print(f"  {col_headers}")

    try:
        while True:
            hwnd, matched = finder.find(window_title)
            if hwnd is None:
                print(f"\r{'[window not found]':>40}", end="", flush=True)
                time.sleep(1)
                continue
            if finder.is_minimized(hwnd):
                print(f"\r{'[minimized]':>40}", end="", flush=True)
                time.sleep(1)
                continue

            client_rect = finder.get_client_rect(hwnd)
            cols = []

            for evt, detector in detectors:
                name = evt["name"]
                frame = capture.capture_roi(client_rect, evt["roi"])
                result = detector.match(frame)
                threshold = evt["threshold"]
                hit = " HIT" if result.score >= threshold else "    "
                template_short = os.path.basename(result.template_path)
                cols.append(f"{result.score:.3f}{hit} [{template_short}]")

                if args.save_crops:
                    if result.score >= threshold * 0.8 and pos_counts[name] < CROP_CAP:
                        save_crop(frame, "POSITIVE", name, debug_dir)
                        pos_counts[name] += 1
                    elif result.score < threshold * 0.3 and neg_counts[name] < CROP_CAP:
                        save_crop(frame, "NEGATIVE", name, debug_dir)
                        neg_counts[name] += 1

            line = "  ".join(f"{c:>28}" for c in cols)
            print(f"\r{line}", end="", flush=True)
            time.sleep(poll_interval)

    except KeyboardInterrupt:
        print("\nCalibration stopped.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run calibrate.py against the real game**

```bash
python calibrate.py
```

Observe scores in both game states:
- No event visible: score should be below 0.50, ideally below 0.30
- Event visible: score should be above 0.90
- Gap must be >= 0.20

If gap is insufficient: re-crop the template, adjust the ROI, or add a second template variant.

- [ ] **Step 3: Run calibrate.py with crop saving and inspect the output**

```bash
python calibrate.py --save-crops
```

Open `debug_crops/` and visually confirm:
- POSITIVE crops contain the event icon
- NEGATIVE crops show the normal background with no icon

- [ ] **Step 4: Re-run regression tests to confirm they still pass after any ROI/template adjustments**

```bash
pytest tests/test_detector_real_images.py -v
```

Expected: 3 tests PASSED.

- [ ] **Step 5: Update config.yaml with correct ROI and threshold if adjusted**

- [ ] **Step 6: Commit**

```bash
git add calibrate.py config.yaml
git commit -m "feat: add calibration probe with crop saving

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: Main Watcher Loop

**Files:**
- Create: `watcher.py`

- [ ] **Step 1: Copy .env from template**

```bash
cp .env.template .env
```

Add `SLACK_WEBHOOK_URL` if available. Leave blank otherwise.

- [ ] **Step 2: Write watcher.py**

```python
"""
Last War Alert Watcher — main entry point.

Run:   python watcher.py
Stop:  Ctrl+C
"""

import ctypes
import logging
import os
import sys
import time
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv

from alert_manager import AlertManager
from detector import Detector
from event_state import EventState
from screen_capture import ScreenCapture
from window_finder import WindowFinder


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def setup_logging(debug: bool) -> logging.Logger:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("watcher")


@dataclass
class EventConfig:
    name: str
    templates: list[str]
    roi: dict
    threshold: float
    consecutive_hits_required: int
    cooldown_seconds: int
    blank_prefilter: bool
    alert_sound: bool
    alert_toast: bool
    alert_slack: bool
    slack_message: str
    detector: Detector = field(init=False)

    def __post_init__(self):
        self.detector = Detector(self.templates)


def load_events(config: dict, log: logging.Logger) -> list[EventConfig]:
    loaded = []
    for raw in config.get("events", []):
        try:
            evt = EventConfig(
                name=raw["name"],
                templates=raw["templates"],
                roi=raw["roi"],
                threshold=raw["threshold"],
                consecutive_hits_required=raw.get("consecutive_hits_required", 2),
                cooldown_seconds=raw.get("cooldown_seconds", 60),
                blank_prefilter=raw.get("blank_prefilter", True),
                alert_sound=raw.get("alert_sound", True),
                alert_toast=raw.get("alert_toast", True),
                alert_slack=raw.get("alert_slack", False),
                slack_message=raw.get("slack_message", raw["name"]),
            )
            loaded.append(evt)
            log.info(f"Loaded '{evt.name}' with {len(evt.templates)} template(s)")
        except (FileNotFoundError, ValueError, KeyError) as e:
            log.error(f"Skipping event '{raw.get('name', '?')}': {e}")
    return loaded


def _warn_if_errors(state: EventState, name: str, log: logging.Logger) -> None:
    n = state.consecutive_errors
    if n == 5 or (n > 5 and n % 10 == 0):
        log.warning(f"{name}: {n} consecutive capture/detect errors")


def main() -> None:
    set_dpi_aware()
    load_dotenv()

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    debug_mode: bool = config.get("debug_mode", False)
    log = setup_logging(debug_mode)

    window_title: str = config["window_title"]
    expected_w: int = config["window_width"]
    expected_h: int = config["window_height"]
    poll_fps: int = config.get("poll_fps", 2)
    poll_interval = 1.0 / poll_fps
    slack_url: str = os.getenv("SLACK_WEBHOOK_URL", "")

    events = load_events(config, log)
    if not events:
        log.error("No events loaded. Check config.yaml and template files.")
        sys.exit(1)

    event_states = {evt.name: EventState() for evt in events}
    finder = WindowFinder()
    capture = ScreenCapture()
    alert_mgr = AlertManager(debug_dir="debug_screenshots")

    log.info(f"Watching '{window_title}' at {poll_fps} FPS. Ctrl+C to stop.")

    last_not_found_log: float = 0.0
    last_warned_size: tuple | None = None
    logged_window_title: bool = False

    try:
        while True:
            loop_start = time.time()

            hwnd, matched_title = finder.find(window_title)

            if hwnd is None:
                logged_window_title = False
                now = time.time()
                if now - last_not_found_log > 60:
                    log.warning(f"Window '{window_title}' not found — will retry")
                    last_not_found_log = now
                time.sleep(max(0.0, poll_interval - (time.time() - loop_start)))
                continue

            if not logged_window_title:
                log.info(f"Window found: '{matched_title}'")
                if finder.last_match_count > 1:
                    log.warning(
                        f"{finder.last_match_count} windows match '{window_title}'. "
                        "Using first match. Close duplicate windows if detection is unreliable."
                    )
                logged_window_title = True

            if finder.is_minimized(hwnd):
                time.sleep(max(0.0, poll_interval - (time.time() - loop_start)))
                continue

            w, h = finder.get_client_size(hwnd)
            if (w, h) != (expected_w, expected_h) and (w, h) != last_warned_size:
                log.warning(
                    f"Window size mismatch: expected {expected_w}x{expected_h}, "
                    f"got {w}x{h}. ROIs and templates may be misaligned."
                )
                last_warned_size = (w, h)
            elif (w, h) == (expected_w, expected_h):
                last_warned_size = None

            client_rect = finder.get_client_rect(hwnd)

            for evt in events:
                state = event_states[evt.name]

                try:
                    frame = capture.capture_roi(client_rect, evt.roi)
                    state.clear_errors()
                except Exception as e:
                    log.error(f"{evt.name}: capture failed: {e}")
                    state.increment_error()
                    _warn_if_errors(state, evt.name, log)
                    continue

                if evt.blank_prefilter and Detector.is_blank(frame):
                    log.debug(f"{evt.name}: blank frame, skipping")
                    continue

                try:
                    result = evt.detector.match(frame)
                    state.clear_errors()
                except Exception as e:
                    log.error(f"{evt.name}: detection failed: {e}")
                    state.increment_error()
                    _warn_if_errors(state, evt.name, log)
                    continue

                above = result.score >= evt.threshold
                log.debug(
                    f"{evt.name}: score={result.score:.3f} "
                    f"hits={state.consecutive_hits} "
                    f"template={os.path.basename(result.template_path)}"
                )

                should_alert = state.update(
                    above_threshold=above,
                    consecutive_hits_required=evt.consecutive_hits_required,
                    cooldown_seconds=evt.cooldown_seconds,
                )

                if should_alert:
                    log.info(
                        f"DETECTED: {evt.name} "
                        f"score={result.score:.3f} "
                        f"template={os.path.basename(result.template_path)}"
                    )

                    if evt.alert_sound:
                        alert_mgr.fire_sound()

                    if evt.alert_toast:
                        alert_mgr.fire_toast("Last War Alert", evt.slack_message)

                    if evt.alert_slack and slack_url:
                        alert_mgr.fire_slack(slack_url, evt.slack_message)

                    if debug_mode:
                        alert_mgr.save_debug_screenshot(frame, evt.name)

            time.sleep(max(0.0, poll_interval - (time.time() - loop_start)))

    except KeyboardInterrupt:
        log.info("Watcher stopped.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the watcher against the real game**

```bash
python watcher.py
```

Expected idle log:
```
10:23:01 INFO     Loaded 'dig_event' with 1 template(s)
10:23:01 INFO     Watching 'Last War' at 2 FPS. Ctrl+C to stop.
10:23:01 INFO     Window found: 'Last War: Survival'
```

Expected on detection:
```
10:23:45 INFO     DETECTED: dig_event score=0.923 template=dig_event.png
```
Followed by a beep and a Windows toast.

- [ ] **Step 4: Verify rising-edge behavior**

Trigger the event and confirm:
1. Alert fires once on first confirmed detection
2. Alert does NOT fire repeatedly while the icon remains on screen
3. After the icon disappears, trigger it again — alert fires again

- [ ] **Step 5: Verify debug mode**

Set `debug_mode: true` in `config.yaml`, restart. Confirm per-poll confidence scores appear and a screenshot is saved on detection. Revert `debug_mode: false`.

- [ ] **Step 6: Commit**

```bash
git add watcher.py .env.template
git commit -m "feat: add main watcher with rising-edge detection and exception recovery

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 10: README, CHANGELOG, Final Validation

**Files:**
- Create: `README.md`
- Create: `CHANGELOG.md`

- [ ] **Step 1: Final test suite run**

```bash
pytest tests/ -v
```

Expected: all tests PASSED, zero failures.

- [ ] **Step 2: Write README.md**

```markdown
# Last War Alert Watcher

A lightweight Windows background tool that watches the Last War game window and
fires an immediate local alert (sound + toast) when a known event icon appears,
triggering on the rising edge only — one alert per event appearance.

## Requirements

- Windows 10/11
- Python 3.11+
- Last War running in windowed mode at a **fixed, consistent window size**

## Known Limitations

**The game window's watched region must be visible and unobstructed.**
v1 captures the screen compositor image. If another window overlaps the watched
region, the capture sees the overlapping window, not the game — this will cause
missed detections or false positives. Keep the Last War watched region clear while
the watcher is running.

**Do not resize the game window after configuring.** All ROI coordinates and
template images are tied to a specific window size. Resizing breaks detection
silently. If you must resize, recapture all templates and re-tune all ROIs.

**Game updates may change icon appearance.** If a game update changes the event
icon, update the template image and re-run calibration.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Copy `.env.template` to `.env` (Slack is optional):
   ```
   cp .env.template .env
   ```

3. Create a template image for each event:
   - Screenshot the game while the event icon is visible
   - Crop the icon tightly (minimal background)
   - Save to `templates/<event_name>.png`

4. Edit `config.yaml` — set window title, dimensions, event ROI and threshold

5. Run calibration to tune ROI and threshold:
   ```
   python calibrate.py
   ```

6. Validate with offline regression tests:
   ```
   pytest tests/test_detector_real_images.py -v
   ```

## Running

```
python watcher.py
```

Stop with **Ctrl+C**. The watcher sleeps and retries if the game window is closed
or minimized.

**Debug mode:** set `debug_mode: true` in `config.yaml` to see confidence scores
every poll and save screenshots to `debug_screenshots/` on each detection.

## Calibration

```
python calibrate.py               # live scores
python calibrate.py --save-crops  # + save sample ROI crops to debug_crops/
```

Target:
- No event: score < 0.50 (ideally < 0.30)
- Event visible: score > 0.90
- Gap: at least 0.20 between the two states

## Adding a New Event

1. Crop the icon from a screenshot → save to `templates/<name>.png`
2. Add an entry under `events:` in `config.yaml`
3. Run `python calibrate.py` to find the right ROI and threshold
4. Run `pytest tests/test_detector_real_images.py -v` to validate
5. Restart `python watcher.py`

## Background Operation (No Terminal)

To run the watcher without keeping a terminal open, use `pythonw`:
```
pythonw watcher.py
```
This runs with no visible console. Logs are lost unless redirected to a file.
For persistent background operation, use Windows Task Scheduler with
`pythonw watcher.py` as the action, triggered at login.
```

- [ ] **Step 3: Write CHANGELOG.md**

```markdown
# Changelog

## [Unreleased]

### Added
- Window discovery by partial title match; logs exact matched title; warns on multiple matches
- Window-relative ROI capture via mss (in-memory; no continuous disk writes)
- Multi-template grayscale matching via OpenCV; returns DetectionResult with score, template name, location
- Blank-frame pre-filter (per-event, optional) to skip matchTemplate on dark captures
- Rising-edge state machine per event — alerts only on absent→present transition, not on persistent icon
- Consecutive-hit confirmation (configurable) to filter single-frame false positives
- Per-event cooldown as secondary anti-spam guard
- Local sound alert (winsound.Beep) — synchronous, fires first
- Windows toast notification via win10toast (non-blocking)
- Async Slack webhook backup notification (daemon thread)
- Debug screenshots saved on confirmed detection (debug mode only)
- `calibrate.py` probe — live confidence scores per event, best template name, optional ROI crop saving
- Offline regression tests using real game reference screenshots
- DPI awareness set at startup
- Rate-limited "window not found" warning (at most once per minute)
- Window size mismatch warning if game window is resized during session
- Exception handling in the main loop — errors are logged, watcher keeps running
- Consecutive error counter per event with escalating warnings
```

- [ ] **Step 4: Final commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: add README with limitations section and CHANGELOG

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review

### Spec Coverage (revised)

| Requirement | Task |
|---|---|
| Multi-template matching per event | Task 4 — Detector |
| Grayscale matching default | Task 4 — Detector |
| DetectionResult with score, template, location | Task 4 — Detector |
| Rising-edge state machine | Task 5 — EventState |
| Consecutive-hit confirmation | Task 5 — EventState + Task 9 — watcher |
| Cooldown as secondary guard | Task 5 — EventState |
| Local sound | Task 6 — AlertManager |
| Toast notification | Task 6 — AlertManager |
| Async Slack | Task 6 — AlertManager |
| Exception handling in loop | Task 9 — watcher |
| Consecutive error counting + warning | Task 9 — watcher |
| Window title logged on match | Task 9 — watcher |
| Multiple match warning | Task 9 — watcher |
| Offline regression tests | Task 7 |
| Calibration with crop saving | Task 8 |
| Blank prefilter per-event | Task 4 + Task 9 |
| detection_mode config key | Task 1 — config.yaml |
| Visibility limitation documented | README + Limitations section |
| Window size limitation documented | README + Limitations section |
| Poll FPS default 2, explain when to use 5 | config.yaml comment |
| GitHub private/optional | Task 1 — noted as optional |
| Performance notes | Revised plan above |

### Known Gaps (honest)

1. **No process-name or window-class validation.** If a non-game window happens to contain "Last War" in its title, it will be matched. Partial title match is the only discriminator in v1. Workaround: use a more specific title substring.

2. **Regression tests depend on threshold from config.** If the threshold in `test_detector_real_images.py` diverges from `config.yaml`, tests may pass while the live watcher is miscalibrated. The test file hardcodes THRESHOLD = 0.85. Consider parameterizing it to read from config.yaml in a future revision.

3. **EventState.last_alert_time is set in the state machine.** This means the cooldown clock starts at the moment the alert fires. If the watcher restarts, the clock resets. A persistent icon that was just detected pre-restart will re-alert immediately after restart.

4. **win10toast compatibility.** win10toast has known issues on some Windows 11 builds. If toast notifications don't appear, the sound alert still fires. A future revision could switch to plyer or a ctypes-based notification.

5. **No test for watcher.py itself.** The main loop is integration-tested manually. A future revision could extract the per-event detection-and-alert logic into a function that can be unit tested with mocked dependencies.
