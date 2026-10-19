---
name: topic-driller
description: >-
  Use this skill when the user asks to deeply understand a topic, system, file, architecture, or technical decision up to 10 levels deep. It employs a recursive "Whys" root-cause chain integrated with a 5W1H (What, Why, How, Where, Who, When) dimensional matrix to systematically unpack concepts from surface behavior down to foundational first principles.
---

# 10-Level Deep Topic Driller (Recursive Whys + 5W1H)

## Purpose & Philosophy

Surface explanations leave developers with shallow familiarity ("I know how to run this") without deep comprehension ("I understand why this must exist, how it breaks, its fundamental limits, and how to defend its architectural trade-offs").

This skill guides the agent to perform an exhaustive, structured **10-Level Deep Exploration** of any concept, file, system, or technology using two converging analytical lenses:
1. **The Recursive "Whys" Chain**: A continuous causal inquiry where each answer's underlying justification becomes the next level's question ($Q_n \rightarrow Ans_n \rightarrow \text{Why } Ans_n \rightarrow Q_{n+1}$).
2. **The 5W1H Dimensional Matrix**: At every level of depth, grounding the explanation in **What**, **Why**, **How**, **Where**, **Who**, and **When** to eliminate hand-waving and abstractions.

---

## When to Activate

Trigger this skill whenever the user:
- Asks for a "deep dive", "10 levels deep", "first principles", or "root cause" explanation of a topic.
- Wants to understand a complex file, module, algorithm, or distributed system architecture.
- Asks *"Why was this built this way?"* or *"Why do we need this?"* beyond superficial answers.
- Requests a conceptual breakdown linking concrete code lines to theoretical constraints.

---

## The 10-Level Progressive Taxonomy

Each level must peel back a distinct layer of abstraction without repeating earlier points. The 10 levels progress from human interfaces down to universal laws:

| Level | Abstraction Plane | Focus Area |
| :---: | :--- | :--- |
| **L1** | **Surface & Interface** | User interactions, CLI flags, API endpoints, visible UI widgets, direct inputs/outputs. |
| **L2** | **Workflow & Pipeline** | Sequence of operations, data orchestration, execution lifecycle, request/response flow. |
| **L3** | **Modular Subsystems & Contracts** | Boundaries between components, interfaces, adapters, RPC/event boundaries. |
| **L4** | **State, Data Structures & Schemas** | Memory models, serializations, vector spaces, relational schemas, caching keys. |
| **L5** | **Algorithmic Mechanics** | Step-by-step algorithms, mathematical transformations, similarity metrics, heuristics. |
| **L6** | **Physical & Hardware Constraints** | Memory budgets, CPU/GPU parallelism, network latency, token limits, disk I/O. |
| **L7** | **Failure Modes & Entropy** | Silent degradations, edge cases, race conditions, distribution shifts, fallback mechanisms. |
| **L8** | **Domain Governance & Invariants** | Business rules, compliance, legal liability, data privacy, RBAC security, SLA guarantees. |
| **L9** | **Architectural Trade-offs (Pareto Frontier)** | What was sacrificed (speed vs. accuracy, cost vs. quality), rejected alternatives. |
| **L10**| **Axiomatic First Principles** | Information theory, computational complexity (P vs. NP), statistical physics, mathematical limits. |

---

## The 5W1H Matrix at Every Depth

At each depth level ($L_1$ to $L_{10}$), synthesize the findings through the **5W1H questions**:

* **WHAT**: What is the exact entity, data structure, or mechanism operating at this level?
* **WHY**: Why does this specific layer behave this way? (The recursive pivot to the next level).
* **HOW**: How does it mechanically execute under the hood (step-by-step or equation)?
* **WHERE**: Where is this state or execution situated (stack frame, GPU VRAM, network pipe, disk)?
* **WHO**: Who/What is the actor, caller, consumer, or responsible subsystem?
* **WHEN**: When is this triggered, at what lifecycle phase, or under what inflection point?

---

## Execution Protocol & Output Format

When generating the 10-level deep analysis, structure the output cleanly:

```markdown
# 🔬 10-Level Deep Dimensional Analysis: [Topic / Concept Name]

[Brief 2-sentence executive summary defining the core system and its ultimate first principle.]

---

### Level 1: Surface & Interface (The Visible Symptom / Tooling)
* **Q1:** [Direct question addressing the surface utility]
* **Ans 1:** [Crisp, concrete answer]
* **5W1H Matrix:**
  * **What:** [Exact tool / UI / API]
  * **How:** [Command / invocation method]
  * **Where:** [Client, UI port, terminal]
  * **Who:** [User / developer persona]
  * **When:** [Development, testing, or user interaction time]
* **The Recursive Pivot (Why Ans 1?):** [Causal bridge leading into Level 2]

---

### Level 2: Workflow & Pipeline Orchestration
...
[Repeat through Level 10]
...

---

### Level 10: Axiomatic First Principles (Physics & Information Theory)
* **Q10:** [The ultimate boundary question]
* **Ans 10:** [The non-negotiable law of nature or computation that forces this design]
* **5W1H Matrix:**
  * **What:** [Universal law: Shannon Entropy, CAP theorem, P vs NP, Von Neumann bottleneck]
  * **How:** [Mathematical or physical equation / theorem]
  * **Where:** [Universal physical / mathematical substrate]
  * **Who:** [Applies universally across all computational entities]
  * **When:** [In all conceivable systems and timeframes]

---

## 🗺️ Synthesis Diagram
[Include a Mermaid diagram mapping the 10 levels vertically from Surface to First Principle]
```

---

## Golden Rules for the Agent

1. **Strictly Monotonic Depth**: Each level MUST go one layer deeper than the previous one. Never circle back or rephrase Level 2 at Level 5.
2. **Anchor to Real Artifacts**: When analyzing a specific codebase, link directly to source code symbols, file paths (using `file:///` URLs), constants, or config flags.
3. **Prevent Hand-Waving**: Avoid generic phrases like *"it optimizes performance"*. Specify *what* resource is optimized (e.g., *"reduces Cross-Encoder matrix multiplications from O(N) to O(K) where K << N"*).
4. **Contrast with Counterfactuals**: At Level 9 (Trade-offs), always explain what catastrophic failure or inefficiency occurs if this architectural decision is inverted.
5. **No Token Bloat**: Be dense and precise. Use bullet points and bolding for rapid mental model ingestion.
