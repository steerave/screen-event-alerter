# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added

- `alert_sound_name` per-event config option — plays a Windows system sound (e.g. `SystemExclamation`) instead of the raw beep, which is far more noticeable through speakers
- `alert_beep_pattern` per-event config option — plays a sequence of `[frequency, duration]` beep tones in a daemon thread; more distinctive than any single sound. Default config uses a 3-tone ascending pattern (600 → 900 → 1200 Hz)

## [0.1.0] - 2026-04-20

### Added

- Main watcher loop (`watcher.py`) with rising-edge detection, consecutive-hit confirmation, and cooldown guard
- Startup config validation — fails fast with clear errors before entering the poll loop
- Per-event configurable alerts: sound (frequency + duration), Windows toast, and optional Slack webhook
- Debug mode — saves ROI crop and annotated full-window screenshot on detection when `debug_mode: true`
- Calibration probe (`calibrate.py`) for live confidence score display and optional crop saving
- Template matching detector (`detector.py`) — normalized cross-correlation across multiple templates per event, grayscale by default
- Rising-edge state machine (`event_state.py`) — fires alert only on absent → present transition; suppresses re-alerts on persistent icons
- Alert manager (`alert_manager.py`) — sound, toast, Slack, and debug screenshot helpers
- Screen capture (`screen_capture.py`) — DPI-aware mss capture returning a BGR numpy array
- Window finder (`window_finder.py`) — partial title match via pywin32 EnumWindows; warns on multiple matches
- 44 unit and integration tests across all modules
- Offline regression tests that validate positive/negative screenshot scores against configured thresholds
- YAML config with per-event ROI, threshold, consecutive-hit requirement, cooldown, and alert settings
