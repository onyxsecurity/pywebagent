"""Order-independent view of a lane dump.

metadata.sources is written by an AUTHORITATIVE per-object replace, so for an edge that appears in
more than one object of the same scan the surviving list is whichever object landed last — and its
element order follows from that. This normalises that one field (sorts the array canonically) and
then sorts the lines, so a comparison measures WHAT was written rather than IN WHAT ORDER the eight
objects happened to arrive.
"""
import json, re, sys

pat = re.compile(r'\{"sources": (\[.*?\])\}')

def norm(line: str) -> str:
    def repl(m):
        arr = json.loads(m.group(1))
        arr.sort(key=lambda d: json.dumps(d, sort_keys=True))
        return '{"sources": ' + json.dumps(arr, sort_keys=True) + '}'
    return pat.sub(repl, line)

lines = [norm(l.rstrip("\n")) for l in open(sys.argv[1])]
sys.stdout.write("\n".join(sorted(lines)) + "\n")
