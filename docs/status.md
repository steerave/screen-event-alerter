# Project Status Log

## 2026-04-24

**Done:**
- Added `alert_sound_name` per-event config option to play a Windows system sound (e.g. `SystemExclamation`) instead of the raw `winsound.Beep` — much more noticeable through speakers
- Updated `alert_manager.py` `fire_sound()` to use `winsound.PlaySound` with `SND_ALIAS | SND_ASYNC` when `sound_name` is set
- Updated `watcher.py` `EventConfig` and `load_events` to carry `alert_sound_name` through to the alert call
- Set `alert_sound_name: SystemExclamation` as default in `config.yaml`

**In Progress:**
- GitHub remote not yet configured — commit is local only (`git push` failed with no remote)

**Next:**
- Set up GitHub remote: `gh repo create lastwar-alert-system --public --source=. --push`
- Test `SystemExclamation` sound during a live dig event detection to confirm it's audible enough; try `SystemHand` if not

**Notes:**
- Python process (PID 12488) confirmed running during session — watcher survived a terminal resize
- `alert_sound_frequency` and `alert_sound_duration` remain as beep fallback when `alert_sound_name` is absent or blank
