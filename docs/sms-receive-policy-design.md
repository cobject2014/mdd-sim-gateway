# IMSI-bound SMS-only policy
User-approved 2026-09-10, clarified during implementation: remember selected SIM by IMSI; on insertion radio on, mobile data off, VoWiFi off. SMS BOTH receive and send remain available. Do not add outbound blocking or send unsolicited tests. Provide settings and accurate device/service state. Existing two AK9563 lines must remain unchanged.

Persist explicit per-IMSI sms_only versus normal policy; default normal does not override existing settings. Enforce policy in host reconciliation using live modem identity (not stale USB assignments). Do not log full IMSI or expose it unnecessarily. Removing policy unlocks controls but does not auto-enable data.

API contract: GET/PUT /api/devices/{device_id}/sim-policy, PUT {mode: 'sms_only'|'normal'}. Unified device and line adds sim_policy: {mode, imsi_masked, bound: bool}. UI uses active registered cellular status independently of VoWiFi STOPPED; distinguishes disconnected hardware, registered/roaming cellular, registered VoWiFi, searching, radio off. No invented unsupported-carrier inference. IP when data off: disabled instead of waiting. Mode copy states SMS receive/send available, data and VoWiFi disabled.
