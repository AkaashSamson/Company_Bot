# Detailed Technical Notes Report Generator

## Purpose

Transform a collection of technical notes, conversations, documents, experiments, explanations, and learning material into a **comprehensive, structured technical report**.

The objective is not to simply summarize the notes.

The objective is to:

* Extract all important knowledge.
* Preserve important details and terminology.
* Organize fragmented notes into a coherent knowledge structure.
* Identify relationships between concepts.
* Separate facts, observations, assumptions, decisions, and recommendations.
* Capture examples and practical applications.
* Preserve important questions and unresolved issues.
* Identify knowledge gaps.
* Highlight contradictions or inconsistencies without silently resolving them.
* Convert scattered learning into reusable revision material.
* Connect theory to practical implementation.
* Produce a report that can be used later for learning, revision, implementation, and decision-making.

---

# 1. When to Use

Use this skill when the user asks to:

* Make detailed notes from conversations.
* Create a report from multiple notes.
* Summarize a technical learning journey.
* Consolidate previous discussions.
* Turn notes into revision material.
* Create documentation from learning material.
* Extract knowledge from conversations/files.
* Create a technical knowledge base.
* Review everything learned about a topic.
* Create a comprehensive report from multiple sources.

Examples:

> "Make detailed notes from everything we discussed about Kafka."

> "Create a report from all my Redis notes."

> "Consolidate everything we learned about caching."

> "Turn this conversation into revision notes."

> "Create a detailed technical report from these documents."

---

# 2. Core Principle

Do not treat the source material as a collection of isolated messages.

Treat it as a **knowledge system**.

Use:

```text
Raw Notes
   ↓
Extract
   ↓
Normalize
   ↓
Classify
   ↓
Connect
   ↓
Organize
   ↓
Analyze
   ↓
Identify Gaps
   ↓
Synthesize
   ↓
Validate Against Sources
   ↓
Detailed Report
```

The report should make the user's existing knowledge **easier to understand and retrieve** without silently replacing it with unrelated external knowledge.

---

# 3. Source Fidelity

The source material is the primary authority for the report.

Preserve:

* Terminology
* Definitions
* Examples
* Architecture descriptions
* Decisions
* Questions
* Problems
* Reasoning
* Tradeoffs
* Conclusions
* Experiments
* User observations
* Project-specific context

Do not silently:

* Correct a source claim.
* Replace a source explanation.
* Invent missing information.
* Resolve contradictions without evidence.
* Introduce external knowledge as if it came from the notes.

If additional knowledge is introduced, clearly label it.

Use categories such as:

```text
SOURCE-DERIVED
MODEL INFERENCE
EXTERNAL CONTEXT
OPEN QUESTION
```

---

# 4. First Pass — Inventory the Material

Before writing the report, identify all available material.

Sources may include:

* Conversations
* Uploaded documents
* Markdown files
* PDFs
* Code
* Architecture diagrams
* Experiments
* Logs
* Questions
* Previous reports
* Revision notes
* Project documentation

Create an internal inventory:

```text
Source
├── Topic
├── Subtopics
├── Important concepts
├── Decisions
├── Questions
├── Examples
├── Experiments
├── Conclusions
└── Gaps
```

Do not begin synthesis before understanding what material exists.

---

# 5. Extract Knowledge

Extract information rather than merely extracting sentences.

Identify:

### Concepts

What concepts were discussed?

### Definitions

How were they defined?

### Problems

What problems were being solved?

### Mechanisms

How were things explained to work?

### Architecture

What components and relationships were described?

### Examples

What concrete examples were provided?

### Decisions

What choices were made?

### Reasoning

Why were those choices made?

### Tradeoffs

What benefits and costs were discussed?

### Failures

What problems or failure modes were identified?

### Experiments

What was tested?

### Results

What happened?

### Questions

What remained unclear?

### Insights

What important conclusions were reached?

---

# 6. Classify Every Important Piece of Information

Classify information into useful categories.

```text
FACT
OBSERVATION
DEFINITION
EXPLANATION
ASSUMPTION
QUESTION
HYPOTHESIS
EXPERIMENT
RESULT
DECISION
TRADEOFF
RECOMMENDATION
WARNING
FAILURE MODE
BEST PRACTICE
OPEN ISSUE
```

Do not treat all statements as equally authoritative.

For example:

```text
FACT:
The system uses Redis.

OBSERVATION:
Repeated requests were identified as a performance concern.

ASSUMPTION:
Caching those responses will reduce expensive calls.

DECISION:
A cache was implemented.

OPEN QUESTION:
Whether semantic caching produces acceptable answer quality.
```

---

# 7. Preserve the Evolution of Thinking

When the notes show that the user's understanding changed over time, preserve that evolution.

Show:

```text
Initial Understanding
        ↓
Problem Encountered
        ↓
New Information
        ↓
Changed Understanding
        ↓
New Decision
```

Do not erase earlier misunderstandings if they are useful for learning.

They may reveal:

* Why a concept was difficult.
* What misconception existed.
* What caused the misconception.
* What finally clarified it.

These are valuable learning artifacts.

---

# 8. Organize Into a Knowledge Hierarchy

Do not organize the report purely chronologically.

Prefer conceptual organization.

Typical structure:

```text
Topic
├── 1. Problem
├── 2. Motivation
├── 3. Core Concepts
├── 4. Mental Model
├── 5. Architecture
├── 6. Components
├── 7. Mechanisms
├── 8. Data / Request Flow
├── 9. Failure Modes
├── 10. Tradeoffs
├── 11. Alternatives
├── 12. Practical Application
├── 13. Project Context
├── 14. Decisions
├── 15. Experiments
├── 16. Lessons Learned
├── 17. Open Questions
└── 18. Future Learning
```

Adapt the hierarchy to the actual material.

Do not force irrelevant sections.

---

# 9. Connect Related Notes

Identify concepts that were discussed separately but are related.

For example:

```text
Caching
   ├── LRU Cache
   ├── Semantic Cache
   ├── Redis
   ├── Cache Quality
   ├── TTL
   └── Cache Invalidation
```

Then explain their relationships.

Use:

```text
Concept A
   ↓
affects
   ↓
Concept B
   ↓
creates tradeoff with
   ↓
Concept C
```

The report should reveal the **knowledge graph** hidden inside the notes.

---

# 10. Detect Repetition

When the same concept appears multiple times:

1. Combine the explanations.
2. Preserve unique information.
3. Remove unnecessary repetition.
4. Mention important changes in understanding.

Do not simply repeat the same explanation multiple times.

However, preserve repetition when it represents:

* A changed conclusion.
* A new insight.
* A different example.
* A recurring problem.
* An important learning pattern.

---

# 11. Detect Contradictions

Look for statements that conflict.

Examples:

```text
Note A:
"Redis is being used for response caching."

Note B:
"Redis has not yet been integrated."
```

Do not silently choose one.

Report:

```text
Potential Contradiction

Source A indicates X.

Source B indicates Y.

The available material does not establish which state is current.
```

If dates or chronology resolve the contradiction, explain that explicitly.

---

# 12. Identify Knowledge Gaps

A detailed report should identify what the notes **do not establish**.

Examples:

* Missing implementation details.
* Unverified assumptions.
* Unanswered questions.
* Missing benchmarks.
* Missing failure testing.
* Missing production data.
* Missing documentation.
* Missing architectural decisions.

Use:

```text
Known
─────
Supported by the notes.

Unknown
───────
Not established by the notes.

Needs Validation
─────────────────
A claim exists but requires evidence.

Next Question
──────────────
The most useful question to investigate next.
```

---

# 13. Build Mental Models

For important concepts, create concise mental models.

Use:

```text
Problem
   ↓
Mechanism
   ↓
System Behavior
   ↓
Tradeoff
   ↓
Use Case
```

Example:

```text
Repeated expensive computation
        ↓
Store previous result
        ↓
Reuse result on future request
        ↓
Lower latency / cost
        ↓
Must handle stale or incorrect data
```

The report should help the reader **visualize the concept**, not merely memorize definitions.

---

# 14. Capture "Why"

For each major design or concept, extract:

```text
What?
Why?
How?
Why this approach?
What alternative existed?
What tradeoff was accepted?
When does it stop being appropriate?
```

Do not document only what was done.

Document the reasoning behind it whenever the source material supports that reasoning.

---

# 15. Capture Tradeoffs

For important decisions, use:

| Decision | Benefit | Cost | Risk | Alternative |
| -------- | ------- | ---- | ---- | ----------- |
|          |         |      |      |             |

Never present a technical decision as universally correct unless the source material establishes that.

---

# 16. Capture Experiments

For every experiment or implementation attempt, document:

```text
Experiment
───────────
Goal:

Hypothesis:

Setup:

Change:

Expected Result:

Observed Result:

Actual Result:

What Was Learned:

Unexpected Behavior:

Next Experiment:
```

This converts experimentation into reusable engineering knowledge.

---

# 17. Capture Failures

Failures are important learning material.

Document:

```text
Failure
   ↓
Symptoms
   ↓
Possible Causes
   ↓
Investigation
   ↓
Root Cause
   ↓
Fix
   ↓
Lesson
   ↓
Prevention
```

If the root cause was not established, say:

> Root cause not confirmed.

Do not invent one.

---

# 18. Capture Project Application

If the notes relate to a real project, create a dedicated section:

## Application to the Project

Include:

* Current architecture.
* Relevant components.
* Current implementation.
* Problems identified.
* Proposed changes.
* Decisions already made.
* Risks.
* Open questions.
* Experiments.
* Future improvements.

Clearly distinguish:

```text
CURRENT STATE
PROPOSED STATE
PLANNED WORK
OPEN QUESTION
```

Do not describe planned work as completed work.

---

# 19. Create a Decision Log

Extract important decisions.

Use:

| Decision | Context | Reason | Alternatives | Status |
| -------- | ------- | ------ | ------------ | ------ |
|          |         |        |              |        |

Possible statuses:

* Proposed
* Discussed
* Accepted
* Implemented
* Rejected
* Superseded
* Unknown

---

# 20. Create a Question Log

Capture important questions from the notes.

Group them:

### Answered

Questions with sufficient answers.

### Partially Answered

Questions with incomplete answers.

### Unanswered

Questions requiring future investigation.

### New Questions

Questions generated by later understanding.

This preserves the user's learning trajectory.

---

# 21. Create a Key Insights Section

Extract the most important insights.

Do not simply copy sentences.

Convert them into concise principles.

Example:

```text
Insight:
A cache is not merely a performance optimization; it introduces
correctness concerns because stale or low-quality data can be reused.
```

Only include insights supported by the source material or clearly mark them as synthesis/inference.

---

# 22. Create a "What I Learned" Section

Summarize the actual learning outcomes.

Organize into:

```text
I now understand...
I can explain...
I can implement...
I can debug...
I can compare...
I still need to learn...
```

This should reflect the material, not invent achievements.

---

# 23. Create Revision Notes

After the detailed report, create a compact revision layer.

Include:

### Key Concepts

### Important Definitions

### Core Mental Models

### Important Commands / APIs

Only include commands/APIs if present in the source material.

### Important Tradeoffs

### Common Failure Modes

### Important Decisions

### Questions to Recall

### Things to Remember

---

# 24. Create Active Recall Questions

Generate questions from the report.

Group them by difficulty.

## Level 1 — Recall

"What is X?"

## Level 2 — Understanding

"Why does X exist?"

## Level 3 — Application

"When would you use X?"

## Level 4 — Troubleshooting

"What could cause X to fail?"

## Level 5 — Engineering Judgment

"Given constraints A, B, and C, what factors would determine the design?"

Questions must be answerable from the report unless explicitly marked as requiring additional knowledge.

---

# 25. Create a Knowledge Map

At the end of the report, create a compact relationship map.

Example:

```text
Problem
  │
  ├── Requirement
  │      │
  │      └── Architecture
  │             │
  │             ├── Component A
  │             ├── Component B
  │             └── Component C
  │
  ├── Tradeoffs
  │
  ├── Failure Modes
  │
  └── Decisions
```

Use Mermaid when appropriate and when the environment supports it.

---

# 26. Separate Source and Synthesis

The final report should distinguish:

### Source-Derived

Directly supported by the provided material.

### Synthesized

Combined from multiple pieces of the material.

### Inferred

A conclusion derived from the material but not explicitly stated.

### External Context

Information introduced from outside the source.

### Unverified

Claims that cannot currently be confirmed.

This prevents accidental hallucination.

---

# 27. Do Not Over-Summarize

The report is intended to preserve knowledge.

Therefore:

Do not reduce:

```text
50 pages → 1 page
```

unless the user specifically requests a short summary.

Instead create multiple layers:

```text
Executive Summary
        ↓
Detailed Report
        ↓
Key Insights
        ↓
Revision Notes
        ↓
Active Recall Questions
```

This provides both depth and quick revision.

---

# 28. Recommended Report Structure

Unless the user requests another structure, use:

```text
# Technical Knowledge Report

## 1. Executive Summary

## 2. Scope and Sources

## 3. Learning / Project Context

## 4. Core Problems

## 5. Key Concepts

## 6. Mental Models

## 7. Detailed Explanations

## 8. Architecture / System Model

## 9. Components and Relationships

## 10. How the System Works

## 11. Why the Design Exists

## 12. Alternatives and Tradeoffs

## 13. Failure Modes

## 14. Experiments and Results

## 15. Project Application

## 16. Decisions and Rationale

## 17. Evolution of Understanding

## 18. Important Insights

## 19. Contradictions / Uncertainties

## 20. Knowledge Gaps

## 21. Open Questions

## 22. Lessons Learned

## 23. Revision Notes

## 24. Active Recall Questions

## 25. Knowledge Map

## 26. Recommended Next Learning Steps
```

Only include sections that are relevant.

---

# 29. Report Quality Checklist

Before finalizing, verify:

### Coverage

* [ ] All important sources were reviewed.
* [ ] Major topics were captured.
* [ ] Important examples were preserved.
* [ ] Important questions were preserved.
* [ ] Important decisions were captured.

### Accuracy

* [ ] No unsupported claims were introduced.
* [ ] Source-derived information is distinguishable.
* [ ] Inferences are identified.
* [ ] Uncertainty is explicit.
* [ ] Contradictions are not silently resolved.

### Structure

* [ ] Related concepts are grouped.
* [ ] Repetition is consolidated.
* [ ] Dependencies and relationships are explained.
* [ ] The report follows a logical conceptual structure.

### Learning Value

* [ ] Mental models are included.
* [ ] Why/how explanations are present.
* [ ] Tradeoffs are captured.
* [ ] Failure modes are included.
* [ ] Active recall questions are included.
* [ ] Knowledge gaps are identified.

### Practical Value

* [ ] Project application is documented.
* [ ] Experiments are captured.
* [ ] Decisions are recorded.
* [ ] Open questions are identified.
* [ ] Next learning steps are clear.

---

# 30. AI Agent Operating Rules

When generating the report:

1. Read all relevant material before synthesizing.
2. Do not rely on a single note when multiple sources exist.
3. Preserve source terminology.
4. Do not silently correct source material.
5. Do not invent missing information.
6. Distinguish facts from interpretation.
7. Preserve important uncertainty.
8. Preserve evolution of understanding.
9. Detect contradictions.
10. Connect related concepts.
11. Remove unnecessary repetition.
12. Preserve unique examples.
13. Identify knowledge gaps.
14. Identify unanswered questions.
15. Prefer conceptual organization over chronological organization.
16. Keep project-specific information separate from generic concepts.
17. Never claim something was implemented if the source only says it was planned.
18. Never claim an experiment succeeded unless the source records the result.
19. Never turn an assumption into a fact.
20. Optimize for future retrieval and understanding.

---

# 31. Final Objective

The final report should function as a **personal technical knowledge base**.

It should allow the user to:

```text
Review what they learned
        ↓
Understand the concepts
        ↓
Remember the important details
        ↓
Understand why decisions were made
        ↓
Recall previous mistakes
        ↓
Apply the knowledge
        ↓
Identify what they still don't know
        ↓
Determine what to learn next
```

The objective is not simply:

> "Summarize my notes."

It is:

> **Transform fragmented learning into a structured, traceable, reusable body of technical knowledge without losing the reasoning, uncertainty, decisions, experiments, and questions that produced that knowledge.**
