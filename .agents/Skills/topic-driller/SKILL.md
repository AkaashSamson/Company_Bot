---
name: topic-drill-down
description: Drill into any topic with 10 What, 10 Why, 10 Where, 10 Who, 10 When and 10 How questions (60 in total) to build a deep, complete, connected understanding of it. Use this skill whenever the user wants to learn, understand, master, study, break down, "go deep on", "drill down into", "explain fully", or get "the full picture" of a topic, concept, technology, event, person, industry, system, skill or idea. Also trigger on mentions of 5W1H, 6 questions, "10 whats and whys", first-principles learning, or requests like "teach me X properly", "I want to really understand X", "help me study X", or "what should I know about X". Trigger even if the user doesn't name the method. Do NOT use for quick factual lookups or single-answer questions.
---

# Topic Drill-Down: The 60-Question Method

A structured learning engine. It takes one topic and interrogates it from six angles (What, Why, Where, Who, When, How), asking **10 distinct questions per angle**, answering each accurately, then synthesizing everything into a single mental model the learner can recall, explain and apply.

The output is a map of the topic in the learner's head, not a pile of facts.

---

## 1. Core Principles

1. **Depth over breadth.** Ten questions per lens must each attack a different facet. If two questions produce the same answer, one is redundant. Replace it.
2. **Every question must be specific to the topic.** Never write generic questions like "What is important about X?". Generic questions produce generic answers.
3. **Progress from concrete to abstract, and from simple to hard,** within each lens. Question 1 is a foundation. Question 10 is an edge, a frontier, or a hard trade-off.
4. **Connect the lenses.** The value is in the links: the *why* explains the *what*, the *who* and *when* explain the *how*. Draw these links explicitly in the synthesis.
5. **Be accurate and honest about uncertainty.** Flag contested claims, unknowns and simplifications. Never invent facts, dates, names, statistics or sources.
6. **Use search for anything time-sensitive.** Current state, latest versions, recent events, living people, prices, laws and "who leads X now" must be verified with web search, not answered from memory.
7. **Teach, don't dump.** Use plain language first, precise terms second. Define jargon the first time it appears. Use one analogy per lens where it genuinely helps.
8. **Fit the learner.** Calibrate to their level, goal and time. A student preparing for an interview needs a different drill than a hobbyist.

---

## 2. Workflow Overview

| Phase | Name | Purpose |
|---|---|---|
| 0 | Scope | Pin down the topic, learner level, goal, depth |
| 1 | Orient | Give a one-paragraph map so the drill has context |
| 2 | Drill | Run the six lenses, 10 questions each |
| 3 | Synthesize | Merge the answers into one connected model |
| 4 | Test | Check understanding, expose gaps |
| 5 | Extend | Give a learning path and next drills |

Run all phases in order unless the user asks for a specific mode (see Section 9).

---

## 3. Phase 0: Scope the Topic

Before drilling, establish four things. **Infer from the conversation first. Ask only for what is genuinely missing, and ask at most one short question.** If the user has given enough, state your assumptions in one line and proceed.

1. **Topic boundary.** What exactly is in scope? "Python" is huge. "Python decorators" is drillable. If the topic is too broad, propose 2 to 4 sub-topics and drill the most likely one, or drill the broad topic at survey level and offer to go deeper on a branch.
2. **Learner level.** Beginner, intermediate or advanced in this topic.
3. **Goal.** Curiosity, exam, interview, build something, teach others, make a decision, or write about it. The goal decides which questions get the most weight.
4. **Depth and format.** Full 60-question drill, or a lighter mode.

### Topic-type classifier

Classify the topic. It changes how the six lenses are aimed (see Section 5).

- **Concept / idea** (entropy, inflation, recursion)
- **Technology / tool / framework** (Firebase, Kubernetes, transformers)
- **System / process / organization** (the immune system, a supply chain, a company)
- **Event / period** (the 2008 crisis, the Meiji Restoration)
- **Person / group / movement**
- **Skill / practice** (public speaking, options trading, meditation)
- **Field / discipline** (economics, computer vision)

---

## 4. Phase 1: Orient

Write **one paragraph (3 to 5 sentences)** that gives the learner a working picture before the drill starts: what the topic is in plain words, why anyone cares, and where it sits in the larger landscape. Then list the **key terms** they will meet (5 to 8 terms, one-line definitions).

This paragraph is scaffolding. It must not pre-empt the drill answers.

---

## 5. Phase 2: The Drill (60 Questions)

For each lens, generate **exactly 10 questions**, then answer each one. Number them **W1 to W10** (What), **Y1 to Y10** (Why), **R1 to R10** (Where), **O1 to O10** (Who), **T1 to T10** (When), **H1 to H10** (How), so they can be referenced later.

### Answer format per question

- **Q:** the specific question
- **A:** a direct, complete answer. Length scales with the depth mode (default 2 to 5 sentences).
- Where useful add: an **Example**, a **Common mistake**, or a **Connection** (link to another question ID).

### Lens 1: WHAT (definition, composition, boundaries)

Goal: know precisely what the thing is and is not.

Question slots to cover (adapt wording to the topic):

1. What is it, in one plain sentence?
2. What is it, precisely? The formal or technical definition.
3. What are its core components, parts or building blocks?
4. What are the key terms and vocabulary?
5. What are its main types, categories or variants?
6. What does it look like in a concrete, real example?
7. What is it *not*? Which similar things get confused with it, and what separates them?
8. What are its fundamental rules, laws, principles or properties?
9. What are its inputs and outputs (or causes and effects)?
10. What are its limits, assumptions and edge cases? What are the open or unresolved parts?

### Lens 2: WHY (purpose, causes, value, reasoning)

Goal: understand the reason it exists and why it works the way it does.

1. Why does it exist? What problem was it created to solve?
2. Why does it matter? What value does it create, and for whom?
3. Why does it work? What is the underlying mechanism or principle?
4. Why is it designed or structured this way rather than another way?
5. Why did it emerge when it did (conditions that made it possible or necessary)?
6. Why do people adopt, choose or use it? What are the incentives?
7. Why does it fail, break or get misused? What are the root causes?
8. Why do experts disagree about it? What are the real debates?
9. Why should *this learner* care, given their goal?
10. Why might it change, be replaced or become obsolete?

### Lens 3: WHERE (context, location, domain, placement)

Goal: know where it lives, where it applies and where it does not. "Where" is not only geography. It covers domains, layers, systems and situations.

1. Where did it originate (place, field, institution, community)?
2. Where is it used or found most today (industries, regions, products)?
3. Where does it sit in the bigger picture? Which larger field, stack or system contains it?
4. Where does it connect to neighboring topics (upstream inputs, downstream dependents)?
5. Where is it strongest? In which conditions or contexts does it shine?
6. Where does it fail or not apply? Which contexts are a poor fit?
7. Where does it appear inside a system? Which layer, stage or component handles it?
8. Where can the learner observe it directly (a real product, dataset, place, case, demo)?
9. Where are the best resources to learn it (primary sources, docs, courses, communities)?
10. Where is it heading? Which frontiers or emerging areas are active?

### Lens 4: WHO (people, roles, stakeholders)

Goal: understand the human side: creators, users, beneficiaries, opponents and experts.

1. Who created, discovered or founded it?
2. Who are the key figures, thinkers, organizations or schools of thought?
3. Who uses it day to day (roles, professions, communities)?
4. Who benefits most from it?
5. Who is harmed, excluded or disadvantaged by it, or bears its costs?
6. Who are its critics or competitors, and what do they argue?
7. Who governs, regulates, standardizes or maintains it?
8. Who are the authorities worth following or reading?
9. Who does it depend on (the supporting cast, suppliers, contributors)?
10. Who should learn it, and who does not need to?

### Lens 5: WHEN (time, sequence, conditions, triggers)

Goal: understand history, order, timing and the conditions under which it applies.

1. When did it begin? Give the origin story and timeline start.
2. What are the major milestones, turning points or versions?
3. When was it different? What did it look like in earlier stages?
4. When is it the right time to use or apply it (triggers, conditions)?
5. When is it the wrong time (anti-triggers, contraindications)?
6. When in a process or workflow does it occur? What comes before and after?
7. When do results appear? What are the timescales, durations and lead times?
8. When did it face major crises, failures or paradigm shifts?
9. When is it changing right now? What is the current state? (verify with search)
10. When will a learner realistically become competent? What is the learning timeline?

### Lens 6: HOW (mechanism, method, practice)

Goal: know how it actually works and how to do it.

1. How does it work at a high level?
2. How does it work step by step, internally (the mechanism)?
3. How is it built, made or set up from scratch?
4. How is it used correctly in practice (the standard procedure)?
5. How do experts do it differently from beginners?
6. How is it measured, evaluated or judged as good or bad?
7. How does it go wrong, and how do you diagnose and fix it?
8. How does it compare to alternatives (trade-offs, when to pick which)?
9. How can it be optimized, scaled or extended?
10. How should the learner practice and start today (a concrete first exercise)?

### Aiming the lenses by topic type

Reweight and reword the slots to fit the type. Keep 10 per lens.

- **Concept:** What = definition and properties; Why = reasoning and proof; How = worked examples and derivations.
- **Technology:** Where = ecosystem, stack layer, deployment; How = architecture, setup, debugging; When = versions, release history, when to choose it; Who = maintainers, community, companies.
- **System / process / organization:** Where = components and boundaries; How = flows, feedback loops, failure modes; Who = actors and stakeholders.
- **Event / period:** When = detailed chronology; Why = causes and consequences; Who = actors, factions; Where = geography and theaters; How = mechanisms of how it unfolded.
- **Person / group:** Who = biography, influences, network; Why = motives, beliefs; When = life and career timeline; How = methods and style; What = works and ideas; Where = places, institutions.
- **Skill / practice:** How = technique, drills, progression; When = practice schedule, milestones; Why = mechanism of improvement; Who = coaches, benchmarks; Where = environments and tools; What = components of the skill.
- **Field / discipline:** Where = map of sub-fields; What = core branches; Who = schools and major figures; When = history of eras; How = methods and research practice.

### Question quality rules

- **No overlap.** Each question targets a new facet. Check before answering.
- **Answerable.** Each question has a real, specific answer, not "it depends" without saying on what.
- **Ordered.** Foundation first, frontier last.
- **Includes at least two "hard" questions per lens** (trade-offs, controversies, edge cases) so the drill is not just surface facts.
- **Topic-specific wording.** Replace "it" with the actual topic name and use its real vocabulary.

---

## 6. Phase 3: Synthesize

After the drill, build the connected picture. This is the most important phase. Produce all of the following:

1. **The one-sentence essence.** The topic explained in a single sentence a smart 12-year-old could follow.
2. **The 30-second explanation.** A short paragraph weaving What, Why and How together.
3. **The mental model.** A single analogy, diagram description or framework that holds the topic together. If a visual would help, offer a simple diagram (ASCII, Mermaid, or a rendered visual if tools allow).
4. **The cross-lens connections.** List 5 to 8 links between answers, using question IDs. Example: "Y3 (the mechanism) explains why H7 (common failures) happen; T2 (milestones) shows how W5 (variants) emerged."
5. **The 10 things that matter most.** Pull the ten highest-value takeaways from all 60 answers, ranked. These are what to remember if nothing else sticks.
6. **Misconceptions cleared.** The top 3 to 5 wrong beliefs about the topic and the correction for each.
7. **Open questions and uncertainty.** What is genuinely unknown, contested or fast-changing.

---

## 7. Phase 4: Test Understanding

Do not skip this. A drill that ends at the answers is passive.

1. **Feynman check.** Ask the learner to explain the topic back in their own words. Offer to critique it.
2. **Five recall questions** drawn from across the six lenses, at rising difficulty, with answers held back until the learner responds (if in an interactive setting). In a single-shot output, put the answers in a clearly separated "Answer key" section at the end.
3. **One application scenario.** A realistic situation where the learner must use the topic to make a decision or solve a problem.
4. **Gap detection.** After the learner answers, name specifically which question IDs their answer shows weakness in and re-teach those.

---

## 8. Phase 5: Extend

Close with a forward path:

- **Learning path:** 3 stages (Foundation, Working knowledge, Mastery) with a concrete action and a rough time estimate for each.
- **Key resources:** primary sources, best docs, canonical books or courses, communities. Verify with search that they exist and are current. Never fabricate titles, authors or URLs.
- **Adjacent topics:** 3 to 5 topics that would deepen understanding, each with a one-line reason.
- **Next drill offers:** propose two or three sub-topics that deserve their own 60-question drill.

---

## 9. Modes and Depth Control

Default to **Full** unless the user's wording, goal or time signals otherwise.

| Mode | Questions per lens | Answer length | Use when |
|---|---|---|---|
| **Sprint** | 3 (the highest-value slots) | 1 to 2 sentences | Fast overview, little time |
| **Standard** | 5 | 2 to 3 sentences | Working understanding |
| **Full (default)** | 10 | 2 to 5 sentences | Deep understanding, the method as named |
| **Deep** | 10 plus a follow-up "drill the answer" on the 3 hardest questions | 4 to 8 sentences with examples | Mastery, research, teaching |
| **Interactive** | 10, one lens at a time | Per lens | Learner wants to participate and pace it |
| **Single-lens** | 10 in one chosen lens | 3 to 6 sentences | Learner already has the rest |

### Interactive mode protocol

1. Present the lens name and its 10 questions.
2. Ask the learner which questions they can already answer, or have them attempt two before you reveal.
3. Reveal answers, correct misunderstandings, then move to the next lens.
4. After each lens give a 2-line recap. After all six, run Phase 3 and Phase 4.

### Drill-the-answer (recursive drilling)

If the learner says "go deeper on W3" (or any ID), treat that answer as a new mini-topic and ask 3 to 5 sharper sub-questions (each prefixed W3.1, W3.2, and so on). Repeat as many levels as the learner wants. Keep the ID chain so nothing gets lost.

---

## 10. Output Format

### Where the output goes

- **Full or Deep drill:** produce a structured document. Default to a Markdown artifact or file, since the learner will keep and revisit it. Produce a Word or PDF file only if the user asks for that format.
- **Sprint, Standard or Single-lens:** answer in the chat reply.
- **Interactive:** answer in chat, one lens per message.

### Document skeleton

```
# [Topic]: Deep Dive

**Level:** ... | **Goal:** ... | **Mode:** ... | **Topic type:** ...

## 0. Orientation
(paragraph + key terms)

## 1. WHAT (W1 to W10)
### W1. [Question]
[Answer]
...

## 2. WHY (Y1 to Y10)
## 3. WHERE (R1 to R10)
## 4. WHO (O1 to O10)
## 5. WHEN (T1 to T10)
## 6. HOW (H1 to H10)

## 7. Synthesis
- One-sentence essence
- 30-second explanation
- Mental model
- Cross-lens connections
- The 10 things that matter most
- Misconceptions cleared
- Open questions

## 8. Test Yourself
(5 recall questions, 1 scenario, answer key at end)

## 9. Learning Path and Next Steps
```

### Formatting rules

- Number every question with its ID so it can be referenced.
- Use tables only for genuinely tabular content (comparisons, timelines). Use prose for explanations.
- Keep each answer self-contained but link to other IDs where the connection teaches something.
- Bold the key term the first time it is defined.
- No filler introductions or closing pleasantries. Start with the content.

---

## 11. Research and Accuracy Protocol

1. **Verify volatile facts.** Search for current versions, current office-holders, latest research, recent events, prices, laws and statistics. State the date of the information when it may age.
2. **Distinguish levels of certainty.** Use clear markers: established fact, widely accepted view, contested, speculative.
3. **Cite sources for non-obvious claims** when web search was used. Paraphrase. Do not reproduce long passages of copyrighted text.
4. **Never fabricate.** If you do not know a date, name, number or source, say so and offer to search.
5. **Represent debates fairly.** For contested or political topics, present the strongest versions of the main positions in the WHY and WHO lenses without taking a side.
6. **Sensitive topics** (medical, legal, financial): give the educational picture and note where a qualified professional is needed for personal decisions.

---

## 12. Quality Checklist (run before delivering)

- [ ] Exactly 10 questions in each lens that is in scope (or the count the chosen mode specifies)
- [ ] No two questions overlap in what they ask
- [ ] Every question is specific to this topic, not generic
- [ ] Each lens moves from foundational to advanced, with at least two hard questions
- [ ] All time-sensitive facts were verified or flagged
- [ ] Jargon is defined at first use
- [ ] Synthesis explicitly links answers across lenses by ID
- [ ] The 10 most important takeaways are ranked and distinct from each other
- [ ] Misconceptions and open questions are included
- [ ] A test section and a learning path are present
- [ ] Depth matches the learner's level and goal

If any box fails, fix it before responding.

---

## 13. Handling Edge Cases

- **Topic too broad** ("science", "history"): do a survey drill (Sprint level) across its major branches, then offer focused full drills on the branches the learner picks.
- **Topic too narrow** (a single fact): expand to the smallest surrounding concept that makes 60 distinct questions meaningful, and say so.
- **Ambiguous topic** (a word with several meanings): list the meanings in one line, pick the most likely, state the assumption, proceed.
- **A lens barely applies** (for example WHERE for a pure abstraction): reinterpret the lens (domains, contexts, layers, applications) rather than dropping it, so the count stays at 10.
- **Learner already knows a lot:** skip the definitional slots, replace them with advanced questions (trade-offs, internals, edge cases, current research), and say which you swapped.
- **Learner is overwhelmed:** drop to Interactive or Sprint mode and rebuild from the essence sentence upward.
- **Learner wants to apply it to a project or decision:** add a final section, "Applying this to your situation", after Synthesis.

---

## 14. Worked Micro-Example (illustrative, shortened)

**Topic:** Retrieval-Augmented Generation (RAG). **Level:** intermediate. **Goal:** build one.

- **W2.** What is RAG precisely? A pattern in which a language model receives relevant documents fetched at query time from an external store, and generates its answer grounded in that retrieved text.
- **Y1.** Why does it exist? Models have fixed training data and hallucinate. Retrieval supplies fresh, checkable, private knowledge without retraining.
- **R7.** Where does it sit in the system? Between the user query and the model call: query, embed, vector search, rerank, prompt assembly, generate.
- **O3.** Who uses it daily? ML engineers, search teams, and enterprise product teams building document Q&A and support bots.
- **T9.** When is it changing now? (verify by search) Retrieval quality, chunking strategy, long-context models and agentic retrieval are actively shifting the trade-offs.
- **H7.** How does it go wrong? Poor chunking, weak embeddings, retrieving irrelevant passages, or the model ignoring the context. Diagnose retrieval and generation separately.

Synthesis line: "RAG turns an open-book exam into an engineering problem: Y1 says why the book is needed, R7 says where it plugs in, H7 says where the exam is failed."

---

## 15. Tone

Direct, clear and confident. Explain as a sharp mentor would: no hedging on settled facts, no padding, no condescension. Be honest and specific when something is uncertain or wrong. Respect the learner's time.