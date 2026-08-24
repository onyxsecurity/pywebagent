#!/usr/bin/env python3
"""at7-23 carrier verifier — READS EVERY CITED FILE instead of trusting the row that cites it.

Round 41 failed this run because at7-23 recorded the POSTURE lifecycle cell as SETTLED citing
evidence/at7-52-posture-ticket-correction.txt, a file that did not exist and whose underlying work had
never been done. The generator had trusted intent. This verifier is the fix: for every cell, every
carrier it names is opened and three things are asserted mechanically —

  E  EXISTS      the file is on disk and non-empty
  H  ON-HEAD     a text carrier's own header names the head sha (PNG/JSON carriers are exempt from the
                 header rule but must be non-trivial); a carrier explicitly labelled HISTORICAL/SUPERSEDED
                 in the citing row is exempt and reported as such rather than silently skipped
  S  SUPPORTS    the carrier contains at least one identity literal of the class it is cited for

Exit code is non-zero if any cell fails, so a SETTLED verdict cannot outrun its evidence again.
"""
import os, re, sys, json

E = os.environ["AGENT_FACTORY_ARTIFACTS"] + "/evidence/"
HEAD = "2b60fdc4df25188104e737e6311087681355eff8"
SRC = E + "at7-23-attestations.txt"
text = open(SRC, errors="replace").read()

# identity literals per class, taken from each CLASS header line in the file itself
CLASS_RE = re.compile(r"^CLASS (\d) — ([A-Z ]+?)\s{2,}\((.*?)\)\s*$", re.M | re.S)
classes = []
for m in CLASS_RE.finditer(text):
    start = m.end()
    nxt = text.find("\nCLASS ", start)
    end = text.find("\nTALLY", start) if nxt == -1 else nxt
    classes.append({"n": m.group(1), "name": m.group(2).strip(), "hdr": " ".join(m.group(3).split()),
                    "body": text[start:end]})

CARRIER = re.compile(r"\b((?:evidence/)?at\d+[a-z]?-[0-9a-z]+[A-Za-z0-9._-]*\.(?:txt|png|json|md|diff))")
# A citation written as PROSE ("the at7-52 ticket-currency correction") names no path, so a
# path-only checker cannot open it — which is exactly how a SETTLED verdict outran its evidence in
# round 41. Bare at7-NN references are resolved to their file on disk and checked like any other.
# A truly BARE reference only — "at7-52" with nothing attached. The negative lookahead must also
# reject a full filename ("at7-09-db-rows-tools.txt"), otherwise one citation drags in every sibling
# that shares the stem and the checker invents failures of its own.
BARE = re.compile(r"\bat(\d+)-(\d+)(?![-\w./])")
import glob as _glob
def _resolve_bare(atn, nn):
    hits = sorted(_glob.glob(E + "at%s-%s-*" % (atn, nn))) or sorted(_glob.glob(E + "at%s-%s.*" % (atn, nn)))
    return [os.path.basename(h) for h in hits]
HIST = re.compile(r"HISTORICAL|SUPERSEDED|must not be re-cited", re.I)

rows, failed = [], 0
for c in classes:
    lits = [x for x in re.findall(r"\b\d{2,7}\b", c["hdr"])] + \
           [x for x in re.findall(r"[a-z0-9_]*r50at7002800[a-z0-9_-]*", c["hdr"])]
    for cell in re.finditer(r"^ (d-c2-[a-z-]+)\s+([A-Z]+)\s", c["body"], re.M):
        cs = cell.end(); ce = c["body"].find("\n d-c2-", cs)
        block = c["body"][cs: ce if ce != -1 else len(c["body"])]
        verdict = "SETTLED" if re.search(r"\bSETTLED\b", block) else \
                  ("NOT SETTLED" if re.search(r"NOT SETTLED", block) else "—")
        carriers = sorted(set(CARRIER.findall(block)))
        for atn, nn in set(BARE.findall(block)):
            for b in _resolve_bare(atn, nn):
                if b not in [os.path.basename(x) for x in carriers]:
                    carriers.append(b)
        carriers = sorted(set(carriers))
        for car in carriers:
            base = os.path.basename(car); p = E + base
            hist = bool(HIST.search(block)) and base in block
            if not os.path.isfile(p) or os.path.getsize(p) == 0:
                rows.append((c["name"], cell.group(1), verdict, base, "MISSING/EMPTY", "-", "-")); failed += 1; continue
            if base.endswith(".png"):
                ok_h = "n/a(png)" if os.path.getsize(p) > 20000 else "TOO-SMALL"
                blob = ""
            else:
                blob = open(p, errors="replace").read()
                if "SUPERSEDED — READ THIS FIRST" in blob:
                    ok_h = "SUPERSEDED"
                else:
                    ok_h = "yes" if HEAD[:10] in blob else ("HISTORICAL" if hist else "NO-HEAD-SHA")
            # Only carriers that are supposed to CARRY the class's rows are held to the literal rule.
            # A ticket fetch or a render-binding note legitimately contains none of the class's ids;
            # failing those would train a reader to ignore the column.
            carries_rows = cell.group(1).startswith(("d-c2-rows", "d-c2-fid"))
            if not carries_rows:
                ok_s = "supporting"
            elif base.endswith(".png") or not lits:
                ok_s = "yes"
            else:
                ok_s = "yes" if any(l in blob for l in lits) else "NO-LITERAL"
            if ok_h in ("TOO-SMALL", "NO-HEAD-SHA", "SUPERSEDED") or ok_s == "NO-LITERAL":
                failed += 1
            rows.append((c["name"], cell.group(1), verdict, base, "yes", ok_h, ok_s))

print("  %-14s %-18s %-11s %-44s %-8s %-11s %s" % ("CLASS", "CELL", "VERDICT", "CARRIER", "EXISTS", "ON-HEAD", "SUPPORTS"))
for r in rows:
    print("  %-14s %-18s %-11s %-44s %-8s %-11s %s" % r)
print()
print("  cells x carriers checked: %d · failures: %d" % (len(rows), failed))
sys.exit(1 if failed else 0)
