## 1. Correction and proof

- [x] Reproduce early same-account redispatch with Retry-After above ten seconds.
- [x] Cap generated backoff without shortening the upstream hint.
- [x] Cover initial/post-refresh recovery, request-budget exhaustion, cancellation,
      original error identity, and unchanged ownership/settlement.
- [x] Run affected SQLite/MariaDB gates, lint, typing, and strict spec validation.
- [x] Independently review current source and separately stage its immutable candidate.
- [ ] Qualify the candidate and complete private atomic delivery after coordinating
      with the concurrent transport rollout; preserve serving/rollback/peer owners.

The source correction is verified, but is not yet live. The change remains active
and must not be archived as delivered until the private runtime gate is complete.
