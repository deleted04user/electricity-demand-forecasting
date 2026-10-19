# Security policy

Security fixes target the latest release and `main`; older releases may require
an upgrade. Report a suspected vulnerability through GitHub's
[private vulnerability reporting](https://github.com/deleted04user/electricity-demand-forecasting/security/advisories/new).
Include the affected revision, a minimal reproduction, and the expected impact.
Keep secrets and private input data out of public issues and reports.

The [threat model](docs/THREAT_MODEL.md) describes the local deployment boundary,
trusted serialized model, input validation, research isolation, and remaining
deployment responsibilities. Python/JavaScript dependency audits and CodeQL
analysis run in GitHub Actions; successful checks do not establish that software
is free of vulnerabilities.

For a model replacement, review the source and provenance before regenerating
its trusted manifest. A matching checksum detects replacement relative to that
manifest; it does not make an unknown pickle safe to load.
