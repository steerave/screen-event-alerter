# Last War Alert Watcher — Design Spec
**Date:** 2026-04-20
**Status:** Approved for implementation planning

---

## Purpose

A lightweight Windows background tool that watches a specific region inside the Last War game window and notifies the user immediately when a known event indicator appears. Notification-only for v1 — no click automation, no gameplay automation.

---

## Scope

### In v1
- Detect one or more known event icons in a watched region
- Fire local alerts (sound + toast) and a Slack backup notification
- Run continuously as a background process, gracefully handling window absence/minimization
- Config-driven: events, ROIs, thresholds, cooldowns all defined in YAML

### Explicitly out of v1
- No automatic clicking or gameplay automation
- No saving screenshots to disk continuously (only on confirmed hits or debug mode)
- No ML/AI models
- No multi-monitor awareness beyond what mss handles automatically
- No persistent state across restarts (cooldowns reset on restart; acceptable for v1)

---

## Detection Strategy Decision

**Chosen: Option A — Template Matching (with one optional pre-filter)**

Rejected alternatives:
- **Option B (generic change/occupancy detection):** The changing background between base view and world view (animated terrain, moving units) would cause unacceptable false positive rates without significant additional engineering (baseline learning, temporal smoothing, color filtering, edge filtering). By the time you add all that mitigation, you've built Option C complexity without Option A's precision.
- **Full Option C (hybrid pre-filter + template):** Premature for v1. On a small ROI at 5 FPS, a change-detection pre-filter saves negligible CPU. The added complexity is not justified.

**What Option A looks like in practice:**
- One or more template PNG images per event type, captured from the actual game
- `cv2.matchTemplate` with normalized cross-correlation (`TM_CCOEFF_NORMED`)
- Configurable confidence threshold per event (typically 0.80–0.92)
- Optional pre-filter: skip matchTemplate if ROI mean brightness is below a minimum (catches blank/black captures cleanly, 2 lines of code)

**On the generic trigger question:** Generic "something appeared here" detection IS feasible but only with: tight spatial isolation, color signature filtering for distinctive icon colors, temporal persistence (require N consecutive frames), and structural edge detection. Because we know what the icon looks like, template matching is simpler and more reliable. Save generic detection for v2 if needed.

---

## Hard Requirements (Non-Negotiable for Correctness)

### Window Size Must Be Stable
This is a **hard correctness requirement**, not a soft preference. If the game window is resized:
- All pixel-coordinate ROIs break silently
- All template images break silently (scale mismatch)
- Template matching returns zero confidence with no error

The design must:
- Store expected window dimensions in config
- Validate dimensions at startup
- Warn loudly if dimensions change during a session
- Document that changing window size requires re-capturing templates and re-tuning ROIs

### DPI Awareness Must Be Set at Startup
Without explicit DPI awareness, GetWindowRect returns virtual (scaled) coordinates while mss captures physical pixels. On a 150% scaled display, every coordinate is off by a factor of 1.5 — the ROI lands in the completely wrong place with no error.

Fix: call `ctypes.windll.shcore.SetProcessDpiAwareness(2)` at startup before any coordinate operations.

---

## Architecture

```
config.yaml
  window_title         # partial match string (not exact)
  window_width         # expected width — validated at startup
  window_height        # expected height — validated at startup
  poll_fps             # default: 5
  debug_mode           # if true: save annotated screenshot on detection
  slack_webhook_url    # read from env var, not hardcoded here

  events:
    - name: "rally_alert"
      roi:
        x: 120         # window-relative pixels (not screen-absolute)
        y: 450
        w: 80
        h: 80
      template: "templates/rally_alert.png"
      threshold: 0.85
      cooldown_seconds: 30
      alert_sound: true
      alert_toast: true
      alert_slack: true
      slack_message: "Rally alert detected in Last War"
```

```
Main loop:
  1. Find game window by partial title match (EnumWindows, not FindWindow exact)
     → if not found: log warning (rate-limited to once per minute), sleep, retry
     → if minimized (IsIconic): skip capture, sleep, retry
  2. Get client area rect → compute absolute screen coordinates for each ROI
  3. For each event:
     a. Capture ROI with mss → numpy array (in memory only, never written to disk)
     b. Optional: skip if mean brightness below minimum threshold
     c. cv2.matchTemplate with cached template → confidence score
     d. If confidence >= threshold AND cooldown elapsed:
        - Fire local sound (synchronous — must be first and fastest)
        - Fire Windows toast (synchronous)
        - Fire Slack webhook (async thread — network must not block the loop)
        - If debug_mode: save annotated screenshot with timestamp
        - Update cooldown timestamp in memory
  4. Sleep to maintain target poll_fps
```

### Component Responsibilities

| Component | Responsibility |
|---|---|
| **WindowFinder** | Locate game window by partial title; return HWND + client rect; detect minimized state |
| **ScreenCapture** | Accept window-relative ROI + client rect; translate to screen coords; return numpy array via mss |
| **Detector** | Load and cache templates at startup; run matchTemplate; return confidence score |
| **AlertManager** | Track cooldowns per event; dispatch sound, toast, Slack; save debug screenshots |
| **MainLoop** | Orchestrate all components; handle exceptions; maintain poll rate |

---

## Technology Stack

| Purpose | Library | Notes |
|---|---|---|
| Window discovery | `pywin32` (win32gui, win32con) | EnumWindows for partial title match; IsIconic for minimized check |
| Screen capture | `mss` | Fast, in-memory, uses DXGI compositor — works with GPU-rendered windows |
| Computer vision | `opencv-python` | matchTemplate for detection; numpy arrays throughout |
| Local sound | `winsound` (stdlib) | Beep() as zero-dependency fallback; playsound for custom audio file |
| Toast notification | `win10toast` or `plyer` | Windows toast notifications |
| Slack | `requests` | Simple webhook POST; called in a daemon thread |
| Config | `PyYAML` | YAML config file |
| Secrets | `python-dotenv` | SLACK_WEBHOOK_URL from .env, never in config.yaml |

Python 3.11+.

---

## Notification Model

Priority order (all can fire simultaneously):

1. **Sound** — fastest, requires zero visual attention, works even if display is off
2. **Windows toast** — visible when tabbed to other apps; auto-dismisses
3. **Slack webhook** — for "away from desk" scenarios; async, non-blocking

**Slack is a backup channel, not the primary channel.** Realistic Slack latency: 1–10 seconds. Local sound/toast latency: under 100ms.

Sound fallback: if no custom sound file is configured, use `winsound.Beep()` (always available, no dependencies).

Slack webhook URL comes from environment variable `SLACK_WEBHOOK_URL` (via `.env`), never from config.yaml or committed to git.

---

## Performance Profile

| Metric | Expected value |
|---|---|
| CPU (at 5 FPS, 200×200 ROI) | < 0.1% of a single core |
| Memory (resident) | < 100MB |
| Disk writes (normal operation) | Zero |
| Disk writes (debug/alert) | One screenshot per confirmed hit |
| Detection latency (at 5 FPS) | 0–200ms (worst case) |
| End-to-end alert latency (local) | ~250ms worst case |
| End-to-end alert latency (Slack) | 1–10 seconds |

**On polling frequency:** 5 FPS is the recommended default. At this rate, worst-case detection lag is 200ms, which is imperceptible for this use case. The cost is negligible (≈15ms CPU per second). There is no meaningful reason to default to 1–2 FPS given the ROI size.

Faster polling (10–15 FPS) is warranted only for events that auto-dismiss in under 1 second.

---

## Key Constraints

- Windows only
- Python 3.11+
- Dynamic window discovery by partial title (not hardcoded HWND or fixed screen position)
- Window-relative ROI coordinates (not absolute screen coordinates)
- Process captures in RAM only — no continuous disk writes
- Save screenshots only on confirmed detection (or explicit debug mode)
- Continue running gracefully when game window is absent, minimized, or temporarily closed
- Per-event: configurable threshold, cooldown, and alert message
- Secrets (Slack URL) via environment only — never in committed files
- No click automation in v1

---

## Assumptions That Were Validated

| Assumption | Status |
|---|---|
| Partial title matching is sufficient for window discovery | Valid — use EnumWindows with substring check |
| Stable window size is "probably" important | **Strengthened to hard requirement** |
| 1–2 FPS is enough | Valid but conservative — defaulting to 5 FPS |
| Local alert faster than Slack | Confirmed correct |
| Simple CV better than ML for v1 | Confirmed correct |
| Config-driven design | Confirmed correct |
| Small ROI only | Confirmed correct and essential |

## Assumptions That Were Corrected

| Original assumption | Correction |
|---|---|
| "Changing background is less of a problem than changing icon size" | **Wrong.** Background changes cause silent false positives (the harder problem). Icon size changes cause obvious failures (detectable). Background change is the primary risk for any generic detection approach. |
| Fixed screen position not required | Correct, but DPI scaling is an equally important "invisible coordinate space" problem that was not in the original plan. |

---

## Known Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Window title doesn't exactly match | Use partial/substring match via EnumWindows |
| Window minimized → blank capture | IsIconic() check before every capture |
| DPI scaling → ROI in wrong place | SetProcessDpiAwareness(2) at startup |
| GPU rendering → blank mss capture | Test on actual game before finalizing (mss usually works via DXGI) |
| Game update changes icon appearance | User replaces template PNG; no code change needed |
| Template false positives | Tune threshold; add color pre-check if needed |
| Alert spam | Per-event cooldown (in design) |
| Slack network failure | Caught silently; local alert already fired |
| Watcher process crashes | Document restart; optionally add Task Scheduler watchdog in v2 |

---

## Template Acquisition Workflow

Before the first event can be detected, a template image must be captured. This is not a one-time manual step — it is a repeatable workflow for adding new event types:

1. Trigger the event in-game
2. Use the watcher's debug mode (or any screenshot tool) to capture the game window
3. Crop the icon to a tight bounding box — remove as much background as possible
4. Save as PNG to `templates/<event_name>.png`
5. Run the watcher in debug/calibration mode to confirm confidence scores
6. Set threshold in config to approximately 10% below the lowest observed true-positive confidence

The two existing PNG files in the project root (`SS - Dig.png`, `SS - No Dig.png`) appear to be candidate reference screenshots and may be the source for the first event's template.

---

## Phased Implementation Plan

### Phase 1: Proof of Detection (no alerts)
Goal: confirm detection works on the real game before building anything else.
- Window discovery by partial title
- mss ROI capture (window-relative → screen coords)
- Single hardcoded template and threshold
- Print confidence score to console on every poll
- **Gate:** detection reliably fires on the real event and not on normal game state

### Phase 2: Local Alerting
- winsound.Beep() as immediate alert
- Windows toast notification
- Per-event cooldown

### Phase 3: Config-Driven
- YAML config for all parameters
- Multiple event support
- Debug mode with screenshot saving
- Startup validation (window size, template file existence)

### Phase 4: Slack Integration
- SLACK_WEBHOOK_URL from .env
- Async send (daemon thread)
- Graceful error handling

### Phase 5: Robustness
- DPI awareness at startup
- Rate-limited "window not found" logging
- Window size change detection and warning
- Structured logging with timestamps
