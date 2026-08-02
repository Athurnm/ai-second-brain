#!/usr/bin/env python3
"""kg_query.py - query the PSB knowledge graph instead of grepping the repo.

Pure graph traversal over journal/state/graph.json. No LLM, no embeddings, no
network, at build time or query time. Same input always gives the same output.

Retrieval design adapted from Graphify-Labs/graphify (Apache-2.0) as prior art:
IDF-weighted tiered scoring, capped seed selection with a per-term guarantee,
shallow BFS with hub avoidance, and refusal on ambiguity. Reimplemented here on
stdlib only, with an Indonesian stopword list added and the provenance default
inverted (a missing confidence tag is AMBIGUOUS, never EXTRACTED).

This is a DISCOVERY index. It tells you which files to open. It is not evidence.
Any status claim still gets verified against the primary source in the same turn.

Usage:
  python3 .agent/scripts/kg_query.py query "apa yang nyambung ExampleVendor ke OMS"
  python3 .agent/scripts/kg_query.py path "Rohit Salaria" "Example Program"
  python3 .agent/scripts/kg_query.py explain "WAIT-0209"
  python3 .agent/scripts/kg_query.py stats
"""

import argparse
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict, deque

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_GRAPH = os.path.join(REPO, "journal", "state", "graph.json")

# Scoring tiers. A whole-label hit must dominate a substring hit, hence the
# three orders of magnitude between them.
EXACT_BONUS, PREFIX_BONUS, SUBSTR_BONUS = 1000.0, 100.0, 1.0
MAX_SEEDS = 3
SEED_GAP_RATIO = 0.2       # drop a seed scoring below 20% of the best one
DEPTH = 2                  # 3 hops makes everything connect to everything
# Hub threshold is p99 of the live degree distribution, floored low on purpose.
# graphify floors this at 50, which is tuned for large code graphs. This graph
# has a median degree of 1 and a max of 70, so a floor of 50 would leave
# 'b2c' (49), 'todo' (43) and 'Your Name' (43) traversable and every
# query would flood with everything those touch. Measured p99 here is 18.
HUB_FLOOR = 12
CHAR_BUDGET = 6000

# English filler plus the Indonesian question and connector words that would
# otherwise compete as content terms. graphify ships six European languages and
# no Indonesian, which is the wrong shape for the owner's queries.
STOPWORDS = {
    # English
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "of", "to", "in",
    "on", "at", "by", "for", "with", "and", "or", "but", "if", "then", "than",
    "that", "this", "these", "those", "it", "its", "as", "from", "into", "about",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how", "all",
    "any", "can", "do", "does", "did", "has", "have", "had", "not", "no", "so",
    "show", "me", "give", "list", "find", "get", "between", "connect", "connects",
    # Indonesian
    "apa", "apakah", "siapa", "kapan", "kenapa", "mengapa", "bagaimana", "gimana",
    "mana", "yang", "di", "ke", "dari", "dan", "atau", "tapi", "kalau", "kalo",
    "untuk", "buat", "dengan", "sama", "pada", "dalam", "adalah", "itu", "ini",
    "ada", "gak", "nggak", "ga", "tidak", "bukan", "sudah", "udah", "belum",
    "akan", "bisa", "boleh", "harus", "juga", "saja", "aja", "lagi", "masih",
    "nyambung", "nyambungin", "hubungan", "antara", "terkait", "soal", "tentang",
    "gw", "gue", "lo", "lu", "kita", "saya", "aku", "dia", "mereka", "nya",
}

def strip_diacritics(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c))

def tokens(s):
    return re.findall(r"\w+", strip_diacritics(s).lower(), flags=re.UNICODE)

def query_terms(question):
    raw = tokens(question)
    kept = [t for t in raw if len(t) > 2 and t not in STOPWORDS]
    return kept or raw          # never return nothing

class KG:
    def __init__(self, path):
        with open(path, encoding="utf-8") as fh:
            blob = json.load(fh)
        self.meta = {k: v for k, v in blob.items() if k not in ("nodes", "edges")}
        self.nodes = {n["id"]: n for n in blob["nodes"]}
        self.edges = blob["edges"]
        self.adj = defaultdict(list)      # undirected, for traversal
        self.out = defaultdict(list)
        self.inn = defaultdict(list)
        for e in self.edges:
            s, t = e["source"], e["target"]
            self.adj[s].append((t, e))
            self.adj[t].append((s, e))
            self.out[s].append(e)
            self.inn[t].append(e)
        for n in self.nodes.values():
            hay = " ".join(filter(None, [n.get("label"), n.get("search_text"),
                                         n.get("id")]))
            n["_norm"] = strip_diacritics(hay).lower()
        self._idf = None
        self._hub = None

    def degree(self, nid):
        return len(self.adj.get(nid, ()))

    def hub_threshold(self):
        if self._hub is None:
            degs = sorted(self.degree(n) for n in self.nodes)
            p99 = degs[int(len(degs) * 0.99)] if degs else 0
            self._hub = max(HUB_FLOOR, p99)
        return self._hub

    def idf(self, term):
        if self._idf is None:
            self._idf = {}
        if term not in self._idf:
            df = sum(1 for n in self.nodes.values() if term in n["_norm"])
            self._idf[term] = math.log(1 + len(self.nodes) / (1 + df))
        return self._idf[term]

    # ------------------------------------------------------------- scoring

    def score(self, terms):
        """Return (ranked[(nid, score)], best_node_per_term)."""
        joined = " ".join(terms)
        scores = Counter()
        best_by_term = {}
        for nid, n in self.nodes.items():
            hay = n["_norm"]
            total = 0.0
            matched = 0
            if joined and hay == joined:
                total += EXACT_BONUS * 10 * self.idf(joined)
            elif joined and hay.startswith(joined):
                total += PREFIX_BONUS * 10 * self.idf(joined)
            for t in terms:
                idf = self.idf(t)
                sub = 0.0
                if hay == t:
                    sub = EXACT_BONUS * idf
                elif re.search(r"\b" + re.escape(t), hay):
                    sub = PREFIX_BONUS * idf
                elif t in hay:
                    sub = SUBSTR_BONUS * idf
                if sub:
                    matched += 1
                    total += sub
                    if sub > best_by_term.get(t, (None, 0.0))[1]:
                        best_by_term[t] = (nid, sub)
            if total and terms:
                # a node matching 3 of 3 terms must outrank one matching 1 of 3
                total *= (matched / len(terms)) ** 2
            if total:
                scores[nid] = total
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
        return ranked, {t: v[0] for t, v in best_by_term.items()}

    def pick_seeds(self, ranked, best_by_term):
        if not ranked:
            return []
        top = ranked[0][1]
        seeds = []
        for nid, sc in ranked:
            if len(seeds) >= MAX_SEEDS or sc < top * SEED_GAP_RATIO:
                break
            seeds.append(nid)
        # guarantee every term contributed at least one entry point, so a
        # dominant term cannot starve the rest of the question
        for _, nid in sorted(best_by_term.items()):
            if nid not in seeds:
                seeds.append(nid)
        return seeds

    # ------------------------------------------------------------ traversal

    def bfs(self, seeds, depth=DEPTH):
        hub = self.hub_threshold()
        seen = {s: 0 for s in seeds}
        q = deque((s, 0) for s in seeds)
        order = list(seeds)
        while q:
            nid, d = q.popleft()
            if d >= depth:
                continue
            # a hub is reachable but not traversable: everything touches YourManager
            # and Work, so routing through them makes any two things "related"
            if nid not in seeds and self.degree(nid) >= hub:
                continue
            for nbr, _ in sorted(self.adj.get(nid, ()), key=lambda x: x[0]):
                if nbr not in seen:
                    seen[nbr] = d + 1
                    order.append(nbr)
                    q.append((nbr, d + 1))
        return seen, order

    def induced_edges(self, visited):
        return [e for e in self.edges
                if e["source"] in visited and e["target"] in visited]

# ----------------------------------------------------------------- rendering

def fmt_node(kg, nid, hop=None):
    n = kg.nodes.get(nid, {"id": nid, "type": "?", "label": nid})
    bits = [f"[{n.get('type')}]", n.get("label", nid)]
    if n.get("status"):
        bits.append(f"({n['status']})")
    if n.get("source_file"):
        bits.append(f"<{n['source_file']}>")
    if hop is not None:
        bits.append(f"hop={hop}")
    bits.append(f"deg={kg.degree(nid)}")
    return "  " + " ".join(str(b) for b in bits)

def cmd_query(kg, args):
    terms = query_terms(args.question)
    ranked, best = kg.score(terms)
    if not ranked:
        print(f"no match for terms: {terms}")
        return 1
    seeds = kg.pick_seeds(ranked, best)
    seen, order = kg.bfs(seeds, args.depth)
    edges = kg.induced_edges(set(seen))

    print(f"terms   : {terms}")
    print(f"seeds   : {len(seeds)} (hub threshold deg>={kg.hub_threshold()})")
    for s in seeds:
        print(fmt_node(kg, s))
    print(f"\nsubgraph: {len(seen)} nodes, {len(edges)} edges\n")

    out, used = [], 0
    ordered = sorted(order, key=lambda n: (seen[n], -kg.degree(n), n))
    for nid in ordered:
        if nid in seeds:
            continue
        line = fmt_node(kg, nid, seen[nid])
        if used + len(line) > args.budget:
            out.append(f"  [!] truncated, {len(ordered) - len(out)} more nodes")
            break
        out.append(line)
        used += len(line)
    print("NODES")
    print("\n".join(out))

    print("\nEDGES")
    shown = 0
    for e in sorted(edges, key=lambda e: (e["source"], e["target"])):
        if shown >= args.max_edges:
            print(f"  [!] truncated, {len(edges) - shown} more edges")
            break
        sl = kg.nodes.get(e["source"], {}).get("label", e["source"])
        tl = kg.nodes.get(e["target"], {}).get("label", e["target"])
        print(f"  {sl}  --{e['relation']}-->  {tl}   [{e.get('confidence', 'AMBIGUOUS')}]")
        shown += 1
    return 0

def find_node(kg, needle):
    """Tiered exact-first lookup. Returns (matches, tier_name)."""
    key = strip_diacritics(needle).lower().strip()
    tiers = [
        ("id", lambda n: n["id"].lower() == key),
        ("exact label", lambda n: strip_diacritics(n.get("label", "")).lower() == key),
        ("id contains", lambda n: key in n["id"].lower()),
        ("label prefix", lambda n: strip_diacritics(n.get("label", "")).lower().startswith(key)),
        ("label substring", lambda n: key in n["_norm"]),
    ]
    for name, pred in tiers:
        hits = sorted(n["id"] for n in kg.nodes.values() if pred(n))
        if hits:
            return hits, name
    return [], None

def resolve_or_refuse(kg, needle):
    """Refuse rather than guess when a name is ambiguous. This is the same rule
    as feedback_no_guessing_names: a wrong person is worse than no answer."""
    hits, tier = find_node(kg, needle)
    if not hits:
        print(f"no node matches {needle!r}")
        return None
    if args_pick := getattr(resolve_or_refuse, "_pick", None):
        if args_pick in hits:
            return args_pick
    if len(hits) > 1:
        # A person and that person's own People/ page share a label. people.json
        # records the link in the `page` field, so this is resolvable from data
        # rather than guessed: keep the entity, drop its own page.
        entities = [h for h in hits if kg.nodes[h].get("type") != "document"]
        if len(entities) == 1:
            page = kg.nodes[entities[0]].get("page")
            docs = [h for h in hits if h not in entities]
            if page and all(str(kg.nodes[h].get("source_file", "")).endswith(page)
                            for h in docs):
                return entities[0]
    if len(hits) > 1:
        files = {kg.nodes[h].get("source_file") or kg.nodes[h]["type"] for h in hits}
        if len(files) > 1 or len(hits) > 6:
            print(f"AMBIGUOUS: {len(hits)} nodes match {needle!r} at tier '{tier}'. "
                  f"Refusing to pick one. Candidates:")
            for h in hits[:12]:
                print(fmt_node(kg, h))
            if len(hits) > 12:
                print(f"  ... {len(hits) - 12} more")
            return None
    return hits[0]

def cmd_explain(kg, args):
    nid = resolve_or_refuse(kg, args.node)
    if not nid:
        return 1
    n = kg.nodes[nid]
    # An exact hit on a truncated person slug is the split-identity trap: the
    # match is unambiguous but the answer is still incomplete. Say so.
    if n.get("type") == "person":
        kin = sorted(o for o in kg.nodes
                     if o != nid and kg.nodes[o].get("type") == "person"
                     and (o.startswith(nid + "-") or nid.startswith(o + "-")))
        if kin:
            print(f"[!] SPLIT IDENTITY: {len(kin)} other person id(s) share this "
                  f"name stem. This node's connections are PARTIAL.")
            for k in kin:
                print(f"      {k}  (deg={kg.degree(k)})")
            print()
    print(f"Node    : {n.get('label')}")
    print(f"  id    : {nid}")
    print(f"  type  : {n.get('type')}")
    for k in ("status", "due", "deadline", "project", "portfolio", "role", "team",
              "date", "recording", "source_file", "registered", "sla_hours"):
        if n.get(k) not in (None, ""):
            print(f"  {k:6}: {n[k]}")
    if n.get("search_text"):
        print(f"  text  : {str(n['search_text'])[:300]}")
    print(f"  degree: {kg.degree(nid)}")

    print("\nConnections")
    rows = []
    for e in kg.out.get(nid, []):
        rows.append(("-->", e["target"], e["relation"], e.get("confidence", "AMBIGUOUS"),
                     e.get("evidence", "")))
    for e in kg.inn.get(nid, []):
        rows.append(("<--", e["source"], e["relation"], e.get("confidence", "AMBIGUOUS"),
                     e.get("evidence", "")))
    rows.sort(key=lambda r: (-kg.degree(r[1]), r[1]))
    for arrow, other, relation, conf, ev in rows[:args.max_edges]:
        lbl = kg.nodes.get(other, {}).get("label", other)
        line = f"  {arrow} {lbl}  [{relation}] [{conf}]"
        if ev and args.verbose:
            line += f"   via {ev}"
        print(line)
    if len(rows) > args.max_edges:
        print(f"  ... {len(rows) - args.max_edges} more")
    return 0

def cmd_path(kg, args):
    src = resolve_or_refuse(kg, args.source)
    tgt = resolve_or_refuse(kg, args.target)
    if not src or not tgt:
        return 1
    if src == tgt:
        print("source and target resolve to the same node")
        return 1
    prev = {src: None}
    q = deque([src])
    while q:
        cur = q.popleft()
        if cur == tgt:
            break
        for nbr, _ in sorted(kg.adj.get(cur, ()), key=lambda x: x[0]):
            if nbr not in prev:
                prev[nbr] = cur
                q.append(nbr)
    if tgt not in prev:
        print(f"no path between {kg.nodes[src]['label']!r} and {kg.nodes[tgt]['label']!r}")
        return 1
    chain = []
    cur = tgt
    while cur is not None:
        chain.append(cur)
        cur = prev[cur]
    chain.reverse()
    print(f"Shortest path ({len(chain) - 1} hops):\n")
    for i, nid in enumerate(chain):
        print(fmt_node(kg, nid))
        if i + 1 < len(chain):
            nxt = chain[i + 1]
            e = next((x for x in kg.edges
                      if {x["source"], x["target"]} == {nid, nxt}), None)
            if e:
                arrow = "-->" if e["source"] == nid else "<--"
                print(f"      {arrow} [{e['relation']}] "
                      f"[{e.get('confidence', 'AMBIGUOUS')}]")
    return 0

def cmd_stats(kg, args):
    print(f"generated_at : {kg.meta.get('generated_at')}")
    print(f"build_seconds: {kg.meta.get('build_seconds')}")
    print(f"nodes {len(kg.nodes)}   edges {len(kg.edges)}   "
          f"hub threshold deg>={kg.hub_threshold()}")
    print("\nnodes by type:")
    for k, v in Counter(n["type"] for n in kg.nodes.values()).most_common():
        print(f"  {v:6d}  {k}")
    print("\nedges by confidence:")
    for k, v in Counter(e.get("confidence", "AMBIGUOUS") for e in kg.edges).most_common():
        print(f"  {v:6d}  {k}")
    print("\nmost connected nodes (reachable, but never traversed through):")
    for nid, d in sorted(((n, kg.degree(n)) for n in kg.nodes),
                         key=lambda x: (-x[1], x[0]))[:12]:
        print(f"  {d:4d}  {kg.nodes[nid].get('label')}  [{kg.nodes[nid]['type']}]")
    return 0

def main():
    # shared flags are attached to every subcommand as well, so both
    # `kg_query.py -v explain X` and `kg_query.py explain X -v` work
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--graph", default=DEFAULT_GRAPH)
    common.add_argument("--max-edges", type=int, default=40)
    common.add_argument("--budget", type=int, default=CHAR_BUDGET)
    common.add_argument("-v", "--verbose", action="store_true")

    ap = argparse.ArgumentParser(description=__doc__, parents=[common],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("query", parents=[common]); q.add_argument("question")
    q.add_argument("--depth", type=int, default=DEPTH)
    e = sub.add_parser("explain", parents=[common]); e.add_argument("node")
    p = sub.add_parser("path", parents=[common])
    p.add_argument("source"); p.add_argument("target")
    sub.add_parser("stats", parents=[common])

    args = ap.parse_args()
    if not os.path.exists(args.graph):
        print(f"graph not found at {args.graph}\nrun: python3 .agent/scripts/kg_build.py")
        return 2
    kg = KG(args.graph)
    return {"query": cmd_query, "explain": cmd_explain,
            "path": cmd_path, "stats": cmd_stats}[args.cmd](kg, args)

if __name__ == "__main__":
    sys.exit(main())
