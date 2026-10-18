# Design

Both dashboard GET routes accept `burnWindowMinutes` in {1, 15, 60, 180},
default 180, and echo the window in weeklyCreditPace. The existing history
fetch preserves the complete three-hour tail, covering every choice. Per fresh
eligible account, integrate positive quota deltas over observed intervals clipped
to the requested window, interpolating the boundary interval. Ignore quota
decreases, real window changes and reset-marker changes larger than one minute;
tolerate small countdown timestamp jitter. Divide by the greater of the observed
elapsed span and min(window, 30 minutes), retaining the short-history guard
without diluting a one-minute selection by a thirty-minute denominator. Sum
per-account rates; incomplete account observation coverage makes the pool rate
unknown, not a partial sum. This result feeds both simulation and displayed runway.

Accessible card buttons use a browser-local preference. Projection query keys
contain the selected window; only matching response metadata can populate the
card. Keep controls available during loading, insufficient samples and failures.
Never paint another window's numbers under the selected button. Rounded quota
percentages cannot establish a truly instantaneous rate: explain short-window
noise and do not claim a measured safe runway without positive observed burn.

No migration, environment variable, new dependency or routing change. Rollback
is ordinary source/assets rollback; clients omitting the query retain 3 h.
