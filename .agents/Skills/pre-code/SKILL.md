# SKILL.md — Research Method & Implementation Architect

## Skill Name

**Research Method & Implementation Architect**

## Purpose

Use this skill whenever the user needs to research, design, compare, select, or implement a technical solution—especially LLM, RAG, evaluation, agent, retrieval, prompt, observability, testing, or AI application work.

The skill converts an ambiguous engineering objective into a **research-backed implementation plan** and prevents premature commitment to a single tool, framework, architecture, or methodology.

The core principle is:

> **Research the problem space first, enumerate viable implementation options, compare them explicitly, then recommend a decision path with measurable acceptance criteria.**

Do not simply answer "use X." For every meaningful implementation option, investigate multiple ways to implement it, explain trade-offs, identify suitable use cases, and show how it can be validated.

---

# 1. Operating Principles

1. **Understand before implementing.**
2. **Separate facts, evidence, inference, and recommendation.**
3. **Prefer primary/official documentation for tool capabilities and APIs.**
4. **Use current sources for rapidly changing libraries, APIs, models, pricing, and platform capabilities.**
5. **Never assume the latest tool is automatically the best tool.**
6. **Compare architecture, complexity, reliability, observability, cost, maintainability, and lock-in.**
7. **For each significant option, produce at least 5 implementation approaches.**
8. **For each approach, explicitly document drawbacks and appropriate use cases.**
9. **Use measurable acceptance criteria rather than vague quality claims.**
10. **Prefer reversible decisions early in a project.**
11. **Design for failure, not only the happy path.**
12. **Validate the smallest risky assumption before building the entire system.**
13. **Keep research proportional to decision impact.**
14. **When evidence is insufficient, say what is unknown and define how to test it.**
15. **Never fabricate tool features, benchmarks, APIs, integrations, or performance numbers.**

---

# 2. Default Research Workflow

Follow this sequence unless the user explicitly requests another method.

```text
Problem
  ↓
Requirements
  ↓
Constraints
  ↓
Unknowns
  ↓
Research Questions
  ↓
Candidate Options
  ↓
5 Implementation Paths per Option
  ↓
Trade-off Analysis
  ↓
Proof-of-Concept Strategy
  ↓
Evaluation / Benchmarking
  ↓
Recommendation
  ↓
Implementation Plan
  ↓
Validation
  ↓
Production Readiness
```

---

# 3. Phase 1 — Understand the Problem

Extract:

- Goal
- Current system
- Desired system
- Inputs
- Outputs
- Users
- Data sources
- Dependencies
- Constraints
- Performance requirements
- Security requirements
- Compliance requirements
- Cost constraints
- Latency requirements
- Reliability requirements
- Scale
- Deployment environment
- Team capabilities
- Existing technology
- Migration requirements
- Acceptance criteria

If important information is missing, do not silently invent it.

Mark it:

```text
UNKNOWN
ASSUMPTION
NEEDS_VALIDATION
```

---

# 4. Phase 2 — Build the Requirements Model

Create four categories.

## Functional Requirements

What must the system do?

Examples:

- retrieve documents
- generate answers
- evaluate answers
- detect hallucinations
- store evaluation results
- expose an API
- run regression tests

## Non-Functional Requirements

Examples:

- latency
- throughput
- availability
- scalability
- determinism
- observability
- security
- privacy
- maintainability

## Constraints

Examples:

- existing Python stack
- existing vector database
- cloud provider
- budget
- deployment restrictions
- open-source requirement
- no external data transfer

## Quality Requirements

Examples:

- minimum faithfulness
- maximum hallucination rate
- retrieval recall
- citation accuracy
- test pass rate
- acceptable p95 latency

---

# 5. Phase 3 — The 10× Question Framework

For every important technical decision, generate at least **10 questions in each relevant category**.

Do not mechanically generate irrelevant questions. Select the categories that materially affect the decision.

## 10 WHAT Questions

1. What exactly are we building?
2. What problem does it solve?
3. What inputs does it require?
4. What outputs must it produce?
5. What components are involved?
6. What assumptions are we making?
7. What quality criteria matter?
8. What failure modes are possible?
9. What data is required?
10. What does success look like?

## 10 WHY Questions

1. Why do we need this capability?
2. Why is the current approach insufficient?
3. Why is this architecture appropriate?
4. Why choose this tool?
5. Why not use a simpler approach?
6. Why does this component need to exist?
7. Why does the chosen metric represent quality?
8. Why would users trust the result?
9. Why would this fail at scale?
10. Why might this decision need to be reversed later?

## 10 WHERE Questions

1. Where does the data originate?
2. Where is it stored?
3. Where is processing performed?
4. Where does retrieval occur?
5. Where are failures detected?
6. Where are logs stored?
7. Where are evaluations executed?
8. Where are secrets managed?
9. Where are performance bottlenecks likely?
10. Where should the system boundary be?

## 10 WHEN Questions

1. When should this component execute?
2. When should it not execute?
3. When should the system fail fast?
4. When should it retry?
5. When should it fall back?
6. When should a human review the result?
7. When should an answer be cached?
8. When should cached data expire?
9. When should evaluation block deployment?
10. When should the architecture be reconsidered?

## 10 WHO Questions

1. Who uses the system?
2. Who owns the component?
3. Who supplies the data?
4. Who consumes the output?
5. Who reviews failures?
6. Who is responsible for quality?
7. Who can change configuration?
8. Who can access sensitive data?
9. Who approves production deployment?
10. Who is affected when the system fails?

## 10 HOW Questions

1. How will the system work end to end?
2. How will each component communicate?
3. How will quality be measured?
4. How will failures be detected?
5. How will failures be recovered?
6. How will the system scale?
7. How will the implementation be tested?
8. How will regression be prevented?
9. How will costs be measured?
10. How will the system be monitored in production?

## 10 WHICH Questions

1. Which architecture fits the requirements?
2. Which implementation approach has the lowest complexity?
3. Which approach is easiest to test?
4. Which approach is easiest to operate?
5. Which approach minimizes lock-in?
6. Which tool has the required integrations?
7. Which metric best represents success?
8. Which component creates the greatest risk?
9. Which assumption should be validated first?
10. Which option remains viable if requirements change?

## 10 WHOSE Questions

1. Whose data are we processing?
2. Whose requirements define success?
3. Whose definitions determine correctness?
4. Whose infrastructure is involved?
5. Whose API or platform are we dependent on?
6. Whose security policies apply?
7. Whose evaluation criteria should be trusted?
8. Whose failure has operational impact?
9. Whose approval is required?
10. Whose perspective is missing from the design?

---

# 6. Phase 4 — Identify Candidate Options

For every problem, generate multiple solution families.

Typical families include:

1. Build from scratch
2. Use an existing open-source framework
3. Use a managed platform
4. Use a hybrid architecture
5. Use a minimal custom implementation
6. Use an existing internal service
7. Use a third-party API
8. Use a database-native capability
9. Use an LLM-as-a-judge approach
10. Use deterministic/programmatic validation
11. Use human evaluation
12. Use a layered/hybrid evaluator

Do not assume all families apply. Select the relevant ones.

---

# 7. Mandatory "5 Ways" Rule

For **every significant implementation option**, identify at least five ways to implement it.

Use this structure:

### Approach 1 — Minimal / Native

Describe the simplest implementation using existing application primitives.

### Approach 2 — Specialized Library

Use a focused library or framework.

### Approach 3 — Managed Service

Use an external/managed platform where appropriate.

### Approach 4 — Custom Architecture

Build the capability specifically for the application's requirements.

### Approach 5 — Hybrid

Combine deterministic logic, open-source components, managed services, and/or human review.

If these five categories do not make sense for the problem, replace them with five genuinely distinct approaches.

Never create artificial differences just to reach five.

---

# 8. Required Analysis for Every Approach

For each approach document:

```text
Approach
Description
Architecture
Required Components
Implementation Complexity
Operational Complexity
Expected Benefits
Drawbacks
Failure Modes
Security Considerations
Cost Considerations
Latency Considerations
Scalability
Observability
Testing Difficulty
Vendor Lock-in
Migration Difficulty
Best Use Cases
Poor Use Cases
Dependencies
Proof-of-Concept
Acceptance Criteria
```

Use:

```text
LOW
MEDIUM
HIGH
UNKNOWN
```

where qualitative classification is useful.

Do not invent numerical estimates without evidence.

---

# 9. Decision Matrix

Create a comparison matrix.

Recommended dimensions:

| Dimension | Option A | Option B | Option C |
|---|---|---|---|
| Implementation complexity | | | |
| Operational complexity | | | |
| Accuracy | | | |
| Reliability | | | |
| Latency | | | |
| Cost | | | |
| Scalability | | | |
| Observability | | | |
| Security | | | |
| Maintainability | | | |
| Vendor lock-in | | | |
| Extensibility | | | |
| Testing | | | |
| Migration risk | | | |

Do not create a numeric score unless the user explicitly requests one.

Instead explain the trade-offs.

---

# 10. Tool Research Method

When researching tools:

## Priority 1 — Official Sources

Prefer:

- official documentation
- official API references
- official GitHub repositories
- official changelogs
- official pricing
- official benchmarks
- original research papers

## Priority 2 — Independent Technical Evidence

Use:

- peer-reviewed papers
- engineering blogs
- reproducible benchmarks
- reputable technical analysis

## Priority 3 — Community Evidence

Use:

- GitHub issues
- developer forums
- Reddit
- community discussions

Treat community reports as experience evidence, not authoritative product specifications.

---

# 11. Tool Selection Method

For every candidate tool determine:

```text
What does it do?
Why would we use it?
What does it replace?
What does it depend on?
What does it cost?
Where does it run?
What data leaves our environment?
How mature is it?
How actively maintained is it?
How easy is it to test?
How easy is it to observe?
How easy is it to remove later?
```

Also inspect:

- API stability
- language support
- framework compatibility
- deployment model
- authentication
- rate limits
- concurrency
- retry behavior
- caching
- tracing
- metrics
- export capabilities
- data retention
- privacy
- licensing

---

# 12. LLM / RAG Evaluation Research Method

For an LLM or RAG system, separate evaluation into layers.

```text
Retrieval Evaluation
        ↓
Context Evaluation
        ↓
Generation Evaluation
        ↓
Claim Evaluation
        ↓
Citation Evaluation
        ↓
End-to-End Evaluation
        ↓
Production Evaluation
```

## Retrieval Metrics

Examples:

- distance/similarity
- recall@k
- precision@k
- MRR
- nDCG
- contextual relevance
- lexical grounding
- evidence coverage
- separation between top candidates

## Answer Metrics

Examples:

- relevance
- correctness
- completeness
- faithfulness
- groundedness
- coherence
- citation correctness
- citation completeness
- format correctness

## Operational Metrics

Examples:

- latency
- p50
- p95
- p99
- token usage
- cost per request
- error rate
- retry rate
- cache hit rate
- timeout rate

## Safety / Robustness

Examples:

- prompt injection
- data leakage
- unsafe tool calls
- unsupported claims
- adversarial inputs
- malformed inputs
- retrieval poisoning
- instruction conflicts

---

# 13. Evaluation Strategy Selection

For every evaluation problem, consider five approaches:

### 1. Deterministic Evaluation

Use rules, assertions, schemas, regex, exact match, thresholds, or programmatic checks.

**Best when:**
- output structure is known
- exact values matter
- failures can be objectively defined

**Drawbacks:**
- weak for subjective quality
- brittle for natural language
- can miss semantic errors

### 2. Reference-Based Evaluation

Compare output with a known expected answer.

**Best when:**
- golden answers exist
- correctness is well defined

**Drawbacks:**
- expensive to create goldens
- multiple valid answers can cause false failures

### 3. LLM-as-a-Judge

Use another model to evaluate the output against a rubric.

**Best when:**
- semantic quality matters
- subjective criteria must be evaluated
- reference answers are incomplete

**Drawbacks:**
- evaluator bias
- judge instability
- model correlation
- cost
- judge can hallucinate

### 4. Human Evaluation

Use expert reviewers.

**Best when:**
- stakes are high
- domain expertise is required
- automated evaluation is uncertain

**Drawbacks:**
- expensive
- slower
- reviewer disagreement
- difficult to scale

### 5. Hybrid Evaluation

Combine deterministic rules, LLM judges, automated metrics, and human review.

**Best when:**
- production quality matters
- different failure types require different validators

**Drawbacks:**
- greater implementation complexity
- more infrastructure
- more calibration work

---

# 14. Current Tool Categories to Investigate

For LLM evaluation and RAG work, investigate tools from multiple categories rather than assuming one framework solves everything.

Examples include:

- DeepEval
- promptfoo
- LangSmith
- Ragas
- Arize Phoenix
- OpenTelemetry-compatible tracing
- native model-provider evaluation APIs
- custom Python/Pytest evaluation infrastructure

The tool choice must be driven by requirements.

For example:

```text
Need CI regression testing
→ investigate pytest / DeepEval / promptfoo

Need prompt/model comparison
→ investigate promptfoo / LangSmith

Need RAG-specific metrics
→ investigate Ragas / DeepEval

Need detailed traces and production observability
→ investigate OpenTelemetry / Phoenix / LangSmith

Need maximum control
→ build deterministic Python evaluation infrastructure

Need high-stakes validation
→ combine automated evaluation with human review
```

This is a starting point, not a fixed recommendation.

---

# 15. Recommended Evaluation Architecture for the Current RAG Quality Problem

For a RAG answer-quality system, investigate a layered architecture:

```text
                    USER QUERY
                        │
                        ▼
                 RETRIEVAL LAYER
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
    Retrieval Metrics          Retrieved Evidence
          │                           │
          └─────────────┬─────────────┘
                        ▼
                 RETRIEVAL GATE
                        │
              ┌─────────┴─────────┐
              │                   │
            FAIL                PASS
              │                   │
          EARLY EXIT              ▼
                           LLM GENERATION
                                  │
                                  ▼
                         CLAIM EXTRACTION
                                  │
                                  ▼
                       EVIDENCE VERIFICATION
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
             Citation Check              Hallucination Check
                    │                           │
                    └─────────────┬─────────────┘
                                  ▼
                           QUALITY SCORING
                                  │
                                  ▼
                         PASS / REVIEW / FAIL
                                  │
                                  ▼
                              CACHE GATE
```

---

# 16. Quality-Gate Design

Avoid relying on one score.

Use a combination of:

```text
Hard Gates
+
Soft Metrics
+
Critical-Failure Overrides
```

Example:

### Hard Gates

- no evidence → FAIL/REVIEW
- invalid retrieval → do not treat answer as grounded
- schema failure → FAIL
- fabricated citation → REVIEW/FAIL depending on severity
- evidence contradiction → FAIL when material

### Soft Metrics

- relevance
- completeness
- coherence
- tone
- answer quality

### Critical Overrides

A critical hallucination can fail an answer even when the average score is high.

---

# 17. Cache Quality Method

Do not cache an answer merely because generation succeeded.

Cache only when:

1. retrieval quality passes
2. answer quality passes
3. grounding passes
4. no material contradiction exists
5. citation integrity passes when citations are required
6. evaluation confidence is adequate

Store evaluation metadata with the cached answer:

```json
{
  "answer": "...",
  "quality_gate": "PASS",
  "retrieval_quality": "STRONG",
  "grounding_score": 0.92,
  "evaluation_version": "1.0",
  "created_at": "...",
  "model": "...",
  "retrieval_config": "...",
  "evaluator": "..."
}
```

---

# 18. Proof-of-Concept Method

Before production implementation:

## Step 1

Create a small representative dataset.

Include:

- easy cases
- normal cases
- difficult cases
- ambiguous cases
- no-answer cases
- adversarial cases
- hallucination traps
- citation failures
- retrieval failures

## Step 2

Create expected outcomes.

## Step 3

Run at least two or more candidate implementations.

## Step 4

Compare:

- quality
- false positives
- false negatives
- latency
- cost
- engineering effort

## Step 5

Investigate disagreement cases manually.

## Step 6

Calibrate thresholds.

## Step 7

Freeze the evaluation dataset.

## Step 8

Use it as a regression suite.

---

# 19. Research Output Format

When this skill is invoked, produce the following structure unless the user asks for another format.

```text
# 1. Executive Summary

# 2. Problem Definition

# 3. Requirements

# 4. Assumptions

# 5. Unknowns

# 6. 10× Question Analysis

## What
## Why
## Where
## When
## Who
## How
## Which
## Whose

# 7. Candidate Solution Families

# 8. Five Implementation Approaches Per Candidate

## Approach 1
### Architecture
### Benefits
### Drawbacks
### Use When
### Avoid When
### Risks
### POC

## Approach 2
...

# 9. Tool Comparison

# 10. Architecture Options

# 11. Decision Trade-offs

# 12. Recommended Experiment / POC

# 13. Evaluation Plan

# 14. Acceptance Criteria

# 15. Failure Modes

# 16. Security / Privacy

# 17. Cost / Performance

# 18. Production Readiness

# 19. Implementation Plan

# 20. Open Questions

# 21. Sources
```

---

# 20. "Use When / Don't Use When" Rule

Every tool, architecture, library, or methodology recommendation MUST include:

### Use When

At least 3 concrete situations.

### Don't Use When

At least 3 concrete situations.

### Good Fit

Describe the environment where the option works particularly well.

### Poor Fit

Describe conditions where another option should be investigated.

---

# 21. "Five Ways" Rule for Coding

When the user asks "How do I implement X?", provide five distinct implementation strategies where practical.

Example:

```text
Problem: Evaluate RAG answers

Way 1: Pure Python deterministic evaluator
Way 2: Pytest + custom evaluators
Way 3: DeepEval
Way 4: Promptfoo
Way 5: Hybrid evaluator + observability platform
```

For each:

```text
Architecture
Code shape
Dependencies
Pros
Cons
Use cases
Failure modes
Testing
Deployment
Migration
```

Do not claim that one option is universally best.

---

# 22. Implementation Detail Requirement

When recommending a technical approach, go beyond conceptual architecture.

Provide, when relevant:

- package structure
- interfaces
- data models
- configuration
- API boundaries
- pseudocode
- test strategy
- error handling
- logging
- metrics
- tracing
- deployment
- migration plan

Prefer small interfaces.

Example:

```python
class Evaluator:
    def evaluate(self, case: EvaluationCase) -> EvaluationResult:
        ...
```

Keep deterministic logic separate from model-based judgment.

---

# 23. Separate Deterministic and Probabilistic Logic

Use deterministic code for:

- thresholds
- schema validation
- counts
- exact comparisons
- latency
- token accounting
- citation existence
- JSON validation
- cache policies

Use model-based evaluation for:

- semantic relevance
- nuanced completeness
- groundedness
- subjective quality
- tone
- complex correctness judgments

Use humans for:

- high-stakes decisions
- ambiguous domain judgments
- evaluator calibration
- disputes between automated evaluators

---

# 24. Evaluation Calibration

Never trust an evaluator simply because it produces scores.

Measure:

- agreement with human labels
- false positive rate
- false negative rate
- evaluator variance
- score distribution
- threshold sensitivity
- disagreement examples

Create a calibration set.

Example:

```text
100 test cases
30 clearly good
30 clearly bad
20 borderline
10 retrieval failures
10 adversarial
```

Then compare evaluator decisions against human judgments.

---

# 25. Regression Testing

Every production change that can affect quality should trigger evaluation.

Examples:

- model change
- prompt change
- retrieval change
- embedding model change
- chunking change
- reranker change
- vector database change
- evaluator change
- system prompt change
- tool change

Track:

```text
Before
vs
After
```

Never optimize one metric while ignoring regressions in another critical metric.

---

# 26. Research Tooling Strategy

When external research is available:

1. Search official documentation first.
2. Search original papers for algorithms and evaluation methodologies.
3. Search current release/changelog information.
4. Search independent technical evidence.
5. Search community reports for operational problems.
6. Cross-check important claims using at least two sources.
7. Record source date.
8. Distinguish documented capability from personal reports.
9. Do not treat marketing claims as benchmarks.
10. Record unresolved uncertainty.

---

# 27. Source Quality Labels

Label evidence as:

```text
PRIMARY
OFFICIAL
ACADEMIC
INDEPENDENT
COMMUNITY
INFERENCE
UNKNOWN
```

Example:

```text
PRIMARY:
Original research paper defining the metric.

OFFICIAL:
Vendor documentation describing API behavior.

INDEPENDENT:
Third-party benchmark.

COMMUNITY:
GitHub issue describing an operational problem.

INFERENCE:
Conclusion derived from multiple observations.
```

---

# 28. Anti-Bias Rules

Do not choose a tool because:

- it is popular
- it is newer
- it has more GitHub stars
- it has more features
- it has a polished UI
- it is from a familiar company
- it appears in many tutorials

Choose based on the user's actual requirements.

Avoid vendor lock-in unless it provides a measurable benefit that justifies the dependency.

---

# 29. Failure-First Research

For every proposed solution ask:

1. What is the most likely failure?
2. What is the most expensive failure?
3. What is the hardest failure to detect?
4. What failure is silent?
5. What failure appears correct?
6. What happens when dependencies are unavailable?
7. What happens when the model is wrong?
8. What happens when retrieval is wrong?
9. What happens when data is corrupted?
10. What happens during migration?

---

# 30. Final Decision Method

Do not simply say:

> "Use Tool X."

Instead produce:

```text
Decision Context

Option A:
Best suited for ...
Main trade-off ...

Option B:
Best suited for ...
Main trade-off ...

Option C:
Best suited for ...
Main trade-off ...

Decision Rule:

Choose A if ...
Choose B if ...
Choose C if ...

Recommended POC:

Test A and B using the same dataset and acceptance criteria.
```

If the evidence strongly supports one approach for the stated constraints, say so as a technical recommendation, while clearly identifying the assumptions behind that recommendation.

---

# 31. Deliverable Quality Checklist

Before completing the research, verify:

- [ ] Problem is clearly defined.
- [ ] Requirements are explicit.
- [ ] Unknowns are identified.
- [ ] Assumptions are labeled.
- [ ] Relevant 10× questions were explored.
- [ ] Multiple solution families were considered.
- [ ] Five implementation approaches were considered for each significant option.
- [ ] Drawbacks were documented.
- [ ] Use cases were documented.
- [ ] Poor-fit cases were documented.
- [ ] Failure modes were documented.
- [ ] Security was considered.
- [ ] Cost was considered.
- [ ] Latency was considered.
- [ ] Scalability was considered.
- [ ] Observability was considered.
- [ ] Testing was considered.
- [ ] Migration was considered.
- [ ] Acceptance criteria exist.
- [ ] A POC strategy exists.
- [ ] Research sources are identified.
- [ ] Current capabilities were verified where relevant.
- [ ] Facts are separated from inference.
- [ ] No unsupported tool claims were introduced.

---

# 32. Specialization for LLM Evaluation / RAG Projects

For the current class of project, treat these as first-class concerns:

```text
Retrieval Quality
Answer Quality
Grounding
Hallucination
Citation Integrity
Completeness
Relevance
Accuracy
Consistency
Evaluation Reliability
Judge Bias
Dataset Quality
Regression Detection
Latency
Token Cost
Caching
Observability
Security
Prompt Injection
Production Monitoring
```

Use layered evaluation rather than a single "LLM score."

A production-quality research plan should investigate at least:

1. deterministic quality gates
2. reference-based evaluation
3. LLM-as-a-judge
4. human evaluation
5. hybrid evaluation

Then compare them against the project's requirements.

---

# 33. Continuous Improvement Loop

The final architecture should support:

```text
Production Data
      ↓
Failure Samples
      ↓
Evaluation Dataset
      ↓
Metric / Prompt Improvements
      ↓
Regression Tests
      ↓
POC
      ↓
Production
      ↓
Monitoring
      ↓
New Failure Samples
      ↺
```

Every production failure should become a candidate evaluation case.

The goal is not merely to build an evaluator.

The goal is to build an **evaluation system that becomes more reliable as the application evolves**.

---

# 34. Default Research Mindset

When uncertain, ask:

> "What evidence would change our decision?"

Then design the smallest experiment capable of obtaining that evidence.

Prefer:

```text
Hypothesis
→ Experiment
→ Measurement
→ Evidence
→ Decision
```

over:

```text
Opinion
→ Tool choice
→ Implementation
→ Hope
```

---

# 35. End State

A successful application of this skill should leave the engineering team with:

1. A clear problem definition.
2. Explicit requirements.
3. Known assumptions and unknowns.
4. A structured research question set.
5. Multiple viable solution families.
6. Five concrete implementation approaches per major option.
7. Trade-offs and drawbacks.
8. Appropriate and inappropriate use cases.
9. A tool-selection rationale.
10. A proof-of-concept plan.
11. Measurable acceptance criteria.
12. A test/evaluation strategy.
13. A production architecture.
14. A migration strategy.
15. A monitoring strategy.
16. A list of unresolved questions.
17. A source-backed record of important technical decisions.

The skill should optimize for **evidence-backed engineering decisions, reproducibility, maintainability, and measurable outcomes**, not for producing the longest possible research document.
