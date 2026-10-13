# Graph Report - readcode-graph-nuc4y7_4  (2026-10-12)

## Corpus Check
- 12 files · ~252 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 1 file(s) not represented in the graph (top: (none) 1)

## Summary
- 30 nodes · 39 edges · 5 communities (4 shown, 1 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- billing.py
- api.ts
- Queue
- main.py
- README.md

## God Nodes (most connected - your core abstractions)
1. `Invoice` - 6 edges
2. `Queue` - 5 edges
3. `process()` - 4 edges
4. `refund()` - 4 edges
5. `main()` - 3 edges
6. `process()` - 3 edges
7. `hash_token()` - 2 edges
8. `compute_total()` - 2 edges
9. `process_refund()` - 2 edges
10. `fetchInvoice()` - 2 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `process()`  [EXTRACTED]
  app/main.py → app/services/billing.py
- `main()` --calls--> `NewQueue()`  [INFERRED]
  worker/main.go → worker/queue.go
- `main()` --calls--> `process()`  [EXTRACTED]
  app/main.py → app/services/auth.py
- `process()` --calls--> `Invoice`  [EXTRACTED]
  app/services/billing.py → app/models.py
- `refund()` --calls--> `Invoice`  [EXTRACTED]
  app/services/billing.py → app/models.py

## Import Cycles
- None detected.

## Communities (5 total, 1 thin omitted)

### Community 0 - "billing.py"
Cohesion: 0.33
Nodes (5): Invoice, compute_total(), process(), refund(), process_refund()

### Community 1 - "api.ts"
Cohesion: 0.43
Nodes (3): fetchInvoice(), ApiResponse, Invoice

### Community 2 - "Queue"
Cohesion: 0.33
Nodes (3): main(), Queue, NewQueue()

### Community 3 - "main.py"
Cohesion: 0.60
Nodes (3): main(), hash_token(), process()

## Knowledge Gaps
- **1 isolated node(s):** `Fixture app`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 8 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `process()` connect `billing.py` to `main.py`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `main()` connect `main.py` to `billing.py`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **What connects `Fixture app` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._