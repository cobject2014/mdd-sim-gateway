# Upstream fixes integration plan

Scope: preserve IMSI SMS-only mode, Bark, offline history, accurate status and overview filter. Do not enable MMS or cellular data. Integrate on an isolated branch, verify each batch before deployment.

1. Cellular safety and identity: backport e2b7cd4, 0838f29, 3093b55, cbf7da6 with focused modem tests.
2. SMS reliability: late multipart handling and stable subscriber-scoped identity; integrate storage policy only with upgrade-safe keep default, without pulling MMS data connections into SMS-only mode. Test duplicate notification suppression and migration.
3. Reliability: AMI cleanup and recovery isolation, preserving local Bark delivery. Run focused and combined regressions.
4. Review diff, retain rollback backup, deploy validated batches and verify live settings and UI, commit and push batch history.

## Batch 1 result
Integrated e2b7cd4, 0838f29, 3093b55, cbf7da6, 022caa2 and 005078d. Preserved IMSI policy reconciliation and the SMS placeholder and duplicate-push fixes. 160 focused tests and 17 additional storage/transport/UI-contract tests pass.

The larger v1.10 SMS identity/storage migration remains isolated on local branch work/upstream-sms-migration, not deployed: the upstream commits depend on MMS schema and send-tracker changes. That draft is not release-ready. Recovery isolation remains for a later batch.


## Batch 2 integration

- Integrate SMS store/scanner and PDU parser from upstream 82c8195, including subscriber-scoped identities, TP-SCTS, atomic migrations, verified/reused backup, rollback reconciliation, and storage policy.
- Ruling: preserve the upstream schema sequence and pure MMS codec as migration dependencies; no MMS transport, downloader, API or cellular bearer is enabled. Binary cellular objects remain on the modem until a supported archive path exists.
- Ruling: default storage policy is keep for all installations; existing explicit choices remain effective. Keep literal dash-only SMS after raw D-Bus confirmation and bridge cellular-in-v2 tombstones from the fork.
- Review fixes: preserve ModemManager generation on local sends and external outgoing identity; check generation after Create and before deletion; cancelled creations cannot claim external SMS.
- Live database-copy rehearsal: 44 messages retained, 60 legacy markers retained, 0 historical reimports, integrity ok, schema 5, exactly 1 verified backup. No push hooks called.
- Baseline suite: 970 tests, 3 failures + 10 errors; candidate first full run: 1011 tests with exactly the same failing test names (pre-existing auto-provision/hotplug expectations and sandbox port allocation). Focused suite passed; final counts recorded below.
- Recovery isolation remains the next separate batch; do not mix it into this database rollout.

Final local validation: 192 focused tests passed; full suite 1057 tests with the identical 13 baseline failures/errors. Independent review cleared the generation and creation-tracking fixes.

Deployment verified on 2026-09-19: schema 5, 44 messages, 60 legacy markers, integrity ok, keep policy; control startup completed without tracebacks and both existing VoWiFi engines registered. Rollback database/source/image backups are named before-upstream-batch2-20260919. No external SMS or push test was sent.
