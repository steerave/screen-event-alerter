# Screen Event Alerter

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?logo=windows&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-template%20matching-5C3EE8?logo=opencv&logoColor=white)
![Alerts](https://img.shields.io/badge/Alerts-Sound%20%7C%20Toast%20%7C%20Slack-brightgreen)

A lightweight Windows computer vision tool that monitors a configurable region of any application window using OpenCV template matching and fires multi-channel alerts — sound, Windows toast notification, and Slack webhook — the moment a known visual pattern appears on screen.

Built to catch time-sensitive events in the mobile strategy game **Last War: Survival** while working at a second monitor, but the core detection engine is application-agnostic and reusable for any window.

---

## In Action

| Dig event detected | Announcement event detected |
|---|---|
| ![Dig event](docs/images/dig-event.png) | ![Announcement event](docs/images/announcement-event.png) |

---

## How It Works

```
Screen capture (mss, DPI-aware)
  └─ ROI crop (configurable x/y/w/h per event)
       └─ OpenCV template match (normalized cross-correlation, grayscale)
            └─ Rising-edge state machine (EventState)
                 ├─ Consecutive-hit filter  →  suppress single-frame false positives
                 ├─ Cooldown guard          →  suppress repeat alerts
                 └─ Multi-channel alert
                      ├─ Sound (Windows system sound or beep)
                      ├─ Toast notification (win10toast)
                      └─ Slack webhook (requests)
```

The detector never fires twice for the same persistent icon — the `EventState` machine tracks absent → present transitions and re-arms only after the icon leaves the frame.

---

## Features

- **Template matching detection** — OpenCV normalized cross-correlation against one or more cropped icon images per event
- **Rising-edge alerts only** — fires once when the icon first appears; does not re-fire while the icon stays on screen
- **Consecutive-hit confirmation** — requires N frames above threshold before alerting (default: 2) to suppress false positives from partial renders
- **Cooldown guard** — secondary per-event cooldown (default: 60 s) prevents re-alerting even after the icon briefly disappears and returns
- **Per-event configurable alerts** — sound (frequency + duration), Windows toast, and optional Slack webhook per event
- **Calibration probe** — live confidence score display to set ROIs and thresholds without running the full watcher
- **Debug mode** — saves ROI crop and annotated full-window screenshot on every detection
- **DPI-aware capture** — correct pixel coordinates on scaled/high-DPI displays
- **Graceful exception recovery** — capture and detection errors are counted and logged; the loop continues

---

## Requirements

- Windows 10/11
- Python 3.10+
- Target application window visible and unobstructed while the watcher runs

Install dependencies:

```
pip install -r requirements.txt
```

---

## Setup

### 1. Copy the environment template

```
cp .env.template .env
```

Add your `SLACK_WEBHOOK_URL` if you want Slack alerts. Leave blank to disable.

### 2. Configure `config.yaml`

Key settings:

| Setting | Description |
|---|---|
| `window_title` | Substring of the target window title (partial match, case-insensitive) |
| `window_width` / `window_height` | Window client size in pixels — **do not resize after setting** |
| `poll_fps` | How often to check the screen (default: 2) |
| `debug_mode` | `true` to log scores per poll and save debug screenshots |

Per-event settings:

| Setting | Description |
|---|---|
| `templates` | List of template image paths (cropped from a positive screenshot) |
| `roi` | `{x, y, w, h}` region of interest relative to the window client area |
| `threshold` | Confidence threshold 0.0–1.0 (set to lowest positive score minus 0.10) |
| `consecutive_hits_required` | Frames above threshold before alert fires (default: 2) |
| `cooldown_seconds` | Minimum seconds between alerts for this event (default: 60) |
| `blank_prefilter` | Skip detection on near-black frames (disable for dark-background icons) |
| `alert_sound` | Play a sound on detection |
| `alert_beep_pattern` | List of `[frequency_hz, duration_ms]` pairs played in sequence (most distinctive option). Overrides `alert_sound_name` and the single-beep fallback when set |
| `alert_sound_name` | Windows system sound alias (e.g. `SystemExclamation`, `SystemHand`). Used when `alert_beep_pattern` is not set |
| `alert_sound_frequency` | Beep frequency in Hz (default: 1000) — fallback when neither pattern nor name is set |
| `alert_sound_duration` | Beep duration in milliseconds (default: 300) — fallback only |
| `alert_toast` | Show Windows toast notification |
| `alert_slack` | POST to Slack webhook |
| `slack_message` | Message text for toast and Slack |

### 3. Capture template images

1. Take a screenshot when the event icon is visible
2. Crop tightly around the icon (use Paint, Snipping Tool, or any image editor)
3. Save to `templates/` (e.g., `templates/dig_event.png`)
4. Update `templates` in `config.yaml`

### 4. Calibrate ROI and threshold

```
python calibrate.py
```

Or with crop saving for visual confirmation:

```
python calibrate.py --save-crops
```

The calibration probe prints live confidence scores without firing any alerts. Observe scores when the icon is present vs absent. Set `threshold` to (lowest positive score) minus 0.10. Verify the gap is at least 0.20.

---

## Commands

**Run the watcher:**

```
python watcher.py
```

**Run the calibration probe (live scores, no alerts):**

```
python calibrate.py
```

**Save ROI crops during calibration:**

```
python calibrate.py --save-crops
```

**Run tests:**

```
pytest tests/ -v
```

---

## Limitations

### Target window must be visible and unobstructed

v1 uses the Windows desktop compositor (mss) to capture the screen. If another window overlaps the watched region, the watcher captures whatever is on top. Keep the watched region free of overlapping windows while running.

### Window size must remain fixed

ROI pixel coordinates and all template images are tied to a specific window resolution. If the window is resized, all ROI coordinates become wrong and all templates fail to match silently. Fix the window to one size and set `window_width` and `window_height` accordingly. Moving the window is fine — only resizing breaks detection.

### Templates must match the current application version

Application updates may change icon artwork. If an event icon changes appearance, templates must be recaptured. The watcher will fail silently (no matches) until templates are updated.

### Cooldown state resets on restart

Cooldowns are in-memory only. Stopping and restarting the watcher resets all cooldowns.

---

## Project Structure

```
watcher.py              Main entry point
calibrate.py            Live calibration probe
config.yaml             All runtime settings
.env                    SLACK_WEBHOOK_URL (not committed)
.env.template           Required env key list (committed)
templates/              Template images for each event
debug_screenshots/      Debug artifacts saved by watcher (debug_mode: true)
debug_crops/            ROI crops saved by calibrate.py --save-crops

detector.py             Multi-template OpenCV matching
event_state.py          Rising-edge state machine per event
alert_manager.py        Sound, toast, Slack, debug screenshot helpers
screen_capture.py       mss-based ROI screen capture
window_finder.py        pywin32 window lookup by title substring
tests/                  pytest test suite (44 tests)
docs/images/            Screenshots used in this README
```
