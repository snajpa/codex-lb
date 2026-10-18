# Design

Change the existing four-value API/type/button contract from 1 to 5 minutes.
Keep the query keys parameterized by their actual interval. A stored value of 1
maps once to 5 and is persisted under the same browser-local preference key;
other invalid values still fall back to 180. The rate integration already clips
arbitrary supported elapsed-time windows, so retain that mechanism unchanged.

Prove five-minute numerical rates/boundary clipping, both HTTP routes accepting
5 and rejecting 1, preference migration, real built-browser rendered values and
rapid/error switching. Qualify a separate immutable build, retain the current
selected revision as rollback, and verify the normal address after cutover.
