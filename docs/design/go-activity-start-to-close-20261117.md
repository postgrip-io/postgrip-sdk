# Honor Go activity start-to-close timeouts

A literal cookbook run requested StartToCloseMs=14400000 but scheduled a
30-second activity. ExecuteActivity forwards LeaseTimeoutSeconds and never
reads StartToCloseMs. TypeScript and Python already encode their start-to-close
timeouts as the task lease timeout, which the server records in activity timeout history and uses as the renewable
lease. A heartbeating activity can exceed it; it is not a hard wall-clock limit.

Map positive Go StartToCloseMs to lease_timeout_seconds, rounding up fractional
seconds without integer-addition overflow. Explicit StartToCloseMs takes
precedence over LeaseTimeoutSeconds; otherwise preserve the existing lease
setting/default. Keep replay behavior and protocol schema unchanged. Explain
precedence on ActivityOptions. HeartbeatTimeoutMs has no separate wire deadline;
do not invent one or claim the start-to-close change adds that behavior.

Prove the old bug with a recorded HTTP enqueue regression, then cover4h,
fractional/minimal milliseconds, conflicting lease values and unchanged defaults.
Run Go tests/vet/race and protocol/generator/layout checks. A fresh live walker
runs the corrected cookbook with a40-second synthetic activity on old and fixed
SDKs; inspect scheduled timeout, heartbeats and final activity/workflow ordering.
The original40-second run also succeeds because heartbeats renew its30-second
lease; do not claim the change fixes a hard deadline or an observed failure.
Publish through Codex review and green CI; coordinate web source pin and cookbook
updates to the exact reviewed merge. No package registry release is implied.
