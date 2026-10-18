## Why

Native compaction currently loses tool-prefix inputs on the upstream Responses-v2 adapter, uses a shorter hidden upstream deadline, records compact endpoint calls as ordinary requests without the supplied session identity, selects history using a guessed capacity budget, and reconstructs outputs rather than preserving the native window. These behaviors impede cache reuse, terminate expensive compact calls, and obscure their ownership.

## What Changes

Preserve native-v2 reasoning and tool-prefix parameters, use the actual operation deadline for the upstream call, and log the endpoint-defined compaction kind with its session identity. Preserve complete validated history and returned native windows; reject plaintext substitutes and malformed capsules; scope capability metadata to actual backend provenance. Join account admission cleanup under cancellation while preserving settlement, error identity and file/account ownership. Correct stale compact transport documentation.

## Impact

Responses API compatibility, compact lifecycle, default compact budget, request-log consumers and native clients. No new configuration mode, retry protocol, local summary substitute, database migration or credential/retention change.
