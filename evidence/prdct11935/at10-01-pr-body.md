RE-FETCHED LIVE AT AUDIT TIME — this file is the PR body as the API returns it, not a local draft.
  command:   curl -H 'Authorization: Bearer $GH_TOKEN' https://api.github.com/repos/onyxsecurity/onyx/pulls/12329 | jq -r .body
  fetched:   2026-08-24T03:53:32Z
  pr:        https://github.com/onyxsecurity/onyx/pull/12329
  onyx head: 2b60fdc4df25188104e737e6311087681355eff8
  bytes:     242520
  identity:  everything below the marker line is byte-identical to what that command returned.
  round 49:  the deploy-safety round. research adjudicated verify-r39 GAP 1 and re-froze the plan
             (sha 863dbd105e74...). This body now states the MEASURED production LaunchDarkly posture
             with its read timestamp, drops the false 'could not determine' entry for it, and carries
             the pre-merge instruction to confirm the intended posture before flux-fleet#2307 is
             merged — because as measured the enablement is a LIVE CUTOVER for Centerpoint Energy and
             every unmatched c02 tenant, not a dark deploy. The same statement is on flux-fleet#2307
             itself. Evidence: at10-08-prod-ld-posture.txt (audit-time ?env=production read, READ-ONLY).
Azure cells were still on the gen-1 scheduled Go/Temporal scanner flow. The new asset-writer lane —
`endpoint_asset_ingestion`, the scanner-lane "one writer" that ingests off Temporal — did not exist there:
the service built an S3 client and an SQS consumer unconditionally, and its parser understood only S3
notifications. Flipping the per-tenant `endpoint-asset-ingestion` flag for an Azure tenant was a silent
no-op, and following the documented cutover order would have left that tenant with no writer at all.

This makes the lane exist on Azure, end to end, and fixes the live footguns the ticket names.
===== PR BODY AS RE-FETCHED, VERBATIM, BEGINS ON THE NEXT LINE =====
Azure cells were still on the gen-1 scheduled Go/Temporal scanner flow. The new asset-writer lane —
`endpoint_asset_ingestion`, the scanner-lane "one writer" that ingests off Temporal — did not exist there:
the service built an S3 client and an SQS consumer unconditionally, and its parser understood only S3
notifications. Flipping the per-tenant `endpoint-asset-ingestion` flag for an Azure tenant was a silent
no-op, and following the documented cutover order would have left that tenant with no writer at all.

This makes the lane exist on Azure, end to end, and fixes the live footguns the ticket names.

**App (parity gap A).** `ONYX__CLOUD` now selects the whole path: Service Bus consumption (a client per
worker — the ASB receiver is not coroutine-safe — with a dedicated client behind readiness), object reads
through `create_storage_client` (`BlobStorageClient` already satisfies the pipeline's `ObjectStore`), and an
Event Grid `BlobCreated` parser ported from `backend/internal/queue/eventgrid/event.go` and normalized onto
the existing `S3Record` shape, so nothing downstream of parsing is cloud-aware. A boot-time assertion refuses
any config whose transport contradicts the declared cloud.

**Dead path (parity gap D4).** Both gen-2 event consumers carried a real-looking Azure branch that acked and
dropped 100% of Event Grid messages. It is deleted, and `ONYX__CLOUD=azure` is now a startup refusal naming
the service that owns the lane.

**Infra + deployment (parity gaps B and C)** are authored in sibling branches (see the reconciliation list);
both are proven here by validate/render plus a live replica of the design in the Azure lab.

---

## ⚠️ OWNER SCOPE CORRECTION (round 45) — read this before anything below it

The ticket owner ruled this ticket **Azure enablement only. It is not a bug-fix PR.** That ruling
overrides every earlier direction in this body, and two things follow from it.

**1. The old-lane parity work has been REVERTED out of this PR.** It was work this branch had
accumulated against the *shared writer*, not against the Azure transport, and it does not belong to
this ticket. Reverted, each back to `main` byte-for-byte:

| file | what came out |
|---|---|
| `ingestion/writers.py` | seeded Claude connectors (`build_seeded_connector_servers`), the `scanner_version` stamp, `_meter_session_alerts`, the `InventoryWriteResult` plumbing |
| `ingestion/extract.py` | `_extension_name_from_mcpb` and its helpers |
| `ingestion/object_processor.py` | the `processed_with_failures` split and `agent_slices_dropped` |
| `ingestion/pipeline.py` | `failed_agent_slices`; `write_inventory` returns `list[int]` again |
| `desktop_agent_creator/scanner_version.py` | deleted — `resolve_scanner_version_for_agent` stays where `main` has it, `workflow.py:207` |
| `metrics.py` | **partial**: the `processed_with_failures` outcome value, `AgentSlicesDroppedLabels` and the `agent_slices_dropped` counter are gone; the SQS→queue HELP-text rewording stays, as the ruling directs |
| four parity test files | `test_writers.py`, `test_extract.py`, `test_object_processor.py` restored; `test_session_alert_failure_is_metered.py` deleted |

Everything that makes the Azure lane work is **kept**: `transport_guard.py` and its validators,
`AssetIngestionASBConfig`, the `service.py` cloud branch, blob dispatch in `event_parser.py`,
`_system_properties` in `asb.py`, `event_time.py`,
the sibling consumers' dead-Azure-branch deletion plus `assert_cloud_supported`, the helm ASB stanzas,
`azure-storage-blob`, the ADR (now 0069), the monitoring doc, and their tests.

**The queue-layer abandon/pool work was DROPPED from this PR as superseded by `main`** (owner ruling #2,
round 46). `main` landed its own `abandon_message` while this branch was open — the same hazard, solved the
same way — and the owner ruled: drop yours, do not merge the two designs. So `client.py`, `sqs.py` and
`consumer_pool.py` are **byte-identical to `origin/main` and out of this diff entirely**, and `asb.py`
keeps only `_system_properties`, which `main` does not have.

*The trap in that merge is real and was checked, not assumed:* `asb.py` and `client.py` merge **cleanly**
and each ends up with **two** `abandon_message` definitions; Python takes the last, so `main`'s `-> None`
silently wins and any caller reading a bool gets `None` — always falsy — with the tests still green. Both
files now carry exactly ONE definition and no code in this PR reads a return value from it. Every check:
[`at11-09`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-09-r46-queue-supersession.txt).

**Three things this PR therefore no longer ships, all tracked as follow-ups.** *Retry pacing on Service
Bus* — deferred, not dropped, and tracked on **[PRDCT-12070](https://app.clickup.com/t/86bbj2pqn)**
(*"Durable retry for the Azure scanner-ingestion lane: a dependency outage permanently dead-letters real
objects (max_delivery 5 × 5s backoff exhausts the budget in ~25s)"*), which already carried exactly this
scope from a live outage observed on the lab lane. Without pacing a dependency outage cycles receive →
fail → abandon at full speed and burns the queue's `max_delivery_count` on work that was never bad; the
ticket now also records what this PR removed, so whoever picks it up has the shape and not just the intent
([`at10-07`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-07-r46-body-and-adr.txt)
carries the live fetch). *Serialising sends on the one AMQP
link* — `ServiceBusSender` is not coroutine-safe, and two overlapping sends leave the loser with a
half-open handler. *Deriving the lock-renewal delay from the message's own `locked_until_utc`* rather than
from a configured interval another repo's Terraform has to stay below. The last two went because the
plan's guard is explicit that `_system_properties` is the only `asb.py` hunk this PR may carry.

Audited hunk-by-hunk against the ruling, per bullet and per kept member:
[`at11-01-diff-audit.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-01-diff-audit.txt)
— 40 files, 100 hunks, **0 uncategorised**, every REVERT bullet absent, every KEEP member present with
its test file resolved.

**One judgement call inside the partial revert, surfaced rather than decided quietly.** The ruling's
`metrics.py` bullet names the SQS→queue rewording as the thing to keep. Four of the five surviving
lines are exactly that. The fifth is a different rewording — `step_total`'s help text went from *"map
1:1 to the retired Temporal workflows/activities"* to *"…to the Temporal units this lane replaces,
still live on every cell not yet cut over"*. It is not on the drop list and it is not the SQS→queue
line either. It was kept because reverting it restores a sentence that is factually wrong (those
Temporal units are not retired), but it is the owner's to overrule.

**2. C13 is NO LONGER CLAIMED AS PROVEN by this PR.** Every C13 parity claim below this banner —
including the "direction rule is met absolutely" language in Design Decisions and in the C13 section —
is **withdrawn**. Stated plainly, and without hedging:

> **The new lane diverges from gen-1. It does not write seeded Claude connectors, it does not derive
> mcpb extension provenance, and it does not stamp `scanner_version`.** That divergence is real, it is
> unfixed in this PR, it is **out of scope for this ticket**, and it is **tracked separately on
> [PRDCT-12061](https://app.clickup.com/t/86bbhqxe8)**, whose description now enumerates all five
> reverted capabilities ([live fetch](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-06-tracker-fetch.txt)). The
> owner will rule it an accepted gap.

The fixes are not re-added anywhere, and no separate PR was opened to carry them —
[`at11-06-single-pr.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-06-single-pr.txt)
enumerates every PR naming this ticket in all three repos and lists #12382's complete file set to show
it carries none of the reverted files. The C13 material further down is left in place as the **record of
what was measured**, not as a claim this PR makes; read it with this banner attached.

What at6 still stands behind, unchanged by the ruling, is the narrower and load-bearing claim: **the
same writer, fed the same bytes, writes the same rows on either transport.**

---

## This PR changes NO behaviour that runs on an AWS cell

The ruling asks for this to be proven and stated. It is stated here, and the proof is four independent
lines of evidence rather than one.

**0. Which change causes the AWS rolling restart — measured, because an earlier version of this section got
the attribution wrong.** An independent review reported that the AWS cells which actually run these services
(`ox-aws-p-use1-c01/intuit`, `ox-aws-p-use1-c03/saas` prod, `ox-aws-s-use1-c01/saas` staging) take an
**8 / 8 / 18** line render delta — empty ASB stanzas plus a `checksum/config` rollover, i.e. a one-time
rolling restart. **That figure is right.** What this section briefly claimed — that it does not reproduce —
was measuring the wrong change, and the correction is worth stating plainly because it cuts against this PR:

- **flux-fleet#2307 contributes 0.** `git diff --name-only 2c8ad2f2d4..a4493c1e5ac0` is **8 files, six of
  them the two AZURE instances plus two docs**; re-rendering the three AWS cells at that PR's merge-base and
  at its head with the repo's own `scripts/render-snapshot.sh` gives **0 changed lines** on all three.
  Merging the flux flip cannot restart an AWS workload.
- **This PR's own chart change contributes the 8 / 8 / 18.** `infra/helm/onyx-app/values.yaml` removes the
  two empty gen-2 stanzas (`scanner_events_asb`, `mcp_gateway_events_asb`) and adds two empty ones
  (`alert_processing_asb`, `asset_ingestion_asb`), which moves the rendered `config.yaml` and rolls its
  `checksum/config`. Measured with **identical values on both sides**, so the delta is the chart's:
  [`at11-08`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-08-flux-render-aws-cells.txt) — 8 for `c01/intuit`, 8 for `c03/saas`, 18 for
  `s-use1-c01/saas`, and **0** for every cell that does not deploy these services.

So the consequence is real and is **this PR's**: a single rolling restart of those three workloads when the
chart lands. It is semantically inert — an empty stanza is what the config model already defaults to, and a
removed field is accepted-and-ignored because `BaseCustomSettings` sets `extra="allow"` — and carve-out (b)
below has always disclosed it. Both measurements, and this correction, are in
[`at10-25-aws-cell-render.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-25-aws-cell-render.txt).

**1. Nothing in the diff can reach an AWS cell's behaviour.** All 40 files walked individually in
[`at10-22-scope-revert.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-22-scope-revert.txt)
§4. Three files are never executed on AWS; three are a verbatim move (`_parse_event_time` lifted into
`event_time.py`, docstring generalised, every statement identical); six are shared code an AWS pod does
run, and each is measured, not argued:

- the shared queue layer — `client.py`, `sqs.py`, `consumer_pool.py` — is **not in this diff at all**
  after the round-46 ruling: each is byte-identical to `origin/main`. There is nothing left in it for this
  PR to regress, and the AWS pod runs exactly `main`'s code.
- `parser_for_cloud(AWS)` returns **the same function object** the lane already called, and
  `empty_parse_is_poison(AWS)` is `False`, so the new dead-letter branch is unreachable on AWS.
- `AssetIngestionMessageHandler`'s new arguments **default to the previous hard-coded behaviour**; the
  poison path moved into `_park_poison` with the same labels, the same call and the same fallback.
- `AssetIngestionS3Config`'s base swap keeps all four fields with the **same names and same defaults**
  (`aws_region` still defaults to `us-east-1`, the rest to `None`), and `create_storage_client`'s AWS arm — pre-existing
  `common_core`, not in this diff — constructs `S3Client` from exactly those fields.
- `metrics.py` is HELP text only: **no metric name, label set or type moved**, so no dashboard, alert
  or recording rule changes.
- the gen-2 consumers keep their old `else` arm, dedented. `_health_client` went away because on AWS it
  was literally assigned `self._queue_client`.

**2. The lane, run for real on both images, writes the same rows — and the delta that used to stand here is
gone because its CAUSE was removed, not normalised away.** A real `onyx-scanner` run's eight
`source=mcp-scanner` request bodies were recorded verbatim and replayed **byte-for-byte through the real
Kong front door** (key-auth, real consumer) into two fully isolated lanes — one writer on an image built
from the merge-base (`:r45c-base`, digest `d65c32ca…`), one on the head image (`:r46b-head`, digest
`d1087c00…`), each with its own bucket, queue and tenant.

**Re-driven this round, twice, and the raw diff is now 0.** Earlier revisions reported a **raw 8-line**
delta defended by a normalised 0-line comparison — every one of the 8 an element ORDER difference inside one
connection's `metadata.sources` array, because `replace_scan_connection_sources` overwrites that field
authoritatively once per object, so the surviving order is whichever object landed last. That is a
pre-existing, arrival-order dependence this PR does not touch (`mcp_writer.py` and `source_attribution.py`
both have **0** diff lines). Rather than keep normalising it, the harness now **settle-gates the replay**:
body N+1 is not sent until N has landed, the leg queue is drained and the leg writer has logged its Nth
`outcome=processed`. Identical arrival order on both legs removes the race, and the measurement becomes:

- **RAW base-vs-head diff: `changed lines: 0`** in each of two consecutive runs — and **one sha256,
  `bfab55dfb10901c1…`, across all four writer-graph dumps** (base×run1, head×run1, base×run2, head×run2,
  1074 lines each). Cross-run per-leg diff: 0. The r45 normaliser still runs and still reports 0; it no
  longer carries the argument.
- **The two legs provably ran different images**: every one of the base leg's 8 `outcome=processed` lines is
  `lineno=135`, every one of the head leg's is `lineno=171`. 32/32 Kong POSTs returned 200; the no-key guard
  returned 401.
- **Ten negative isolation assertions, all clean**: shared bucket prefixes unchanged (158 / 57), shared queue
  0, both DLQs 0, zero cross-leg keys or log lines in either direction, and the shared writer processed
  **zero** lines for either leg tenant in the window.
- `issue_instances` is **reported separately and excluded from the criterion**, with the reason: it is
  written by the shared downstream issue-detection service (one instance serving both legs, zero
  merge-base..head hunks), so it says nothing about base-vs-head. Measured 0 | 0 in both runs, with a live
  control proving the mechanism is not simply dead.

One honest note about the harness itself: setup's recipe **deadlocked twice** as handed over, because this
node's kubelet discards rotated container-log history, so the settle gate's cumulative `processed` count
collapsed mid-run. The gate now reads a continuous per-leg follower from a window mark instead. Payloads,
lanes, dump queries and the comparison were untouched, and the aborted attempts are disclosed rather than
reported as results.
[`at11-02`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-02-aws-lane-base.txt) · [`at11-03`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-03-aws-lane-head.txt) ·
[`at11-04`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-04-aws-lane-diff.txt)

**A pre-existing behaviour this leg documents rather than fixes:** asset identity for an **unpinned**
launcher is not a pure function of the payload. `mcp-remote`'s concrete version is resolved from npm's live
`dist-tags.latest` at write time (`version_resolution.py:373-380` → `package_registry/npm.py:78`, or the
async heal at `mcp_server_enrichment/activities.py:926`, read back at `mcp_writer.py:477-478`), so two
windows hours apart legitimately key the same server under different versions — this leg's dumps differ from
an earlier window's by exactly four lines, all `mcp-remote::0.1.45` → `0.1.49`. All five files on that path
carry **0** merge-base..head diff lines, so it is pre-existing and transport-independent; both legs resolved
identically within each run, so it contributes 0 to every comparison above.

**3. The two gen-2 consumers boot and consume identically on both images.** Their changed hunks execute
at AWS-mode boot, so hunk-reading is not enough: both were rolled onto each image and driven through one
real consume. Same receive, same source decision, same ack, 0 restarts, 0 errors on either.
[`at11-07`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-07-sibling-consumers-aws.txt)

**4. gen-1 is untouched and still running.** `backend/` — 2145 tracked files, **0 changed**;
`desktop_agent_creator/` — 39 tracked, **0 changed**. `ScannerTenantWorkflow` observed executing on the
stack under the head deploy, before and after the controlled legs.
[`at11-05`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-05-gen1-untouched.txt)

### The two carve-outs, stated rather than buried

**(a) Metrics HELP text.** The kept SQS→queue rewording is visible on an AWS cell's `/metrics`. It is
text on existing metrics — no name, label or type changed — and the owner ruled it Azure-correct and
kept. The `step_total` rewording in the judgement call above is the same kind of thing.

**(b) One rolling restart when the chart lands.** The named cells `c01/saas`, `c01/bamfunds` and
`c04/saas` render **0 changed lines** base-vs-head — but they deploy none of the services this PR
touches, so their zeros prove little. The AWS cells that *do* run them — **`c01/intuit`, `c03/saas`,
`s-use1-c01/saas`** — render an 8-to-18-line delta: two empty ASB stanzas added to
`endpoint-asset-ingestion`'s `config.yaml`, the two empty gen-2 `*_asb` stanzas removed, and a
`checksum/config` annotation change. The config is semantically unchanged (an empty stanza is what the
model already defaults to; a removed field is accepted-and-ignored because `BaseCustomSettings` sets
`extra="allow"`), and the real rendered `c03/saas` config was fed to the head config model and boots
into the AWS lane. The one operational consequence is therefore a **single rolling restart** of those
workloads on deploy. Every cell's diff, and that probe:
[`at11-08`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-08-flux-render-aws-cells.txt)

### The bound on the live leg, pre-declared

The base-vs-head live leg drives the **created** class. Matched and reingest-skip on the AWS transport
are covered instead by the hunk map (no hunk touches the writer's per-class paths), the gen-2 consumer
leg, the per-instance render diffs, and at6's same-image two-transport per-class diffs. That is a real
bound and it is stated here rather than left to be discovered.

---

## Where each proof lives — read this if you are scoring this PR

An external review board scored this PR **LOW 2/7** on five rules, and the diagnosis was placement rather
than substance: the proofs existed but lived in a workspace no reviewer can reach. **They are now in this
PR.** Every text proof below is INLINE — in this body or in a PR comment, never behind a path you cannot
open. Nothing is truncated: where a capture exceeded GitHub's 65,536-character comment limit it is split
at line boundaries into numbered parts, and the parts were re-fetched from the API and proven
byte-identical to the source capture before this line was written — **24/24 payloads verified, across 40
comments, 0 secret-shaped tokens**.

| Rule | What it proves | Where it is now |
|---|---|---|
| **S4** | sibling sweep — every cloud-branching consumer site, one decided row | **this body**, section *S4 — sibling sweep* · raw measurement (every cite printed with its line numbers) in [this comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379850160) |
| **C15** | defaults inventory ⚠️ awaiting the owner's ruling | **this body**, section *C15 — defaults inventory*, plus the full 101-item measurement in a comment |
| **C11** | before the 2nd ingest | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379800473) |
| **C11** | after the 2nd ingest | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379800879) |
| **C11** | the redelivery on the real broker | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379801257) |
| **C11** | dedup keys at their enforcement points | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379801402) |
| **C11** | the constraint NAMES from the live DB | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379801555) |
| **C11** | the isolated replay + positive control | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379801701) |
| **C13** | **per-class closure table — every settlement class, closed or not-run (34 rows)** | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5380385507) |
| **C13** | the completeness check output (`25/25 closed`) | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5380385636) |
| **C13** | [`at6-05-per-class.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-05-per-class.txt), pasted whole | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5380385786) |
| **C13** | the closure half of [`at6-06-ledger.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-06-ledger.txt), pasted whole (2 parts) | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5380385933) |
| **C2** | **POSTURE — pasted `issue_instances` + `asset_posture_findings` rows** | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5380387800) |
| **C13** | settlement inventory | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379801853) |
| **C13** | gen-1 FULL row dump (7 parts) | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379801987) |
| **C13** | new-lane FULL row dump (7 parts) | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379803070) |
| **C13** | diff · created leg | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379804072) |
| **C13** | diff · matched leg | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379804181) |
| **C13** | diff · reingest-skip leg | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379804287) |
| **C2** | the real install on the machine | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379804405) |
| **C2** | the scan payload sent through Kong | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379804532) |
| **C2** | DB rows · desktop agent | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379804636) |
| **C2** | DB rows · MCP server | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379804734) |
| **C2** | DB rows · skills | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379804847) |
| **C2** | DB rows · subagents | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379804976) |
| **C2** | DB rows · usage sessions | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379805095) |
| **C2** | DB rows · tools + posture | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379805213) |
| **C2** | fidelity — scanned vs stored | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379805327) |
| **C2** | the second scan (lifecycle) | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379805443) |
| **C15** | the full defaults inventory (101 rows) | [comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379824656) |

*(The C13 row dumps are the two largest: the gen-1 and new-lane full dumps are 7 comment-parts each.
Parts are numbered `part N of M` and concatenate byte-for-byte back to the capture.)*

---

## Design Decisions

- **C13 parity is NOT claimed by this PR — WITHDRAWN by the round-45 owner ruling.** This bullet used to
  argue that C13's direction rule was met absolutely and that the residual divergences rode a plan
  amendment. The ticket owner has since ruled the ticket Azure enablement only, so that argument is
  withdrawn and the parity work it described has been reverted out of the branch. What this PR now says
  about C13 is only this: **the new lane does not write seeded Claude connectors, does not derive mcpb
  extension provenance, and does not stamp `scanner_version`** — out of scope here, tracked separately,
  and the owner will rule it an accepted gap. The narrower claim that survives, and that this PR does
  stand behind, is transport equivalence: the same writer, fed the same bytes, writes the same rows on
  SQS+S3 as on Service Bus+Blob ([`at6-07`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-07-transport-equivalence.txt), 0 changed lines).
- **One Event Grid BlobCreated parser in the platform — this lane consumes `parse_blob_event_message`
  rather than shipping a second one.** While this branch was open, `main` landed
  `common_core/services/ingestion_events/blob_event.py` for the sensor lane: the same notification,
  normalised onto the same `S3Record`. Merging textually would have left two parsers of one schema
  colliding in one package `__init__`, free to drift. Neither was a superset, so the merge is a
  *resolution*: `eventgrid_event.py` and `EventGridSubjectError` are deleted and this lane reads the
  shared parser. It is the incumbent, it already has a live consumer, and it brings what this one
  lacked — the CloudEvents spelling, an `eventType` filter, and `SubscriptionValidationEvent`
  tolerance. It reads the blob location from `data.url`, which the real captured lab delivery carries
  alongside `subject`, naming the identical container and key ([`evidence/at1-03-eventgrid-message.json`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-03-eventgrid-message.json),
  pinned as a parser test). The one capability that was ours — telling *permanently unprocessable* from
  *junk body*, so the first dead-letters and the second acks — moved to the consumer, where settlement
  policy belongs: the shared parser already raises on a non-JSON body and returns `[]` for one that
  names no object, and `empty_parse_is_poison(cloud)` records why the two clouds settle that empty
  result differently (on AWS it is only ever an `s3:TestEvent`, which must be acked). `blob_event` also
  now reads the shared `event_time` helper instead of a third private copy. The sensor lane's parser
  contract, tests and consumer are untouched.
- **The declared cloud selects transport + storage + schema together, and a mismatch refuses to boot**
  (`common_core/services/queue/transport_guard.py`, called from each service's config validator). The ticket
  offered "cloud-aware flags **or** a boot assertion"; the assertion is deterministic, in-repo, and covers
  every misconfiguration rather than only the flag-shaped one. It fires on a *contradiction* only, so a local
  run with no transport configured stays valid. Rationale and rejected alternatives: ADR
  [`docs/decisions/0069-the-declared-cloud-decides-the-ingestion-transport.md`](docs/decisions/0069-the-declared-cloud-decides-the-ingestion-transport.md).
- **Gen-2's Azure branch is deleted, not ported** (`scanner_event_consumer_service`,
  `mcp_gateway_event_consumer_service`). Porting the parser there would have given Azure a second writer for
  the same objects, against the one-writer direction this lane exists to establish. Deleting alone would have
  left a worse trap (silent fall-through to SQS), so each config now refuses `cloud=azure` explicitly.
- **Poison settles by cause, not by transport.** An Event Grid event whose `subject` carries no blob location
  can never be processed, so it is dead-lettered with a reason (Go treats the same class as permanent);
  junk that is not this transport's schema stays a metered `parse_err` that acks, exactly as the AWS lane
  behaves. On Azure this uses the queue's native `$DeadLetterQueue` — no `dlq_url` to configure.
- **The blob key IS percent-decoded** (`common_core/services/ingestion_events/blob_event.py:56`, `unquote(key)`).
  **Round-34 correction (gate GAP-7b):** this bullet used to read "The blob name is not URL-decoded" and cite
  `eventgrid_event.py` — wrong twice, and the second half is the one that matters. That file does not exist at
  HEAD (this PR deletes it in favour of the platform parser, as §43 records), and the shipped behaviour is the
  *opposite* of what the bullet claimed: `blob_event.py` unquotes both key and container, and its own comment
  says why — Vector writes `=` in every path segment (`tenant=`, `source=`), so a still-encoded `%3D` would
  miss on fetch and defeat the tenant/source extraction downstream. Correcting only the filename would have
  left a false claim about what the lane does. Tenant/source segments stay
  readable regardless, because `key_parser` already decodes each segment defensively.
- **`eventType` is deliberately not filtered** (Go doesn't either). The Event Grid subscription's
  `included_event_types` is where that restriction belongs; a non-created event that slipped past it fails its
  blob read and settles on the existing failed → redeliver → dead-letter path instead of being swallowed here.
- **Service Bus publishes the same `_sys_*` delivery facts SQS does** (`asb.py`), normalizing its
  *prior*-delivery count to SQS's 1-based receive count, so the shared handler meters redeliveries and message
  age identically on both clouds. Without it the Azure lane would have silently reported zero redeliveries.
- **The lane binds to its own published keys, not the shared `${servicebus_namespace}`** (infrastructure).
  The shared key is published only when the *extension* lane's toggle is on, so reusing it would make this
  lane silently depend on a different lane's switch. The lane's own pair is published **with the resources
  it reads** — gated on `create_service_bus && create_endpoint_asset_ingestion_queue`, because both values
  are read off the real queue and namespace rather than string-composed. Be precise about what that gate
  does and does not do, because an earlier version of this bullet — and of the comment it quoted — had it
  backwards. It does **not** fail the render: Flux resolves an unprovided `${...}` to the **empty string**
  and the Kustomization reconciles successfully. An instance whose flux release enables the lane while the
  queue toggle is off therefore renders an **empty queue name**, and the failure surfaces at the pod, as
  the transport guard's refusal to start — a CrashLoopBackOff, not a substitution error. That is exactly
  why the apply **order** is load-bearing rather than hygiene: infrastructure first, then the flux toggle.
  Both `release.yaml` comments and the mirrored `fluxcd_config.tf` comment were corrected to say so
  ([`evidence/at8-04-comment-fix.diff`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-04-comment-fix.diff)).
- **The alert fan-out follows the cloud too.** The sessions step fans out one alert-processing message per
  (session, policy), and its producer was SQS-only — so on an Azure cell the lane would have written session
  rows and dropped every alert they derive, behind one warning. It now branches on `ONYX__CLOUD` the way the
  Temporal worker and the sanitization service already do, and the boot assertion covers that queue as well
  (absent stays a loud degrade; the wrong cloud's queue is a refusal).
- **The failed-handler release is `main`'s, not this PR's — WITHDRAWN as superseded.** This bullet used to
  describe a release-and-pace design added here: an explicit `abandon_message` on the queue client, called
  by the pool when a handler raises, returning whether the release was immediate so the pool could sleep
  `error_backoff_seconds` on Service Bus and not on SQS. `main` landed its own `abandon_message` while this
  branch was open and the owner ruled that one wins. The design is gone from this PR; the pacing half is a
  tracked follow-up. See the round-46 paragraph near the top of this body.
- **`azure-storage-blob` is declared where it is imported.** It reached the image only as a transitive of the
  `azure_mgmt` extra, so a lean install could accept an Azure config it had no Blob client to serve.
- **`op: remove`, not add-null, for the AWS-only leaf** (flux-fleet `drop-aws-only-values.yaml`). The ticket
  said add-null; `asset_ingestion_sqs` is a pydantic sub-model with a `default_factory`, not an optional
  scalar, so a rendered `asset_ingestion_sqs: null` fails validation and crash-loops the pod. `remove` is safe
  by that file's own rule (the base overlay sets the path unconditionally). **What `helm-equivalence.sh`
  actually does here, corrected:** it was run twice and exits **1** both times with a non-empty diff, and it
  structurally must — its only exit-0 condition is byte-identical rendered objects, which is unreachable for a
  change that *enables a new workload*. `at8-03` says exactly that in its own header. The earlier wording here
  ("shows it changes zero rendered bytes") was false and is withdrawn. What answers `d-c4null` is the
  **isolation-ref run**: rendering against a reference that differs only by the drop entries shows they are
  **load-bearing** — without them the Azure pod receives `${region}=us-east-1` and the IRSA annotation. That
  run, and both exit-1 runs, are in `evidence/at8-03`.

- **Seeding the Claude connector MCP servers — WITHDRAWN by the round-45 owner ruling; this bullet used to
  describe code that is no longer in the diff.** An earlier revision described `_mcp_upsert` merging
  `build_seeded_connector_servers(agent.app_name)` into its server list so the in-process writer would write
  the four connector assets gen-1 writes. That work was **reverted**. At this head the symbol appears only in
  gen-1's own Temporal lane (`integrations/desktop_agent_creator/connector_seed.py:37`, `workflow.py:34,726`),
  the new lane never calls it (`grep -rn seeded_connector backend_python/src/endpoint_asset_ingestion/` →
  **0**), and the PR diff mentions it **0** times (`git diff 822abd2356..HEAD | grep -c
  build_seeded_connector_servers`). The reason is the owner's, quoted in the banner at the top of this body:
  *"PRDCT-11935 is Azure ENABLEMENT ONLY. It is not a bug-fix PR."* The connector gap is therefore an
  **owner-accepted gap** again rather than something this transport PR fixes, it is tracked with the other
  reverted items on PRDCT-12061 — and, the part a reviewer scoring blast radius should take from it, **this
  PR no longer changes what any AWS cell writes for a Claude Code agent.**
## S4 — sibling sweep: every cloud-branching consumer site, one decided row

The board scored S4 LOW because the sweep behind this change was never shown. Here it is, in full. The
pattern this PR fixes is *"a consumer picks its queue transport and object store from the declared cloud"*.
The sweep below is mechanical — every `ConsumerPool` construction and every `create_storage_client` /
cloud-switch call site in `backend_python/src` and `backend/` — and **every site gets
a decision, including the ones this PR deliberately does not touch.** The sweep was **re-run at the current
head `2b60fdc4df`** as this body is written (it used to cite `16b7bca77c`, a head that no longer exists on
this branch): the consumer class is unchanged — `grep -rl 'ConsumerPool(' backend_python/src` returns the
same five services listed in table A plus the pool module itself — and every `file:line` below was re-opened
at head, which moved exactly one cite (A5, corrected in place).

Two of these rows are findings the sweep itself produced, and I am **not** self-approving either: they are
marked *awaiting the owner's ruling*, like the C15 table below.

### A · Queue consumers (the exact pattern class — services running a `ConsumerPool`)

| # | Site | Branches on cloud? | Calls the guard? | Decision |
|---|---|---|---|---|
| **A1** | `endpoint_asset_ingestion/service.py:232` | yes, on `ONYX__CLOUD` | **yes** — `config.py:202` | **FIXED HERE.** The subject of this PR: ASB factory-mode pool on Azure, shared SQS client on AWS. |
| **A2** | `scanner_event_consumer_service/service.py:75` | no — branch **deleted** by this PR | **yes** — `config.py:87` `assert_cloud_supported(supported=AWS)` | **FIXED HERE.** The dead Azure branch is removed, not ported; 0 hits for `ASBQueueClient\|ASBConfig\|parse_blob_event_message` in the package at head. |
| **A3** | `mcp_gateway_event_consumer_service/service.py:74` | no — branch **deleted** by this PR | **yes** — `config.py:93` | **FIXED HERE.** Symmetric deletion; same 0-hit grep. |
| **A4** | `alert_processor_service/service.py:96` | **yes, on `ONYX__CLOUD`** | **NO** | ⚠️ **UNGUARDED SIBLING — awaiting the owner's ruling. Not fixed here, and not silently absorbed.** This is the closest structural twin of A1: same cloud switch, same ASB-factory-vs-shared-SQS shape. Its config has **no `model_validator` at all**, so `ONYX__CLOUD=azure` with only the SQS queue URL set boots green and consumes the AWS queue — the exact fail-open footgun 3 exists to stop, in a different service. I did not extend this PR into another service's boot path on a placement round; the sweep's job is to surface it, and the owner's is to decide whether it rides here or gets its own change. |
| **A5** | `sensor_service/sensor_event_consumer.py:326-327` (its two pools at `:371`/`:373`; this row cited `:336` until the head-move re-check moved it) | yes — but on *which queue setting is configured*, **not** on `ONYX__CLOUD` | **NO** | **DELIBERATELY OUT OF SCOPE — pre-existing, documented counter-design.** The code states the choice explicitly (`:334-335`: transport is chosen by whichever is configured *"so the two queue settings cannot be contradicted by a third"*). It is a second Event-Grid consumer (`parse_blob_event_message` at `:190`) and it fails open by design (`:389` continues when the consumer will not start). Changing it would reverse a deliberate decision made outside this ticket. Named here so it is not mistaken for an oversight. |

### B · Queue producers that branch on cloud (same switch, no consumer loop)

| # | Site | Calls the guard? | Decision |
|---|---|---|---|
| **B1** | `endpoint_asset_ingestion/service.py:156,164` (alert fan-out) | **yes** — `config.py:214`, `required=False` | **FIXED HERE.** Deliberately `required=False`: an unconfigured alert producer warns loudly rather than refusing to boot, because losing alert fan-out must not take ingestion down with it. |
| **B2** | `python_temporal_worker/worker.py:2690` | no | **OUT OF SCOPE — named, and the sharper edge named with it.** Its `elif` at `:2703` carries **no cloud test**, so an Azure cell with an incomplete ASB stanza falls through to the SQS branch; both branches swallow the error and disable queue alerting while the worker stays healthy. Same family as A4. |
| **B3** | `sanitization_service/api/dependencies/sqs_alert_producer.py:40` | no | **OUT OF SCOPE — named.** Cloud switch with no assertion in `sanitization_service/config.py`. Same family as A4. |

### C · Go consumers (the gen-1 lanes — same pattern, other language)

| # | Site | Decision |
|---|---|---|
| **C1–C3** | `extension_ingest_consumer/consumer_service.go:299`, `extension_stats_consumer/consumer_service.go:69`, `extension_learner_consumer/consumer_service.go:240` | **OUT OF SCOPE, and this PR touches zero Go files** (`git diff origin/main...HEAD --name-only` has no `backend/` entry). All three branch on `cfg.Cloud` and each already errors on an unknown cloud and on a missing stanza for the selected cloud — so they are *partly* guarded. What none of them rejects is the mismatch case this PR's guard catches (`cloud=azure` **and** an SQS stanza present), and `grep -rn 'transport.*cloud\|TransportCloud' backend/` returns **0** — there is no Go equivalent of `transport_guard.py`. Porting the guard to Go is a separate change in a separate language; recorded, not smuggled in. |
| **D1–D4** | `alertenqueue/client.go:27`, `extension_ingest_consumer/consumer_service.go:223`, `temporal/worker/general/main.go:523`, `extension_ingest_consumer/consumer_service.go:272` | **OUT OF SCOPE — named.** D3 switches on raw `"azure"`/`"aws"` string literals rather than the `storage.CloudProvider` constants; D4 has **no** cloud branch at all (SQS-only DLQ), so an Azure cell gets no dead-letter path there. Both are pre-existing and outside this diff. |

### E · Object-store readers of scanner objects

| # | Site | Decision |
|---|---|---|
| **E1** | `endpoint_asset_ingestion/service.py:129` `create_storage_client(...)` | **FIXED HERE.** The hard `S3Client` is replaced by the cloud-selecting factory; the container comes from the storage **event record**, not from a bucket string. |
| **E2** | gen-1 Go scanner + MCP-gateway lanes (`temporal/worker/general/main.go:265`, `scanner_collector/activities.go:310`) | **ALREADY CLOUD-AWARE via the shared factory, with one thing I could not settle from this repo:** both pass `config.Ingestion.S3.Bucket` as the container name on Azure. That is correct only if the Azure overlay sets that field to the container. The overlays live in flux-fleet/infrastructure and I did not verify it — **stated as undetermined rather than asserted either way.** |
| **E3** | ~40 further `create_storage_client` sites (integrations, siem export, enrichers, crud, sanitization) | **ALREADY CORRECT.** All route through `common_core/services/storage_factory.py:47`, which is cloud-selecting. No sibling defect. |
| **E4** | `crud_service/api/routes/scanner_installations.py:410` — streams the **scanner scan log** from a hard-coded `S3Client` | ⚠️ **AWS-ONLY READER IN THIS LANE — awaiting the owner's ruling.** No cloud branch at all. On an Azure cell the ingest now writes the object (this PR) but this download endpoint cannot resolve it. The identical gap is already accepted and documented in-tree for a sibling path (`sanitization_service/services/swg_upload_storage.py:146-152`, *"⚠ KNOWN GAP, deliberately accepted: the READER is still AWS-only"*) — but the scanner-lane instance carries **no** such note. Surfaced by this sweep; not fixed here because it is a crud-service read path outside this PR's write path, and I will not self-approve a second service's scope. |

**Summary of the sweep:** 3 sites fixed here (A1–A3) plus 2 more in the same diff (B1, E1); 2 findings raised
for the owner (**A4**, **E4**); the rest named with an explicit reason for being out of scope. No site in the
pattern class is left undecided.

---

## C15 — defaults inventory ⚠️ AWAITING THE OWNER'S RULING (not self-approved)

The board scored C15 LOW because this change alters defaults and never inventoried them. It does — **101
of them**, across three repos (the numbering runs 1–102 but **skips #28**; this body said "102" twice and
was wrong by one). Re-derived at all three current heads this round — **62 HOLDS · 22 MOVED · 17 WITHDRAWN ·
39 NEW** — because two owner rulings removed capability after the first inventory was written, and 22 cites
had drifted (the whole `service_bus.tf` block moved ~+92 lines). The complete measured inventory, with `file:line` and before → after for
every one, is inline in **[this comment](https://github.com/onyxsecurity/onyx/pull/12329#issuecomment-5379824656)**. Below are the ones that carry real blast radius.

**Twelve more rows in the linked comment describe code the rulings removed.** Seventeen rows in total are
**WITHDRAWN** in the refreshed inventory — ten by the round-45 revert (#13, #14, #37, #38, #39, #40, #41,
#42, #43, #44, #45) and seven by the round-46 supersession (#19, #20, #21, #22, #23, #25 and the pacing
half) — and every one of the nine reverted files carries **0 hunks** against the merge-base, with the five
load-bearing ones byte-identical to `origin/main`. Only three of the seventeen were struck in this table
before this round. Two of them mattered most, because both advertised **GLOBAL** blast radius: **#37**
(seeded connectors — *"GLOBAL (BOTH CLOUDS)"*) and **#42** (`processed_with_failures` — *"any dashboard
filtering `outcome=processed` silently UNDER-COUNTS"*). A reviewer reading those believed this PR changes
what every cell meters and what every Claude Code install writes. **It changes neither.** The refreshed
inventory also adds **39 defaults the first pass never listed**, and re-anchors the cites that had drifted — 22 of them:
[`at10-13-defaults-inventory.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-13-defaults-inventory.txt).

**And the authorisation is cited honestly.** Roughly twenty of these defaults have **no ticket
authorisation** — they are judgement calls this run made, and the refreshed inventory marks each one as an
owner decision rather than inventing a quote for it. The same applies in the other direction: the ticket
contains no *"Azure enablement only"* sentence and no *"do not change AWS behaviour"* sentence — both come
from the **owner's rulings**, which is where this body cites them, and the ticket itself says
*"Live footguns (fix even if parity is deferred)"* and *"Do not retire gen-1 until parity lands."*

**I am not approving this table.** Several rows change behaviour on cells and services that never opted
into this lane, and two of them alter what an *existing, unrelated* service measures. That is an owner's
call, not mine, and it is the one thing in this PR I am explicitly asking for a decision on rather than
asserting is fine.

| # | Default | before → after | Blast radius | Deploy-day story |
|---|---|---|---|---|
| **78** ⚠️ | `endpoint-asset-ingestion.enabled` (`release.yaml:30`, both Azure cells) | `false` → **`true`** | **Live cutover, not a dark deploy** | Prod LD re-read at head: `on`, **`fallthrough` → `true`**; holdouts only `bamfunds`/`fireblocks`/`intuit-prod`; `Centerpoint Energy` targeted `true`. **LD is not a gate — this line is.** Confirm posture before merging flux-fleet#2307. |
| 15 | cloud/transport mismatch refusal (`transport_guard.py:22-84`, `config.py:189-225`) | any combination booted → `TransportCloudMismatchError` | **GLOBAL — every boot, AWS included** | A new way for a deploy to stop. **Second, uninventoried refusal:** `service.py:129-133` → `storage_factory.py:67-68` raises if `cloud=azure` lacks `blob.account_url`. |
| 10b ✅ **CORRECTED** | `reject_cleartext_endpoint` | ~~"GLOBAL, AWS cells too"~~ — **wrong.** It **pre-exists on `main`** (`c32bad53cc`; `git diff <merge-base> HEAD -- common_core/config.py` is **empty**) | **This service only** | Real change is `config.py:55`: `AssetIngestionS3Config(BaseCustomSettings)` → `(S3Config)`. Chart default `endpoint: ""` passes, so no cell is hit. |
| 24 | `_sys_*` receive-count/sent-timestamp (`asb.py:48-67`, applied `:192`) | absent → always present | **Azure, ALL ASB consumers — incl. one this PR never touches** | `alert_processor_service/.../message_handler.py:105`/`:110` gate `queue_wait` on these; redeliveries now excluded. **Its comment at `:67-68` is now factually wrong.** `sensor_service` receives but never reads them. |
| 49 ✅ **CORRECTED** | `max_delivery_count` (`service_bus.tf:292`) | n/a → **5** | The new queue | The row used to say it *deviates from every sibling, which use 3* — **stale.** `posture_issue_verdicts` (`:100`) also uses **5**, same rationale at `:88`. 1 of 2, not a lone deviant. **No ticket authorisation.** |
| **NEW** | Event Grid has **no dead-letter destination** (`blob_events_to_servicebus/main.tf:35-79`) | `retry_policy` + `storage_blob_dead_letter_destination` **unset** | Every BlobCreated event | **Measured on the pinned provider (azurerm 4.81.0, real apply + `az … show`):** 30 attempts, 1440-min TTL, `deadLetterDestination: null` → Event Grid **silently drops** the event. `$DeadLetterQueue` covers only what *reached* the queue. |
| **NEW** | plan-time precondition (`service_bus.tf:312-320`) | none → queue **refused at plan** without an Event Grid producer | Any caller of `cell-azure-instance` | Added in review, after the first inventory. Turns pre-existing `customer_event_grid_topic_principal_id` (default `""`) into a gate on whether the queue builds. |
| 46 + 47 | `parse_event_time` log text (`event_time.py:29`); `azure-storage-blob` (`pyproject.toml:140`) | 2 messages → 1; transitive → **direct** `>=12.27.1` | **GLOBAL — neither is Azure-gated** | Log alerts on the old strings stop matching (`service.py:158-172` reworded too). Image contents change for **every** `backend_python` service. **No authorisation.** |
| 93-95 | base-overlay values inert while the lane was off (`endpoint-asset-ingestion.yaml` lines 118, 124 and 33-34) | `maxReplicaCount` **20** (chart 5), `fallback.replicas` **5** (chart 1), requests **500m / 512Mi** (chart 0.05 / 256Mi) | Both Azure cells, the moment #78 ships | Never *changed* here — they go **live** when the lane turns on. Worst case KEDA pins 5 replicas at 500m on a cell that never ran it. **No authorisation.** |
| 4e + 4f | Flux `${…}` for the queue params (`fluxcd_config.tf:113-116`); `create_byoc_events_topic` on saas (`main.tf:110`) | published only when the TF flag is on; `false` → **`true`** | Both Azure cells; 3 **already-live** lanes on saas | **Flux resolves an unprovided `${…}` to the empty string and reconciles successfully** → empty queue name → guard refuses → `CrashLoopBackOff`. Order is infra → flux; **whether that apply landed on `ox-az-p-eus2-c02` I could not determine** (`az … show` → `ResourceGroupNotFound`; state → `AccessDenied`). |
| ~~19 + 21~~ | ~~pool releases the message when the handler raises~~ | **WITHDRAWN — this row described the release-and-pace design `main` superseded and the owner ruled out of this PR (round 46). `consumer_pool.py`, `sqs.py` and `client.py` are byte-identical to `origin/main`; the behaviour is `main`'s, not a deviation this PR introduces.** | — | — |
| ~~41 + 42~~ | ~~object outcome label `processed_with_failures`~~ | **WITHDRAWN — reverted out of this PR by the round-45 owner ruling. `object_processor.py` and the metric are byte-identical to `main`; no dashboard filtering `outcome="processed"` is affected.** | — | — |
| ~~37~~ | ~~Claude connectors seeded before the emptiness guard~~ | **WITHDRAWN — reverted out of this PR by the round-45 owner ruling. `writers.py` is byte-identical to `main`; a Claude Code install with zero MCP servers still creates none.** | — | — |
| 32 | ASB pool `max_messages` (`service.py:246` and `asb.py:27` — **pinned twice**) | n/a → **hard-coded `1`**, ignoring `config.max_messages` (default 10) | Azure only | Deliberate (the ASB receiver is not coroutine-safe), but it means the configured value is silently ignored on one cloud and honoured on the other. |
| 33 | ASB client ownership (`service.py:232-253`) | one shared client → **one client per worker** (concurrency 5 ⇒ 5) **plus a 6th** for readiness | Azure only | Six AMQP links per pod instead of one connection. Sized for `concurrency: 5`; raising concurrency raises the link count 1:1. |
| 99 | `releases_kvs.*` (`endpoint-asset-ingestion.yaml:89-91`) | `${…:=}` ⇒ empty on Azure | Azure cells | No such SSM parameter is published there, so the scanner-version KVS fallback is simply **off** on Azure. Recorded so it is not discovered as a mystery later. |

**Of the things I could not determine, three are now measured and one still cannot be** (full detail in
[`at10-13-defaults-inventory.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-13-defaults-inventory.txt)):
- **the azurerm defaults and the Event Grid retry policy — MEASURED**, not guessed, on the pinned provider
  (`~> 4.0`, resolved 4.81.0, no lock file is committed) by a **real `terraform apply` against a
  Standard-SKU namespace in the Azure lab** with a byte-identical argument set, read back with `az … show`
  and destroyed: queue `max_size_in_megabytes` **5120**, `auto_delete_on_idle`
  **`P10675199DT2H48M5.4775807S`** (never), `requires_session`/`requires_duplicate_detection`/
  `partitioning_enabled` **false**, `batched_operations_enabled` **true**; Event Grid
  `retry_policy.max_delivery_attempts` **30**, `event_time_to_live` **1440 min**, schema
  **`EventGridSchema`**, and `deadLetterDestination` **null**. Two corrections fell out of it:
  `enable_partitioning`/`enable_batched_operations` **do not exist in azurerm 4.x**, and the subscription
  resource is `azurerm_eventgrid_system_topic_event_subscription`.
- **whether `sensor_service` reads the new `_sys_*` properties — DEFINITIVE NO.**
  `grep -rc '_sys_' backend_python/src/sensor_service` → **0** in every file: it receives the properties and
  reads only `msg.body`/`msg.id`. The `_sys_*` side effect is correctly scoped to `alert_processor_service`.
- **whether the Terraform apply has landed on the cell — still NOT determinable from here**, and merged is
  not applied: `az servicebus queue show … -g ox-az-p-eus2-c02` → `ResourceGroupNotFound`, `az account list`
  shows the lab tenant only, and the prod state bucket is `AccessDenied` from this box. Stated, not assumed.

*(This list used to carry a fourth entry claiming the two Azure tenants' production flag state was
undeterminable. It was not: one read-only API call answers it, and the answer changes what merging
flux-fleet#2307 does. The entry is withdrawn; the measurement is in the deploy-safety row of the table
above, which exists because of it.)*

**The inventory also surfaced two defects, neither fixed here:** the stale `alert_processor_service`
comment (row 24), and the undeclared metric-semantics change (rows 41+42) shipping with no flag.

---

## How it was proven

**Evidence currency — what was re-driven on the shipped head, and what was not.** An earlier version of
this section claimed the head was `16b7bca77c` and that *"every artifact in this bundle is stamped
16b7bca77c"*. Both halves were false by the time anyone read them: the head is `2b60fdc4df`, five commits
later, and the run's own `at10-04-evidence-provenance.txt` was simultaneously marking every at1–at9
artifact as *"6 … 25 lane-touching commit(s) landed after it"*. A bundle cannot be both current and 25
commits behind, and the document should not have said the first while its own generated file said the
second.

The round-45 revert and the round-46 queue drop changed `writers.py`, `extract.py`, `object_processor.py`,
`pipeline.py`, `metrics.py`, `asb.py` and the three shared queue files — code the captures rest on — so the
answer is not a staleness argument, it is a re-drive. Done on `2b60fdc4df`, against the real lab:

| what | result | artifact |
|---|---|---|
| at6 transport equivalence, **created** | **`changed lines: 0`**, both dumps `sha256 578016f3434b9630…`, 8/8 object pairs byte-identical | [`at6-04a`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04a-diff-created.txt) · [`at6-07`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-07-transport-equivalence.txt) |
| at6 **matched** | **`changed lines: 0`**, both dumps `sha256 e2e331b12293c84a…`, 16/16 pairs byte-identical | [`at6-04b`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04b-diff-matched.txt) |
| at6 **reingest-skip** | **`changed lines: 0`**, both dumps `sha256 e2e331b12293c84a…`, 29/29 pairs byte-identical; every writer step counter equal across lanes, read from each pod's own `/metrics` (`asset_ingestion_step_total{outcome="skipped",step="mcp_upsert",tenant_schema="prdct11935_ta26"} 16.0` and the same value on the other tenant) | [`at6-04c`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04c-diff-reingest-skip.txt) |
| at6 settlement classes | `skipped_unknown_tenant`, `parse_err`, `skipped_flag_off`, `failed → redelivered → processed` all driven live | [`at6-05`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-05-per-class.txt) |

**Why the earlier re-drives of this leg did not come back at zero, and what that turned out to be.** An
independent review measured a **deterministic** non-zero transport diff on all three classes and named the
residual precisely: the same MCP server, same content hash, keyed `…/bundle.cjs::<serial>::unknown` on one
tenant and `node::<serial>::unknown` on the other, with an unpinned `mcp-remote` resolving to two different
concrete versions. That reproduced, so it needed a cause, not a re-run. It has one, and it is **not the
transport**:

- the writer resolves versions **inline before the first write** (`writers.py:916-926` →
  `version_resolution.py:378` → `package_registry/npm.py:78`), which is a **live npm `dist-tags.latest` HTTP
  GET at ingest time** — the function's own docstring calls itself *"THE RULE-9 EXCEPTION, CONSCIOUSLY
  BOUNDED"*;
- the identity name and bridge version then come from the per-tenant `mcp_package_cache`, falling back to
  the raw `command` only on a cold miss (`mcp_writer.py:405-436`, `:466-478`);
- and in front of that table sits a **module-global `LRUCache`** keyed `(tenant_schema, cache_key_hash)`
  (`common/repository/mcp_package_cache.py:17-19`) which caches negatives too and **is not invalidated by
  `TRUNCATE mcp_package_cache`** — so per-pod state survived every tenant reset the earlier harnesses did;
- the resolved name and version are locals that never enter the content hash (`extract.py:229-235` sets
  `name=None`), which is exactly why the divergence showed **identical `content_hash` with a different
  `unique_identifier`** — a payload difference would have moved both;
- and **all ten files on that path carry 0 changed lines** from the merge-base, so none of it is this PR's.

Holding resolution constant — both writers created cold at the same instant, both caches truncated, both
lanes driven inside one settle-gated window, transports untouched — makes the residual disappear: the exact
rows that used to diverge now agree on both tenants (`node::ec255301…::unknown`, hash `6ba6cf0f…`,
`mcp-remote::0.1.49`), with the two `mcp_package_cache` tables row-for-row identical. That is the
discriminating measurement rather than an argument, and it is what the zeros above rest on.
| at4 / at5 post-fix halves | both refusal directions + both gen-2 refusals re-captured verbatim; `post-fix/meta.json` regenerated on `2b60fdc4df` | [`at4-01`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at4-01-postfix-refusal-azure-s3.txt) · [`at5-01`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at5-01-scanner-postfix.txt) |
| at8 renders | re-rendered on flux-fleet#2307's **current head `a4493c1e5ac0`** — that PR is **OPEN, not merged** (the earlier wording said "the MERGED flux-fleet head", which was never true of #2307); all 7 repo gates exit 0 | [`at8-05`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-05-parity-check.txt) |
| at9 terraform + live Azure | `fmt`/`validate` rc=0, `terraform test` 6 passed, live semantics re-read | [`at9-01`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-01-tf-validate.txt) |
| at7 posture re-affirm | reproduces on head — `updated_at` advanced 18:41:57 → 19:32:35 | [`at7-50`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-50-amendment-r30-reaffirm.txt) |

**And the honest remainder.** Not every artifact was re-driven. The per-artifact ledger —
[`at10-23-evidence-currency.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-23-evidence-currency.txt)
— lists all of them in three buckets: re-driven this round, not re-driven with the lane delta that
applies, and not re-driven with a measured zero delta. It is generated from each file's own header, so it
cannot flatter the bundle. Read that file rather than this paragraph if you want the per-artifact truth.

**One measurement correction worth calling out, because it changes what an earlier number meant.** The
previous round's at6 run reported **43 changed lines** on the matched and reingest-skip classes and could
not clear them. That was the instrument, not the code: gen-1 was unpaused between legs (11 gen-1-created
rows leaked into the AWS tenant), and the two tenants were dumped as two sequential shell calls, so a scan
landing between them made the halves disagree by construction. With gen-1 quiesced for the whole sequence
and both tenants read inside one repeatable-read snapshot, all three classes come back 0. The first
attempt this round still showed a 2-line hash difference on one MCP server at 19:08; re-reading the same
rows atomically once the lane went quiet showed them identical — the row simply had not converged in the
AWS tenant when the Azure one was read.

**The AI-Assets list surface was frozen, and it was fixed rather than worked around.** at7's
`ui_proof_steps` asks for each class located in the list. That list is served from the `asset_inventory`
read model, which had been stuck at **157 rows / 2026-08-18 19:42Z against 316 live assets** because
nothing was polling the `python-worker` Temporal task queue — the worker pod was `1/1 Running` with 0
restarts, but its log ends with its own clean shutdown after a Postgres connection refusal, and a
freshness-schedule execution had been wedged since 2026-08-19T09:05Z. Restarting the worker and
terminating the wedged execution unblocked it, and it has since caught up completely: measured at push
time, `asset_inventory` holds **382 rows against 382 live assets**, and **all five** of this run's
head-window subjects (131106, 131278, 131332, 131552, 131966) are present in it — checked with a single
`SELECT count(*) … WHERE asset_id IN (…)` rather than asserted. (The round-25 gate found the earlier
"316 rows … subjects are now in it" sentence false when it measured: 316 against 355 live assets with 0 of
the 5 subjects present. The projection had not finished catching up when that sentence was written.) The per-class rows are located the way a user
locates them — by typing into the table's own search box:

![this run's skill and subagent located in the AI-Assets list by search](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-34-list-skill.png)

Receipts, cited separately because they measure different moments: the poller repair itself — the wedged freshness schedule, the worker restart, and the projection coming back — is [`evidence/at7-37-list-surface-revived.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-37-list-surface-revived.txt), which records the projection as it stood when that repair ran — 316 rows against 316 live assets — and
does not contain today's numbers. The **382/382 with all five subjects present** quoted above is measured at push time and carried in [`evidence/at7-31-inventory-read-model.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-31-inventory-read-model.txt) §ROUND-28/29, which prints the `SELECT count(*) … WHERE asset_id IN (…)` it comes from. The round-26 gate was right that the earlier sentence cited at7-37 for a number at7-37 does not hold.


Everything below ran on the full Tilt stack with a **real Azure lab replica** of the parity-gap-B design
(subscription *Agents Development*): storage account + container, Event Grid system topic with the
`subject → Label` delivery property, Service Bus topic with SQL-filtered subscriptions, and the
`endpoint-asset-ingestion` queue with its native dead-letter sub-queue. There is no local Azure emulator, and
nothing here is mocked. Objects reach the lab through the product's own front door: `onyx-scanner` → Kong →
vector → Blob → Event Grid → Service Bus.

| Acceptance test | Real surface | Evidence |
|---|---|---|
| **at1** Azure lane exists | Kong → Blob → Event Grid → Service Bus → azure-mode writer | [`at1-01-lab-resources.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-01-lab-resources.txt), [`at1-03-eventgrid-message.json`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-03-eventgrid-message.json), [`at1-04-consumer-logs.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-04-consumer-logs.txt), [`at1-05-db-readback.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-05-db-readback.txt), [`at1-06-flagoff-guard.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-06-flagoff-guard.txt), [`at1-07-cutover-guard.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-07-cutover-guard.txt), [`at1-08-config-provenance.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-08-config-provenance.txt), [`at1-09-flag-verification.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-09-flag-verification.txt), [`at1-10-competing-consumer.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-10-competing-consumer.txt) (an orphaned second consumer on the same queue, found and stopped this round), [`at1-11-merged-head-creates.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-11-merged-head-creates.txt) (the merged head CREATING rows through the shared parser, machine sha256 matched) |
| **at2** replay / dedup (C11) | the same real broker MESSAGE redelivered on the real queue, on the head image, with every concurrent writer quiesced | [`at2-05-isolated-replay.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at2-05-isolated-replay.txt) (the isolated re-run: abandon/`receive_count` lines and the content diff in the SAME run, plus the positive control), [`at2-01-before.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at2-01-before.txt), [`at2-02-after.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at2-02-after.txt), [`at2-03-redelivery.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at2-03-redelivery.txt), [`at2-04-dedup-keys.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at2-04-dedup-keys.txt) |
| **at3** poison path | the real queue + its native `$DeadLetterQueue` | [`at3-01-poison-send.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at3-01-poison-send.txt), [`at3-02-dlq-receive.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at3-02-dlq-receive.txt), [`at3-03-consumer-logs.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at3-03-consumer-logs.txt), [`at3-04-sibling-db.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at3-04-sibling-db.txt) |
| **at4** boot assertion (bug) | the service's own boot + readiness, both bad shapes and the good one | `pre-fix/at4-01..03`, [`at4-01-postfix-refusal-azure-s3.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at4-01-postfix-refusal-azure-s3.txt), [`at4-02-postfix-refusal-aws-asb.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at4-02-postfix-refusal-aws-asb.txt), [`at4-03-postfix-correct-boot.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at4-03-postfix-correct-boot.txt) |
| **at5** gen-2 dead path (bug) | both consumers in azure mode against the real lab queues | `pre-fix/at5-01..03`, [`at5-01-scanner-postfix.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at5-01-scanner-postfix.txt), [`at5-02-mcpgw-postfix.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at5-02-mcpgw-postfix.txt), [`at5-03-shapes.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at5-03-shapes.txt), `at5-04/05-replay-*.txt` |
| **at6** settlement classes + **transport** equivalence — C13 was **rescoped by the round-45 owner ruling and gen-1 parity is NOT claimed** (this row used to describe the withdrawn gen-1-vs-new-lane leg) | the ONE writer image on the **AWS transport** vs the same image on the **Azure transport**, same object bytes, three classes, gen-1 quiesced for the whole sequence | [`at6-01-inventory.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-01-inventory.txt), [`at6-02-old-lane-rows.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-02-old-lane-rows.txt), [`at6-03-new-lane-rows.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-03-new-lane-rows.txt), `at6-04a/b/c-diff-*.txt`, [`at6-05-per-class.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-05-per-class.txt), [`at6-06-ledger.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-06-ledger.txt) (the C3 ledger, with the round-22 conformance block), [`at6-07-transport-equivalence.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-07-transport-equivalence.txt) (re-driven on the head sha — the artifact states its own measured changed-line count and both dump sha256s; the "8/8 per-loss greps" this row used to advertise are not in that file and the claim is withdrawn), [`at6-08-residual-losses.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-08-residual-losses.txt), [`at6-09-fresh-tenant-parity.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-09-fresh-tenant-parity.txt) (fresh pair on the head sha, enumerated across assets / asset_connections incl. `metadata.sources` / tools / scanner_installations for all three both-lane classes), [`at6-10-followup-ticket.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-10-followup-ticket.txt) (PRDCT-12061 fetched, each required element checked), [`at6-11-veto-permalink.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-11-veto-permalink.txt) (the amendment's veto post resolved against Slack), [`at6-12-image-provenance.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-12-image-provenance.txt) (the writer image built from head and proven byte-exact — 4741/4741 files) |
| **at7** C2 real install → rows → UI → fidelity → lifecycle | a real npm install of Codex and OpenClaw, `codex mcp add`, a bundle packed by Anthropic's own `mcpb` CLI, real skill/subagent files — then the authenticated SPA | [`at7-00-isolation.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-00-isolation.txt), [`at7-01-real-install.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-01-real-install.txt), [`at7-02-scan-payload-ref.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-02-scan-payload-ref.txt), `at7-03..07-db-rows-*.txt`, [`at7-08-fidelity.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-08-fidelity.txt), [`at7-09-db-rows-tools-posture.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-09-db-rows-tools-posture.txt) (the single capture, plus the plan's two pinned names [`at7-09-db-rows-tools.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-09-db-rows-tools.txt) and [`at7-09-db-rows-posture.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-09-db-rows-posture.txt), materialised from its own sections), the at7 UI captures (`at7-10`, `at7-11`, `at7-12`, `at7-13`, `at7-14`, `at7-15`, `at7-19`, `at7-19b`, `at7-20`, `at7-21`, `at7-22`; the lifecycle frames are captured at the plan's pinned names and annotated in context, and because the skill and subagent surfaces genuinely do not change when the file is removed, [`at7-28-lifecycle-ui-redrive.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-28-lifecycle-ui-redrive.txt) MEASURES the non-change on this round's own frames — product region only, annotation chrome excluded, and it states plainly which pairs it makes no pixel claim for — from six DISTINCT captures, the before halves being the pre-removal frames `at7-12`/`at7-13`/`at7-10b` cited by their own names rather than copied to new ones), [`at7-18-lifecycle-db.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-18-lifecycle-db.txt) (per-class, in the amendment_r26 vocabulary), [`at7-41-lifecycle-head.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-41-lifecycle-head.txt) (the head-build removal + second-scan measurement, with the per-class re-coverage vehicle and the siblings' literal presence in the second scan's payload), [`at7-42-lifecycle-followup-ticket.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-42-lifecycle-followup-ticket.txt) (PRDCT-12069 fetched and matched against the live task), [`at7-43-veto-permalink-r26.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-43-veto-permalink-r26.txt) (the round-26 amendment's veto post resolved against Slack), [`at7-23-attestations.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-23-attestations.txt) (one row per class, so the demands settle individually), [`at7-24-removal.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-24-removal.txt), [`at7-29-posture-bridge.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-29-posture-bridge.txt), [`at7-30-agent-lifecycle-control.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-30-agent-lifecycle-control.txt) (the removed/still-installed control pair), [`at7-31-inventory-read-model.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-31-inventory-read-model.txt) (why the inventory LIST carries no row from this run — measured identical on BOTH lanes, so not a parity loss), [`at7-37-list-surface-revived.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-37-list-surface-revived.txt) + `at7-32..36-list-*.png` (the AI-Assets LIST captures, obtainable again after the read-model projection was revived), `recordings/at7.{webm,trace.zip}`, `recordings/at7-lifecycle.{webm,trace.zip}`, `recordings/at7-lists-r23.{webm,trace.zip}` |
| **at8** deployment config | kustomize + helm render of BOTH Azure instances, and a LIVE KEDA arm in kind | [`at8-01-render-saas.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-01-render-saas.txt), [`at8-02-render-centerpoint.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-02-render-centerpoint.txt), [`at8-03-helm-equivalence.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-03-helm-equivalence.txt), [`at8-04-comment-fix.diff`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-04-comment-fix.diff), [`at8-05-parity-check.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-05-parity-check.txt), [`at8-06-keda-live.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-06-keda-live.txt), [`at8-07-instance-identity.diff`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-07-instance-identity.diff), [`at8-08-render-drift.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-08-render-drift.txt) |
| **at9** Azure infra | terraform fmt/validate/tflint + a credentialed CI plan + the semantics demonstrated live | [`at9-01-tf-validate.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-01-tf-validate.txt), [`at9-02-sqlrule-positive.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-02-sqlrule-positive.txt), [`at9-03-sqlrule-negative.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-03-sqlrule-negative.txt), [`at9-04-delivery-property.json`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-04-delivery-property.json), [`at9-05-roles.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-05-roles.txt), [`at9-06-flux-config.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-06-flux-config.txt), [`at9-07-key-match.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-07-key-match.txt) |
| **at11** round-45/46 owner-ruling audit + no-AWS-behaviour-change | the PR diff audited hunk-by-hunk, and the AWS lane driven live on two writer images through the real Kong front door | [`at11-01-diff-audit.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-01-diff-audit.txt) · [`at11-02`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-02-aws-lane-base.txt)/[`at11-03`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-03-aws-lane-head.txt)/[`at11-04`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-04-aws-lane-diff.txt) (the base-vs-head tenant-DB comparison **and the 8-line delta it found**, run to ground) · [`at11-05`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-05-gen1-untouched.txt) gen-1 untouched + running · [`at11-06`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-06-single-pr.txt) · [`at11-07`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-07-sibling-consumers-aws.txt) · [`at11-08`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-08-flux-render-aws-cells.txt) · [`at11-09`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-09-r46-queue-supersession.txt) |
| **at10** PR readiness | this PR: body, embedded images, CI | [`at10-01-pr-body.md`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-01-pr-body.md), [`at10-02-image-check.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-02-image-check.txt), [`at10-03-ci.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-03-ci.txt), [`at10-09-ci-failures.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-09-ci-failures.txt) (the two infrastructural CI failures on the merge commit, diagnosed from their own logs and re-run) |

*Note on the at1 row — round-37 correction of a round-34 correction (gate F1, verify round 32).* Round 34 moved this note out of a fourth pipe-delimited cell, which was the right diagnosis, and then asserted that it had been *"moved out of the table and closed properly"*. It had not: the note was left sitting **between the at1 row and the at2 row**, and the blank line before it TERMINATED the table, so GFM rendered a two-row table (header + at1) and emitted at2..at10 as literal pipe-delimited text absorbed into this paragraph as lazy continuation. Measured, not eyeballed — GitHub's own renderer, `POST /api/markdown` mode=gfm over the section: **2 `<tr>` before, 11 `<tr>` after** (header + all ten ATs), with 0 rows left as literal text. The note now sits BELOW the table, which is the only position that cannot re-break it, and the claim above is stated from that measurement rather than from intent.

**[`at1-08-config-provenance.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-08-config-provenance.txt) — REBUILT in round 32:** the live vector `azure_blob` sink is no longer hand-authored for the lab — it is mechanically derived from the authored `flux-fleet .../vector-sas-generator.yaml` render with exactly three per-cell substitutions (connection string, container, `inputs`), its normalized diff against the live sink is EMPTY, and it is re-proven by one marked scan driven through it end to end (`at1-08-derive-sink.py`, `at1-08-rediff.py`, `at1-08-rendered-sink.yaml`, `at1-08-live-sink-readback.yaml`, [`at1-08-rediff-output.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-08-rediff-output.txt)).

Highlights, all from the captured artifacts:

- **The transport is the only thing this change moves — proven, not argued.** The same writer image was run
  twice over the same bytes with gen-1 switched off entirely: tenant TA on AWS transport (SQS notification +
  S3 GetObject) and tenant TB on Azure transport (Event Grid over Service Bus + Blob download). The two
  tenants' content/state/lifecycle dumps are **byte-identical** — the two dump files share one sha256
  (`557c156f906cb353`, 862 lines each), which is a stronger statement than a zero diff — across
  **264 assets, 276 asset_connections**, every MCP identity, every skill and subagent content hash, and
  every issue row ([`evidence/at6-07-transport-equivalence.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-07-transport-equivalence.txt), whose input dump paths and per-section
  `(N rows)` markers are now printed in the artifact so each number is re-derivable).
  **Round-34 correction (gate GAP-2):** this sentence used to read "0 changed lines across 217 assets, 230
  asset_connections, 50 MCP-tool rows". None of those three traced to the artifact it cites — the artifact's
  own summary line was itself wrong (it had copied "644" from an unrelated in-flight message count), and the
  real numbers are the dump's own row markers, which match at6-07's live settle line `TA|TB assets,edges =
  264|264|276|276`. The MCP-tool count is dropped rather than corrected because this leg's dumps contain
  **zero** tool rows: the leg never evidenced tool-row transport equivalence, and that class is carried by
  `at6-04`'s per-class diffs and `at7-09` instead. That is why the residual writer-vs-gen-1 differences in
  the ledger belong to the one-writer cutover and not to this PR: they reproduce identically on AWS.
- **What was driven for real, in the scope the owner left standing.** The comparison this PR is held to is
  **transport** equivalence, not gen-1 parity: one writer image, the same object bytes, delivered once over
  SQS/S3 and once over Service Bus/Blob. What makes every row on the Azure side the new lane's is stronger
  than a workflow count — in the `at6-07` transport leg gen-1's two workers were at **zero pods** for the
  whole leg and the Azure-transport tenant still received its rows, and that tenant's own
  `scanner_installations` carry the Azure object keys the writer read. The gen-1 side-by-side and its five
  divergence rows are **withdrawn as evidence for this PR** (see *"The gen-1-vs-new-lane comparison —
  WITHDRAWN"* below) and survive only as an owner-accepted gap in [`evidence/at6-06-ledger.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-06-ledger.txt),
  which names each item, its root cause at `file:line`, whether the transport has anything to do with it (it
  does not), and its disposition.
- **`failed → redeliver` is demonstrated end to end, and so is its boundary.** **Re-driven from scratch on
  the shipped head `2b60fdc4df`.** The running pod's lane tree (`endpoint_asset_ingestion` plus
  `common_core/services/queue`) was sha256'd file by file against that head and is byte-identical, so every
  cite below points into the code that produced the logs. The induction is real and lives entirely OUTSIDE
  the service: a `SHARE` lock is taken on `onyx_security.scanner_installations` from `psql`, which blocks the
  lane's own INSERT while leaving every SELECT free, and the waiting statement is then cancelled with
  `pg_cancel_backend` — SQLSTATE `57014`, which the lane itself classifies as retryable
  (`common/database/pg_retry.py:40`), so `with_db_retry` (`ingestion/db_retry.py:81`) spends its budget and
  the failure propagates. No code, no service config, no queue property and no KEDA setting was changed, and
  nothing anywhere was mocked. The pool then logs `Handler error for message, abandoning it and continuing
  with remaining messages` (`consumer_pool.py:226`) → `Abandoned message for redelivery` (`asb.py:265`), with
  `outcome="failed"` metered in the try/except around the ingest call (`object_processor.py:144`).

  Service Bus re-presents **that same `message_id`** — `c2bd8d2b-424a-40af-8550-94ab345f2cec`, enqueued
  **once**, at `2026-08-23 21:14:40.260000+00:00`. The broker's own peeks (a read of broker state, not of the
  app's logs) show `delivery_count` at `0`, then `1`, then `3`, with the same enqueued time and the same blob
  url throughout; the consumer's own lines read `receive_count=2`, then `receive_count=3`, then
  `receive_count=4`; and the pod's counter scrape reads `asset_ingestion_redeliveries_total 3.0`, with
  exactly three such lines in that pod's entire lifetime, all carrying that one id. When the lock is released
  the fourth delivery succeeds and the message is settled with `Completed message` (`asb.py:244`) — it never
  reached the dead-letter queue, and the queue's `max_delivery_count=5` was never approached
  ([`evidence/at2-03-redelivery.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at2-03-redelivery.txt)).

  **What the redeliveries do to the database is nothing**, which is the C11 assertion itself. An 11-query,
  `3755`-line dump taken *during delivery 2* and again *during delivery 4* differs on exactly one line — the
  dump's own `### DUMPED_AT` stamp. No new row, no duplicate row, no resurrected row. The same capture
  carries the positive control that proves the dump would have seen a change if there were one: the ingest
  itself added exactly three rows (the marker skill asset, its `agent_skills` row and its `AgentToSkill`
  edge), and the stored `skill_md_hash` equals the on-disk `sha256` ([`evidence/at2-02-after.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at2-02-after.txt)). The reprocess
  is not silent at the code level either — on each real redelivery the writer logs its duplicate-start
  rejections: `MCP downstream already started for this object — redelivery no-op` (`mcp_downstreams.py:54`)
  and `custom-data embedding already started for this object — redelivery no-op`
  (`custom_data_downstreams.py:50`).

  **Two boundaries are disclosed rather than smoothed over.** (i) The posture-bridge `REJECT_DUPLICATE`
  branch (`writers.py:692`, logged at `writers.py:703`) cannot fire inside this same-message chain: the
  inducement blocks the object *before* the posture trigger, which then succeeds on the settling delivery.
  That one line is observable only in the clearly-labelled same-**object**-twice extra in
  [`evidence/at2-04-dedup-keys.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at2-04-dedup-keys.txt) — labelled there as an extra, never as the vehicle. (ii) An earlier revision of
  this bullet quoted a per-message release-pacing line, with a five-second floor and interval
  statistics around it. **That
  pacing no longer ships**: `fb12b015be` dropped the queue-layer abandon-and-pacing work as superseded by
  main, and `grep -rn "Backing off before" backend_python/src/` returns nothing at this head. The claim is
  therefore withdrawn rather than restated, and the artifact measures only what at2 asks for — the same
  broker message, delivered more than once, on the real at1-chain queue.

- **The C11 "nothing resurrects" half is now proven in ISOLATION, because a previous window could not
  attribute what it saw.** A round-24 replay window showed a soft-deleted `asset_connections` row flip
  `is_deleted true → false` and two `mcp_ingestion_state.content_hash` values rewritten — but the shipping
  consumer's own ingest had started an async Temporal posture/CVE plane writing the same tenant in the same
  window, so the change could not be pinned on the replay. Rather than argue it away, the whole experiment
  was re-run on the head image with **every** concurrent writer quiesced — gen-1's collector schedule paused,
  `scanner-event-consumer`, `temporal-scanner-worker`, `temporal-general-worker`, the posture plane
  (`temporal-python-worker`), the shipping consumer and `inventory-assets-enricher` all at zero — on a
  dedicated Service Bus queue, with the abandon/`receive_count` lines and the before/after content diff
  captured **in the same run** ([`evidence/at2-05-isolated-replay.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at2-05-isolated-replay.txt)).

  Across three legs spanning `receive_count` **1→30**, **20→46** and **68→85** of the same real broker
  messages, every content diff is **empty** — 1549-line dumps carrying `is_deleted`, `status`, hashes and
  versions for assets, `asset_connections`, `mcp_servers`, `mcp_ingestion_state`, skills, subagents, tools
  and sessions. One diff runs from *before the message existed* through 30 deliveries of it and is still
  empty. Seventeen soft-deleted `asset_connections` rows sat on the table throughout — real resurrection
  candidates — and not one flipped, while 240–368 `bulk_upsert_asset_connections` calls per leg prove the
  cascade genuinely re-ran rather than short-circuiting.

  And the symptom was reproduced where it actually lives, which is what attributes it: with the concurrent
  writers restored and **zero** redeliveries — every message delivered exactly once — one ordinary scan
  flipped **seven** `AgentToMcp` edges `true → false` and re-typed two `mcp_servers` rows. That is the
  documented self-heal which restores an edge when its server is observed again
  (`restore_soft_deleted_connection`, `asset_connection.py:702-750`, called from `touch_mcp_asset_last_seen`,
  `activities.py:1401-1408`, whose docstring says "without this a reaped edge stayed dead forever"). It is
  driven by **what each observation reports**, not by the transport redelivering a message. So: no defect in
  the redelivery path, and the gate's finding is explained rather than dismissed. [`evidence/at6-05-per-class.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-05-per-class.txt) §J also records the two inductions that do *not* reach this
  class and why — blocking the **tenant lookup** (`public.tenants`) releases and redelivers the message but
  can never reach the counter, which is metered only after the tenant resolves; and locking a table the
  cascade only **writes** (`agent_skills`) is skipped past entirely by the agent-level content-hash skip —
  because that boundary is part of the settlement contract too.

- **A pod on Azure finally reads the per-tenant flag.** The azure-mode writer consumed every real Event Grid
  delivery the frozen base had left parked, parsed each one, resolved the tenant from the blob key, evaluated
  `endpoint-asset-ingestion` for that tenant and settled `outcome=skipped_flag_off` with tenant + object-key
  ids — ack, zero rows, nothing dead-lettered. On the base, no pod existed to read that flag at all.
- **Poison parks instead of vanishing.** An Event-Grid-shaped body whose subject lacks the `/blobs/` segment
  is dead-lettered into the real `$DeadLetterQueue`. **Re-driven on the shipped head `2b60fdc4df`**, and the
  body is not hand-invented: it is a **real Event Grid body captured in this same window**, with only
  `subject` and `data.url` truncated to the container and a unique marker (`r50-poison-213225`) inserted in
  two places. Send and read-back are one window and join on one `message_id`
  (`e9803f4a-42ee-4a49-a2ee-9b2d2e409e43`) — the id the consumer's own line names as it parks the message —
  plus that marker, matched on the way back out. The queue's own counters move from
  `active=0 dead_letter=120` to `active=0 dead_letter=121` across the send, and the read-back is a real
  peek-lock receive that walked all `121` dead-lettered messages and **settled nothing** (no complete, no
  abandon, no dead-letter), so the sub-queue is left exactly as it was found for any later round. What comes
  back is the broker's own `dead_letter_reason` — `no ingestible object in the message`, the *application's*
  reason rather than `MaxDeliveryCountExceeded` — with `"delivery_count": 0`: parked on first receipt, never
  acked, never retried, never looped. Across the pod's entire log that id appears exactly twice
  (`message_handler.py:108`, `asb.py:251`), with zero `redelivered queue message`, zero `Completed message`
  and zero `Abandoned message for redelivery` lines, and the parking pod's counters read
  `asset_ingestion_poison_messages_total` and `asset_ingestion_dead_letters_total` at `1`. Two
  Kong-originated sibling scans driven in the same window — the second entirely *after* the park — landed
  their rows normally, so the park did not wedge the consumer.
  [`evidence/at3-01-poison-send.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at3-01-poison-send.txt), [`evidence/at3-02-dlq-receive.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at3-02-dlq-receive.txt), [`evidence/at3-03-consumer-logs.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at3-03-consumer-logs.txt),
  [`evidence/at3-04-sibling-db.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at3-04-sibling-db.txt).
- **Both Event Grid body shapes parse.** The single-event shape rode the real chain; the array shape (which
  the Event-Grid→Service-Bus transport does not emit — it delivers one event per message) was placed on the
  real queue built from two real captured event bodies, and produced two records from one message.
- **The SQL rule does not collide with its siblings, in both directions.** Real blobs written under
  `source=extension/` and `source=sensor-events/` raised real Event Grid events and were routed to their own
  lanes' queues only; the scanner consumer never saw them, and the scanner label never landed on theirs.
- **The consumer's identity, stated as it actually is.** What the shipped Terraform grants the
  endpoint-asset-ingestion workload identity is three narrow data roles and nothing else: Service Bus
  **Data Receiver** on its own ingestion queue, Service Bus **Data Sender** on the alert-processing queue
  (added this round — without it the sessions fan-out cannot publish at all), and **Storage Blob Data
  Reader** on the ingestion account. No namespace-wide grant, no Contributor, no Owner.
  **And the lab now runs it as that identity — this round stopped asserting the deviation and removed it.**
  A **secretless user-assigned managed identity** (`prdct11935-at9lp-eai`, the same identity *type* the
  Terraform authors, credentials over IMDS, no client secret anywhere) was created holding **exactly two**
  role assignments and nothing else:

  ```
  COUNT= 2
    Azure Service Bus Data Receiver | .../namespaces/prdct11935bus/queues/at9lp-eai
    Storage Blob Data Reader        | .../storageAccounts/prdct11935st/blobServices/default/containers/ingestion
  ```

  A consumer clone was run as it, and a **real Kong-originated scan** went Blob → Event Grid → Service Bus →
  that identity's queue → the tenant DB: `outcome=processed`, `prdct11935_ta18.assets` rose from 153 rows to 438 across the drive, and the
  marker skills' stored `skill_md_hash` equal to their on-disk `sha256`. So the lane works under least
  privilege, measured rather than argued. The negatives were driven under that same identity and are quoted
  verbatim: SEND on its own queue → *"'Send' claim(s) are required … amqp:unauthorized-access"*; LISTEN on
  the shared ingestion queue → *"'Listen' claim(s) are required"*; a foreign container and a foreign storage
  account → `ErrorCode:AuthorizationPermissionMismatch`.

  **The role claim that stood here was backwards, and the correction is the interesting part.**
  On `alert-processing-prdct11935` the authored identity gets **SEND and not LISTEN**: the queue-scoped
  `Azure Service Bus Data Sender` supplies the Send claim, and with no Receiver at that scope a receive is
  refused with *"'Listen' claim(s) are required"*. An earlier reading of *LISTEN allowed* came from the
  **lab's** old runtime identity (`coder-agent-app`), which separately holds a **namespace-wide** Data
  Receiver on `prdct11935bus` — a superset the module never grants this lane. Three postures were measured
  to settle it: `coder-agent-app` → SEND allowed / LISTEN allowed; two-roles-only → both denied; the two
  roles **plus** the authored third grant → SEND allowed / LISTEN denied. (One correction to the sentence
  above while we are here: the authored block grants **three** roles, not two — its own comment says so, and
  the third is that queue-scoped Sender.)

  **The federated half is a bounded limitation, stated as one.** `az aks list` → `[]` and
  `Microsoft.ContainerService` is `NotRegistered`, so there is no OIDC issuer in the lab. Federated-credential
  *support* was confirmed (Azure accepted the resource on the UAMI) and the token exchange was attempted with
  a **real** projected service-account token, which failed at Entra with **`AADSTS501661: Request to External
  OIDC endpoint failed`** — Entra cannot fetch discovery from kind's in-cluster issuer. Fixing that needs a
  kube-apiserver `--service-account-issuer` change that would invalidate every service-account token on a box
  running five other legs, so it was not done. Not proven, not softened.
  [`evidence/at9-05-roles.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-05-roles.txt) ·
  [`evidence/at9-09-least-privilege-runtime.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-09-least-privilege-runtime.txt) ·
  [`evidence/at9-08-credential-footprint.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-08-credential-footprint.txt)
- **The KEDA trigger actually scales — driven live on this head and this flux render, not asserted.** Until
  this round the only capture was a round-21 one: its own inner block read *"It is HISTORICAL: it was NOT
  re-driven this round"* (`a2486bb33f` / `:prdct11935-r26` / flux `cab40f0e42`) while the file's header and
  this paragraph both said it had been re-captured. One file, two voices — now one, and the measurement is
  new ([`at8-06-keda-live.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-06-keda-live.txt)):

  | time (UTC) | KEDA's own metric (active msgs) | `deploy/eai-azure` replicas |
  |---|---|---|
  | 02:54:22 | 0 | 1 (= `minReplicaCount`) |
  | 02:55:03 | **303** | 1 |
  | **02:55:08** | 303 | **1 → 4** — HPA `SuccessfulRescale`, *reason: external metric `s0-azure-servicebus-endpoint-asset-ingestion-prdct11935` … above target* |
  | 02:55:23 / :38 / :53 | 285 / 271 / 265 | 4 → 8 → 16 → **20** |
  | 02:57:23 | 0 (drained) | 20 |
  | 03:01:39 / :54 / 03:02:09 | 0 | 20 → 13 → 6 → **1**, *reason: All metrics below target* |
  | 03:02:17 | 0 | **1**, held to 03:09:21 |

  **The backlog rode the real at1 chain**, not a hand-placed message: 300 POSTs of a real recorded scanner
  body to the real Kong front door (`300 x 200` with `0 non-200`, fired 02:54:35.930Z–02:54:41.916Z) → 300 blobs in the lab container → Event Grid
  → the `sys.Label LIKE '%source=mcp-scanner/%'` rule → the queue; the object keys are named in the artifact,
  and the pods KEDA started settled them `outcome=processed`. **Auth is the SAS `TriggerAuthentication`** —
  `secretTargetRef` → `Endpoint=sb://prdct11935bus…;SharedAccessKey=<redacted>`, no `podIdentity` — with
  `numberOfFailures 0, status Happy`, `Active=True`, and **`Fallback=False`**, so no number here is a
  fallback artefact. `kubectl` was **read-only** throughout the arm (`get`, `logs`, `get --raw`): no apply,
  patch, annotate, scale, exec or port-forward in the arm path.

  **How the burst was sized, because that is where this measurement could have fooled itself:** live vector
  batches per rendered blob prefix, so N posts on one principal collapse to **one** message — depth is a
  function of distinct principals, not of request count. From measured quantities (HPA sync 15 s, KEDA
  `pollingInterval` 30 s, one replica's drain rate **0.9 msg/s** measured in-window, ≥12 active needed at 1
  replica, up to 10 hidden as locked) the floor is ~49; 300 real principals were used (~6×), holding above
  threshold for ~2m20s ≈ 9 HPA syncs. A 3-principal pilot confirmed the partition model first.

  Two traps are honoured rather than repeated: the apply-time scale-target line KEDA emits when it first enforces `minReplicaCount` on a fresh object is
  **not quoted** anywhere — it is KEDA enforcing `minReplicaCount` on a fresh object, and this
  ScaledObject was created five days before the window and its `metadata.generation is still 1` — and scale-from-**zero** is not
  claimed, because `minReplicaCount` is 1 on both rendered instances by construction.

**Evidence provenance — stated per artifact, not blanket.** An earlier version of this body claimed every
artifact had been re-captured on the current head. That was not true, and it has been corrected. What is true:

- **13 commits sit above `0cfbd4240c` now, 4 of them merges ([`evidence/at10-08-commit-shape.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-08-commit-shape.txt)).** (This bullet said "two" and stayed
  frozen while the branch moved — the round-19 gate counted ten. It is measured here:
  `git rev-list --count 0cfbd4240c..HEAD` → **13**, `--merges` → **4**.) The one that changed the
  receive path the at1/at2/at3 captures exercise is `dfe23b9e83`, a *functional* change to `asb.py`, not a merge.
  - `c0a5e99722` is a merge of `origin/main` that **touches no backend file at all**:
    `git diff --name-only c0a5e99722~1..c0a5e99722 | grep -c '^backend'` → **0** (one frontend commit, a
    posture-drawer name truncation). It cannot have moved any capture.
  - `dfe23b9e83` rewrites `ASBQueueClient`'s lock-renewal timing. Rather than argue that it moves nothing,
    **the whole transport leg was re-driven on an image built from it** — and it has since been re-driven
    again, twice: `at1-02/04/05` on the round-48 head image, and `at2-01/02/03/04` plus `at3-01/02/03/04` in
    round 49 on the current shipped head `2b60fdc4df` (image `:r46b-head`, whose lane tree was sha256'd
    file-by-file against the head before either window opened). Their provenance is quoted from
    [`evidence/at10-04-evidence-provenance.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-04-evidence-provenance.txt) as it stands at push time rather than from memory: every one of
    those rows now reads *"CURRENT — 0 lane-touching commits landed after it"*. The older `f4b3e9dfb2` /
    image `prdct11935-r24` stamps those rows used to carry are gone with the captures they described.
    The replay claim itself no longer rests on those rows at all: it was re-driven this round
    on the head image, in isolation, as [`evidence/at2-05-isolated-replay.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at2-05-isolated-replay.txt). (`at2-04` was the last holdout: it asserts content-derived identity rules a transport change
    cannot move, so an earlier round left it deliberately un-redriven — but its header then said both
    "NOT RE-DRIVEN" and "re-captured on the CURRENT head", and cited a pod that no longer existed. Re-running
    it was cheaper than arbitrating between two headers, and its duplicate counts are now read live on this
    image: **0** duplicate identities across all four key classes, in *both* tenants.) The pod was byte-verified against the tree first, not assumed:
    **4741 head `.py` files with 0 content mismatches** (the image carries one extra, an empty `__init__.py` from the base layer) under `backend_python/src`, with `asb.py` itself at md5
    `1d2402062c32fd6264f4263d227d2ce6` on both sides. The one extra file in the container is an empty
    untracked `__init__.py` the Dockerfile creates.
  - **The re-drive policy is stated as it is now practised:** the front-door leg is re-driven on every head
    that changes **writer *or* transport** code. The earlier wording said "writer", which is what let a
    transport commit land without a re-drive; at1/at2/at3 assert the transport, so they follow it.
  Per-commit position, with the reason each older capture is still valid *measured* rather than asserted:

  | commit | what it changes | artifacts taken before it | why they still hold |
  |---|---|---|---|
  | `b4f0b544e5` | the writer's MCP seeding for a detected claude-code agent | the at2/at6/at7 row dumps were **re-taken on it**, so none | — |
  | `8342fed114` | stamps the agent's `scanner_version` onto **seeded** connectors | at2-01/02/04, at6-02..07, at7-02..09, at7-18 | **Measured, not argued** ([`evidence/at6-08-gateway-version-gate.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-08-gateway-version-gate.txt), which carries the code gate and both queries): the value this commit propagates reaches a row only through `crud.py:133-134`, which writes it *only* when `protects_all_mcps and not gateway_tag_present`. On this box `protects_all_mcps` is false for every `desktop_agent_users` row in every schema, so `current_gw_version` is NULL on every installation row in both lanes. The commit moves nothing observable here, which is exactly why its proof is a unit test. |
  | `c70493626a` | paced the release path (the pool backed off before re-attempting an immediately-redelivered message) | at2-03, at6-05 §J | **Not argued at all — re-driven, and the change itself is gone.** `fb12b015be` dropped that queue-layer pacing as superseded by main, and `at2-03` is re-captured on the current head with no pacing claim in it; see §C11 above. |

  `at5-01/02` were **also** re-captured on this head, because `0cfbd4240c` rewrote one of the two refusal
  messages they quote and a `required_evidence` artifact must quote what ships. Both gen-2 images were
  rebuilt from `0cfbd4240c` for that capture (the clone Deployments had been left on the round-5 image).
- **88** of the ledger's **146** artifact rows are not CURRENT — that count is read out of
  [`evidence/at10-04-evidence-provenance.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-04-evidence-provenance.txt) as this body is written, not restated from
  memory (the previous "70 of 85" was a stale restatement, which is exactly the failure this bullet
  exists to prevent). That file is *generated*
  from the artifacts' own headers, and it now accounts for **every one** of them individually: the block
  is built from the computed list, so an artifact with no entry prints `UNEXPLAINED` rather than
  vanishing (which is exactly how two `at7` rows had been slipping out of a block that called itself
  exhaustive — its selector matched kinds *starting with* `live-runtime` and missed
  `db-rows + live-runtime`). Each entry is either superseded by a head-image capture or sound because
  the commits after it cannot reach what it asserts; the one exception is the live KEDA arm (at8-06),
  which is NOT superseded and is not claimed to be.
- **at8's coverage is computed, not asserted** — `at10-04` reports `on-head coverage: at1, at2, at3, at6, at7, at8, at9, at10`. Where
  its renders lag, the reason is
  structural: its subject is what the flux-fleet sibling *renders*, to which this onyx head contributes no
  line. What moves it is the sibling's head, tracked in the C row above and in [`at10-03-ci.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-03-ci.txt).
- **Staleness is per artifact, and it is generated.** Read it from the per-row GROUP column in
  [`evidence/at10-04-evidence-provenance.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-04-evidence-provenance.txt), which states, for every artifact
  individually, how many functional commits landed after it. The oldest row in that table is
  [`at1-01-lab-resources.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-01-lab-resources.txt) at `2026-08-23T19:44:46Z` (re-driven this round on the shipped head), and its GROUP reports the full branch after it.
  `b4f0b544e5` is the commit that changes the writer's output, so everything pasting writer output
  (at2-01..04, at6-02..07, at7-02..09, at7-18) was taken on it or later.
  The 4 merges are `85c90a7518`, `23247bd494`, `a1197e088f`, `c0a5e99722`; the round-7 pair resolves this
  change set's only real collision — main landed its **own** ADR 0062, which ADR 0053 already cites as its
  supersessor — and it has now happened three times (main took 0063, then 0064) — so this branch's ADR is **0066** and the index carries every row.
- **What those merges changed inside the packages this evidence depends on is listed file-by-file in
  at10-04**, with two called out rather than waved through. Both are now RUN and captured in
  [`evidence/at10-07-merge-impact.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-07-merge-impact.txt), and running them corrected one of them. Main's new
  *device-less-placeholder adoption hook* sits inside `process_single_agent`, which the scanner lane
  genuinely calls. It is not gated off for this run's apps:
  `placeholder_lookup_prefixes` returns a non-empty tuple for `endpoint_claude` and `endpoint_claude-code`. It was written from the app *names* in the scan rather than the `app_definition_id`s in the
  database, which are hyphenated and include `endpoint_claude`; for `endpoint_claude` and
  `endpoint_claude-code` the function returns a **non-empty** tuple, so the hook is not gated off at all.
  What makes it a no-op here is the step after: it can only adopt a placeholder asset that already exists,
  and this tenant holds **zero** — both queries are in the artifact. And the change that could have moved
  asset names — main lifting the display-name map into `common/models/agent_display_names.py` — was checked
  **differentially**, not by eye: the pre-merge humanizer is loaded straight out of
  `git show 23247bd494^:…/activities.py`, the shipped one from the tree, and both are run over every slug
  either map knows. The two curated maps are **43 slugs each, union 43, and 0 display names changed**; the
  harness also probes the 7 agent slugs this run detects, 5 of which are in neither map, so the universe it
  actually compares is 48 — **0 changed under either universe**, with `claude-code` → `Claude Code` on both
  sides. Section 1 of that artifact now prints the comparison script and its verbatim stdout, so both
  numbers can be re-derived rather than taken on trust — And the front-door leg is **re-driven on every head that
  changes writer *or transport* code** — real `onyx-scanner` binary through Kong, gen-1's two workers scaled
  to 0 for the window. Most recently on **`3979910bde` — the head this PR ships** — in the env repaired for
  it (migration applied through the repo's own migrate Job, image rebuilt from that head, exactly one
  consumer on the queue): a scan driven through the front door reporting `"payloads_sent":
  2` and `"skills_total": 91`, every settlement `outcome=processed`, and the lane **creating** a new
  skill row whose `skill_md_hash` equals the machine's own `sha256sum` byte for byte
  ([`evidence/at1-11-merged-head-creates.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-11-merged-head-creates.txt)) — and, the reason this leg had to be on this image,
  **0** `MessageLockLost` / `Failed to renew message lock` lines — and that is now a *measurement*,
  not an absence of mention: `grep -cE 'MessageLockLost|Failed to renew message lock'` over the running pod's
  last 90 minutes of log (3858 lines) returns **0**. The lock is load-bearing here because the
  queue carries the authored TF `PT5M` lock duration and objects take tens of seconds
  ([`evidence/at1-11-merged-head-creates.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-11-merged-head-creates.txt)).

**Key log points (C12).** The paths that matter all log with ids: the azure-branch boot line
(`azure ingestion transport selected`, with queue + namespace + auth mode), `asset_ingestion_record_handled`
(outcome + `tenant_uuid` + `s3_key` on every record, including the deliberate `skipped_flag_off` skip),
`poison message — no ingestible object, dead-lettering` and `Dead-lettered message` (message id + reason),
`failed to parse object-created event message` (message id), the redelivery line (message id + receive count),
(an earlier revision named a release-pacing line here — `Backing off before the next attempt at an
immediately-redelivered message`. **That line no longer exists on this head**: `fb12b015be` dropped the
queue-layer pacing as superseded by main, and `grep -rn "Backing off before" backend_python/src/` returns
nothing, so the log point is withdrawn rather than restated), **the downstream-start-failure line — `MCP downstream start FAILED (non-duplicate) — asset committed,
downstream not started` (`mcp_downstreams.py:60`, with `workflow` + `workflow_id` + `s3_key`)**, **the
alert-publish failure line — `failed to publish one session alert-processing request (continuing)`
(`sessions_writer.py:114`, with `session_id` + `policy_id` + `correlation_id`)**, and the config refusal
itself, which names both the declared cloud and the offending transport setting.
**Round-34 addition (gate GAP-1):** the first two were named by at10's own flow and were missing here. The
downstream one was missing from every artifact too, so rather than cite it from source it was **driven** —
the Temporal frontend scaled to zero (an infrastructure transient, no code touched) and a real payload
posted through Kong, producing the line with
`workflow_id=mcp-cve-scan-prdct11935_tb-25b3bf92904b6c222735236c54209538` and two counter series
(`McpCveScanWorkflow`, `DesktopAgentCustomDataEmbeddingWorkflow`): [`evidence/at12-01-downstream-start-failure.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at12-01-downstream-start-failure.txt).
The alert-publish line was already captured in [`evidence/at11-01-azure-alert-path.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at11-01-azure-alert-path.txt). The captured examples are in `at1-04`, `at1-06`,
`at2-03`, `at3-03`, `at4-01/02` and `at5-01/02` — and the parse-failure point, which no artifact used to
carry, is now driven for real and captured in **[`evidence/at6-13-parse-err.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-13-parse-err.txt)**: a body that is not JSON
at all makes `_parse` raise, the lane logs
`failed to parse object-created event message` at `message_handler.py:96`, meters
`records_total{result="parse_err"}`, and **acks** it rather than dead-lettering, because a parse failure
is deterministic and redelivering it would loop forever. The same artifact keeps the neighbouring probe
that is NOT this class — valid JSON naming no object, which the Azure path dead-letters as poison — so
the boundary between the two is visible rather than asserted.

## Before / After

> **Correction to this section's own history, recorded rather than quietly fixed (round 42).** Rounds 33–35
> of this run attested that both halves of each defect AT were "verbatim captures". That was not true of the
> **Before** halves: until this round at4's *Before* and at5's *Before* were **prose reconstructions** — an
> accurate description of what the pre-fix capture showed, plus a workspace path, but not the capture. The
> **After** halves were, and remain, verbatim. Both Before halves are now the captures themselves, quoted
> below, and every path in this section is a link a logged-out reader can open. The distinction matters
> because a description of evidence is the claim the evidence was supposed to settle; an external review
> caught it, and the earlier attestation was wrong.


**at4 — the fail-open boot (footgun 3).** Same image, same config shape, before and after:

*Before* (frozen base, [`evidence/pre-fix/at4-01-boot-log.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/pre-fix/at4-01-boot-log.txt)): with `ONYX__CLOUD=azure`, **blob settings
present** (as any Azure operator would set them) and an **S3/SQS-only transport**, the base passed config
validation, the pod went **Ready** (`Application startup complete`, 1/1), and it built an SQS consumer and an
S3 client against LocalStack *while declaring `cloud=azure`* — reading the wrong cloud's transport and
storage, with no error to see. That is the fail-open, and it is the shape the fix must flip.

**And here is that capture, verbatim** — round 42 replaced the description with the thing itself
([`pre-fix/at4-01-boot-log.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/pre-fix/at4-01-boot-log.txt), frozen base
`main@67b4096f3323`, captured 2026-08-18T16:51:07Z, before this branch's first commit):

```
# operator would set) + S3/SQS-ONLY transport config. NO transport≠cloud assertion exists, so the service:
#   - passes config validation, boots green, readiness OK ('Application startup complete', pod 1/1)
#   - constructs an SQS consumer + S3 client against LocalStack WHILE DECLARING cloud=azure — silently reading the wrong
#     storage/transport for its declared cloud; no error, no refusal (fail-open). Boot log:
2026-08-18T16:50:08.384988Z [info     ] ingestion lane selected        [endpoint_asset_ingestion.service] filename=service.py func_name=start lane=scanner lineno=191
2026-08-18T16:50:08.458211Z [info     ] SQS client connected           [common_core.services.queue.sqs] filename=sqs.py func_name=connect lineno=101 queue_url=http://localstack:4566/000000000000/endpoint-asset-ingestion
2026-08-18T16:50:08.458484Z [info     ] Asset ingestion worker pool started [endpoint_asset_ingestion.service] filename=service.py func_name=start lineno=204
INFO:     Application startup complete.
#
# RECONCILIATION NOTE (spec deviation, surfaced not silently absorbed): at4.pre_fix.expected_broken says the no-blob shape
# 'passes config validation'. On the real base it does NOT (blob-field validator fires). The demand's substance — footguns
```

`Application startup complete` with an **SQS** client connected to LocalStack, while the service declares
`cloud=azure`. That is the fail-open in the base's own words.

> **Nuance the pre-fix capture surfaced, carried here rather than left in the artifact.** The AT's literal
> wording is a narrower shape — `cloud=azure` with *no* blob settings at all — and the base already refused
> **that** one, but for an unrelated reason: an inherited validator requires `ONYX__BLOB__ACCOUNT_URL` when
> `ONYX__CLOUD=azure` (`common_core/config.py:812-819`), so it fails on a missing blob field, not on the
> transport contradicting the declared cloud. No transport≠cloud assertion existed at all. The defect's
> substance — footguns 1 and 3 — reproduces exactly in the blob-present shape above, which is also the
> operationally realistic one; the deviation is recorded in the artifact's own reconciliation note and in the
> C3 ledger rather than smoothed over.

*After* ([`at4-01`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at4-01-postfix-refusal-azure-s3.txt), quoted verbatim — **re-driven 2026-08-23 on the shipped head
`2b60fdc4df`**, pod `eai-azure-refuse-s3-85bbcf6899-chbbv`, image `:r46b-head`):

```
## 1. WHAT KUBERNETES SHOWS
## deployment eai-azure-refuse-s3   pod eai-azure-refuse-s3-85bbcf6899-chbbv   state: 0/1 Error 0
     cloud: azure
     asset_ingestion_sqs:
       queue_url: "http://localstack:4566/000000000000/endpoint-asset-ingestion"

## 2. THE REFUSAL, verbatim from the pod's own log
  Value error, endpoint_asset_ingestion: ONYX__CLOUD=azure but the AWS queue transport is configured
  (ONYX__ASSET_INGESTION_SQS__QUEUE_URL='http://localstack:4566/000000000000/endpoint-asset-ingestion').
  Refusing to start: this pod would use the AWS queue while declaring cloud=azure.
```

`state: 0/1 Error` is the whole assertion, and it is **stronger than the previous capture showed**. That
one ran on the dev image, whose `uvicorn --reload` parent outlived the failed lifespan and left the pod
not ready, but not gone — Kubernetes showed it Running. The shipped image has no reloader, so the process
**exits**: the guard fails closed rather than lingering in a state an operator could misread as working.

The symmetric shape (`cloud: aws` + a Service Bus queue) is refused the same way — [`evidence/at4-02-postfix-refusal-aws-asb.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at4-02-postfix-refusal-aws-asb.txt).

**at5 — the healthy-looking silent drop (footgun 2).**

*Before* (frozen base, `evidence/pre-fix/at5-*`): both consumers, in azure mode against the real lab queues,
received 9 real Event Grid BlobCreated deliveries each and **acked all of them** — no dispatch, no errors, no
dead-letters. Healthy pods, zero ingestion.

**The capture, verbatim** — this is where the number 9 comes from, which the prose above previously asserted
with no visible provenance ([`pre-fix/at5-03-queue-counts.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/pre-fix/at5-03-queue-counts.txt)):

```
# at5 pre-fix — queue + DLQ counts AFTER the azure-mode base consumers ran (2026-08-18T16:48:41Z)
# Before: 9 active messages on EACH queue (real Event Grid deliveries). After:
scanner-events-prdct11935: active=0 deadLetter=0
mcp-gateway-events-prdct11935: active=0 deadLetter=0
endpoint-asset-ingestion-prdct11935: active=9 deadLetter=0
# scanner-events + mcp-gateway-events: consumed-and-VANISHED (acked, no DLQ, nothing dispatched).
# endpoint-asset-ingestion-prdct11935 still holds its 9 — NO consumer exists for it on the base (the absent writer this ticket builds).

## ScannerObjectWorkflow executions (Temporal) — EMPTY (nothing was dispatched):

  WORKFLOW TYPE | WORKFLOW ID | RUN ID | TASK QUEUE | START TIME | EXECUTION TIME | END TIME
```

Both gen-2 queues drained to `active=0 deadLetter=0` — consumed and vanished — while
`endpoint-asset-ingestion-prdct11935` still holds its 9, because no consumer existed for it on the base. The
Temporal `ScannerObjectWorkflow` list is **empty** in the same window, which is what makes it a silent drop
rather than a slow one. Per-consumer logs:
[`pre-fix/at5-01-scanner-drop.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/pre-fix/at5-01-scanner-drop.txt) ·
[`pre-fix/at5-02-mcpgw-drop.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/pre-fix/at5-02-mcpgw-drop.txt).

*After* ([`evidence/at5-01-scanner-postfix.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at5-01-scanner-postfix.txt), [`at5-02-mcpgw-postfix.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at5-02-mcpgw-postfix.txt)) — **provenance corrected here;
the previous wording was stale, and the artifacts behind it were worse than stale.** Until round 50 both
files head-stamped `2b60fdc4df` / `:r46b-head` while their bodies printed, under a **REFUSES** heading, a pod
that was `1/1 Running`, `exitCode=`, `restarts=0` on the **pre-fix** image `:prdct11935-r26`. Re-captured
this round from the pods that actually refuse, on images built here from the clean head tree: scanner
`:r50at5-head` `sha256:943a1264…d8d79b85f`, gateway `:r50at5-head` `sha256:15be1519…5b244ee55`, with all
**6385** files of `git archive 2b60fdc4df backend_python/src` proven byte-identical to `/app/src` inside
both images. **And the reason the old artifact looked healthy is now known**: under the Tilt dev entrypoint
(`uvicorn --reload`) the reload supervisor does not propagate its child's startup failure, so a pod whose
app refused still reports `1/1 Running`. The `exitCode=3` / CrashLoopBackOff evidence therefore comes from
the **production entrypoint shape** (`--workers 1`, `backend_python/Dockerfile:202/210`) — which is the
shape a cell runs. `at10-04`, generated from those headers, lists both rows as CURRENT with zero lane-touching commits
landed after them (that ledger is regenerated from the artifacts' own headers at push time, which is why
it is cited rather than quoted as a fixed string). The earlier text here claimed `0665ecc545` /
`:prdct11935-r25` with a paragraph rationalising a staleness that no longer exists; that is withdrawn.

The branch is gone and each service refuses to start on that cloud, so it cannot consume. **Measured on the
lab namespace, and this number is corrected too:** the artifacts record `scanner-events-prdct11935` at
**47 active / 0 dead-lettered before the leg and 47 / 0 after**, and `mcp-gateway-events-prdct11935` the
same — unchanged across the whole run, which is the assertion that matters. The earlier "**11,004 active
messages**" appears in no captured artifact and is withdrawn; it was a figure carried forward from an
archived round-18 body. Re-read live at push time the two queues stand at **744 / 0** each — they keep
growing precisely because the refusing consumers never drain them, which is the same fact the 47/47 pair
shows over a bounded window. That is the difference from the pre-fix behaviour, where the same service
acked 9 real deliveries and wrote nothing.

Both refusal texts, verbatim from the pods that actually refuse: `r50at5-scanner-azure-prod`
(`…-585fc5c9bb-r8kf2`) and `r50at5-mcpgw-azure-prod` (`…-567897ff94-grjx9`), each **0/1 CrashLoopBackOff,
`exitCode=3 reason=Error restarts=5`**, booted on **`2b60fdc4df25188104e737e6311087681355eff8`** from
images built from that exact tree (`:r50at5-head`, digests `sha256:943a1264…` and `sha256:15be1519…`). The
guard is re-proven on the same pods — **0** `ASB client connected` and **0** `Completed message` against the
pre-fix captures' 10 and 9 real acks — the two lab queues only GREW (6660 → 6693 each) with `dead_letter=0`
and the oldest message still at `"delivery_count": 0`, and the **AWS** half of the same build boots `1/1`
with only `ONYX__CLOUD` flipped. The gateway one **changed in this PR** —
it used to name the *scanner* lane as the owner, which is a different object source with no Azure routing at
all — so an artifact quoting the old text would have been quoting something the branch no longer ships:

```
Value error, scanner_event_consumer_service: ONYX__CLOUD=azure is not supported by this service (it
implements aws only). Refusing to start rather than consuming a queue it cannot process. The Azure
scanner-object lane is owned by endpoint_asset_ingestion (ONYX__CLOUD=azure), which parses Event Grid
BlobCreated events off Service Bus and writes the assets in-process.
```

```
Value error, mcp_gateway_event_consumer_service: ONYX__CLOUD=azure is not supported by this service (it
implements aws only). Refusing to start rather than consuming a queue it cannot process. There is no Azure
implementation of the MCP-GATEWAY object lane yet: the Azure side ships one Service Bus queue,
endpoint-asset-ingestion, fed by a sys.Label 'source=mcp-scanner' rule, so gateway objects are not routed on
an Azure cell at all. endpoint_asset_ingestion CAN run its gateway lane (ONYX__CLOUD=azure), but it would
need its own Service Bus queue and an Event Grid subscription rule for source=mcp-gateway, neither of which
exists. Run this service on an AWS cell, or track the Azure gateway lane before enabling one.
```

**Before / After, in one more place — the lane's product effect.** Before this change an Azure tenant had no
writer at all; after it, the same machine's payload lands and renders. The two halves of the gate were
captured with the *same pod*: flag OFF → `outcome=skipped_flag_off`, zero rows; flag ON → `outcome=processed`,
rows written and rendered above. The stranding scenario the ticket names is closed end to end: with the old
lane's schedule paused, a fresh scan still landed through the Azure lane.


## Review threads

Every review thread on this PR is answered in-thread and resolved. The full accounting — each thread, what
it claimed, what was measured, and which commit closed it — is [`evidence/at10-05-review-responses.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-05-review-responses.txt),
whose counts are read from the GraphQL API at write time. Three review findings became code:
`c70493626a` (pace the release path), `8342fed114` (stamp seeded connectors' scanner version) and
`dfe23b9e83` (derive the lock renewal from the lock), each with a test that fails without it.

### One question routed to the plan owner, and how it was ruled

**The lifecycle end-state for four C2 asset classes has no product representation.** C2 clause 5 asks that
after a removal the second scan "shows it stale or marked deleted". Measured on the head build
([`evidence/at7-41-lifecycle-head.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-41-lifecycle-head.txt)): the skill, subagent and MCP bundle were really deleted from disk, a
real second scan ran, and **nothing moved** — all three stay `AssetStatusDiscovered` / `is_deleted=f` with
their original `updated_at`, and the bundle's five tools stay `is_active=t`. The reason is in the type
system, not in this lane: the stored `AssetStatus` enum is exactly {Sanctioned, Unsanctioned, Discovered}
with no stale or removed value, **neither** ingestion lane moves `status`/`is_deleted` on absence-from-scan
(the new lane's only absence-driven soft-delete is agent→MCP *edges*, `mcp_writer.py:1603-1662`, with the
empty keep-set deliberately skipped under the PRDCT-6301 "absence is not a delete instruction" design; gen-1's
only reconcile knob routes to that same edges-only activity, `post_inventory.go:118,196`), and the SPA's
entire lifecycle vocabulary for these classes is a `Deleted` badge gated on `is_deleted` that the scanner
lane never sets.

Rather than answer a contract question at run time, it was **routed to `research` as the plan's owner**, which
ruled it in the round-26 plan amendment (`test_plan.json` `spec_interpretations` (8) and the four
`d-c2-lc-*.amendment_r26` fields, frozen at `sha256 e4943218…` *(superseded)*; the veto post is resolved against Slack in
[`evidence/at7-43-veto-permalink-r26.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-43-veto-permalink-r26.txt)). The ruling: the demand's second half binds untouched and is proven;
its stale-rendering half is **OVERTAKEN** — the premise that the product represents such a state does not hold
— and the gap is a pre-existing cross-lane **product** gap, ticketed as
**[PRDCT-12069](https://app.clickup.com/t/86bbhzk2z)** ([`evidence/at7-42-lifecycle-followup-ticket.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-42-lifecycle-followup-ticket.txt)). It is
carried as a row in the C3 ledger below, not waived.

Inventing the missing state here — reading a frozen `updated_at` as "stale", or adding soft-delete-on-absence
to the shared writer — would have been either a dishonest reading or a behavioural change on every cloud, in a
transport PR, to the exact semantics that protect a laptop that is merely offline. **This PR therefore claims
no stale or deleted rendering for any class it did not measure one on**, and every caption below says what the
product actually shows.

## Branch currency — one head sha, measured at push time

Two sections used to stand here and they contradicted each other and the head: one argued against merging
`main` and cited a head of `16b7bca77c` *"19 commits behind"*; the other announced a round-44 merge and
claimed *"every artifact in this bundle is stamped `16b7bca77c`"*. Both are gone. The head is
**`2b60fdc4df25188104e737e6311087681355eff8`**, it is the only head sha this document states, and everything
below is re-measured as the body is written rather than restated:

| measured now | value | how |
|---|---|---|
| head | `2b60fdc4df` | `gh pr view 12329 --json headRefOid` |
| merge-base with `main` | `822abd2356` | `git merge-base HEAD origin/main` |
| behind / ahead | **11** / 37 | `git rev-list --count HEAD..origin/main` and its reverse |
| files `main` moved since the merge-base | 295 | `git diff --name-only 822abd2356..origin/main` |
| of those, files this PR also touches | **3** — `backend_python/pyproject.toml`, `backend_python/uv.lock`, `docs/decisions/README.md` | a `comm` of the two file lists |
| **lane** files `main` moved | **0** | the same list grepped for `endpoint_asset_ingestion`, `common_core/services/{queue,ingestion_events,storage}`, and both gen-2 consumers |
| merge state | `MERGEABLE` / `BLOCKED` — the human CODEOWNERS gate, **not** `BEHIND` | the PR API |

None of the three overlapping files collide: `main`'s `pyproject.toml` hunk adds a `glean` extra and extends
the `temporal-worker` extra list while this PR adds `azure-storage-blob` to the runtime dependencies,
`uv.lock` follows from that, and `docs/decisions/README.md` takes one index row from each side. GitHub
reports the branch `MERGEABLE`, and this repo does not require up-to-date branches, so the merge stays with
the codeowner at merge time.

**Evidence stamping is per artifact, not per bundle.** The blanket *"every artifact is stamped X"* claim was
the wrong shape and it was false in both directions — some artifacts were newer than that sha and some were
older. What replaces it is a generated, per-artifact accounting: [`at10-04-evidence-provenance.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-04-evidence-provenance.txt) prints
every artifact's own stamp, the onyx sha it was captured on, and the lane-touching commits that landed after
it, and [`at10-23-evidence-currency.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-23-evidence-currency.txt) buckets the same set by whether the lane actually moved
underneath each one. Where an artifact is not current, the ledger says so in its own row rather than a
sentence here claiming otherwise.

*ADR numbering, which this PR lost three races on:* `main` landed its own **0066**, then **0067**, then
**0072**, and has since added **0068**, **0071** and **0073**, while this branch was open. Numbering by max+1 loses that race every time, so this PR's record
now sits at **0069** (`docs/decisions/0069-the-declared-cloud-decides-the-ingestion-transport.md`) — a real
gap in the sequence, which an author adding a new record cannot take out from under it, because they pick
max+1. `docs/decisions/README.md` carries every row in order and `task docs:check` passes.

> **⚠️ TO WHOEVER MERGES THIS — re-check the ADR number first.** The owner's instruction, adapted to the
> number this record ended on: *re-check right before merge that **0069** is still free on `main`; if
> another PR has taken it, renumber this one to the next free number and update the file name, the index
> row in `docs/decisions/README.md`, and every reference to it.* This is not boilerplate — this branch has
> already lost the race three times (0066 → 0067 → 0072 were all taken while it was open), and the check
> costs one command:
> ```
> git ls-tree -r --name-only origin/main docs/decisions | sed 's|.*/||;s/-.*//' | grep -x 0069
> ```
> Empty output means 0069 is still free. Verified free at the time of writing; a human merges later.

## Known side-PRs carrying this ticket id

One other open PR carries `PRDCT-11935` in its title. It implements **zero demands of this contract** and
gates nothing here, but a human arriving at the ticket will find it, so it is disclosed rather than left
dangling.

**[onyx#12382 — `PRDCT-11935 | dev: auto-inject per-caller service_identity so parallel agents stop
colliding on LD flags`](https://github.com/onyxsecurity/onyx/pull/12382)** — opened by **May Bohadana**
(`may@onyx.security`) on 2026-08-19. **This run has since pushed to it. Read the correction below before
anything else in this section.** Live fetch behind every number here: [`at10-24`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-24-sibling-pr-12382.txt). Disclosed on that PR itself: [comment](https://github.com/onyxsecurity/onyx/pull/12382#issuecomment-5388120319).

### ⚠️ Correction — an earlier version of this section was false

Until now this section said *"opened 2026-08-19, untouched since"*, *"1 commit, 5 files, +74/−0"*, and, in
bold, ***"I did not close it and I did not push to it"***. **All three were false when they were written,
and the last one is the one that matters.** On **2026-08-23 between 10:40 and 10:55 UTC this run pushed six
commits to that branch**, authored under this box's git identity (`default <iddo.g@onyx.security>`):

| sha | time (UTC) | subject |
|---|---|---|
| `42c8ad61d3` | 10:40:31 | Merge `origin/main` into `fix/si-env` |
| `8e34c3e173` | 10:44:34 | Stamp the identity under the name each runtime actually binds |
| `62044a38e6` | 10:45:01 | Merge `origin/main` into `fix/si-env` |
| `5345e62891` | 10:51:56 | Cover the ai-guard render path, and say only what the derivation guarantees |
| `b2d2e2921e` | 10:54:57 | Strip each identity value before the fallback, and drop the ticket id from fixtures |
| `b2c431e44c` | 10:55:43 | Merge `origin/main` into `fix/si-env` |

(The branch's seventh commit, `2a53965d4a` at 17:15:05 on 2026-08-19, is **May's own** — the one the PR was
opened with. Every subject above is quoted from a live
a live read of that PR's commits endpoint as this body is written; one of them used to read *"drop
the ticket id from the code"* and the live subject is *"…from fixtures"*.)

Those commits address the two findings this section had itself recommended — the Go/Python env-name split
and the uncovered ai-guard render path — and add the two Go tests (`service_identity_test.go`,
`service_identity_env_test.go`). The work was directed; **the false sentence is mine.** It was written in an
earlier round, the pushes happened in a later one, and I did not come back and correct it. It stood in a
document I was asking reviewers to trust. It is corrected here, disclosed to the ticket owner on
PRDCT-11935, and disclosed on #12382 itself so its author reads it there and not only here.

### The live state, re-fetched

| | |
|---|---|
| Head | `b2c431e44c0f5488a21d028f94c5896c9985a802` · updated **2026-08-23T19:50:22Z** (re-fetched as this body is written; the row said `11:07:01Z`, which had gone stale) |
| State | OPEN · `CHANGES_REQUESTED` |
| Currency | `compare main...b2c431e4` → **ahead 7, behind 30, diverged** (was 26 when this row was first written; `main` has moved since) |
| Size | **7 commits, 9 files, +238/−0** — onyx `tilt/helm.star`, onyx `tilt/ai_guard.star`, the tilt-dev skill doc, `main.tf` in each of the four coder templates, and two new Go tests |
| Review | 10 threads, **1 unresolved** |
| Relationship to this contract | **none** — it touches no demand, no acceptance test, and no file in this PR's diff |

**Why it carries this ticket's id.** It is dev-tooling for the LaunchDarkly `service_identity` attribute —
the mechanism that lets one caller point a shared dev flag at *itself* instead of flipping the tenant
default for every other run on the dev project. This run depends on exactly that attribute: the flag-ON leg
here was proven against the real LD rule
`{contextKind: tenant, attribute: service_identity, in: [agent-prdct11935]}`, and
`ONYX__FEATURE_FLAGS__SERVICE_IDENTITY` is set on this lane's own pod. So the ticket id records where the
need was found; the change itself is dev-infrastructure, not scanner ingestion.

**Disposition — the author's and the ticket owner's, not mine.** It is **30** behind `main` with one unresolved
thread, and its own tip is a `Merge remote-tracking branch 'origin/main' into fix/si-env`. Whoever picks it up should know that a different run pushed most of its current content, and may
reasonably prefer to re-cut it. Related work exists on the router side — `onyx#12377`
(`PRDCT-10171 | ld-router: mediate service_identity clauses`) — a **different ticket on a different branch
that I have not reviewed or verified**; if that lands, the two together are what would make per-caller LD
targeting work end to end, and they are worth deciding as a pair.

---

## Ticket reconciliation

Every deliverable the ticket names, with a status.


**Known follow-ups this PR opens or carries — five, all filed, none of them a place to hide work:**

1. **[PRDCT-12061](https://app.clickup.com/t/86bbhqxe8)** — *One-writer cutover prerequisite: converge
   script-launched local MCP server identity (re-key migration) + cold-cache version-key semantics*. It is
   the C13 amendment's condition (4), and its fetched body is captured verbatim with each required element
   checked in [`evidence/at6-10-followup-ticket.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-10-followup-ticket.txt). It blocks gen-1 retirement (ticket footgun 4) and
   carries the cutover exposure for PRDCT-9710.
2. **[PRDCT-12069](https://app.clickup.com/t/86bbhzk2z)** — *Product gap: no stale/deleted representation
   for scanner-discovered desktop-agent / skill / subagent / MCP-server assets (and their tools) after
   on-machine removal*. The C2 clause-5 lifecycle half no product surface represents; scope extended to the
   desktop-agent class in round 28. Verbatim in [`evidence/at7-45-lifecycle-followup-ticket-r28.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-45-lifecycle-followup-ticket-r28.txt).
3. **[PRDCT-12070](https://app.clickup.com/t/86bbj2pqn)** — *Durable retry for the Azure scanner-ingestion
   lane: a dependency outage permanently dead-letters real objects (`max_delivery 5 × 5s backoff` exhausts
   the budget in ~25s)* — **NEW, filed this round, and it is not our defect to hide: it is shipped
   behaviour this PR's own verification surfaced.** During independent verification a roughly one-hour
   Postgres outage (the kind node self-tainted with `disk-pressure`, `postgres-1` evicted) made every
   in-flight object fail with `ConnectionRefusedError` to `postgres-rw`. The consumer behaved correctly
   per message — it abandoned rather than acked — but the retry budget cannot outlive a dependency outage:
   `max_delivery_count = 5` (`infrastructure/…/cell-azure-instance/service_bus.tf:199`, live queue confirms
   `maxDeliveryCount: 5`) against a flat `error_backoff_seconds: 5`
   (`endpoint_asset_ingestion/config.py:80`, applied at `common_core/services/queue/consumer_pool.py:160-162,197`)
   burns all five deliveries in **≈25 seconds**. The `$DeadLetterQueue` grew **29 → 57** and roughly **28
   real scanner objects were permanently parked**, with no automatic redrive. The same shape applies on AWS
   — `consumer_pool` is shared — so this is not Azure-specific; Azure is where it became visible because the
   native DLQ makes the loss countable. It is also, structurally, one of the label-less exits this PR's own
   settlement inventory now reports: a broker-side `MaxDeliveryCountExceeded` park runs no application code,
   so no app-side counter moves ([`evidence/at6-01-inventory.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-01-inventory.txt), item 4). Evidence: [`evidence/at6-16-durable-retry-followup.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-16-durable-retry-followup.txt), which carries the filed ticket, the
   `max_delivery_count = 5` setting read from both the Terraform source and the live queue, the flat
   `error_backoff_seconds` default and where it is applied, and the outage's DLQ growth — alongside the
   verifier's own capture under `evidence/verify-r26/`. Not fixed here — changing retry semantics on a shared consumer pool
   is a behavioural change on every cloud and belongs in its own change, with the existing constraints
   intact (absence of a write is never a delete instruction; a genuinely poison message must still park).
4. **[PRDCT-12071](https://app.clickup.com/t/86bbj56qh)** — *Product defect: posture issues re-affirm Open
   with deleted content as live Evidence* — **NEW, filed for the round-30 adjudication.** After a scanner
   artifact is deleted from the machine, the posture pipeline re-touches its `issue_instances` Open on every
   subsequent scan of the owning agent, and `/posture-issues` renders the deleted file's content as live
   Evidence with Status: Open. This is a **user-visible wrong state**, not merely a missing stale rendering —
   which is why it is ticketed separately from PRDCT-12069 rather than folded into it, and **cross-linked**
   to it: they share a root cause, since no scanner-lane writer sets `assets.is_deleted`, the gate on the one
   absence-adjacent close hook. Measured on head in [`evidence/at7-09-db-rows-posture.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-09-db-rows-posture.txt), shown pre-existing
   in [`evidence/at7-47-posture-path-identity.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-47-posture-path-identity.txt), shown transport-independent in
   `evidence/r30-genone-reaffirm.txt`, and rendered honestly in `evidence/at7-22-ui-lifecycle-posture.png`.
   Not fixed here: closing on absence would auto-resolve real customer findings whenever the classifier has a
   hiccup — the posture plane documents that constraint itself — and inventing close semantics inside a
   transport-enablement PR is the change-class the round-21/26 adjudications declined. Adjudicated in
   `d-c2-lc-posture.amendment_r30`, [veto post](https://onyx-security.slack.com/archives/C0BCW4JDZB2/p1787324020228879?thread_ts=1787063683.640599&cid=C0BCW4JDZB2).
5. **[PRDCT-12076](https://app.clickup.com/t/86bbjf3f0)** — *MCP redaction parity: the Python ingestion
   lane persists a live credential the Go scanner lane redacts* — **NEW, filed this round.** Found while
   ledgering a cross-lane `mcp_servers.hash` divergence the round-29 gate asked for. The hash difference
   was the symptom; the cause is that the Python lane's redactor
   (`common/services/mcp_secret_redaction.py:153`) is weaker than the Go scanner lane's
   (`pkg/secrets/mcp_identity_redaction.go:54`) — it applies CLI-flag and query-param redaction but has no
   basic-auth-userinfo pass and no credential-prefix sweep. Measured on the same server in the same window:
   gen-1 stores `?tavilyApiKey=[REDACTED]`, gen-2 stores the **live key**, into
   `mcp_gateway_installations.args` and into the hashed bytes. The Go side already pins this requirement and
   names this exact shape (`mcp_redaction_parity_test.go:13-27`, *"a weaker WRITE persists the raw secret
   into inventory"*); there is no equivalent Python test, which is how it drifted.
   **Not fixed here, deliberately:** the two consequences pull in opposite directions — hardening gen-2 to
   match gen-1 would also lose the CVE resolution that currently works, because gen-1's redacted hash
   resolves to no `mcp_package_cache` row at all (`cve_scan.py:75` then silently drops the asset). The
   redactor and the cache-population key have to move together, on shared code that runs on every cloud,
   and the MCP identity derivation is the locked pair whose own note forbids changing one side alone before
   the M2 cutover. Measured and ledgered in [`evidence/at6-06-ledger.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-06-ledger.txt) (the `mcp_servers.hash` row).

| Item | Status |
|---|---|
| **Verdict** — the new flow is absent on Azure | **delivered** — it exists now; the writer consumes the real Event-Grid-fed queue and reads Blob (at1) |
| **Footgun 1** — LD flag flip is a silent no-op on Azure | **delivered** — a pod now reads the flag per tenant on Azure; captured settling `skipped_flag_off` with ids (at1-06). The stranding scenario is closed by parity, not by a flag change |
| **Footgun 2** — gen-2 ASB dead path | **delivered** — branch deleted in both services, `cloud=azure` refused at boot, proven live (at5) |
| **Footgun 3** — no transport/cloud assertion | **delivered** — refuses both mismatch directions and an azure config with no queue (at4) |
| **Footgun 4** — don't retire gen-1 | **delivered** — gen-1's behaviour is untouched by this diff. Stated precisely rather than absolutely: the diff *does* touch one gen-1 file, `desktop_agent_creator/workflow.py`, behaviour-neutrally, and nothing else in the gen-1 lane; the misleading `"retired"` wording in `metrics.py` is corrected to say the units are still live wherever a cell has not cut over |
| **A1** ASB config + blob stanza | **delivered** — `AssetIngestionASBConfig`, plus the inherited `blob` stanza |
| **A2** `CloudProvider.AZURE` branch, ASB factory mode, `max_messages` pinned to 1 for ASB at runtime | **delivered** |
| **A3** `create_storage_client` instead of a hard `S3Client` | **delivered** (see interpretation 4) |
| **A4** the missing Event Grid parser | **delivered, then OVERTAKEN mid-flight and re-resolved** — `main` landed one for the sensor lane while this branch was open, so the lane now consumes `parse_blob_event_message` and this branch's own parser is deleted. One parser, both body shapes, unit-pinned, with the real captured lab delivery as a test. See the Design Decisions bullet and correction 8 |
| **B1** Service Bus queue + toggle, native DLQ | **delivered elsewhere, and now MERGED** — onyxsecurity/infrastructure#1575 merged into `main` at **2026-08-23T12:18:07Z** at head `da993d1ae2eb` (re-fetched live as this body is written; earlier revisions of this row described it as open and awaiting its `approval-gate`, which stopped being true when it merged) (advanced this round: the state migrations moved into a dedicated `moved.tf` at the reviewer's request, a plan-time feed guard added for the queue, and `main` merged so the branch is no longer conflicting — `mergeable: true`) (re-fetched live this round; the body previously named `f9d608e7b38c`, which is that head's PARENT — it stopped being the head when `8498355f0131` landed 2026-08-21T21:24Z, and the B4 row below already named the newer sha, so the body disagreed with itself), `mergeable: true`, `mergeStateStatus: blocked`. Both are quoted because the round-19 gate found this row claiming "mergeable: true, 0 behind" while the PR was live `BEHIND` — `mergeable` alone does not say whether a branch is current. It was brought up to date with `main` this round, and the terraform bar is now IN the evidence rather than asserted: `fmt -check -recursive` clean on all five changed dirs, `validate` Success on the module and both instance roots, `terraform test` **6 passed / 0 failed** (`at9-01`). The one red signal is `approval-gate`, the repo's CODEOWNERS **human** review status. |
| **B2** `byoc_events` subscription + `source=mcp-scanner` SQL rule | **delivered elsewhere** — same branch; rule semantics proven live incl. both non-collision directions (at9-02/03) |
| **B3** blob → Event Grid → Service Bus for non-BYOC SaaS | **delivered elsewhere** — same branch, extracted as a shared module so BYOC and SaaS cannot drift (see interpretation 2) |
| **B4** federated credential + the roles | **delivered elsewhere** — same branch; the role set is asserted live, including the without-roles refusal (at9-05). **Round-34 correction (gate GAP-7d):** the ticket and the plan text both say *two* roles; the shipped Terraform declares **three** — a queue-scoped `Azure Service Bus Data Sender` on `alert_processing` (`workload_identity.tf:119-125`) alongside the Receiver and the Blob Reader. Without it the alert fan-out 401s and every session alert is lost silently. The third grant is ledgered with its call chain, its cost-if-dropped and its AWS-parity precedent in [`evidence/at9-05-roles.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at9-05-roles.txt), and the four stale "two grants" comments in the infrastructure repo were corrected in commit `8498355f` (that branch's head is now `da993d1ae2eb`). The plan text is research's to move; the PR now states three. |
| **B5** publish queue name/namespace into flux config | **delivered elsewhere** — same branch. Published **conditionally**, gated on `create_service_bus && create_endpoint_asset_ingestion_queue` (at9-06, re-captured against the live sibling head): unlike the AWS side, which string-composes its URL from account+region+tenant and so has no resource to gate on, the Azure keys are read off the real queue and namespace. A lane-on/queue-off instance therefore renders an empty queue name — Flux substitutes an unprovided `${...}` to the empty string and reconciles — so it crash-loops on the transport guard's refusal rather than failing the render, which is why infrastructure must be applied before the flux toggle. Full cross-repo key-match table in at9-07 |
| **C** lane enabled on **both** Azure instances, azure-servicebus KEDA trigger on the SAS auth, drop-aws-only entries, stale release.yaml comment | **delivered elsewhere, and the comment sub-item is OVERTAKEN — see correction 10** — onyxsecurity/flux-fleet#2307, head **`a4493c1e5ac0`** (re-fetched live; the `b0d3e1cfbfea` this row used to pin is **131 commits** behind it, and the renders quoted here were re-rendered at `a4493c1e5ac0`, not at that sha), still **OPEN** — `mergeable: true`, `mergeStateStatus: blocked`. It was `CONFLICTING`/`DIRTY` when the round-19 gate looked, and the cause was not a stale rebase: `main`'s PRDCT-4368 (#2334) removed **all 611 comment lines** from the eight instance override files while this branch was adding a ~57-line comment block to the same region. Resolved main's way — both files taken comment-free from main with this lane's 39 value lines replacing the disabled stub, and the three traps the comments carried recorded in `docs/architecture/instance-override-rules.md`, where PRDCT-4368 says rules now go. `make check` (164 kustomizations) and tenant parity both pass on the resolved head, and both instances render the lane enabled with `asset_ingestion_s3` **and** `asset_ingestion_sqs` blank and the `azure-servicebus` KEDA trigger (`at8-01`/`at8-02`, re-rendered at that head). Same `approval-gate` human gate as B1. |
| **Deploy safety — OWNER-VISIBLE DECISION** (round-49 adjudication, `spec_interpretations` **(14)**) | **Merging flux-fleet#2307 is a LIVE CUTOVER, not a dark deploy — this PR used to say the opposite.** Measured read-only three times by three different agents — 2026-08-23T18:22:18Z, 20:33:27Z and 20:56:39Z — via `GET /api/v2/flags/default/endpoint-asset-ingestion?env=production`: `on: true`; `fallthrough.variation: 0  ->  serves True`, so a tenant matching **no** rule gets the lane **ON**; the FALSE holdout rule serves exactly `bamfunds`, `fireblocks` and `intuit-prod`; and rule `c7789aea-0948-42f8-8f54-a31d1d5148b0` serves **true** to 19 tenants **including `Centerpoint Energy`**. The enablement therefore lands hot for Centerpoint Energy and for every unmatched tenant on both c02 instances, and the intuit precedent does not transfer *precisely because* `intuit-prod` is one of the three explicit FALSE holdouts. **⚠️ Before merging flux-fleet#2307, confirm the intended production posture of `endpoint-asset-ingestion` with the flag owner** — the same instruction is carried at the top of that PR, so whoever merges it need never open this one. **This run only READ the flag; no write was made to any production LaunchDarkly environment** — changing it is a human decision. Evidence [`at10-08-prod-ld-posture.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-08-prod-ld-posture.txt); escalated to the owner before the plan re-freeze ([thread](https://onyx-security.slack.com/archives/C0BCW4JDZB2/p1787517269527719?thread_ts=1787063683.640599&cid=C0BCW4JDZB2) · [DM](https://onyx-security.slack.com/archives/D0B6V65HCEN/p1787517269723809)). Note the other half of the same picture: **infrastructure#1575 is already merged** (row B1), so the Azure infra side is on `main` and flux is the remaining gate. |
| **C2 posture** (`d-c2-fid-posture`) | **The class DID mint issues, and it settles under `amendment_r30` — as a defect, not as a fallback.** **ROUND-31 CORRECTION:** this row previously read *"bridge-ran, no issue — the plan's pre-declared fallback"*, which [`evidence/at7-09-db-rows-posture.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-09-db-rows-posture.txt) explicitly refutes, and which contradicted this body's own C2-LC row a few hundred lines below — so the reconciliation shipped **two mutually exclusive dispositions for one class**, in the direction that hid the defect. There is now one. The measured end-state: issue instances **1637 / 1638 / 1639 on asset 211819**, one per firing definition (44 / 45 / 48), persisting after the source was deleted — no new instance, none duplicated, each still joining a live asset row, the subject's asset row count unchanged at 1 and `total_risk_score` steady at 2.49. Across the paired real re-scan `updated_at` advanced **15:17:13.181372 → 15:29:04.521424** while `resolve_state` stayed **Open**, `closed_at` stayed **NULL**, and `asset_posture_findings.classified_at` stayed **FROZEN at 2026-08-21 13:44:18.531816+00** — the row was re-written from a cached finding, not from any live artifact. Attributed to the triggering bridge → `IssueDetectionWorkflow` parentage. The product renders it as **Open ×16, Resolved 0, Closed 0** with the deleted the deleted skill file still in frame (`evidence/at7-22-ui-lifecycle-posture.png`). Path identity for the posture plane is [`evidence/at7-47-posture-path-identity.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-47-posture-path-identity.txt). Ticketed as **[PRDCT-12071](https://app.clickup.com/t/86bbj56qh)**; the bridge execution itself is still shown in [`evidence/at7-29-posture-bridge.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-29-posture-bridge.txt). |
| **C2-LC** — C2 clause 5's stale-rendering half, **all six lifecycle classes** (MCP server, MCP tools, skill, subagent, desktop-agent, posture) | **OVERTAKEN for five classes; a measured, ticketed DEFECT for posture — and the posture half was RE-ADJUDICATED at head this round.** *(This row was briefly lost when a 27 KB gen-1-parity section was removed from this body; it is restored here, in the C3 ledger where the `spec_interpretations` table points, and rewritten to the head's behaviour rather than pasted back.)* **What binds and is proven:** the demand's *not-resurrected / not-duplicated* half — one asset row per artifact identity after a real removal and a second real scan, tenant-wide `is_deleted` = 0, nothing written after the second scan began ([`at7-41-lifecycle-head.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-41-lifecycle-head.txt), [`at7-18-lifecycle-db.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-18-lifecycle-db.txt)). **Why the *stale-or-deleted* half is unrepresentable for the five classes:** the stored `AssetStatus` enum is exactly {Sanctioned, Unsanctioned, Discovered}, **neither** lane moves `status`/`is_deleted` on absence-from-scan, and the SPA's whole lifecycle vocabulary for these classes is a `Deleted` badge gated on `is_deleted` that the scanner lane never sets — a pre-existing cross-lane product gap this transport PR neither introduces nor could honestly fix. Adjudicated in `spec_interpretations` **(8)** (`amendment_r26`), posted for owner veto, and ticketed on **[PRDCT-12069](https://app.clickup.com/t/86bbhzk2z)**. **Desktop agent** joins the row under **(9)** and is re-scoped by **(12)** (`amendment_r31`): the honest cross-window property is a **LAG**, never an absolute freeze — proven as a single-scan staircase (the removed subject's `last_scanned_at` byte-identical across the paired scan while same-machine controls advance) with the column's writer set named from source, and any absolute-freeze claim is a FAIL that this body does not make. **POSTURE — the head no longer behaves the way `amendment_r30` described, and the plan says so.** `spec_interpretations` **(15)** / `amendment_r50` supersedes r30's F1 anchor **and** its part-2 observable: upstream `main` made the instance-write path **diff-guarded and counted** (`issue_repository.py:1316-1329` — `evidence_differs` → `has_evidence_write` → `should_reopen_or_refresh`, which *"deliberately skips rows that are OPEN with nothing new to write"*), so the per-scan `updated_at` re-touch r30 measured on the frozen base is **retired by design**. The contracted observable at head is therefore **STILL-OPEN / RE-EVALUATED / DIFF-GUARDED-FROZEN, with the no-op counter as the proof** (`outcome="unchanged"`), on a **runtime-identity-pinned** worker, anchored on **PR-diff-vs-merge-base = 0** across the eight pathspecs plus the residual report against `origin/main` plus the `writers.py` symbol clause. What has **not** changed is the user-visible defect: an issue whose evidence is a deleted file still renders Open with that content as live Evidence. It is ticketed on **[PRDCT-12071](https://app.clickup.com/t/86bbj56qh)**, it is not presented here as stale-handling, as resolved, or as acceptable, and it is bound to PRDCT-12069 by a shared root cause — no scanner-lane writer sets `assets.is_deleted`, the gate on the one absence-adjacent close hook (`unlink_deleted_assets_from_issues`). Closing on absence inside this PR was rejected for the reason the posture plane documents about itself: *"Closing on that signal silently auto-resolves real customer findings every time the LLM has a hiccup"*. Evidence: [`at7-09-db-rows-posture.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-09-db-rows-posture.txt), [`at7-47-posture-path-identity.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-47-posture-path-identity.txt), and research's re-adjudication captures under `evidence/r50-posture/`. **⚠️ ENTRY (11) SUPERSESSION NOTE — attached inline, as `amendment_r50` requires (at10 check (t)):** wherever this ledger quotes or relies on `spec_interpretations` entry **(11)**, read it with **(15)** attached. Superseded are its **F1 anchor**, its **part-2 observable**, its mechanism sentence (*"ACTIVELY RE-AFFIRMS them Open on every scan"* via the always-refresh branch — accurate for the frozen base `67b4096f`, replaced at head by the diff-guard above) and **every frozen-base line number inside r30's text** (historical; the head cites live in `amendment_r50` alone). Entry (11) itself stays byte-untouched as a frozen record. The same attachment applies to entries **(8)** and **(9)** for the POSTURE class only — the usage cell is unaffected. |
| **C2 usage sessions** (`d-c2-fid-usage`, `d-c2-ui-usage`) | **DELIVERED, and the UI half is now proven on the right surface.** The rows were always real — session **2396**, `external_id 20260821_033142_faf0bc`, written by the head-exact writer with the machine's own session id — the session the embedded capture and `at7-23` actually carry. The UI half failed for rounds because it was probed on `/ai-assets/usage`, which the plan owner has since identified as the inventory-**application** detail tree (`d-c2-ui-usage.amendment_r24`; the plan is now frozen at `sha256 e4943218…` *(superseded)*); nothing was narrowed, the route was corrected. On `/ai-activity?activitySessionId=2396` the per-session panel renders `#2396`, `Hermes Agent (coder)`, the session's own conversation and its Asset Details. Evidence `at7-40`, capture `at7-14` (with `at7-39` the round-24 `#1389` capture of the same surface). |
| **C2 / C11 / C13 proof legs** (rows, replay, both-lane diff, per-class UI) | **delivered.** (Round-32 correction, gate G1: this cell used to read "with ONE exception rowed above (posture: bridge-ran/no-issue, the plan's own pre-declared fallback)" — the very disposition the C2-posture row above withdraws as refuted by [`evidence/at7-09-db-rows-posture.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-09-db-rows-posture.txt). The reconciliation carried two mutually exclusive dispositions for one class, in the direction that hides a user-visible defect. There is now one, and it is the `amendment_r30` defect framing in that row.) The usage-sessions exception that used to sit here is withdrawn — the class is proven. |
| **D1** fairness | **deferred, by the ticket's own sanction** — the Azure lane ships without per-tenant fairness, the same deviation AWS M1 shipped with. Service Bus Sessions is the counterpart; the design belongs to PRDCT-9711. Stated in `docs/architecture/services.md`. Note `fair_ingest_intake` is an infrastructure-repo module, not app code (interpretation 6) |
| **D2** monitoring | **delivered (doc), monitors deferred** — `docs/monitoring/endpoint-asset-ingestion-alerts.md` gains the Azure half: three of the four alerts are app-metric-based and apply unchanged; the DLQ alert's Azure equivalent is the Service Bus queue's `DeadletteredMessages`. Arming goes through Litterbox, never hand-written YAML, and cannot be armed until the lane reconciles onto a cell (no data to derive a threshold from) |
| **D3** cloud-aware flags **or** boot assertion | **delivered** — the assertion; ADR [`docs/decisions/0069-the-declared-cloud-decides-the-ingestion-transport.md`](docs/decisions/0069-the-declared-cloud-decides-the-ingestion-transport.md) says why |
| **D4** gen-2 ASB branch fate | **delivered** — deleted in both named services, with the reason recorded |
| **Prod apply / rollout** | **deferred — human-gated.** This run applies nothing to production Azure and rolls out no flux change itself. The two siblings are **no longer in the same state, and this row used to claim they were**: **infrastructure#1575 is MERGED** (2026-08-23T12:18:07Z, head `da993d1ae2eb`) — so the Terraform half is on `main` and whoever runs the apply owns it from here — while **flux-fleet#2307 is still OPEN** at `a4493c1e5ac0`, parked on its CODEOWNERS `approval-gate`. Merging that one is a **live cutover**, not a dark deploy — see the **Deploy safety** row above; the infrastructure change also carries `moved` blocks whose state move should be confirmed by a real `terraform plan` on the centerpoint data plane before apply |

**Plan revision this PR is written against:** `test_plan.json` @ `sha256 973b3cfa916fa7122561aa3d65739bf6db469ab341eb52b52288496e7dad69a5` — re-emitted in **round 50** to record the re-adjudication of `d-c2-lc-posture` (`spec_interpretations` **(15)** / `amendment_r50`), and matching the sidecar `test_plan.sha256` as this body is written. It supersedes `863dbd105e74…` (round 49, the deploy-safety adjudication) and, before it, the round-36 re-freeze that reconciled the cutover flip-sequence cite to `feature_flags/consts.py:212-216` — the value the head actually holds — after the plan had carried `:202-207` in one field and `:212-216` in others.
**This is the only plan sha this body states as current.** Earlier rounds left two different values standing in
two places, which made it impossible to tell which revision the run had been graded against; the body now
carries exactly one, and `/tmp/prdct11935/audit.py` FAILS the gate if it stops matching `test_plan.sha256`.

**Corrections to the ticket's own text, surfaced rather than silently applied:**

*Plan/PR cite parity (round 33).* The plan owner re-emitted `test_plan.json` under an
orchestrator-authorized refresh of **twelve drifted `file:line` cites** (S1–S12), with an append-only
**CORRECTION LOG** on each frozen record it could not edit
in place ([owner-veto post](https://onyx-security.slack.com/archives/C0BCW4JDZB2/p1787353409866929?thread_ts=1787063683.640599&cid=C0BCW4JDZB2)). **Zero semantic changes** — every mechanism the plan names still
exists and behaves as described; only line numbers moved. This PR mirrors that refresh so the two documents
cannot fork, and the mirror is recorded in **[`evidence/at10-07-stale-cite-refresh.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-07-stale-cite-refresh.txt)**, which re-reads
each corrected line with `sed` at HEAD rather than taking the plan's word for it.

What the mirror actually required, stated plainly: research's own note anticipated that this body's ledger
rows carried the literal `consts.py:202-207` wording, and the round-33 task was written on that
expectation. Measured first — **this body carries none of the twelve stale tokens**, in any form (a
fixed-string sweep for all seventeen old literals plus a loose sweep for the bare line numbers returns
zero; the body cites `consts.py` in exactly one place — the footgun-1 residual row's flip-sequence cite,
added in round 36 at the CORRECTED `:212-216`, never at a stale value); those rows were rewritten in rounds 31–32 for
unrelated reasons and no longer quote line numbers. So no value here was changed, and none was invented to
make the task look done. Where the drift *had* reached the PR side is the evidence set — three of the
twelve (S3, S10, S12) — and those are mirrored, each artifact carrying its own old→new note. Two
occurrences are deliberately left: one sits inside a **verbatim ClickUp fetch** (rewriting it would forge
the receipt — the live ticket is what needs updating), and one is a verifier-authored file.

*All **fifteen** `spec_interpretations` entries in `test_plan.json` are carried here as owner-visible items, so
every scope narrowing is a decision the ticket owner can see and veto. Where each lives (round 31 raised the
count from eleven to thirteen; round 49 added **(14)**, the deploy-safety correction; round 50 added **(15)**,
the posture re-adjudication):*

| `spec_interpretations` | what it rules | carried in this body at |
|---|---|---|
| (1) | the C2-path Azure-chain reading | correction 1 below |
| (2) | the `storage.tf` "zero callers" correction | correction 2 below |
| (3) | the `release.yaml` 64-72 re-scope | correction 3 below (withdrawn/superseded), and correction 10 |
| (4) | `BlobStorageClient` already satisfies `ObjectStore` | correction 4 below |
| (5) | the `byoc_events` third-subscription correction | correction 5 below |
| (6) | `fair_ingest_intake` is an infrastructure module | correction 6 below |
| (7) | the round-21 `d-c13-3` residual-loss amendment | correction 14 below + the **L-2** ledger row |
| (8) | the round-26 C2-clause-5 lifecycle adjudication | the **C2-LC** ledger row |
| (9) | the round-28 desktop-agent lifecycle adjudication | the **C2-LC** ledger row |
| (10) | the round-29 LD-mechanism adjudication | correction 13 below |
| (11) | the round-30 posture lifecycle adjudication | the **C2-LC** ledger row + its entry-(11) supersession note |
| **(12)** | **the round-31 agent-freshness LAG re-scope** (`d-c2-lc-agent.amendment_r31`) | the **C2-LC** ledger row — "THE AGENT CLASS'S FRESHNESS TERM IS RE-SCOPED IN ROUND 31" |
| **(13)** | **the round-31 deliverable-C OVERTAKEN adjudication** (`d-c3comment-{saas,centerpoint}.amendment_r31`) | correction 10 below |
| **(14)** | **the round-49 deploy-safety correction** of deliverable C's *"dark/dormant (intuit precedent)"* framing | the **Deploy safety** row of this ledger (immediately below the **C** row), and the ⚠️ box at the top of flux-fleet#2307 |
| **(15)** | **the round-50 re-adjudication of `d-c2-lc-posture`** — `amendment_r50` supersedes `amendment_r30`'s F1 anchor and part-2 observable, because upstream `main` made the instance-write path diff-guarded and counted, retiring the per-scan `updated_at` re-touch **by design**; the observable is now STILL-OPEN / RE-EVALUATED / DIFF-GUARDED-FROZEN with the counter as proof | the **C2-LC** ledger row's posture half + the at7 posture captures |

1. C2 clause 2 names the production ingest path as "Kong → S3 → SQS → workflows → tenant DB" — the AWS shape —
   while this ticket's whole subject is the Azure lane, which has no S3 or SQS and is off Temporal. Read as
   descriptive (the rule's own "any environment running the real path counts"), the proof rides
   Kong → Blob → Event Grid → Service Bus → writer → tenant DB. Flagged for the owner: if the literal AWS path
   was intended, that half of the proof is mis-scoped.
2. "`storage.tf` … has zero callers" is not accurate: centerpoint's data plane already instantiates that
   pattern with the real topic id. The real gap was that nothing routed scanner blobs *past* the topic.
3. **WITHDRAWN (round 29).** This entry used to say the stale comment lives at flux-fleet
   `release.yaml:60-62` (the ticket cited 64-66) and quote its clause. That is false at head and it
   contradicted correction 10 in this same list. Measured: **both** Azure c02 instance `release.yaml` files
   contain **zero** lines with `#`, and an org-wide code search for the quoted clause returns **zero** hits —
   `main`'s PRDCT-4368 (#2334) deleted all 611 comment lines across the eight instance override files. The
   substance that remains true is exactly what correction 10 already says, so it is said once, there, rather
   than twice and inconsistently: the ticket's "fix the stale comment" sub-item is **OVERTAKEN by `main`**,
   and the knowledge moved to `docs/architecture/instance-override-rules.md`. The only fact worth keeping
   from the old wording — that the asset and gateway overlays *are* patched into the Azure build, and only
   the swg overlay (and separately sensor-service) is excluded — is verified in each instance's
   kustomization and is retained in correction 10's disposition.
4. "Make `BlobStorageClient` satisfy the `ObjectStore` protocol" — it already does (`get_object_bytes`), so A3
   narrowed to the factory wiring, proven by a real blob read through it.
5. `byoc_events` has a **third** subscription the ticket omits (`only-sensor-events`); the new rule must not —
   and does not — collide with it, proven in both directions.
6. The ticket's fairness discussion implies `fair_ingest_intake` is app code; it is an infrastructure-repo
   module, and the deviation is ledgered there.
7. **Correction, and then a correction to the correction.** An earlier note here said re-ingest skip is
   *not* a both-lane class, on the grounds that the Go lane has no content-hash skip of its own — it
   computes and forwards a digest so the Python consumer can skip. That distinction is real and it is why
   gen-1's counterpart is "always re-runs the cascade" ([`at6-01-inventory.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-01-inventory.txt)). But the flat claim
   contradicted this run's own evidence: `at6-04c` captures a re-ingest-skip leg driven through **both**
   lanes on the same payload, and the ledger walks the same ground. The accurate statement is the narrow
   one: **re-ingest skip is driven as a both-lane leg** (both tenants receive the same re-ingest and are
   diffed), while the *skip decision itself* exists only on the new lane. The class stays in the
   both-lane set; only the mechanism is one-sided.
8. **Demand A4 was overtaken by `main` while this branch was open, and is re-resolved rather than merged
   around.** A4 reads "write the missing Event Grid parser", and it was accurate when this branch cut. `main`
   commit `1f532d51f1` (PRDCT-11410) then landed `blob_event.py` — the same parser, for the sensor lane. The
   demand is now *consume the platform's parser*, not *write a second one*: `eventgrid_event.py` is deleted,
   this lane reads `parse_blob_event_message`, and the settlement split that was the local parser's reason to
   exist moved into the consumer. Recorded here because the ledger could not carry it before: it became true
   only after the merge-base moved.
9. **The usage-sessions class is PROVEN — on the surface that actually carries it, after the plan owner
   corrected the route.** Earlier rounds probed `/ai-assets/usage` and failed, and this note used to
   escalate the class as unproven. The plan owner adjudicated why
   (`d-c2-ui-usage.amendment_r24`, posted for veto on [the run thread](https://onyx-security.slack.com/archives/C0BCW4JDZB2/p1787275147227579?thread_ts=1787063683.640599&cid=C0BCW4JDZB2)): that route is the
   inventory-**application** detail tree — its bare route 404s by design and `$appId` takes an inventory
   application id — so passing a session id or an asset id to it was a category error, and the free-text
   search covers employee name/email and prompt content, never a machine session id. **Nothing was
   narrowed**: the per-class UI demand stands in full, on the route that renders a session.
   That route is **`/ai-activity`**, whose per-session panel opens via `activitySessionId`. Driven at
   head on this run's own ingested session — `usage_sessions` id **1389**, `external_id`
   `20260821_002214_f12ead`, written by the head-exact writer inside the round-24 attribution window —
   the panel renders **#1389**, `Hermes Agent (coder)`, the session's own prompt/response conversation
   (token `[REDACTED]` by the product's sanitization), and Asset Details *Hermes Agent (coder) / Endpoint
   AI Agent*. Evidence: [`evidence/at7-40-usage-ai-activity.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-40-usage-ai-activity.txt), captures `at7-38`/`at7-39`.

10. **Item C's "fix the stale comment" sub-item is OVERTAKEN-BY-UPSTREAM for BOTH Azure instances, and delivered its way instead.**
   **Formalised in round 31** (`d-c3comment-saas.amendment_r31` and `d-c3comment-centerpoint.amendment_r31`,
   posted for owner veto — [the round-31 run-thread post](https://onyx-security.slack.com/archives/C0BCW4JDZB2/p1787333760193809?thread_ts=1787063683.640599&cid=C0BCW4JDZB2), receipt [`evidence/research-r31-veto-permalink.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/research-r31-veto-permalink.txt)).
   The round-28 gate was right that this was the one overtaken class in the run carrying no formal amendment; it has one now,
   and [`evidence/at8-04-comment-fix.diff`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-04-comment-fix.diff) is re-emitted to its spec with a **per-instance, error-checked** table.
   Measured for `ox-az-p-eus2-c02/instances/{saas,centerpoint}/onyx-app/release.yaml` at three refs — the flux-fleet
   merge-base with `origin/main` (the repo's effective frozen base, since flux-fleet carries no
   `factory-eval-base` ref), `68bdecfd1e70`, and this branch's head — **comment lines 0 and stale-clause hits 0
   at every ref for both instances**. Re-measured against the CURRENT flux head `a4493c1e5ac0` as this body is written
   (the ref this clause used to pin, `b0d3e1cfbfea`, is 131 commits behind it): `git show <ref>:clusters/ox-az-p-eus2-c02/instances/{saas,centerpoint}/onyx-app/release.yaml | grep -c '^\s*#'` returns **0 for both instances at the current head**, and at the merge-base `2c8ad2f2d4` and at `68bdecfd1e70` too, so the conclusion holds at the sha the reviewer will actually see, with the upstream commit's own `diff --stat` showing **112 deletions per instance**.
   The generator runs `git cat-file -e <ref>:<path>` first and prints an explicit ERROR row rather than a zero if a path
   does not resolve, because the amendment records that an earlier base check was a false pass by construction — a failed
   `git show` swallowed by `grep -c` against a ref that does not exist. And requirement (iii) holds: this branch adds
   **zero** comment lines back into either override file.
   `main`'s PRDCT-4368 (#2334) — flux-fleet commit **`6964ee876`** — removed **all 611 comment lines** from the eight instance override files and
   moved the knowledge they carried to `docs/architecture/instance-override-rules.md`. The ticket asked to fix
   a stale comment at `release.yaml:64-66`; that comment no longer exists, and adding a corrected one would
   now violate the convention `main` just established. Delivered as the convention requires: the files carry
   values only, and the three traps this lane's comment carried — bind the lane's OWN published keys, not the
   shared namespace; those keys publish CONDITIONALLY and Flux renders an unprovided `${...}` as the empty
   string so the failure lands at the pod rather than the render (apply infrastructure first); and why the s3
   leaf is blanked in `release.yaml` rather than in `drop-aws-only-values.yaml` — are recorded in that doc's
   `ox-az-p-eus2-c02` section.
11. **Item C names TWO AWS-only leaves and only one had a status here.** The ticket says add-null entries for
   `asset_ingestion_sqs` **and** `asset_ingestion_s3`; the reconciliation named only the first. Both are
   handled, by deliberately different mechanisms, and both are verified in the re-rendered
   `at8-01`/`at8-02`: `asset_ingestion_sqs` is removed by `drop-aws-only-values.yaml`, while
   `asset_ingestion_s3` is **blanked in `release.yaml` instead** — removing a key from `spec.values` does not
   stop the chart's default reappearing, and that default is a live `aws_region: us-east-1`; because the drop
   file is patched *after* `release.yaml`, a remove there would delete the blanks set here. Rendered result on
   both instances, re-rendered this round and read out of the **final ConfigMap** rather than out of
   `spec.values`: `asset_ingestion_s3: {aws_region: "", endpoint: ""}` and `asset_ingestion_sqs` present as
   the chart's all-blank stanza (`queue_url: ""`, `dlq_url: ""`, `aws_region: ""`, `endpoint: ""`,
   `visibility_timeout: 600`, `wait_time_seconds: 20`), with `us-east-1` occurrences **0** in the lane's block.
   **ROUND-32 CORRECTION (gate G3):** this row used to claim the rendered result was `asset_ingestion_sqs:
   null`. That was wrong twice over. The key is *absent* from `spec.values` — the earlier `yq` printed
   `null` only because it queried a key that is not there (`has("asset_ingestion_sqs")` is `false`) — and
   the shipped ConfigMap then carries the chart default, which is the blank stanza above, not a null. Worse,
   the state it described is one **the real service refuses to boot on**, which is precisely why
   `drop-aws-only-values.yaml` uses `op: remove` here instead of `add … value: null`. Proven rather than
   argued: the head image `:prdct11935-r26` was booted twice from the live ConfigMap, once with each shape —
   the blank stanza reached `Application startup complete` and started its consumer pool, while the `null`
   shape died with `pydantic_core.ValidationError … asset_ingestion_sqs — Input should be a valid dictionary
   or instance of AssetIngestionSQSConfig [input_value=None]` and `Application startup failed. Exiting.`
   Receipt: [`evidence/at8-05-render-and-boot.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at8-05-render-and-boot.txt).
12. **The Azure alert-producer half — one cause fixed elsewhere, one fix NO LONGER IN THIS PR, and this
   item used to claim both.** The measurement that opened it stands: on the pre-fix pod the fan-out failed
   100% of the time — 65 swallowed *"failed to publish one session alert-processing request (continuing)"*
   with the alert queue empty after every drive, and **1042** `'NoneType' object has no attribute
   'create_sender_link'` underneath. Two causes were found. What ships is not what this item said:
   **(a) the coroutine-safety fix is NOT in this PR.** One `ServiceBusSender` is shared across concurrent
   object tasks and the SDK's sender is not coroutine-safe. This PR did serialise the sends; **owner ruling
   #2 (round 46) then took the queue-layer work out** — *"REMOVE FROM THIS PR ENTIRELY … the
   `abandon_message` method you added to `asb.py` (KEEP `_system_properties` — main does not have it)"* —
   and reducing `asb.py` to that one addition removed the serialisation with it. At head:
   `grep -rn '_send_lock' backend_python/src backend` → **0**, the whole `asb.py` diff is **25 insertions**
   that are `_system_properties()` and its two call sites, and `origin/main` carries no sender lock either.
   The two tests this item used to cite — `test_asb_sender_concurrency.py`,
   `test_session_alert_failure_is_metered.py` — **do not exist** (`git ls-files` → 0 each). So the hazard is
   **untreated in the shipped diff**; it has also not recurred (`kubectl logs deploy/eai-azure --since=24h`
   → **0** sender crashes and **0** publish failures on real traffic). It is not re-added here, because the
   owner's ruling removed it and told this run not to re-merge the two designs, and no demand in the frozen
   plan covers the fan-out — it is **tracked instead**, with the measurement, on PRDCT-12061 beside the other
   reverted items — re-fetched live afterwards, element by element, in [`at10-27-tracker-r6-fetch.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-27-tracker-r6-fetch.txt). Full re-measurement: [`at10-26-alert-sender-hazard.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at10-26-alert-sender-hazard.txt).
   **(b) the missing grant is real, and it has merged.** `amqp:unauthorized-access — 'Send' claim(s) are
   required`: the workload identity held Data Receiver on its own ingestion queue and a Blob role on
   storage, but nothing on the alert-processing queue, so the lane as authored could never publish. The
   queue-scoped `Azure Service Bus Data Sender` grant rides onyxsecurity/infrastructure#1575, **merged
   2026-08-23T12:18:07Z**.
   **And the metering sentence was wrong too:** this item said *"both lanes now count `publish_failed`"*. At
   head the **scanner** lane meters only `published` (`writers.py:648`) and `skipped_no_queue` (`:650`);
   `publish_failed` is emitted on the **gateway** lane alone (`gateway_writers.py:420`). A scanner-lane
   producer failing every time still moves no failure counter — the ticket's own footgun-2 shape, now stated
   rather than claimed closed.

13. **ADMIN-GATED RESIDUAL — the LaunchDarkly scoping writes footgun 1's two legs would use literally.**
   This is the row `d-fg1.amendment_r29` requires, and every one of its four conditions was re-captured
   **this round** rather than inherited ([`evidence/at1-10-ld-conditions-r29.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-10-ld-conditions-r29.txt), [`at1-06-flagoff-guard.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-06-flagoff-guard.txt)).
   *The behavioural bar is met in full and is not what is gated:* **LEG A** — the pod reads
   `endpoint-asset-ingestion` in **both** directions through a live streaming server-SDK connection to the
   real dev project (`stream_base_uri https://stream.launchdarkly.com`, `offline false`, `use_ldd false`,
   no data-source override): TRUE with reason **`RULE_MATCH` ruleId `6a17f975-…`** → objects processed, and
   FALSE with reason **`FALLTHROUGH`** → **29 × `outcome=skipped_flag_off`**, 0 processed, and the tenant's
   row counts **byte-identical** across the leg (383/256/62/295/185 before and after). Both evaluations
   present the guard tenant's real key and attributes — only the non-tenant `service_identity` differs, which
   the amendment expressly permits — and a **same-window direct LD API read predicts both reasons** from the
   flag's own targeting state. **LEG B** — with the old lane demonstrably off (**zero**
   `ScannerTenantWorkflow`, **zero** `ScannerObjectWorkflow`, **zero** `ScannerCollectorWorkflow` executions
   in the window, raw listing showing only column headers) a fresh Kong-originated scan **still landed**
   through the new lane (asset `203618`, written by the azure consumer's own `outcome=processed` line). No
   ingestion gap.
   *The flip sequence these writes implement, cited at source.* The **CUTOVER ORDERING CONTRACT** is
   `backend_python/src/common_core/services/feature_flags/consts.py:212-216`, re-read with `sed` at this head
   before citing it and captured in **[`evidence/at1-11-cutover-flip-sequence-r36.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-11-cutover-flip-sequence-r36.txt)** so the cite is checkable
   without trusting either the plan or this body: turn the NEW lane ON **before** turning the OLD lane OFF — `endpoint-asset-ingestion=True`
   FIRST, then `scanner-event-driven-ingestion=False`; **both OFF at once = a window of DROPPED objects**
   (neither lane ingests); and `scannerScheduleDisabled` must ALREADY be ON for the tenant before the flip so
   the scheduled `ScannerTenantWorkflow` sweep is not double-ingesting during it. The three literal writes
   below are exactly that sequence. (Round-36 note: the plan carried this cite as `:202-207` in one field and
   `:212-216` in others; research re-grepped the file and reconciled the plan to `:212-216`, which is what the
   head actually holds — the block moved down by unrelated insertions above it. The ticket description's own
   `:202-207` stays verbatim wherever it is quoted, by rule.)
   *What IS gated is only the LD-side scoping mechanism,* and it was re-attempted this round, not assumed:
   all three literal writes — pinning the guard tenant to `endpoint-asset-ingestion`'s FALSE variation
   `a96fbf33-…`, `scannerScheduleDisabled` ON for the tenant, `scanner-event-driven-ingestion` FALSE for the
   tenant — were driven through the sanctioned ld-router and **refused 6/6 with verbatim HTTP 403
   `context_scope_violation`** and `x-ld-router-outbound-calls: 0`; `coder-agent@onyx.security` is still LD
   **`reader`** with no custom roles; and `agent_key` — the router's only permitted attribute — still returns
   **zero hits** across shipped Python and Go at this head. Escalated with the exact payloads:
   [the DM](https://onyx-security.slack.com/archives/D0B6V65HCEN/p1787221420557539), [the run-thread
   mirror](https://onyx-security.slack.com/archives/C0BCW4JDZB2/p1787063683640599?thread_ts=1787063683.640599)
   and [the round-29 veto post](https://onyx-security.slack.com/archives/C0BCW4JDZB2/p1787315264578359?thread_ts=1787063683.640599&cid=C0BCW4JDZB2)
   carrying the third payload. **An LD admin applying any one of them makes the literal form drivable and it
   should then be driven.**
   *One finding this run reports rather than resolves.* The amendment's condition 4 says an applied
   rule/target for this run's tenant or identity makes the literal form drivable. This round's read found
   applied state on two flags — `endpoint-asset-ingestion`'s `service_identity` rule (applied
   2026-08-19 by a human admin) and a `tenantUUID` contextTarget on `scanner-event-driven-ingestion` — but
   **both serve the TRUE variation, the opposite direction from the literal FALSE forms**, and the writes
   that would produce those forms were refused above. Read to the letter, condition 4 keys on the existence
   of applied state rather than its direction. That is a contract question and this PR does not answer it:
   it is surfaced here and in `at1-06` §CONDITION 4 for the plan owner.
14. **at6's direction rule: one of the three residual losses is closed here, one is measured away, and one
   is STOPPED with the reason.** The rule is absolute — *"the new lane may add, it may never lose what the
   old lane writes"* — and a ledgered loss is still a loss. Re-measured this round on **fresh tenants**
   (both truncated to empty, then ONE Kong-originated payload fanned out to both lanes, `at6-09`), the loss
   list collapses from the six rows and eight edges the accumulated tenants showed to **5 rows and zero
   edges**: the round-15 flag-off probe skill and the two `McpToMcp` self-edges were artifacts of reusing
   the tenants, which is exactly what "fresh tenant each" exists to expose. What remains:
   - **L-4 — FIXED.** The extension-provenance descriptor. The scanner carries no per-server
     `extensionName`; the MCPB marker is in `scannerSupplied`. The Go derivation
     (`extractor.go:349 extensionNameFromMCPBServer`) is now mirrored in `extract.py`, same candidate order,
     same blank-skipping rule. It moves no identity, no row and no edge — only a descriptor — so it carries
     none of L-2's blast radius. Three unit tests; not re-observed live because the bundle that carried the
     edge was uninstalled by an earlier lifecycle leg, and that is stated rather than glossed.
   - **L-3 — measured, and the ledger's own named fix was wrong.** *Both* lanes carry an
     `@playwright/mcp::unknown` row; the resolver is not timing out on this box (its counters show only
     cache hits, and registry egress is 0.08 s against a 0.4 s budget); and the exclusion the ledger names
     mirrors the **writer's** own `_scanner_app_id` gate, so dropping it would issue lookups the writer
     ignores — added hot-path latency for zero row change. Not done, with the measurements in `at6-08`.
   - **L-2 — STOPPED, and this is the identity re-key argument.** `app_definition_id` is
     `{package_name}::{serial}` on both sides, so the fix moves `bash::<serial>` → `<script>::<serial>`.
     The code that owns the identity states the rule and the failure mode: an identity move *"is only safe
     together with the migration that re-keys assets, app_definitions AND their access_control rows in the
     same change — never deployed ahead of it"*, because otherwise *"the guard then finds no rule and
     returns the tenant default, silently turning an enforced block into an allow"*
     (`mcp_asset_creation/activities.py:965-980`). It is also a **locked pair** — the gateway/policy mirror
     rebuilds that same key from the shared `mcp_package_cache` row (`mcp_client_info.py:172`) — and it
     splits one asset into N, orphaning the collapsed row. A transport-parity PR cannot carry that
     migration. Evidence and blast-radius measurements: `at6-08`. **Routed to research**, not re-scoped here.

## The product surfaces, as a user sees them

**Every capture in this section was re-taken on the shipped head `2b60fdc4df`, in one window
(`r50at7002800`, 2026-08-24 00:28–03:00Z).** The previous set was captured on `a2486bb33f` / image
`:prdct11935-r26` — *before* the round-45 revert removed writer capabilities those captures measured — so the
bundle was showing a writer that wrote more than this PR ships. Each PNG below is a real authenticated SPA
page: HTTP 200 asserted programmatically, this window's value asserted present in the DOM, the full surface
in frame with the asserted row outlined, and the browser runs recorded (webm + trace) at the pinned evidence
paths. Two self-checks ran over the set: `sha256sum $AGENT_FACTORY_ARTIFACTS/evidence/at7-*.png | awk '{print $1}' | sort | uniq -d`
is **empty** (an earlier pass produced three detail/list pairs that were byte-identical — one page state
saved under two names — and that was fixed, not explained away), and every capture carries its own
`state_fp` and `png_sha256` in the leg's results JSON.

The machine was given a real install to find: **Codex**, **Claude Code**, **Claude**, **Hermes Agent** and
**OpenClaw** — the last installed this window by `npm install -g openclaw` — an **MCP bundle packed by
Anthropic's own `mcpb` CLI** (`onyx-lab-r50at7002800` 1.0.0, five tools) plus a sibling control bundle, and a
skill and subagent definition written to disk with a sibling control each.

**Attribution, stated honestly.** The round-25 method was to record each table's max id *before* installing
and filter every later query on `id >` that mark. **That pre-install mark was never recorded for this
window**, so [`at7-00-isolation.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-00-isolation.txt) reconstructs all eight marks live
(`max(id) FILTER (WHERE created_at < '2026-08-24 00:28:00+00')`), says so in those words, and proves the
reconstruction sound by showing the id range between each mark and each first-in-window id is **empty**.
Attribution therefore leans on the unique marker names and the exhaustive per-class counts, which is what
that file now presents. It also discloses two things the old receipt would have hidden: the gen-1 collector
was **not** quiesced this window (it ran 132 times) and six writers were live — yet enumeration shows they
contributed **zero** rows to these class tables — and six non-at7 in-window rows (four skill assets from the sibling identity leg
from the sibling identity leg, and two issue instances on a pre-window asset) are named so the counts
reconcile with nothing unexplained.

**Desktop agent** — `OpenClaw (coder)`, asset **10729**, `desktop_agent_applications.id 105`, identity
`endpoint_openclaw::ec255301bd4407d309fbce94811384b0`. The fidelity value is the runtime's own version
string and `assets.version` holds it — `2026.5.7 (eeef486)`, the output of `openclaw --version`, read back in
[`at7-03-db-rows-agent.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-03-db-rows-agent.txt) and joined in [`at7-08-fidelity.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-08-fidelity.txt).

![OpenClaw (coder), asset 10729 — its own detail page on this build, name asserted visible, no Deleted badge](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-10b-ui-desktop-agent-detail.png)

**MCP servers** — asset **442199**, `mcpb:onyx-lab-r50at7002800::1.0.0`, `mcp_servers.id 19792`, display name
`Onyx Lab R50 MCP` — the bundle NAME and VERSION out of the the bundle manifest the packer produced, with the
sibling control at asset **442200** / `mcpb:onyx-sib-r50at7002800::1.0.0` ([`at7-04-db-rows-mcp.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-04-db-rows-mcp.txt)).
*(An earlier revision of this paragraph also claimed this is where residual loss **L-4 closes**, because the
lane wrote an `{"kind":"extension"}` provenance descriptor onto the edge. **That capability was reverted by
the round-45 owner ruling** — `_extension_name_from_mcpb` returns **0** hits at this head — so the claim is
withdrawn, and L-4 is an open residual again in [`at6-08-residual-losses.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-08-residual-losses.txt).)*

![the MCP bundle's detail page — asset 442199, mcpb:onyx-lab-r50at7002800::1.0.0, version 1.0.0](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-11-ui-mcp.png)

**MCP tools** — the manifest's `tools[]` array verbatim: `r50__echo`, `r50__hostname`, `r50__search`,
`r50__time`, `r50__verify`, written to the tenant `tools` table as ids **159-163** on asset 442199
(`type=ToolTypeMCPTool`, `is_active t`), with the sibling's `r50sib__ping` / `r50sib__stat` at **164-165** on
442200 ([`at7-09-db-rows-tools.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-09-db-rows-tools.txt)). The server's own detail page renders them:

![the MCP server's tools list — all five r50__* tools in frame, r50__verify outlined](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-19-ui-tools.png)

**Skill** — `r50at7002800-skill`, asset **441993**, `agent_skills 362069`. The product recomputes the
file's own sha256 as `skill_md_hash` — `3b3e94d234b2801e…e7d5f1e8`, matched byte for byte against
the on-disk `sha256sum` of that skill file ([`at7-05-db-rows-skills.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-05-db-rows-skills.txt)):

![skill detail — r50at7002800-skill, asset 441993](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-12-ui-skills.png)

**Subagent** — `r50at7002800-sub`, asset **442189**, `agent_subagents 52911`. Here the identity *is* the
hash: `subagent_md_hash` and `assets.unique_identifier` are both the file's own sha256
`2d2e397434cc739a…6c11ed26` ([`at7-06-db-rows-subagents.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-06-db-rows-subagents.txt)):

![subagent detail — r50at7002800-sub, asset 442189](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-13-ui-subagents.png)

**Usage sessions** — session **7555**, `external_id 20260824_002925_7185b3`, app 55751 (`Hermes Agent
(coder)`), `has_content_events t`. That external id is verbatim what the `hermes` CLI printed at the end of
the real chat this window ([`at7-07-db-rows-usage.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-07-db-rows-usage.txt)). The route question is settled by the plan's own
round-24 surface correction: `/ai-assets/usage` is the inventory-**application** detail tree, not a session
surface, so the class's real per-session surface is `/ai-activity`, deep-linked by that DB id:

![the /ai-activity per-session panel for this window's own session #7555, session id and acting agent in frame](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-14-ui-usage.png)

**Posture** — the class mints issues, and the head's behaviour is the one `amendment_r50` describes.
![/posture-issues, pre-removal, this window's subject in the list](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-20-ui-posture.png)

### Lifecycle — a real removal, a real uninstall, then real scans

The MCP bundle and its settings entry were removed, the skill directory and the subagent file deleted, and
`npm uninstall -g openclaw` took a whole runtime off the machine. The scanner's own summary moves with the
machine, and the subject is proven absent on-box three ways inside the same capture — the resolver
(`command -v openclaw` → not found, `npm ls -g` empty), the filesystem, and **the scanner's own detector
inside the paired scan's payload** (`{"detector":"openclaw","outcome":"not_installed","instances":[]}`).

**Desktop agent — the `amendment_r31` staircase, on one paired scan** (`scan_run_id
ff9536af-8edb-49cc-9039-64906c9338d5`, 01:22:47–01:23:58Z, real, through Kong), from
[`at7-30-agent-lifecycle-control.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-30-agent-lifecycle-control.txt):

| asset | runtime | `last_scanned_at` before | after | advanced? |
|---|---|---|---|---|
| 10727 | Codex | `00:32:03.550773+00` | `01:24:15.760806+00` | yes — control 1 |
| 23 | Claude Code | `00:32:03.475438+00` | `01:24:14.255375+00` | yes — control 2 |
| 55751 | Hermes Agent (coder) | `00:30:07.674692+00` | `01:23:15.877409+00` | yes — control 3 |
| 10656 | Claude (coder) | `00:30:07.578030+00` | `01:23:15.333524+00` | yes — control 4 |
| **10729** | **OpenClaw (coder) — SUBJECT** | `00:32:03.449330+00` | `00:32:03.449330+00` | **no — byte-identical** |

The scan's own agent list is `["claude-code","claude","codex","hermes-agent"]` — exactly the four that
advanced, and the subject is not in it. Carried as measured, not asserted: `status` is `''` (the value the
row actually holds) and `is_deleted` is `f`, both unchanged. **This is a LAG, never an absolute freeze** —
the column's writers are named and evidenced in [`at7-48-lastscanned-writer.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-48-lastscanned-writer.txt).

**And one part of this class is NOT met on this build, stated rather than smoothed.** `amendment_r28` part 3
asks for the freshness contrast *rendered*, subject beside control. The route the plan names
(`/ai-assets/desktop-agents/group/<id>`) **404s on this build** — an earlier pass captured those 404 pages
without noticing, which is exactly the kind of thing this section exists to catch. The captures below are the
working surface (`/ai-assets/desktop-agents/<assetId>`, HTTP 200, names asserted visible, no Deleted badge),
**but that surface renders no "Last Seen" field at all** (DOM read: `<Last Seen not rendered>` on both), and
`grep last_scanned_at frontend/` returns **0**. So the DB half of the cell is settled and the **render half is
not**; [`at7-23-attestations.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-23-attestations.txt) records it as `DB HALF SETTLED · RENDER HALF NOT SETTLED` rather than
claiming the cell.

![the uninstalled subject's detail surface after the paired scan — asset 10729, HTTP 200, no Deleted badge](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-21-ui-lifecycle-agent.png)
![the still-installed control's identical surface — asset 10727, same build, same assertions](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-21b-ui-lifecycle-agent-control.png)

**MCP server, skill, subagent — the `amendment_r26` classes.** After the removal and the second scan: not
resurrected, not duplicated, and **not refreshed** — one asset row per artifact identity, per-`unique_identifier`
counts all 1, `updated_at` unchanged, and the removed server's tools neither deactivated nor deleted
([`at7-41-lifecycle-head.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-41-lifecycle-head.txt), [`at7-18-lifecycle-db.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-18-lifecycle-db.txt)). The product has no stale/deleted vocabulary
for these classes — its only lifecycle badge is gated on `is_deleted`, which no scanner-lane writer sets — so
the renders below are captioned in the surface's own vocabulary and never as a "stale" state the product
cannot represent:

![the removed MCP server after the second scan: still rendered, not duplicated, no Deleted badge](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-15-ui-lifecycle-mcp.png)
![the same page with the tools list in-frame — the removed server's tools, is_active unchanged](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-19b-ui-lifecycle-tools.png)
![skill detail after the file was deleted and a second scan ran](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-16-ui-lifecycle-skills.png)
![subagent detail after the file was deleted and a second scan ran](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-17-ui-lifecycle-subagents.png)

**Posture — `amendment_r50`, measured on an identity-pinned worker.** The subject skill
`r50at7002800-posture` (assets 447772 / 448472) was really removed at 02:05:14Z. Across **three consecutive
covered post-removal front-door scans**, its seven issue instances — 6721, 6722, 6725, 6726, 6729, 6732, 6733
— stayed **byte-frozen**: `resolve_state IssueInstanceResolveStateOpen`, `closed_at NULL`,
`updated_at 2026-08-24 01:44:50.117728+00` (equal to `created_at`), all five evidence-column md5s unchanged,
`asset_posture_findings.classified_at` frozen at `01:44:48.829425+00`. That is the head's **diff-guard**
(`issue_repository.py:1316-1329`) doing exactly what its own comment says — *"deliberately skips rows that are
OPEN with nothing new to write"* — and the no-op is **counted**: the tenant's `outcome="unchanged"` counter
rose **126,744 → 170,920** across the bracket while `created` moved only by the in-window control's four rows.
The worker that wrote them is byte-pinned to head (every `issue_detection/`, `repository/issues/` and
`posture/` file sha256-identical in-pod), the eight-pathspec PR-diff vs the merge-base is **0**, and the
residual against `origin/main` is **0** ([`at7-51-posture-reaffirm-headcode.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-51-posture-reaffirm-headcode.txt), [`at7-47-posture-path-identity.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-47-posture-path-identity.txt)).

**What has not changed is the defect**, and it is rendered here rather than described: the issue is still
**Open** and the deleted file's own line is still shown as live Evidence.

![/posture-issues after removal — Status Open, the deleted file's content rendered verbatim as live Evidence](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at7-22-ui-lifecycle-posture.png)

That is a user-visible wrong state, ticketed on **[PRDCT-12071](https://app.clickup.com/t/86bbj56qh)**, and
this PR does not present it as stale-handling, as resolved, or as acceptable.

## both blobs downloaded and grepped: the probe skill name + nonce2 are IN the blob bytes
   /tmp/prdct11935/r32/1787346443-65b77d7b-….log: setup-r32-at108-probe-20260821210231 (nonce2 x1)
   /tmp/prdct11935/r32/1787346497-653dda08-….log: (nonce2 x2)

## the azure-mode consumer settled BOTH through the real EG->ASB chain (deploy/eai-azure logs):
   2026-08-21T21:07:23.967963Z … s3_key='tenant=61750f27-…/1787346443-65b77d7b-…' … (blob fetched, mcp/skills extraction running)
   2026-08-21T21:07:24.039551Z [info] Skill asset upsert … func_name=bulk_upsert_skills … s3_key='tenant=61750f27-…/1787346443-…'  <- carries setup-r32-at108-probe
   2026-08-21T21:08:21.215518Z [info] asset_ingestion_record_handled … outcome=processed … s3_key='tenant=61750f27-…/1787346497-653dda08-…'
   2026-08-21T21:08:21.217079Z [info] Completed message … message_id=ef3fc818-70a7-4b96-bdfd-e0c1c741a218
   (zero dead-letter/poison in the window; the only 'error' strings are benign AMQP idle keep-alive
    resets logged at INFO.)
```

`asset_ingestion_record_handled … outcome=processed` is the settlement; `Completed message
message_id=ef3fc818-…` is the broker ack that follows it.

**at1 — and the rows that settlement produced, read back from the tenant.** *Round-43 correction: the
block here was the **round-20** capture (`lab-r20-head-20260820155354`, branch `f4b3e9dfb2`, image
`:prdct11935-r24`) and it was cut off on a bare column header — a different, older run than the settlement
it sat directly beneath. This is the read-back for the **same** r32/head run, three lines further down the
same artifact the settlement above is quoted from* ([`at1-08-config-provenance.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at1-08-config-provenance.txt)):

```
## tenant-DB readback (onyx_security.assets):
     id   |                 name                 |      type      |        status         |          updated_at
   -------+--------------------------------------+----------------+-----------------------+-------------------------------
   307936 | setup-r32-at108-probe-20260821210231 | AssetTypeSkill | AssetStatusDiscovered | 2026-08-21 21:04:11.857486+00
   308396 | setup-r32-at108-probe-20260821210231 | AssetTypeSkill | AssetStatusDiscovered | 2026-08-21 21:07:24.042434+00
   (row 308396 is the azure-lane write: its updated_at is 3ms after the consumer's bulk_upsert_skills
    line against the rendered sink's blob. Row 307936 is the parallel gen-1/AWS dual-write lane's
    earlier upsert from the same probe — both lanes live, per the run's parity design.)
```

Same tenant and same marker as the settlement above (`setup-r32-at108-probe-20260821210231`), and row
`308396`'s `updated_at` is 3 ms after the consumer's own `bulk_upsert_skills` line — so the rows are that
object's, not a neighbouring run's. Row `307936` is the parallel gen-1/AWS dual-write lane's earlier upsert
of the same probe, which is the run's parity design rather than a duplicate.

**at3 — the poison message received back from the queue's native `$DeadLetterQueue`** ([`at3-02-dlq-receive.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at3-02-dlq-receive.txt)):

```json

    $ python3 /tmp/prdct11935/r50/dlqrecv.py e9803f4a-42ee-4a49-a2ee-9b2d2e409e43
    {
     "message_id": "e9803f4a-42ee-4a49-a2ee-9b2d2e409e43",
     "dead_letter_reason": "no ingestible object in the message",
     "dead_letter_error_description": null,
     "delivery_count": 0,
     "label_aka_subject": "/blobServices/default/containers/ingestion",
     "enqueued_time_utc": "2026-08-23 21:32:33.144000+00:00",
     "body_event_id_marker": "r50-poison-213225",
     "body_client_request_id_marker": "r50-poison-213225",
     "body_subject": "/blobServices/default/containers/ingestion",
     "body_blob_url": "https://prdct11935st.blob.core.windows.net/ingestion",
     "body_event_type": "Microsoft.Storage.BlobCreated"
    }

=================== WHAT THIS PROVES, TERM BY TERM ===================
    · joined to at3-01 by message_id e9803f4a-42ee-4a49-a2ee-9b2d2e409e43 — the id the consumer's own
      line names as it parks the message
    · `dead_letter_reason` is the APPLICATION's own reason — "no ingestible object in the message" — not
      the broker's `MaxDeliveryCountExceeded`, so this is a deliberate park, not an exhausted retry
    · `delivery_count` 0: it was parked on its FIRST delivery, so it never looped
    · both body markers match what at3-01 sent, byte for byte
```

*Round-49 re-drive: the block that stood here was the round-32 capture, whose marker and message id no longer
exist on this head. This is the **dead-letter receive** from the round-49 re-drive on head `2b60fdc4df`, read
back out of the real `$DeadLetterQueue` with a peek-lock receive that settled nothing — both body markers
match what at3-01 sent, `dead_letter_reason` is the application's own reason rather than the broker's
`MaxDeliveryCountExceeded`, and `"delivery_count": 0` shows it was parked on first delivery and never looped*
([`at3-02-dlq-receive.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at3-02-dlq-receive.txt)).

**at6 — the side-by-side lane diff, `created` leg — UNTRUNCATED.** *Round-42 correction: this block was
previously "changed lines only" and was cut mid-token at `+Pla`. It is now the whole capture*
([`at6-04a-diff-created.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04a-diff-created.txt) — in the diff, a leading minus marks the gen-1 lane and a leading plus the new lane, on the
same scan bytes). The matched and reingest-skip legs are
[`at6-04b`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04b-diff-matched.txt) and
[`at6-04c`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04c-diff-reingest-skip.txt).

> **This block used to paste the whole 15 KB gen-1-vs-new-lane diff.** It is removed, and not for space:
> the round-45 owner ruling withdrew the C13 parity claim, and at6's guard is explicit that *any* claim in
> the PR body that gen-1 parity holds is a failure. A pasted gen-1-vs-new-lane row diff reads as exactly
> that claim. The measurement still exists — [`at6-04a-diff-created.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04a-diff-created.txt),
> captured 2026-08-21 — and the divergences it shows are enumerated on the tracker
> ([PRDCT-12061](https://app.clickup.com/t/86bbhqxe8) R-1..R-5). What this PR claims instead is the
> narrower thing it can prove: **the same writer, fed the same bytes, writes byte-identical rows on either
> transport** — re-measured on the shipped head for all three content classes, 0 changed lines each
> ([`at6-07`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-07-transport-equivalence.txt),
> [`at6-04b`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04b-diff-matched.txt),
> [`at6-04c`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04c-diff-reingest-skip.txt)).

### at6 — the per-class closure table, in the body

*Round-42: this was previously only in a PR comment and cited as two `evidence/…` files a reviewer could not
open. It is the closure half of C13 — one row per settlement class, **25 IN instruments at head plus the 9
gen-1-only exits = 34 rows**, each saying which lane it was demonstrated on and what was observed, or that it
was not run and why. Generated from the AST enumerator and the ledger's own PART 5, so it cannot drift from
them; the generator's completeness check reports `25/25 closed; outstanding: none`, exit 0.*

| # | settlement class | metric | lane(s) | disposition | where it was demonstrated, or the reason it was not run |
|---|---|---|---|---|---|
| ~~1~~ | ~~`processed_with_failures`~~ | ~~`asset_ingestion_agent_slices_dropped_total`~~ | ~~new only~~ | ~~**DEMONSTRATED LIVE**~~ **→ WITHDRAWN** | ADDED IN ROUND 20, and the class did not exist before it. An object whose agent slice was abandoned by per-agent isolation used to meter plain `processed` — the lane reported success for an object whose rows had not all landed, wh… |  **WITHDRAWN (round 45): both instruments were reverted out of this PR; neither exists on this head.**
| 2 | `reingest-skip` | `asset_ingestion_agents_reingest_skipped_total` | both | **BOTH-LANE CLASS IN CODE** | BOTH-LANE CLASS IN CODE; DEMONSTRATED IN ONE LANE IN THESE LEGS, and the difference is itself ledgered (A-2). The skip is implemented once, in the SHARED python mcp_asset_creation activities BOTH lanes call — evaluate_mcp_ingestio… |
| 3 | `agents_skipped{reason="empty_name"}` | `asset_ingestion_agents_skipped_total` | new only | **NAMED-NOT-RUN** | NAMED-NOT-RUN, with reason and both sides' call sites. THIS IS THE CLASS THE GATE FOUND (round 28 D2, round 30 GAP-3). A coding agent whose name is empty is dropped per-agent during extraction, before it becomes a write step: |
| 4 | `assets_ingested{source}` | `mcp_assets_ingested_total` | both | **DEMONSTRATED IN BOTH** | DEMONSTRATED IN BOTH — ADDED ROUND 37. Read off each lane's own /metrics this round: new lane {source="scanner", tenant_schema="prdct11935_tb"} 15.0; gen-1 worker {tenant_schema="prdct11935_ta"} 8702.0. Emitted from the shared act… |
| 5 | `empty window, all tenants(workflow.go:113)` | `mcp_connectors_suppressed_total` | gen-1 only | **REAL CLASS, NO NEW-LANE COUNTERPART** | REAL CLASS, NO NEW-LANE COUNTERPART, and it does not survive the cutover. The scheduled parent settles SUCCESS having found no tenant with S3 files in the window. The event-driven lane is PUSH-based, so "nothing arrived" is the ab… |
| 6 | `db_retries{reason}` | `asset_ingestion_db_retries_total` | new only | **DEMONSTRATED** | DEMONSTRATED — `db_retries_total{reason="statement_timeout"} 2.0` was measured on the failed->redeliver leg and is carried in this ledger's own entry for that class. 8 reason values are reachable via transient_retry_reason_for (db… |
| 7 | `unparseable -> DLQ` | `asset_ingestion_dead_letters_total` | new only | **DEMONSTRATED LIVE** | DEMONSTRATED live ON THE SHIPPED HEAD — RE-POINTED ROUND 28 (gate GAP-2). This row used to cite at3-01..04, which demonstrate no_ingestible_object — a DIFFERENT poison class — so poison_messages_total{reason="unparseable"} appeare… |
| 8 | `downstream_start_failures{workflow}` | `asset_ingestion_downstream_start_failures_total` | new only | **DEMONSTRATED** | DEMONSTRATED — driven this round by scaling the Temporal FRONTEND to zero (an infrastructure transient, no code touched) and posting a real payload through Kong. Two workflow values fired in one window: McpCveScanWorkflow and Desk… |
| 9 | `skipped_flag_off` | `asset_ingestion_dropped_bytes_total` | new only | **DEMONSTRATED** | DEMONSTRATED on the new lane (at6-05 §D, at1-06) + LEDGERED: gen-1's counterpart is the scannerScheduleDisabled schedule gate This row settles TWO instruments, because the flag-off drop is counted twice by design: objects{outcome=… |
| 10 | `gateway_employee_resolution{source}` | `asset_ingestion_gateway_employee_resolution_total` | gateway lane | **NAMED-NOT-RUN** | NAMED-NOT-RUN ON THIS DEPLOYMENT — the gateway lane is `enabled: false` on both Azure instances, so no gateway object is |
| 11 | `gateway_server_write_failures{write}` | `asset_ingestion_gateway_server_write_failures_total` | gateway lane | **NAMED-NOT-RUN (shared block)** | processed here at all. Inventoried with their lane named rather than excluded, because excluding by lane is the hand-drawn |
| 12 | `inline_version_resolutions{outcome}` | `asset_ingestion_inline_version_resolution_total` | new only | **DEMONSTRATED LIVE** | DEMONSTRATED LIVE — `inline_version_resolution_total{kind="package", lane="agent",outcome="cache_hit"}` present on the pod (version_resolution.py:326). All 6 outcomes reachable. |
| 13 | `inventory_sample_failures` | `asset_inventory_sample_failures_total` | new only | **NAMED-NOT-RUN** | NAMED-NOT-RUN — fires when the inventory gauge sampler fails (inventory_gauges.py:102); the sampler succeeded throughout. |
| 14 | `lines{kind}` | `asset_ingestion_lines_total` | new only | **DEMONSTRATED LIVE** | DEMONSTRATED LIVE for four of its five kinds, NAMED-NOT-RUN with a reason for the fifth — ADDED ROUND 36 (verify r31 GAP-1). Emitted at the success tail of ingest_scanner_object (pipeline.py:169). DEMONSTRATED: read off the SHIPPI… |
| 15 | `reingest-skip` | `asset_ingestion_mcp_servers_reingest_skipped_total` | both | **BOTH-LANE CLASS IN CODE** | BOTH-LANE CLASS IN CODE; DEMONSTRATED IN ONE LANE IN THESE LEGS, and the difference is itself ledgered (A-2). The skip is implemented once, in the SHARED python mcp_asset_creation activities BOTH lanes call — evaluate_mcp_ingestio… |
| 16 | `failed -> redeliver` | `asset_ingestion_objects_total` | new only | **DEMONSTRATED LIVE** | DEMONSTRATED live in at6-14-failed-redeliver.txt (round 25, head image): an ACCESS EXCLUSIVE lock on prdct11935_tb.mcp_ingestion_state makes the writer's read hit statement_timeout (QueryCanceledError), the object meters objects{o… |
| 17 | `parse_err` | `asset_ingestion_parse_errors_total` | new only | **DEMONSTRATED LIVE** | DEMONSTRATED live in at6-13-parse-err.txt (round 24, head image): a non-JSON body on the real queue -> the named log point at message_handler.py:96 -> records_total{result="parse_err"} 1 -> ACKED. RE-STAMPED ROUND 25 (gate G3): th… |
| 18 | `unparseable -> DLQ` | `asset_ingestion_poison_messages_total` | new only | **DEMONSTRATED LIVE** | DEMONSTRATED live ON THE SHIPPED HEAD — RE-POINTED ROUND 28 (gate GAP-2). This row used to cite at3-01..04, which demonstrate no_ingestible_object — a DIFFERENT poison class — so poison_messages_total{reason="unparseable"} appeare… |
| 19 | `ok` | `asset_ingestion_records_total` | new only | **DEMONSTRATED** | DEMONSTRATED on the new lane — records_total{result="ok"} is read live in at6-01 §DEMO (24) and at4-03. It is the per-RECORD counterpart of `processed`: every record that reaches the processor increments it. LEDGERED: gen-1 has no… |
| 20 | `created` | `asset_ingestion_records_written_total` | both | **DEMONSTRATED IN BOTH** | DEMONSTRATED IN BOTH — at6-04a (row diff) + PART 3 counters |
| 21 | `reingest_edges_restored{source}` | `mcp_reingest_edges_restored_total` | new only | **DEMONSTRATED** | DEMONSTRATED on the new lane — ADDED ROUND 37: {connection_type="AgentToMcp",tenant_schema="prdct11935_tb"} 3.0, ABSENT on the gen-1 worker in the same window, for the same stricter-gate reason as the row above (activities.py:1337… |
| 22 | `reingest_skip_evaluations{verdict}` | `mcp_reingest_skip_evaluations_total` | new only | **DEMONSTRATED** | DEMONSTRATED on the new lane, and the gen-1 side is LEDGERED, not assumed — ADDED ROUND 37. New lane this round: {prdct11935_tb,verdict="skip"} 29.0 and {verdict="base_changed"} 15.0. ABSENT on the gen-1 worker's scrape. That is t… |
| 23 | `session_alerts published` | `asset_ingestion_session_alerts_total` | new only | **DEMONSTRATED LIVE** | DEMONSTRATED live — ADDED ROUND 28 (gate GAP-2). **Attribution corrected (round-50 sweep):** this row used to say the family *"is introduced by the head commit itself"*. It is not — `session_alerts` is declared in `metrics.py` at the merge-base `822abd2356` exactly as at head (2 hits each side), and `writers.py` has **0** changed lines in this PR's diff. The measurement stands; the family is pre-existing, and only `published`/`skipped_no_queue` are reachable on the scanner lane (`publish_failed` is gateway-only, `gateway_writers.py:420`). asset_ingestion_session_alert… |
| 24 | `step_total{outcome,step}` | `asset_ingestion_step_total` | new only | **DEMONSTRATED LIVE** | DEMONSTRATED LIVE — read off the shipping pod's /metrics this round: `asset_ingestion_step_total{outcome="ok",step="fetch_object",...}`. 13 steps x {ok,error,skipped} (telemetry/steps.py:118). |
| 25 | `swg_observations{outcome}` | `asset_ingestion_swg_observations_total` | swg lane | **NAMED-NOT-RUN (shared block)** | boundary that caused the original miss. |
| 26 | `empty window, all tenants(workflow.go:113)` | *(gen-1 exit — no Python instrument)* | gen-1 only | **REAL CLASS, NO NEW-LANE COUNTERPART** | REAL CLASS, NO NEW-LANE COUNTERPART, and it does not survive the cutover. The scheduled parent settles SUCCESS having found no tenant with S3 files in the window. The event-driven lane is PUSH-based, so "nothing arrived" is the ab… |
| 27 | `empty window, one tenant(tenant_workflow.go:130)` | *(gen-1 exit — no Python instrument)* | gen-1 only | **LOG ONLY** | Same class one level down: the tenant scan settles SUCCESS having done nothing. Logs LESS than its parent (no window bounds). LOG ONLY. DIRECTION: gen-1 -> nothing. |
| 28 | `schedule no-op underscannerScheduleDisabled(tenant_workflow.go:96)` | *(gen-1 exit — no Python instrument)* | gen-1 only | **LOG ONLY** | The mirror image of the new lane's skipped_flag_off, and the two together ARE the cutover switch: gen-1 no-ops when the flag is ON, the new lane skips when its own flag is OFF. Both are real classes; only one is metered. gen-1: LO… |
| 29 | `LD-eval failure settlesfail-OPEN(tenant_workflow.go:91)` | *(gen-1 exit — no Python instrument)* | gen-1 only | **POLARITY DIVERGENCE** | POLARITY DIVERGENCE, and the sharpest one in this ledger. On a LaunchDarkly evaluation error gen-1 logs a warning and RUNS THE SCAN (tenant_workflow.go:91), while the new lane passes raise_on_error=True and FAILS THE OBJECT so the… |
| 30 | `tenant scan settlesSUCCESS with inventorymissing AND bridgesuppressed(post_inventory.go:204)` | *(gen-1 exit — no Python instrument)* | gen-1 only | **DEMONSTRATED** | THE CLASS THE NEW LANE EXISTS TO CLOSE. The inline DAC child fails, gen-1 logs and continues (no return), so allCreatedAssetIDs stays empty — which ALSO suppresses the Issue/Risk bridge at :232. The scan settles SUCCESS with no as… |
| 31 | `bridge silently notdispatched(post_inventory.go:232)` | *(gen-1 exit — no Python instrument)* | gen-1 only | **NOTHING IS EMITTED** | No assets created -> the bridge is not dispatched, the tenant settles SUCCESS, and NOTHING is emitted — no log, no metric. Reachable both legitimately and pathologically (via :204), and the two are indistinguishable. No new-lane c… |
| 32 | `bridge settles SUCCESSafter issue detectionFAILED` | *(gen-1 exit — no Python instrument)* | gen-1 only | **SEE ROW TEXT** | Issue detection fails after 3 retries, risk calc is silently skipped, the bridge returns nil. Because the bridge is an ABANDON child the failure never reaches the tenant scan either — invisible at every level |
| 33 | `non-scanner payloadsilently discarded(activities.go:1324)` | *(gen-1 exit — no Python instrument)* | gen-1 only | **SILENTLY DISCARDED** | Per payload, silently discarded inside filterScannerPayloads with no count and no log; only the all-empty case surfaces at all (activities.go:624, LOG ONLY, and it does not even increment filesProcessed). The new lane meters the s… |
| 34 | `activity output over the3MB cap(activities.go:225)` | *(gen-1 exit — no Python instrument)* | gen-1 only | **NON-RETRYABLE** | NON-RETRYABLE, and one of only TWO machine-readable settlement discriminators in the whole gen-1 package (error type "ActivityOutputTooLarge", activities.go:73). No new-lane counterpart: there is no Temporal history boundary in a … |



## The gen-1-vs-new-lane comparison — WITHDRAWN, not quietly dropped

A ~27 KB section stood here that put gen-1's rows beside the new lane's, said *"across all three legs the
lanes agree on every asset class"*, and ledgered five named differences — including an **L-1** row reading
*"four seeded connector MCP assets … LOSS by the new lane … **fixed in this PR**, byte-identical"*.

It is removed, and for two reasons that are worth stating rather than hiding behind a diff:

1. **The round-45 owner ruling withdrew the claim.** *"PRDCT-11935 is Azure ENABLEMENT ONLY. It is not a
   bug-fix PR."* … *"Then update the PR body: C13 is NO LONGER claimed as proven."* A side-by-side that
   concludes the lanes agree **is** that claim, whatever the banner above it says, and at6's guard is
   explicit that any such claim in the PR body is a failure.
2. **Its headline item became false in the same ruling.** The seeded-connector work that L-1 called *"fixed
   in this PR"* was **reverted** — `build_seeded_connector_servers` and `_extension_name_from_mcpb` do not
   exist at this head (`grep -rn` over `backend_python/src` returns zero for both). A row claiming a fix
   that is no longer in the diff is worse than no row.

What this PR **does** claim, and proves, is narrower and is the thing the transport change can actually be
held to: **transport equivalence** — the same writer image, fed the same object bytes, writes the same rows
whether the object arrives over SQS/S3 or over Service Bus/Blob ([`at6-07-transport-equivalence.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-07-transport-equivalence.txt),
[`at6-04a`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04a-diff-created.txt) / [`at6-04b`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04b-diff-matched.txt) /
[`at6-04c`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-04c-diff-reingest-skip.txt)) — plus the settlement-class coverage in
[`at6-05-per-class.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-05-per-class.txt) and the closure table below. The gen-1 comparison and its
five divergence rows survive **as an owner-accepted gap** in [`at6-06-ledger.txt`](https://raw.githubusercontent.com/onyxsecurity/pywebagent/prdct11935-evidence/evidence/prdct11935/at6-06-ledger.txt),
which is where a reader who wants that history should go — it is not evidence for this PR.

## Automated reviewer summary

<!-- CURSOR_SUMMARY -->
---

> [!NOTE]
> **High Risk**
> Changes how scanner objects are consumed, stored, and settled on Azure, plus boot-time refusals that can crash-loop misconfigured pods. Poison/DLQ and alert-fan-out paths are security- and data-path critical.
> 
> **Overview**
> Makes the scanner **one-writer** lane (`endpoint_asset_ingestion`) actually run on Azure. `ONYX__CLOUD` now selects queue, object store, and notification schema together: Service Bus + Blob + Event Grid `BlobCreated` on Azure, SQS + S3 on AWS.
> 
> **Fail-closed boot.** New `transport_guard` assertions refuse a cloud/transport mismatch (Azure with SQS, AWS with Service Bus, Azure with no reachable queue). Gen-2 `scanner_event_consumer` and `mcp_gateway_event_consumer` drop their dead Azure branches that acked Event Grid bodies as empty S3 events, and refuse `cloud=azure` at startup, naming this lane as the Azure owner.
> 
> **Azure consumer path.** The handler is transport-agnostic: shared blob parser maps container→bucket and blob path→key; empty Azure parses are **poison** (native `$DeadLetterQueue`), not silent acks. ASB stamps SQS-shaped `_sys_*` receive-count/age (1-based), uses a per-worker client (receiver is not coroutine-safe), and parks poison with a reason. Alert fan-out follows the same cloud (optional ASB producer; wrong-cloud queue is refused).
> 
> **Ops.** Direct `azure-storage-blob` dep so lean installs still get a Blob client. Helm values add ASB stanzas and strip unused gen-2 ASB config. ADR 0069 and monitoring notes document Azure DLQ metrics and the no-fairness deviation (same as AWS M1).
> 
> <sup>Reviewed by [Cursor Bugbot](https://cursor.com/bugbot) for commit 2b60fdc4df25188104e737e6311087681355eff8. Bugbot is set up for automated code reviews on this repo. Configure [here](https://www.cursor.com/dashboard/bugbot).</sup>
<!-- /CURSOR_SUMMARY -->

<!-- evidence/at10-01-pr-body.md — fetch receipt (round-34, gate GAP-7c).
     command : gh pr view 12329 --json body --jq .body
     fetched : 2026-08-22T01:27:51Z
     This is an HTML comment on purpose. at10's required_evidence asks this artifact to show the
     command and timestamp it was re-fetched with, and it is ALSO worth keeping byte-identical to
     the live PR body (which is how a reader knows the artifact is not a doctored copy). A comment
     satisfies both: it lives in the live body and in the file, and GitHub renders nothing for it. -->



