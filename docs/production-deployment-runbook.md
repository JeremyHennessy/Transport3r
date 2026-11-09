# Production deployment and recovery runbook

This is an installation procedure, not evidence that a server has been provisioned. Public
source files and private insurer records must remain separate. Never expose the existing
single-owner private workspace beyond loopback or mistake CORS for authorization.

## Public source preflight

Use an approved machine with sufficient disk for raw sources, the working cut, at least two
accepted warehouse releases and an independent backup. The historical warehouse alone was
approximately 7.4 GB. Capacity for current workloads must be measured; an initial 8 GB RAM /
160 GB disk test configuration is a starting assumption, not a certified production size.
Install dependencies from `scripts/requirements-nationwide.txt`. Obtain the complete authorized
raw-source cut and independently verify it before warehouse promotion. Retain old receipts.

Create a new deep audit without overwriting an earlier result:

```sh
python scripts/audit_warehouse_integrity.py /srv/transport3r-source/candidate.duckdb \
  --deep --output /srv/transport3r-source/candidate.audit.json
python scripts/evidence_release.py --root /srv/transport3r-install stage \
  --warehouse /srv/transport3r-source/candidate.duckdb \
  --audit /srv/transport3r-source/candidate.audit.json
```

The returned `release_id` is the complete warehouse SHA-256. Staging rechecks the deep warehouse
audit, copies and revalidates files and refuses to overwrite a release. It does not revalidate
original publisher bytes or create DNS, TLS, a database service or customer accounts.

Inspect and record the explicit operator choice:

```sh
python scripts/evidence_release.py --root /srv/transport3r-install inspect --release RELEASE_SHA
python scripts/evidence_release.py --root /srv/transport3r-install current
python scripts/evidence_release.py --root /srv/transport3r-install activate \
  --release RELEASE_SHA --expected-current NONE --operator "Authorized operator"
```

Replace placeholders with actual values. On later updates, `--expected-current` must be the
full current release SHA. A stale expectation fails without switching the pointer. Immutable
history records precede the atomic pointer switch; unreferenced history records after a crash
are not completed activations. A retained `.activation.lock` requires operator investigation;
never automatically delete a possibly live lock.

Start the service with the selected release's exact paths:

```sh
python scripts/evidence_api.py /srv/transport3r-install/releases/RELEASE_SHA/warehouse.duckdb \
  --audit-report /srv/transport3r-install/releases/RELEASE_SHA/audit.json \
  --host 127.0.0.1 --port 8787 --allow-origin https://jeremyhennessy.github.io
```

The existing `deploy/evidence-api/compose.nri.example.yml` supports nonroot, read-only mounted
FMCSA/audit/FEMA files. Its Docker healthcheck now uses `/readyz`. Set all three absolute host
paths to accepted files. Docker/Compose startup and host security must be tested on the actual
approved host; they were not established by local Python tests.

## Required host controls before client access

Terminate HTTPS at an approved reverse proxy; restrict direct access to 8787. Configure an
explicit origin, read-only mounts, GET-only public-source routes, request/rate/concurrency limits,
timeouts, TLS renewal, OS/container patching and monitoring. Domain ownership, billing, host
access and identity policies require owner approval. Do not put API credentials into the Pages
bundle. The insurer application must use a separate authenticated private service; these public
endpoints are not that service.

Before setting `EVIDENCE_API_URL`, request `/readyz`, `/healthz`, `/v1/integrity` and known carriers
through the actual HTTPS endpoint. Check the same full warehouse SHA, cut and source lineage
against retained SQL results and actual browser values. Test missing audit, stopped service,
invalid carrier, slow response and changed-file failure. Capture evidence, not just HTTP 200.

Monitor readiness, API error/latency, free disk, memory, job completion, accepted-cut age and
source publication failures. A failed new source cut keeps the prior accepted release and
produces an alert; it must not replace values with zero. Schedule refresh only through authorized
existing infrastructure. No new nationwide acquisition workflow is authorized by this runbook.

## Backup, restore and rollback

Back up immutable release directories and activation history to separate storage. Recompute
file hashes after copy. Test `inspect` against a restored copy. Synthetic tests exercise this
sequence but do not replace an actual recovery drill. Keep failed/new files for diagnosis.

```sh
python scripts/evidence_release.py --root /srv/transport3r-install rollback \
  --expected-current CURRENT_RELEASE_SHA --operator "Authorized recovery operator"
```

Restart the process/container on the selected previous files and repeat HTTPS `/readyz`, exact
SHA, representative carrier, Integrity and browser checks. A pointer update is deliberately
reported as `POINTER_CHANGED_RESTART_AND_HTTP_VERIFICATION_REQUIRED`, never as deployed.
Agree actual RPO/RTO and retention with the operator and insurer; none is certified here.

## Local private workspace

New launches use the OS user-data directory, or an explicit `TRANSPORT3R_PRIVATE_DATA` / `--data`
location outside the repository. The Windows launcher supports `-DataDirectory`.
If legacy records exist inside the repository, startup requests an explicit migration decision
instead of silently opening a new empty workspace. Stop the old service, back up and verify
its entire private directory, copy it to the reviewed location, validate portfolio/review/history
counts and only then restart. Never delete the old directory until recovery is verified.

```sh
python scripts/private_workspace.py --data /srv/transport3r-private/workspace --port 4789
```

This remains single-owner loopback HTTP with session/origin/Host controls. It is not safe to put
behind a public tunnel and call it a multi-user service. Verify owner-only filesystem/Windows
ACLs, encrypted storage, backup permissions and retention on the actual installation. Keep
claims and private screenshots out of Git, Pages and public CI artifacts.

## Recurring cost comparison (USD, observed November 9, 2026)

- A DigitalOcean Basic regular Droplet with 4 vCPU, 8 GiB memory and 160 GiB SSD is listed at
  $48/month. Its basic daily backup option adds 30%, making $62.40/month for those two items;
  weekly backup adds 20%, making $57.60. This excludes taxes, domain, separate recovery storage,
  extra services and operator time. It is a price example, not measured capacity acceptance.
  Sources: https://www.digitalocean.com/pricing/droplets and
  https://docs.digitalocean.com/products/backups/details/pricing/ .
- On an existing owned server, illustrative incremental power of 50 W for 730 hours at
  $0.15/kWh is $5.48/month. All three inputs are assumptions, not the user's actual bill.
  Hardware amortization, UPS, business internet, replacement disks, offsite backup and staff
  are additional. Existing hardware does not make a secure reliable service free.
- Azure requires a region/size/disk/backup/egress/support estimate. Use an actual Canada Central
  quote in the correct account/currency rather than inventing an equivalent VM price. Microsoft's
  calculator uses the Retail Prices API and accepts negotiated account pricing:
  https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/pricing-calculator .

No provider was purchased, connected or deployed. Render was discovered but is not connected;
previous connection suggestions do not establish authorization or provisioned infrastructure.
