# IMSI SMS-only Policy Implementation Plan

> For agentic workers: implement backend and UI with test-driven development; independent review before deployment.

Goal: persist per-IMSI SMS-only mode and show accurate status.
Architecture: focused shared policy module and data JSON; control API integrates policy guards and settings; host applies policy based on current identity; UI derives transport-aware state.
Tech Stack: Python, React, Vite, unittest/node test.
Spec: docs/sms-receive-policy-design.md

## Constraints
Only selected IMSI is protected. Existing AK9563 services remain active. No live outbound messages/calls; no global network changes. Use current deployed source as baseline.

## Task 1 Backend
- [x] Inspect config, host identity lifecycle, SMS/call/USSD/keepalive entrypoints.
- [x] Add failing behavioral tests: policy persist/reload; SIM swap/replug; missing IMSI fails closed; SMS sending remains available in SMS-only mode; normal cards unchanged.
- [x] Add policy module plus API, host reconciliation. Keep unrelated behavior intact.
- [x] Run focused suites and record results.

## Task 2 UI
- [x] Add failing tests for cellular registered + VoWiFi STOPPED, data disabled, unavailable modem, receive-only mode.
- [x] Add SIM mode setting, per-service labels, conflicting toggles with explanations, clear mobile-data wording.
- [x] Run node tests, UI regression checks and production build.

## Task 3 Integration/deployment
- [x] Review integration and all mutation paths, fix findings, run affected regression suites.
- [x] Back up existing code/config and record engine IDs. Build deployment before replacing running service.
- [x] Deploy control/UI/host, enable selected IMSI policy only. Avoid restarting engines/pcscd.
- [x] Verify persistence, effective state, SMS capability status check, both existing IMS registrations and actual Chrome UI.
