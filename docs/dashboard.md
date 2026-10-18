# Weekly credits pace

The Weekly credits pace card offers **5 min**, **15 min**, **1 h** and **3 h**
averaging buttons directly below its title. The default is **3 h**. Your choice
is remembered in this browser and does not change the account pool, dashboard
activity timeframe or another user's preferences.

The selected average drives the displayed credit burn, estimated depletion time
and rate-dependent shortfall recommendations together. A short window responds
to a surge more quickly; a longer window smooths bursts and quiet periods.

Provider quota percentages are rounded. A five-minute window can therefore show
no observed quota change even while requests are running, or a sharp increase
when a rounded percentage advances. This is not a token-by-token instantaneous
measurement, a guarantee of zero consumption, or a monetary account balance.
Insufficient recent observations are shown separately from an observed zero.

Both `/api/dashboard/overview` and `/api/dashboard/projections` accept the
optional integer query parameter `burnWindowMinutes=5|15|60|180`; omission
retains 180 minutes. The weekly credit response echoes `burnWindowMinutes` so
consumers can distinguish responses from different averaging windows.

Normative contracts: [frontend architecture](../openspec/specs/frontend-architecture/spec.md)
and [usage metrics](../openspec/specs/usage-error-metrics/spec.md).
