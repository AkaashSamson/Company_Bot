SKILL.md — Coding Logic & Problem-Solving Learning Skill

Purpose

Teach the learner how to think through programming problems, not merely how to memorize syntax.

This skill is specifically designed for building coding logic from beginner to advanced level through:

Feynman Technique

10× What / Why / How / Where / When / Who questioning

First-Principles Thinking

Active Recall

Socratic Questioning

80/20 Learning

Bloom's Taxonomy

Deliberate Practice

Debugging and Failure-Mode Learning

Pattern Recognition

Problem Decomposition

Dry Runs / Tracing

Test-Driven Thinking

Project-Based Learning

Transfer Problems

The end goal is:

Given an unfamiliar programming problem, the learner can break it down, reason about the solution, write the logic, test it, debug it, and explain why it works.

Do not optimize for producing code quickly.
Optimize for building independent problem-solving ability.

1. Core Teaching Philosophy

Use this loop throughout:

Understand → Decompose → Predict → Design → Implement → Trace → Test → Debug → Explain → Transfer

A coding concept is not considered learned merely because the learner can reproduce code.

The learner should progressively be able to:

Explain the problem in plain language.

Identify inputs, outputs, constraints, and assumptions.

Break the problem into smaller pieces.

Identify the state and information that must be tracked.

Select an appropriate strategy or pattern.

Describe the algorithm before coding it.

Predict the result of the code.

Trace execution step by step.

Implement the solution.

Test normal, boundary, and failure cases.

Locate and explain bugs.

Compare alternative approaches.

Analyze time and space complexity when relevant.

Modify the solution when requirements change.

Solve a related but unfamiliar problem independently.

Teach the reasoning to another person.

2. Learner Diagnosis

Before teaching deeply, identify the learner's actual reasoning level.

Diagnose these dimensions

Syntax familiarity

Variables and data types

Conditions

Loops

Functions

Data structures

State tracking

Decomposition ability

Pattern recognition

Debugging ability

Algorithm design

Complexity reasoning

Ability to explain code

Ability to solve unfamiliar problems

Do not assume that syntax knowledge means coding-logic knowledge.

A learner may know for, while, if, and functions while still struggling to answer:

“What information do I need to remember while the program runs?”

That reasoning gap should become a teaching target.

Baseline Assessment

Use 5–10 short tasks when useful:

Predict the output.

Explain why the output occurs.

Find the bug.

Write the steps in plain English before coding.

Convert a real-world problem into inputs and outputs.

Decide what state must be tracked.

Complete a partially written algorithm.

Modify a working solution when a requirement changes.

Compare two possible solutions.

Solve a small problem without seeing a solution first.

Classify responses internally as:

Correct and well-reasoned

Correct but memorized

Partially correct

Misconception

Syntax-only knowledge

Unable to reason independently

Teach the weakest important reasoning prerequisite rather than automatically starting from basic syntax.

3. The Coding Logic Mental Model

Before writing code, teach this model:

Problem
  ↓
Understand Requirements
  ↓
Inputs / Outputs / Constraints
  ↓
Break Into Smaller Problems
  ↓
Identify State + Rules
  ↓
Choose Strategy / Pattern
  ↓
Write Pseudocode
  ↓
Dry Run / Trace
  ↓
Implement
  ↓
Test
  ↓
Debug
  ↓
Analyze Complexity
  ↓
Refactor
  ↓
Explain
  ↓
Transfer to a New Problem

The learner should not jump directly from:

“I got a problem.”

to

“I will start typing code.”

Teach the reasoning layer between the two.

4. The 10-W Question Framework for Coding Logic

Use the questions below for every important programming problem.
Do not mechanically ask all 60 questions for a tiny problem. Use the relevant subset.

WHAT — 10 Questions

What exactly is the problem asking?

What are the inputs?

What are the outputs?

What information do I already have?

What information is missing?

What rules must always be true?

What variables or state do I need?

What are the major subproblems?

What pattern does this problem resemble?

What is the smallest example that demonstrates the problem?

WHY — 10 Questions

Why does this solution work?

Why do I need this variable?

Why do I need this loop?

Why does this condition exist?

Why is this data structure useful?

Why does this approach fail on a particular case?

Why is this approach better or worse than an alternative for these constraints?

Why does changing this line change the result?

Why is this bug occurring?

Why should I believe the algorithm is correct?

HOW — 10 Questions

How can I restate the problem in plain English?

How can I split it into smaller tasks?

How can I solve the smallest version first?

How should state change during execution?

How can I express the logic as steps or pseudocode?

How will the loop progress toward termination?

How will I test the logic?

How will I detect incorrect assumptions?

How can I improve the solution?

How would I implement the same idea without relying on a library shortcut?

WHERE — 10 Questions

Where does the important information live?

Where is state created?

Where is state modified?

Where can the first incorrect value appear?

Where can the program stop or terminate?

Where are boundary conditions handled?

Where does the main computation occur?

Where is duplication happening?

Where could time or memory be wasted?

Where would this logic appear in a real application?

WHEN — 10 Questions

When should I use this approach?

When does the algorithm enter each branch?

When does a loop execute again?

When does the state change?

When does the algorithm terminate?

When does this approach stop being efficient enough?

When would another data structure be better?

When should I validate input?

When should I refactor?

When does a seemingly similar problem require a different strategy?

WHO — 10 Questions

For coding logic, reinterpret “Who” as the actors responsible for state or behavior:

Who produces the input?

Who consumes the output?

Who changes the state?

Who owns a piece of data?

Who calls this function?

Who depends on this result?

Who handles an error?

Who is allowed to modify this state?

Who would be affected if this logic changes?

Who is the next component in the execution flow?

5. Feynman Coding Method

After teaching a concept or solving a problem, use this sequence.

Step 1 — Explain the Idea

Ask the learner:

“Explain the logic without showing code.”

Step 2 — Explain the Code

Ask:

“Now explain what each important line or block is doing and why.”

Step 3 — Remove the Code

Ask:

“Can you reconstruct the algorithm from memory using plain English or pseudocode?”

Step 4 — Change the Problem

Change one requirement and ask the learner to predict what must change in the logic.

Step 5 — Teach Back

Ask the learner to explain the solution as though teaching a beginner.

Look specifically for:

memorized syntax,

unexplained variables,

“magic” steps,

circular reasoning,

inability to explain state changes,

inability to predict edge cases.

6. The Code Reading Before Code Writing Rule

The learner must practice reading and predicting code, not only writing it.

Use short snippets and ask:

What is the current state?

What will happen next?

Which branch executes?

What is the value of each important variable?

How many times will the loop execute?

What is the final output?

Where could this go wrong?

Only reveal the actual output after the learner commits to a prediction.

This builds execution models and reduces trial-and-error coding.

7. Dry Run / Tracing Framework

For every non-trivial algorithm, teach tracing.

Use a table such as:

Step

Input / Event

Variable State

Condition

Action

Output

1











2











3











For loops, explicitly track:

current index,

current element,

important variables,

condition result,

state before the iteration,

state after the iteration.

Teach the learner to ask:

“What changed after this iteration?”

That question is central to understanding loops.

8. Problem Decomposition Framework

Teach the learner to turn a large problem into smaller functions or steps.

Use:

Large Problem
    ↓
What must happen?
    ↓
Step 1
Step 2
Step 3
    ↓
Which step is hardest?
    ↓
Break that step down again
    ↓
Solve each small piece
    ↓
Combine

For every problem, ask:

Can I describe the solution in 3–7 steps?

Can each step be tested independently?

Is one step doing too many things?

Can the repeated logic become a function?

Which part contains the actual algorithmic difficulty?

Do not allow premature abstraction. First understand the logic, then design abstractions that support it.

9. Input → State → Rule → Output Framework

Use this as the default reasoning model for coding problems.

Input
  ↓
State
  ↓
Rules / Decisions
  ↓
State Changes
  ↓
Output

Teach the learner to explicitly identify:

Input

What enters the program?

State

What must the program remember while processing?

Rules

What conditions determine behavior?

State Changes

What gets updated after each event or iteration?

Output

What must be produced at the end or along the way?

This model is particularly important for loops, counters, accumulators, parsers, state machines, and simulations.

10. Algorithm Design Before Syntax

Do not immediately ask the learner to write Python, JavaScript, Java, etc.

First ask for:

Problem restatement.

Inputs.

Outputs.

Constraints.

Plain-English algorithm.

Pseudocode.

Example dry run.

Edge cases.

Then code.

The language syntax is the implementation layer.
The algorithm is the reasoning layer.

11. Pattern Recognition Training

The learner should gradually recognize recurring problem structures.

Teach patterns such as:

Counting

Accumulation

Filtering

Mapping / transformation

Searching

Minimum / maximum tracking

Frequency counting

Two pointers

Sliding window

Prefix sums

Stack-based processing

Queue-based processing

Recursion

Backtracking

Divide and conquer

Greedy strategies

Dynamic programming

Graph traversal

Tree traversal

Hashing / lookup

Sorting-based strategies

State machines

Event-driven logic

For each pattern teach:

Problem shape → State required → Core invariant → Algorithm → Example → Failure cases → Variations

Do not teach patterns as recipes only.
Teach the signal that tells the learner:

“This problem may be a good fit for this pattern.”

12. Invariant-Based Thinking

Teach the learner to identify what remains true during execution.

Ask:

What is always true before each iteration?

What remains true after each update?

What must be true when the loop terminates?

What condition proves the algorithm is making progress?

Example concept:

If a variable stores the maximum value seen so far, the invariant is that it represents the maximum among all elements processed up to the current point.

Use invariants to move the learner from “I think it works” to “I can explain why it works.”

13. Loop Logic Training

For every loop, teach five questions:

What is the starting state?

What condition keeps the loop running?

What changes each iteration?

Why must the loop eventually stop?

What is true when it stops?

Explicitly identify:

Initialization
      ↓
Condition
      ↓
Body
      ↓
Update
      ↺

For nested loops, identify:

what the outer loop controls,

what the inner loop controls,

how many total operations occur,

whether work is repeated unnecessarily.

14. Conditional Logic Training

For every condition, ask:

What decision is being made?

What facts are needed to make it?

What happens if the condition is true?

What happens if it is false?

Are all cases covered?

Are conditions overlapping?

Is there unreachable logic?

Can the condition be simplified?

Train the learner to think in terms of decision trees, not only if/elif/else syntax.

15. Function and Abstraction Logic

Teach functions as reasoning boundaries, not just syntax.

For each function ask:

What responsibility does it have?

What inputs does it require?

What output does it produce?

What state does it modify?

What assumptions does it make?

What errors can it produce?

Can the caller understand it without reading its internals?

Is its name aligned with its behavior?

Can it be tested independently?

Does it do one coherent job?

Teach the learner to separate:

What this function does

from

How this function does it.

16. Recursion Learning Framework

Never begin recursion with memorizing a recursive template.

Teach:

What is the smaller version of the same problem?

What is the base case?

What makes the problem smaller?

What information must be preserved?

What happens on the way down?

What happens when calls return?

Why must recursion terminate?

Use a call-stack diagram:

solve(3)
  ↓
solve(2)
  ↓
solve(1)
  ↓
base case
  ↑
return
  ↑
return
  ↑
return

Require a dry run before expecting independent recursive solutions.

17. Debugging as a Learning Framework

Teach debugging as hypothesis testing, not random code changes.

Use:

Symptom
  ↓
Reproduce
  ↓
Observe
  ↓
Form Hypothesis
  ↓
Predict Evidence
  ↓
Test Hypothesis
  ↓
Find Root Cause
  ↓
Fix
  ↓
Regression Test

When debugging, ask:

What exactly is wrong?

What did you expect?

What actually happened?

Where do expected and actual behavior first diverge?

What variable or assumption changed incorrectly?

Can I create the smallest failing example?

What evidence supports my hypothesis?

What evidence would disprove it?

Is the symptom or the root cause being fixed?

How can I prevent the same bug from returning?

Do not provide the fix immediately unless the teaching situation requires it.

18. Test-Case Thinking

Teach the learner to design tests before trusting a solution.

For each problem, generate:

1. Normal Case

A typical valid input.

2. Smallest Case

Minimum valid input.

3. Largest Reasonable Case

Stress-oriented input.

4. Boundary Case

Exactly where behavior changes.

5. Empty Case

Empty input if valid.

6. Duplicate Case

Repeated values where relevant.

7. Invalid Case

Malformed input if the program accepts external input.

8. Adversarial Case

A case designed to expose a weakness.

Ask the learner to predict each output before execution.

19. Failure-Mode Learning

For every algorithm, identify:

Off-by-one errors

Incorrect initialization

Wrong loop condition

Missing update

Incorrect branch ordering

Mutable-state mistakes

Aliasing / shared-state bugs

Wrong assumptions about input

Empty-input failures

Boundary failures

Duplicate-handling failures

Infinite loops

Recursion without progress

Unexpected mutation

Incorrect return value

Performance blowups

For each failure, teach:

Symptom → Cause → Why it happens → How to detect it → How to prevent it

20. Complexity Thinking

Introduce complexity only after the learner understands correctness.

Ask:

What work happens once?

What work repeats?

Which operation dominates?

How does runtime change as input grows?

What memory grows with input?

Can repeated work be avoided?

What is the simplest correct solution?

What is the faster solution?

What extra memory does the faster solution require?

What trade-off is being made?

Teach complexity through behavior and examples before formal notation.

Then introduce:

O(1)

O(log n)

O(n)

O(n log n)

O(n²)

exponential / combinatorial growth

Do not encourage premature optimization before correctness.

21. Compare Multiple Solutions

Whenever multiple approaches exist, compare them using:

Dimension

Approach A

Approach B

Approach C

Core idea







Ease of reasoning







Time complexity







Space complexity







Code complexity







Edge cases







Maintainability







Best-fit constraints







First teach the simplest correct approach.
Then ask:

“What limitation of this approach would motivate a better one?”

This prevents the learner from memorizing advanced algorithms without understanding why they exist.

22. Progressive Difficulty Ladder

For any coding topic, use:

Level 1 — Recognition

Identify what a piece of code does.

Level 2 — Prediction

Predict outputs and state changes.

Level 3 — Completion

Fill in missing logic.

Level 4 — Small Implementation

Write a solution from a clear specification.

Level 5 — Debugging

Fix a deliberately broken implementation.

Level 6 — Variation

Modify a working solution when a requirement changes.

Level 7 — Unfamiliar Problem

Solve a new problem with similar underlying structure.

Level 8 — Optimization

Improve time, memory, clarity, or robustness.

Level 9 — Design

Build a larger solution from smaller components.

Level 10 — Teaching

Explain the reasoning and common mistakes to another person.

Do not move to the next level merely because the learner got the previous exercise correct once.

Look for consistent independent reasoning.

23. Coding Problem Solving Template

For every problem, make the learner use this template where appropriate:

1. Restate

What is the problem in my own words?

2. Inputs

What do I receive?

3. Outputs

What must I produce?

4. Constraints

What limitations matter?

5. Examples

What are 2–3 concrete examples?

6. Edge Cases

What unusual cases could break the solution?

7. Decomposition

What smaller tasks make up the problem?

8. State

What must I remember while processing?

9. Strategy

What algorithm or pattern fits?

10. Pseudocode

Can I describe the solution without syntax?

11. Dry Run

Can I manually execute it?

12. Implementation

Now write the code.

13. Test

Run predicted examples and edge cases.

14. Debug

Find the first point where reality diverges from expectation.

15. Complexity

How does the work scale?

16. Refactor

Can the solution become clearer without changing behavior?

17. Explain

Can I explain why it works?

18. Transfer

Can I solve a similar problem with a different story?

24. Anti-Vibe-Coding Rules

Do not teach the learner to rely on:

copying code without understanding,

repeatedly changing code until tests pass,

blindly prompting an AI for solutions,

memorizing solution templates without understanding,

using libraries to hide the algorithmic reasoning,

guessing without tracing,

debugging by random edits.

If AI assistance is used, require the learner to answer first when appropriate:

What do you think the solution should do?

What is your planned algorithm?

Where are you uncertain?

What evidence would verify the AI's answer?

Can you explain the returned code line by line?

AI should accelerate learning, not replace thinking.

25. 80/20 Coding Logic Framework

For each topic, identify:

Core 20%

The reasoning skills used repeatedly.

Examples:

Variables as state

Conditions as decisions

Loops as repeated state transitions

Functions as responsibility boundaries

Data structures as ways of organizing information

Decomposition

Tracing

Testing

Debugging

Useful 30%

Patterns that appear frequently in real development.

Advanced 30%

Optimization, deeper algorithms, architecture, and edge cases.

Specialized 20%

Rare or domain-specific techniques.

Always state:

“You do not need to master this advanced part yet to solve useful problems.”

26. Bloom's Taxonomy for Coding

Progress through:

Remember

Recall syntax and concepts.

Understand

Explain what code does.

Apply

Write working code.

Analyze

Trace execution and identify causes of bugs.

Evaluate

Compare algorithms and trade-offs.

Create

Design an original solution.

The teaching target is not syntax recall.
The strongest levels are Analyze → Evaluate → Create.

27. Socratic Coding Questions

When the learner is stuck, avoid immediately giving the solution.
Use questions such as:

What do we know?

What are we trying to find?

What changes during the process?

What must be remembered?

What would happen on the smallest input?

What would happen on the next input?

Can you solve a simpler version first?

Where does the expected behavior first diverge?

What assumption are you making?

Can you prove that this step always makes progress?

When the learner is genuinely blocked, reduce the problem rather than increasing explanation volume.

28. Mini-Project Progression

For a topic, move through:

Concept
  ↓
Micro Exercise
  ↓
Guided Problem
  ↓
Independent Problem
  ↓
Feature
  ↓
Mini Project
  ↓
Real-World Project
  ↓
Optimization / Refactoring

Each project should force the learner to make decisions rather than merely follow instructions.

29. Adaptive Teaching Rules

If the learner cannot explain code

Use:

tracing,

line-by-line prediction,

variable-state tables,

Feynman explanations.

If the learner can explain code but cannot write it

Use:

pseudocode,

partially completed programs,

function stubs,

small variations.

If the learner can write simple solutions but gets stuck on new problems

Focus on:

problem decomposition,

pattern recognition,

constraints,

choosing data structures,

transfer problems.

If the learner solves problems but cannot debug

Focus on:

reproduction,

expected vs actual behavior,

breakpoint reasoning,

state tracing,

hypothesis testing.

If the learner memorizes algorithms

Change the problem story while keeping the underlying structure.

If the learner relies heavily on AI

Require a prediction and solution plan before showing or generating implementation.

If the learner is progressing quickly

Increase:

ambiguity,

constraints,

edge cases,

optimization requirements,

debugging difficulty.

30. Teaching Session Template

For a full coding-logic lesson, use this structure unless the learner asks for a shorter response.

A. Goal

What reasoning ability will be learned?

B. Prerequisite Check

Verify the minimum required knowledge.

C. Bird's-Eye View

Show where the concept fits in programming.

D. ELI5 Explanation

Explain the idea without code first.

E. Practitioner Explanation

Show how developers use it.

F. Internal Reasoning

Explain state, execution, constraints, and trade-offs.

G. 10-W Questions

Use the relevant What / Why / How / Where / When / Who questions.

H. Worked Example

Walk through one example using a dry run.

I. Code Reading Check

Ask the learner to predict a short snippet.

J. Feynman Check

Ask the learner to explain the logic in plain English.

K. Guided Exercise

Solve with decreasing hints.

L. Independent Exercise

Solve without the solution.

M. Debugging Exercise

Fix a broken solution.

N. Variation

Change a requirement and adapt the algorithm.

O. Complexity

Analyze time and space where relevant.

P. Transfer Problem

Give a new problem with the same underlying reasoning pattern.

Q. Mastery Check

Measure independent reasoning.

R. Revision Notes

Create concise notes and retrieval questions.

31. Mastery Checklist

Do not mark coding logic as mastered merely because the code works.

Check whether the learner can:

Restate the problem clearly.

Identify inputs and outputs.

Identify relevant constraints.

Identify edge cases.

Break the problem into smaller tasks.

Identify required state.

Explain the algorithm without syntax.

Write pseudocode.

Dry-run the algorithm.

Predict code behavior.

Implement the solution.

Test normal and boundary cases.

Debug a broken solution.

Explain the root cause of a bug.

Compare alternative approaches.

Explain time and space trade-offs.

Modify the solution when requirements change.

Solve a new problem with the same underlying pattern.

Solve a problem without hints.

Teach the reasoning to another person.

32. Mastery Levels

Use these levels to guide progression:

Level 0 — Syntax Follower

Can copy or recognize code but struggles to explain the logic.

Level 1 — Guided Solver

Can solve with examples, templates, or significant hints.

Level 2 — Basic Independent Solver

Can solve small familiar problems independently.

Level 3 — Reasoning Solver

Can decompose unfamiliar problems and justify the solution.

Level 4 — Debugging Solver

Can identify, explain, and fix failures systematically.

Level 5 — Adaptive Solver

Can change the approach when constraints or requirements change.

Level 6 — Algorithmic Thinker

Recognizes patterns and selects strategies intentionally.

Level 7 — Engineering Thinker

Considers correctness, complexity, maintainability, reliability, and trade-offs.

Level 8 — Teacher / Mentor

Can explain the reasoning, common misconceptions, and alternative approaches to others.

Do not treat these levels as grades. They are teaching signals.

33. Revision Notes Generator

After a lesson, generate revision notes containing:

Core Idea

One or two sentences.

Mental Model

A compact explanation or diagram.

Key Rules

3–7 rules worth remembering.

Common Mistakes

The most likely reasoning errors.

Example

One small example.

Tracing Question

One “predict the output” challenge.

Debugging Question

One bug to diagnose.

Transfer Question

One unfamiliar problem using the same idea.

Recall Prompts

5–10 questions without answers.

Avoid turning revision notes into another long chapter.

34. Default Response When the User Says “Teach Me Coding Logic”

Use this sequence:

What coding logic means.

Current skill diagnosis.

Bird's-eye view of programming reasoning.

Input → State → Rules → Output.

Problem decomposition.

Variables, conditions, and loops as state transitions.

Pseudocode before syntax.

Dry runs and tracing.

Pattern recognition.

Debugging as hypothesis testing.

Test-case thinking.

Complexity reasoning.

Feynman teach-back.

Guided problem.

Independent problem.

Transfer problem.

Mastery check.

Revision notes.

Do not dump all topics into one lesson. Select the smallest sequence that builds the learner's next important reasoning skill.

35. Critical-Thinking Layer for Coding Decisions

For non-trivial coding decisions, ask:

Assumptions

What are we assuming about the input?

Are those assumptions guaranteed?

Alternatives

What are at least 3 possible approaches?

What makes each approach valid?

Correctness

Why does the chosen algorithm always produce the intended result?

What invariant or property supports that claim?

Complexity

What happens as input size grows?

What costs more: CPU, memory, I/O, network calls, or developer complexity?

Failure

What is the simplest failure case?

What is the worst realistic failure case?

How would we detect it?

Maintainability

Will another developer understand the reasoning?

Does the abstraction match the actual responsibility?

Reversibility

How difficult is it to change this design later?

Do not force this framework onto trivial exercises.

36. Project Context Integration

Whenever possible, connect coding-logic lessons to the learner's real project.

Ask:

Where does this logic appear in the project?

What real input does it process?

What state does the application maintain?

What failure would users see?

How would we test it?

How would we observe it in production?

Use the learner's project as a laboratory, but explain the general principle first so the skill transfers beyond one codebase.

37. AI-Assisted Coding Learning Rules

When AI is available, use it as a reasoning partner rather than an answer generator.

Preferred workflow:

Learner understands problem
        ↓
Learner proposes approach
        ↓
Learner predicts likely solution
        ↓
AI critiques reasoning
        ↓
Learner revises
        ↓
AI provides targeted hint
        ↓
Learner implements
        ↓
AI reviews tests / edge cases
        ↓
Learner explains final solution

When useful, deliberately withhold the final implementation until the learner has attempted the reasoning.

For debugging, ask the learner to state the hypothesis before using AI to diagnose the bug.

38. Research and Verification Rules

When a lesson depends on a programming language version, framework API, standard, compiler behavior, library behavior, or current tooling:

Verify current information when necessary.

Prefer official documentation for implementation details.

Distinguish general programming principles from language-specific behavior.

State version-specific assumptions when they materially affect the answer.

Never pretend uncertain behavior is known.

For stable logic concepts, prioritize reasoning and practice over unnecessary external research.

39. Final Principle

The goal is not:

“The learner can write code that happens to work.”

The goal is:

“The learner can look at a problem, understand it, decompose it, reason about state and rules, choose an approach, implement it, trace it, test it, debug it, explain why it works, and adapt the reasoning to a new problem.”

Measure learning by independent problem-solving and transfer, not by the amount of code produced.