# Native-reader VoWiFi recovery stopped by modem defaults

All times below are Asia/Singapore (UTC+08:00), 2026-09-26.

- 11:11:50: line 1 reports its IMS transport failed; registration attempts receive no response.
- 11:14:02–03: health recovery captures diagnostics and removes engine 1. Its ePDG tunnel was connected; another line on the same exit was still registered, so failover correctly keeps the exit.
- 13:48:57–59: kernel records an Asterisk segmentation fault on line 2; Docker reports exit 139 and restarts that container.
- 13:49:03: line 2 re-establishes its ePDG tunnel, but IMS remains unregistered.
- 13:50:33–34: health recovery captures diagnostics and removes engine 2.
- At investigation, both engine containers are absent. The control service and host orchestrator remain running; both line configurations remain enabled.

The recovery guard incorrectly consulted the modem desired-state defaults for native readers. The deployment has `defaults.vowifi_enabled=false` to keep cellular modem SIMs out of VoWiFi, but native-reader switches are represented by `instance.enabled`. As no per-modem desired record exists for the readers, `_line_auto_start_allowed` returned `vowifi_disabled` and `_auto_recover_instance` cleared its pending retry. The hotplug path had the same guard.

The fix exempts confirmed native readers from modem desired-state defaults, preserving enabled-line, card-presence, protected-SIM, and modem-switch checks. The UI now distinguishes a desired-but-not-running reader from an engine actually waiting for registration.

Validation: two regression tests failed before the guard fix and passed afterwards; 171 focused Python tests passed, 14 frontend tests passed, and the production frontend built successfully. Independent review found no actionable regression.

This fixes the failure to recover, not the original carrier response failure or Asterisk segmentation fault. The available kernel report proves the crash but does not identify the offending Asterisk code path.

Rollback: source archive `data/backups/before-reader-recovery-20260926.tgz` and image `mdd-sim-gateway/control:before-reader-recovery-20260926` on the gateway. No SIM policy, mobile-data setting, or egress selection was changed.

Live verification after deployment: both engines were automatically recreated after the control service restarted. Asterisk reported Registered for both lines, and Chrome displayed VoWiFi registered for both readers. Cellular modem devices remained disconnected with data and VoWiFi off.
