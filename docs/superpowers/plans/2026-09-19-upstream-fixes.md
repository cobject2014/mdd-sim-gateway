# Upstream fixes integration plan

Scope: preserve IMSI SMS-only mode, Bark, offline history, accurate status and overview filter. Do not enable MMS or cellular data. Integrate on an isolated branch, verify each batch before deployment.

1. Cellular safety and identity: backport e2b7cd4, 0838f29, 3093b55, cbf7da6 with focused modem tests.
2. SMS reliability: late multipart handling and stable subscriber-scoped identity; integrate storage policy only with upgrade-safe keep default, without pulling MMS data connections into SMS-only mode. Test duplicate notification suppression and migration.
3. Reliability: AMI cleanup and recovery isolation, preserving local Bark delivery. Run focused and combined regressions.
4. Review diff, retain rollback backup, deploy validated batches and verify live settings and UI, commit and push batch history.

## Batch 1 result
Integrated e2b7cd4, 0838f29, 3093b55, cbf7da6, 022caa2 and 005078d. Preserved IMSI policy reconciliation and the SMS placeholder and duplicate-push fixes. 160 focused tests and 17 additional storage/transport/UI-contract tests pass.

The larger v1.10 SMS identity/storage migration remains isolated on local branch work/upstream-sms-migration, not deployed: the upstream commits depend on MMS schema and send-tracker changes. That draft is not release-ready. Recovery isolation remains for a later batch.
