# Project Status Log

## 2026-05-03

**Done:**
- Created desktop shortcut `LastWar Watcher.lnk` launching `watcher.py` via Python 3.12 with a visible console window — close the window to stop
- Fixed silent-startup crash: shortcut targeted Python 3.12 which lacked project deps — installed `opencv-python`, `mss`, `pywin32`, `numpy`, `win10toast`, `pytest`, `pytest-mock` into 3.12
- Pinned `setuptools<81` in Python 3.12 because `win10toast` still imports the now-removed `pkg_resources` module
- Verified sibling Job Search Tool (also runs on Python 3.12) is unaffected by numpy upgrade (1.26.3 → 2.4.4): 40+ LinkedIn searches scraped with zero errors

**In Progress:**
- Nothing pending

**Next:**
- Run shortcut during a real dig event to confirm alert behavior end-to-end
- Optional: add file logging to `watcher.py` so a silent (`pythonw.exe`) shortcut variant becomes viable for unattended runs

**Notes:**
- Shortcut points at the main project folder (`C:\Users\steerave\Desktop\Claude Projects\LastWar - Alert System`), not the worktree — survives session cleanup
- LastWar Watcher and Job Search Tool share a single Python 3.12 install; package upgrades in one affect both — per-project venvs would be a clean future fix
- Pip's `python-jobspy requires NUMPY==1.26.3` warning was metadata-only; numpy 2.4.4 + pandas 2.3.3 + jobspy 1.1.82 work fine at runtime

## 2026-04-24

**Done:**
- Polished GitHub repo (`screen-event-alerter`): added description, 8 topics (python, opencv, computer-vision, etc.), badges, screenshot table, and "How It Works" pipeline diagram to README
- Added `alert_beep_pattern` per-event config option — plays a `[freq, dur]` sequence in a daemon thread; more attention-grabbing than any single system sound
- Added `alert_sound_file` per-event config option — plays any `.wav` file via `SND_FILENAME | SND_ASYNC`; takes priority over beep_pattern and sound_name
- Switched `dig_event` alert to `C:/Windows/Media/Alarm01.wav` — confirmed audible and distinct from all standard Windows system sounds
- Added 3 new tests (pattern plays all tones, pattern error resilience, wav file path); test suite at 14 passing

**In Progress:**
- Nothing — all sound work committed and pushed

**Next:**
- Run watcher live against a real dig event to confirm `Alarm01.wav` fires correctly end-to-end
- Consider adding a second event (e.g. announcement) with a different alarm variant to distinguish event types by sound

**Notes:**
- Sound priority in `fire_sound()`: `alert_sound_file` → `alert_beep_pattern` → `alert_sound_name` → beep fallback
- `Alarm01.wav`–`Alarm10.wav` and `Ring01.wav`–`Ring10.wav` are all available in `C:/Windows/Media/` if a different tone is ever needed
