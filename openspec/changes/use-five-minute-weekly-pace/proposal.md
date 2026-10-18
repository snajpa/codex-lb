# Use five minutes for the shortest weekly burn average

Whole-percent quota observations are too sparse over one minute. Replace the
shortest in-card average with five minutes while retaining 15 min, 1 h, 3 h
and the three-hour default. Preserve the shared elapsed-time rate and unknown
coverage rules. Move an existing one-minute browser preference to five minutes;
reject one-minute HTTP queries rather than silently labeling another interval.
No migration, dependency, routing or quota-capacity change is needed.

Numerical review also found reset gaps counted as zero-consumption time,
expired balances advanced a week, a cohort-only exhaustion verdict, and nominal
weekly throttling that can still exhaust the remaining pool before refill.
Correct these at the common backend calculation and rendered consumer path.
