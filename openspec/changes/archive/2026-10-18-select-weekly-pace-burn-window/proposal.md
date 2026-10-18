# Select the weekly credit burn averaging window

The weekly credit card hides a fixed three-hour average while its shortfall
forecast uses a sample-count EWMA. Busy accounts append many unchanged,
whole-percent quota snapshots, which drive that EWMA towards zero even while
the pool consumes credits. Operators cannot inspect a recent surge without
confusing these different rates.

Add in-card 1 min, 15 min, 1 h and 3 h controls, defaulting to 3 h. Use one
elapsed-time average for burn, runway and rate-dependent forecasts. Keep the
choice browser-local and the existing layout, authentication, quota calibration
and routing unchanged.
