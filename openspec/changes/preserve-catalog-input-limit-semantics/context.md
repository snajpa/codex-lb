# Catalog window and input-limit correction

The selected gateway's generic adapter used the resolved working window as its
input-context field. Native metadata and the generic maximum-context extension
already distinguish default window from selectable ceiling. A client that
honors an explicit input limit therefore became more restrictive after generic
discovery, despite the advertised larger maximum. Successful production usage
metadata above the synthesized bound supports the diagnosis; it is not proof of
every account's physical maximum.

The correction maps real input declarations, with their tighter value controlling
the existing optional generic input field. It does not guess an input maximum
from total-context or output limits. Generic normal-window aliases still serve
consumers that only understand a default window. Client learned ceilings remain
separate, and an active owner is not restarted or silently rebound during a turn.

For example, a normal window of 272000 and a selectable maximum of 872000 do
not declare an input ceiling of 272000. With no explicit or learned input limit,
a client selecting 550000 with zero output reserve and 90% effective input can
use a 495000 input budget; a separate 90% automatic compaction threshold is
445500. An explicit input ceiling of 300000 still binds that selection, and
a working-window override does not erase or enlarge that ceiling.
