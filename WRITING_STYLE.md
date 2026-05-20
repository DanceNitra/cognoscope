---
name: vault-distributor-writing
description: >-
  Professional writing upgrade for the vault distributor pipeline.
  Transforms vault bridge publications into SEO-optimized essays that
  read like the best technical writing on the internet — curious,
  surprising, layered, and impossible to put down.
on_hint: >-
  Use when running vault_distributor.py --refine, or when asked to
  produce writing that "blows the reader away", or to rewrite any
  publication for external distribution.
---

# Vault Distributor — Writing Upgrade

## The Philosophy

Vault bridge publications are structurally dense, cross-domain, and
intellectually surprising. The default writing style is academic —
correct but flat. To reach a reader who scrolls past 100 posts per
day, the writing must compete on *curiosity*.

**The goal is not to explain an idea. The goal is to make the reader
feel like they discovered it themselves.**

## The 8 Writing Principles

### 1. The Curiosity Gap (Opening)

The first paragraph must create a gap between what the reader knows
and what the essay promises. This is not a summary. It is a question
the reader must read the rest to answer.

**Bad:** "This essay explores the structural isomorphism between
distributed systems and the endocrine system."

**Good:** "Your body is running a distributed consensus protocol.
The hypothalamus is the leader node. Cortisol is the state
replication log. Autoimmune disease is a byzantine fault. And the
CAP theorem applies to your bloodstream right now."

### 2. Narrative Structure, Not List Structure

The essay is a journey with a thesis. Each section is a step that
builds on the previous. The reader should feel momentum — they
cannot skip a section without losing the thread.

Structure template:
- **Opening**: The provocative claim that creates curiosity
- **Setup**: Why the default view is wrong / incomplete
- **The reveal**: The structural isomorphism / core insight
- **Evidence**: Concrete examples that prove it
- **Implications**: What this means for practice
- **The larger view**: Where this connects to the bigger picture
- **Closing**: A memorable final thought that recasts the beginning

### 3. Concrete Before Abstract

Every abstract claim must be immediately followed by a concrete
example. The reader's brain processes concrete examples 10x faster.

**Bad:** "The endocrine system uses negative feedback loops."

**Good:** "When your blood sugar rises after breakfast, your
pancreas releases insulin. When blood sugar drops, insulin
stops. This is a negative feedback loop — the same mechanism
that keeps your house at 22°C and your AWS cluster at 3 nodes."

### 4. The Counter-Intuitive Hook

Every essay should contain at least one claim that sounds wrong but
is true. This is the thing the reader will share. Find it in every
bridge and put it in the first section.

Every vault bridge has a counter-intuitive claim embedded in it.
Extract it and surface it as the hook.

### 5. Scannable Depth

Headings should tell a mini-story. A reader who reads only the
headings should understand the arc. But each section should reward
the reader who dives in.

**Bad heading:** "Section 2: The Mechanism"

**Good heading:** "2. Why Your Pancreas Is Running a PID Controller"

### 6. Pull Quotes as Micro-Viral Content

Each pull quote (> blockquote) should be:
- Tweet-length (under 280 chars where possible)
- A self-contained claim that makes sense on its own
- Something the reader would screenshot and share
- Placed at natural breaking points

### 7. SEO That Doesn't Read Like SEO

Natural keyword placement means:
- The primary keyword appears in H1 and first paragraph
- Related keywords appear in H2 headings
- Keywords are never stuffed — they appear because the topic
  demands them
- Meta description is compelling, not descriptive:
  **Bad:** "A comparison of distributed systems and endocrinology"
  **Good:** "Your body is a distributed system. Here's proof."

### 8. The Closing Frame

The ending should not summarize. It should:
- Recast the opening claim in a new light
- Leave the reader with a question they'll think about
- Or end on a line they cannot forget

## The Rewrite Process

For each publication, the refiner applies this checklist:

```
[ ] Curiosity gap created in first 3 paragraphs?
[ ] At least 1 counter-intuitive claim that sounds wrong but is true?
[ ] Every abstract claim followed by concrete example?
[ ] Headings tell a mini-story when read alone?
[ ] Pull quotes are tweet-worthy and shareable?
[ ] Keywords integrated naturally (no stuffing)?
[ ] Narrative momentum — can reader skip a section?
[ ] Closing recasts the opening, doesn't summarize?
[ ] Meta description makes you want to click, not understand?
```

## SEO Blog Post Checklist (For Standard Blog Format)

When the output needs to be a blog post (not essay):

```
[ ] H1: Compelling, keyword-rich, under 60 chars
[ ] Meta description: 150-160 chars, curiosity-driven
[ ] URL slug: Primary keyword, under 5 words
[ ] H2 headings: Include secondary keywords naturally
[ ] First 100 words: Primary keyword appears once
[ ] Internal links: 2-3 links to related content
[ ] External links: 1-2 links to authoritative sources
[ ] Image alt text: Descriptive, includes keyword
[ ] Tables: At least 1 comparison or data table
[ ] Pull quotes: 2-3 shareable quotes
[ ] Call to action: End with engagement prompt
[ ] Readability: Flesch score > 60 (short sentences, active voice)
```

## Examples of the Style

**Hook that creates curiosity:**
> "The 97% failure rate of day traders is not a statistics problem.
> It's a systems architecture problem. Every failed trader is a
> poorly-configured autonomous agent running without a self-model."

**Counter-intuitive claim:**
> "Price is not the fundamental signal. The agent loop is. Price is
> just the observable output of millions of interacting decision
> loops. Renaissance Technologies doesn't predict prices — they
> model agent behavior, and price is the residual of that model."

**Scannable heading that tells a story:**
> "3. Why Losing 10 Trades in a Row Is Not Bad Luck — It's an
> Architectural Failure"

**Closing that doesn't summarize:**
> "Start at Level 1 and build closure. Or stay at Level 1 and
> become prey."

## Pitfalls

- Don't make the hook clickbait — the essay must deliver what the
  hook promises. Vault bridges are dense enough to justify any claim.
- Don't remove the technical depth. The style upgrade adds
  accessibility, not shallowness. A reader should feel smarter
  after reading, not cheated.
- Don't oversimplify cross-domain connections. The vault's
  contribution is that these connections are real, not metaphors.
  The writing should make them feel inevitable, not clever.
- SEO keywords must be discovered from the content, not injected.
  Each vault bridge has natural keywords embedded in its domain pair.
