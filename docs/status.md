# Project Status Log

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
