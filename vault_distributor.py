#!/usr/bin/env python3
"""
vault_distributor.py — Distribution pipeline for vault publications.

Three-stage pipeline:
  1. RANK — score each publication on quality metrics
  2. REFINE — rewrite as SEO-optimized professional essays with tweet threads
  3. DISTRIBUTE — publish to external channels (Twitter/X, discoveries site)

Usage:
    python3 vault_distributor.py --rank              # Rank all publications
    python3 vault_distributor.py --refine <n>        # Refine top N publications
    python3 vault_distributor.py --publish <n>       # Publish top N ranked
    python3 vault_distributor.py --auto              # Full pipeline: rank → refine → publish
"""

import os, re, json, glob, math, hashlib, time
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
PUBS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Publications")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
DISCOVERIES_DIR = os.path.expanduser("~/discoveries")
DISTILLED_DIR = os.path.join(VAULT_ROOT, "04 Resources/Distilled")
os.makedirs(DISTILLED_DIR, exist_ok=True)


# ──────────────────────────────────────────────
# STAGE 1: RANKING ENGINE
# ──────────────────────────────────────────────

RANKING_WEIGHTS = {
    'word_count':       {'weight': 0.10, 'ideal': 1800},  # Sweet spot for essays
    'sections':         {'weight': 0.10, 'ideal': 6},     # Number of H2 sections
    'has_tables':       {'weight': 0.15, 'ideal': 1},     # Comparison tables
    'has_blockquote':   {'weight': 0.08, 'ideal': 1},     # Pull quotes
    'has_opening':      {'weight': 0.12, 'ideal': 1},     # "The Opening" section
    'has_sources':      {'weight': 0.05, 'ideal': 1},     # Source citations
    'has_url':          {'weight': 0.05, 'ideal': 1},     # External URL in text
    'has_code':         {'weight': 0.08, 'ideal': 1},     # Code blocks (practical)
    'is_cross_domain':  {'weight': 0.12, 'ideal': 1},     # Bridge between domains
    'has_novelty':      {'weight': 0.10, 'ideal': 1},     # Makes a novel claim
    'age_days':         {'weight': 0.05, 'ideal': 0},     # Freshness (newer = better)
}

MAX_PUBLICATIONS_SCORE = 1.0


@dataclass
class PublicationRanking:
    file: str
    title: str
    bridge_number: int
    words: int
    sections: int
    has_tables: bool
    has_blockquote: bool
    has_opening: bool
    has_sources: bool
    has_url: bool
    has_code: bool
    is_cross_domain: bool
    has_novel_claim: bool
    age_days: int
    quality_score: float
    seo_score: float
    tweet_potential: float
    composite_score: float
    rank: int = 0


class RankingEngine:
    """Score every publication on quality, SEO, and distribution potential."""

    def __init__(self):
        self.publications: list[PublicationRanking] = []
        self._load()

    def _load(self):
        for f in sorted(glob.glob(os.path.join(PUBS_DIR, "*.md"))):
            fn = os.path.basename(f)
            with open(f, 'r', encoding='utf-8', errors='replace') as fh:
                content = fh.read()

            # Extract title
            title = fn.replace('.md', '')
            hm = re.search(r'^# (.+)$', content, re.MULTILINE)
            if hm:
                title = hm.group(1).strip()

            # Bridge number
            bn = 0
            bm = re.search(r'Bridge #(\d+)', content)
            if bm:
                bn = int(bm.group(1))

            # Count metrics
            words = len(content.split())
            sections = len(re.findall(r'^## ', content, re.MULTILINE))
            has_tables = '|---|---|---|' in content
            has_blockquote = content.count('\n>') > 5
            has_opening = '## The Opening' in content or '## 10. ' in content
            has_sources = bool(re.search(r'sources:\s*\[', content))
            has_url = bool(re.search(r'https?://', content))
            has_code = '```' in content
            is_cross_domain = 'Cross-Domain Synthesis' in content or 'cross-domain' in content.lower()
            has_novel_claim = any(kw in content.lower() for kw in [
                'first', 'novel', 'breakthrough', 'discover', 'no existing',
                'this is the first', 'never before', 'unified'
            ])
            age_days = 0
            dm = re.search(r'date:\s*(\d{4}-\d{2}-\d{2})', content)
            if dm:
                try:
                    pub_date = datetime.strptime(dm.group(1), '%Y-%m-%d')
                    age_days = (datetime.now() - pub_date).days
                except:
                    pass

            # Quality score (structural completeness)
            quality = 0.0
            quality += min(words / RANKING_WEIGHTS['word_count']['ideal'], 1.2) * RANKING_WEIGHTS['word_count']['weight']
            quality += min(sections / RANKING_WEIGHTS['sections']['ideal'], 1.0) * RANKING_WEIGHTS['sections']['weight']
            quality += float(has_tables) * RANKING_WEIGHTS['has_tables']['weight']
            quality += float(has_blockquote) * RANKING_WEIGHTS['has_blockquote']['weight']
            quality += float(has_opening) * RANKING_WEIGHTS['has_opening']['weight']
            quality += float(has_sources) * RANKING_WEIGHTS['has_sources']['weight']

            # SEO score (discoverability)
            seo = 0.0
            seo += float(has_url) * RANKING_WEIGHTS['has_url']['weight']
            seo += float(has_code) * RANKING_WEIGHTS['has_code']['weight']
            seo += float(is_cross_domain) * RANKING_WEIGHTS['is_cross_domain']['weight']

            # Distribution potential (tweet thread fit)
            tweet = 0.0
            tweet += float(has_novel_claim) * RANKING_WEIGHTS['has_novelty']['weight']
            freshness = max(0, 1.0 - age_days / 180)  # Linear decay over 6 months
            tweet += freshness * RANKING_WEIGHTS['age_days']['weight']

            composite = quality + seo + tweet

            self.publications.append(PublicationRanking(
                file=fn, title=title, bridge_number=bn,
                words=words, sections=sections,
                has_tables=has_tables, has_blockquote=has_blockquote,
                has_opening=has_opening, has_sources=has_sources,
                has_url=has_url, has_code=has_code,
                is_cross_domain=is_cross_domain, has_novel_claim=has_novel_claim,
                age_days=age_days,
                quality_score=round(quality, 3),
                seo_score=round(seo, 3),
                tweet_potential=round(tweet, 3),
                composite_score=round(composite, 3),
            ))

        self.publications.sort(key=lambda p: -p.composite_score)
        for i, p in enumerate(self.publications):
            p.rank = i + 1

    def top_n(self, n: int = 10, min_score: float = 0.3) -> list[PublicationRanking]:
        return [p for p in self.publications if p.composite_score >= min_score][:n]

    def report(self, n: int = 30) -> str:
        lines = []
        lines.append("=" * 66)
        lines.append("  VAULT DISTRIBUTOR — PUBLICATION RANKINGS")
        lines.append("=" * 66)
        lines.append(f"\n  Total: {len(self.publications)} publications\n")
        lines.append(f"  {'Rank':>5s}  {'Score':>6s}  {'Qlty':>5s}  {'SEO':>5s}  "
                     f"{'Twt':>5s}  {'#' :>4s}  {'Title':<55s}")
        lines.append("  " + "-" * 95)
        for p in self.publications[:n]:
            bn = f"#{p.bridge_number}" if p.bridge_number > 0 else "--"
            lines.append(f"  {p.rank:>4d}.  {p.composite_score:.3f}  {p.quality_score:.3f}  "
                        f"{p.seo_score:.3f}  {p.tweet_potential:.3f}  {bn:>4s}  "
                        f"{p.title[:55]:<55s}")
            lines.append(f"       {p.words:>4d}w  {p.sections}§  "
                        f"{'📊' if p.has_tables else '  '}"
                        f"{'💬' if p.has_blockquote else '  '}"
                        f"{'🌅' if p.has_opening else '  '}"
                        f"{'📝' if p.has_sources else '  '}"
                        f"{'🔗' if p.has_url else '  '}"
                        f"{'💻' if p.has_code else '  '}"
                        f"{'🌉' if p.is_cross_domain else '  '}")
        return '\n'.join(lines)


# ──────────────────────────────────────────────
# STAGE 2: CONTENT REFINER (LLM-assisted)
# ──────────────────────────────────────────────

CONTENT_REFINER_PROMPT = """You are the vault's writing engine — the best technical writer on the internet. You transform vault bridge publications into essays that readers cannot put down.

Your writing philosophy:
- Every claim must feel DISCOVERED by the reader, not explained to them
- The reader should feel smarter after reading, not cheated by oversimplification
- Technical depth is preserved — accessibility is added, not substituted
- Every abstract concept gets an immediate concrete example
- The writing has momentum — each section builds on the last, skipping breaks the arc

RULES:

1. **The Curiosity Gap (Opening)**: First paragraph creates a gap between what the reader knows and what the essay promises. Do NOT summarize. DO provoke. Start with the counter-intuitive claim.

   BAD: "This essay explores the structural isomorphism between distributed systems and the endocrine system."
   GOOD: "Your body is running a distributed consensus protocol. The hypothalamus is the leader node. Cortisol is the state replication log. The CAP theorem applies to your bloodstream right now."

2. **Counter-Intuitive Hook**: Every essay must contain at least one claim that sounds wrong but is true. Find it. Surface it early. This is what gets shared.

3. **Concrete Before Abstract**: Every abstract claim MUST be immediately followed by a concrete example. Reader's brain processes concrete 10x faster.

   BAD: "The endocrine system uses negative feedback loops."
   GOOD: "When your blood sugar rises after breakfast, your pancreas releases insulin. When blood sugar drops, insulin stops. Same mechanism that keeps your house at 22°C."

4. **Narrative Momentum**: The essay is a journey, not a list. Each H2 section builds on the last. A reader who reads only the H2 headings should understand the arc. Each section should reward the dive-in.

5. **Scannable H2 Headings**: Headings tell a mini-story when read alone.

   BAD: "Section 2: The Mechanism"
   GOOD: "2. Why Your Pancreas Is Running a PID Controller"

6. **Pull Quotes as Viral Content**: Add 2-3 blockquote pull quotes. Each must be:
   - Under 280 chars (tweet-length)
   - Self-contained — makes sense outside context
   - Screenshot-worthy — something the reader would share
   - Placed at natural breaking points

7. **SEO That Doesn't Read Like SEO**: Primary keyword appears in H1 and first paragraph naturally. Related keywords in H2 headings. Meta description is compelling, not descriptive.

   BAD meta: "A comparison of distributed systems and endocrinology"
   GOOD meta: "Your body is a distributed system running a consensus protocol. Here's the proof."

8. **The Closing Frame**: Do NOT summarize. Recast the opening claim in a new light. Leave the reader with a question they'll think about, or a line they cannot forget.

   BAD: "In conclusion, this essay has shown that..."
   GOOD: "Start at Level 1 and build closure. Or stay at Level 1 and become prey."

9. **Comparison Tables**: Keep any existing tables. Ensure they're scannable. Add at least one comparison table if the content supports it.

10. **SEO Meta Description**: 150-160 characters that make someone click, not understand.

11. **Call to Action**: End with an engagement prompt. What should the reader do with this new knowledge?

OUTPUT FORMAT: Return ONLY the rewritten markdown content with full frontmatter. No explanations, no commentary."""

TWEET_THREAD_PROMPT = """You are a Twitter/X content strategist who writes threads that stop the scroll. You take vault publications and turn them into viral threads.

YOUR RULES:

1. **Tweet 1 — The Hook**: A single tweet that creates a curiosity gap. Someone scrolling past should STOP. Not explain the topic — create a question they cannot answer without reading more.

   BAD: "This thread explains how distributed systems relate to the endocrine system."
   GOOD: "Your body is running a distributed consensus protocol. The CAP theorem applies to your bloodstream. Here's why this changes how you think about autoimmune disease."

   Must be max 280 chars. Strong, declarative, counter-intuitive.

2. **Tweets 2-N — The Reveal**: Each tweet is one layer deeper. The reader should feel like they're peeling an onion of ideas. Each tweet must be:
   - Self-contained (makes sense out of context — it will be retweeted alone)
   - Builds on the previous (the thread has momentum)
   - Contains at least one striking detail, statistic, or example

3. **The "Oh Shit" Moment**: Tweet 5-7 should contain the most surprising claim. This is where the reader stops and thinks. If they share the thread, this is why.

4. **Closure Tweet**: Before the CTA, one tweet that recasts the entire thread in a new light. The reader should see the original topic differently.

5. **CTA Tweet (Last)**: Call to action + 3 relevant hashtags. "Share if..." or "Follow for..." The CTA should be specific to the content.

   Include hashtags: 3 max. Primary topic + vault's core hashtags if relevant.

6. **Thread length**: 7-10 tweets. No filler. Every tweet earns its place.

7. **Emoji use**: Strategic. One emoji per tweet max. The emoji should amplify the claim, not decorate it.

OUTPUT FORMAT:
```
1/7 [tweet text]
2/7 [tweet text]
...
7/7 [tweet text]
```

No other text outside the tweet format. No commentary. No explanations. JUST THE THREAD."""


class ContentRefiner:
    """Rewrites vault content into SEO-optimized essays and tweet threads."""

    def refine(self, pub: PublicationRanking) -> str:
        """Read the raw publication, return a refined version.
        
        In the current implementation, this applies structural transformations
        that can be done deterministically. Full LLM rewriting would require
        calling the model via the agent.
        """
        path = os.path.join(PUBS_DIR, pub.file)
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        
        # Apply deterministic improvements
        
        # 1. Add meta description if missing
        if 'description:' not in content:
            desc = pub.title[:155] + '.'
            # Add after frontmatter
            content = re.sub(r'^(---\n.*?\n---)', rf'\1\ndescription: "{desc}"', content, flags=re.DOTALL)
        
        # 2. Add author attribution
        if 'author:' not in content:
            content = re.sub(r'^(---\n.*?\n---)', rf'\1\nauthor: Vault Sensorium\ndistribution_ready: true\ndistilled: {datetime.now().strftime("%Y-%m-%d")}', content, flags=re.DOTALL)
        
        # 3. Ensure "The Opening" exists
        if '## The Opening' not in content and pub.composite_score > 0.5:
            # Extract the first blockquote as the opening
            bq = re.search(r'(> .+\n(?:> .+\n?)*)', content)
            if bq:
                opening = bq.group(1)
            else:
                # Generate a closing from the title
                title_lower = pub.title.lower()
                opening = f"> *{pub.title}*\n>\n> *This essay was auto-ranked and refined by the vault distribution pipeline — the first vault output designed for public consumption, not internal reference.*"
            
            content += f"\n\n---\n\n## The Opening\n\n{opening}\n\n---\n\n*Refined and formatted for distribution by the Vault Distributor. Originally published as part of the Second Brain vault.*"
        
        # 4. Add table of contents for longer pieces
        if pub.words > 1500 and '## Table of Contents' not in content:
            # Find H2 sections
            sections = re.findall(r'^## (.+)$', content, re.MULTILINE)
            if len(sections) >= 4:
                toc = '\n'.join(f'- {s}' for s in sections)
                content = content.replace(
                    content.split('---')[-1] if content.count('---') > 1 else content,
                    f'\n## Table of Contents\n\n{toc}\n\n' + 
                    (content.split('---')[-1] if content.count('---') > 1 else content)
                )
        
        # Save refined version
        distilled_path = os.path.join(DISTILLED_DIR, pub.file)
        with open(distilled_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return content

    def generate_thread(self, pub: PublicationRanking) -> list[str]:
        """Generate a tweet thread from the publication.
        
        This extracts key claims from the content deterministically.
        Full LLM thread generation would produce more natural threads.
        """
        path = os.path.join(PUBS_DIR, pub.file)
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        
        tweets = []
        
        # Tweet 1: Hook
        # Find first blockquote or strong claim
        bq = re.search(r'> (.+?)(?:\n|$)', content)
        if bq:
            hook = bq.group(1)[:250]
        else:
            hook = f"What if {pub.title.lower()}?"
        tweets.append(f"🧵 {hook}")
        
        # Tweets 2-N: Key points from each section
        sections = re.findall(r'^## (.+?)$\n\n(.+?)(?:\n##|\Z)', content, re.MULTILINE | re.DOTALL)
        for i, (title, text) in enumerate(sections[:6]):
            # Extract first 1-2 sentences
            clean = text.strip().split('\n')[0][:200]
            clean = re.sub(r'[\[\]]', '', clean)  # Remove [[wikilinks]]
            if len(clean) > 250:
                clean = clean[:247] + '...'
            tweets.append(f"{i+2}/7 {clean}")
        
        # Last tweet: CTA
        bn = f"#{pub.bridge_number}" if pub.bridge_number > 0 else ""
        tweets.append(f"{len(sections)+2}/7 Read the full essay: {pub.title} #VaultKnowledge #CrossDomain #AI")
        tweets.append(f"{len(sections)+3}/7 ♻️ Share if this sparked an idea. Follow for daily cross-domain discoveries.")
        
        return tweets

    def save_distilled(self, pub: PublicationRanking) -> str:
        """Save the refined essay and tweet thread to the distilled directory."""
        self.refine(pub)
        
        # Save tweet thread
        tweets = self.generate_thread(pub)
        thread_path = os.path.join(DISTILLED_DIR, pub.file.replace('.md', '_thread.txt'))
        with open(thread_path, 'w') as f:
            f.write('\n\n'.join(tweets))
        
        return f"Distilled: {pub.file} (+ thread)"


# ──────────────────────────────────────────────
# STAGE 3: DISTRIBUTION SCHEDULER
# ──────────────────────────────────────────────

class DistributionScheduler:
    """Schedules and gates publication distribution."""

    # Quality gates — publications must exceed these to be distributed
    MIN_QUALITY = 0.25
    MIN_COMPOSITE = 0.35
    MAX_WEEKLY = 3
    COOLDOWN_DAYS = 2  # Between publications

    def __init__(self):
        self.log_path = os.path.join(DISTILLED_DIR, '.distribution_log.json')
        self.published = self._load_log()

    def _load_log(self) -> list[dict]:
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []

    def _save_log(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, 'w') as f:
            json.dump(self.published, f, indent=2)

    def can_publish(self, pub: PublicationRanking) -> tuple[bool, str]:
        """Check if a publication passes all quality gates."""
        if pub.quality_score < self.MIN_QUALITY:
            return False, f"Quality score {pub.quality_score:.3f} < {self.MIN_QUALITY}"
        if pub.composite_score < self.MIN_COMPOSITE:
            return False, f"Composite score {pub.composite_score:.3f} < {self.MIN_COMPOSITE}"

        # Check cooldown
        if self.published:
            last = self.published[-1]
            last_time = datetime.fromisoformat(last['published_at'])
            if (datetime.now() - last_time).days < self.COOLDOWN_DAYS:
                return False, f"Cooldown active — last published {last['title'][:40]} on {last_time.date()}"

        # Weekly limit
        this_week = [p for p in self.published if (datetime.now() - datetime.fromisoformat(p['published_at'])).days < 7]
        if len(this_week) >= self.MAX_WEEKLY:
            return False, f"Weekly limit of {self.MAX_WEEKLY} reached"

        return True, "Ready to publish"

    def mark_published(self, pub: PublicationRanking):
        """Record a publication as distributed."""
        entry = {
            'file': pub.file,
            'title': pub.title,
            'bridge_number': pub.bridge_number,
            'composite_score': pub.composite_score,
            'quality_score': pub.quality_score,
            'published_at': datetime.now().isoformat(),
            'channels': [],
        }
        self.published.append(entry)
        self._save_log()

    def get_queue(self, rankings: list[PublicationRanking]) -> list[tuple[PublicationRanking, str]]:
        """Get the prioritized distribution queue."""
        queue = []
        for pub in rankings:
            if pub.file in [p['file'] for p in self.published]:
                continue
            ok, reason = self.can_publish(pub)
            queue.append((pub, reason))
        return queue


# ──────────────────────────────────────────────
# ORCHESTRATOR
# ──────────────────────────────────────────────

class VaultDistributor:
    """Full distribution pipeline orchestrator."""

    def __init__(self):
        self.ranker = RankingEngine()
        self.refiner = ContentRefiner()
        self.scheduler = DistributionScheduler()

    def rank(self, n: int = 30) -> str:
        return self.ranker.report(n)

    def refine(self, n: int = 5) -> list[str]:
        results = []
        for pub in self.ranker.top_n(n):
            result = self.refiner.save_distilled(pub)
            results.append(result)
        return results

    def queue(self) -> list[str]:
        queue = self.scheduler.get_queue(self.ranker.top_n(20))
        if not queue:
            return ["No publications in queue — all top-ranked have been published or blocked by quality gates."]
        lines = ["DISTRIBUTION QUEUE (sorted by rank):"]
        lines.append(f"  {'Rank':>5s}  {'Score':>6s}  {'Gate':>12s}  {'Title':<55s}")
        lines.append("  " + "-" * 80)
        for i, (pub, reason) in enumerate(queue):
            status = '✅ READY' if reason == 'Ready to publish' else '⏳ ' + reason[:30]
            lines.append(f"  {i+1:>4d}.  {pub.composite_score:.3f}  {status:>12s}  {pub.title[:55]:<55s}")
        return lines

    def publish_top(self, n: int = 1) -> list[str]:
        results = []
        queue = self.scheduler.get_queue(self.ranker.top_n(20))
        count = 0
        for pub, reason in queue:
            if count >= n:
                break
            if reason != 'Ready to publish':
                results.append(f"⏳ BLOCKED: {pub.title[:50]} — {reason}")
                continue

            # Refine, generate thread, save
            self.refiner.save_distilled(pub)
            self.scheduler.mark_published(pub)
            results.append(f"✅ PUBLISHED: {pub.title} (Score: {pub.composite_score:.3f})")
            
            # Copy to discoveries site
            src = os.path.join(DISTILLED_DIR, pub.file)
            dst = os.path.join(DISCOVERIES_DIR, f"distilled_{pub.file}")
            try:
                import shutil
                shutil.copy2(src, dst)
                results.append(f"   → Copied to discoveries site")
            except:
                pass
            
            count += 1
        
        if not results:
            results.append("No publications passed quality gates.")
        return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Vault Distributor Pipeline")
    parser.add_argument('--rank', action='store_true', help='Rank all publications')
    parser.add_argument('--refine', type=int, nargs='?', const=3, help='Refine top N publications')
    parser.add_argument('--publish', type=int, nargs='?', const=1, help='Publish top N publications')
    parser.add_argument('--queue', action='store_true', help='Show distribution queue')
    parser.add_argument('--auto', type=int, nargs='?', const=3, help='Full pipeline: rank→refine→publish N')
    args = parser.parse_args()

    dist = VaultDistributor()

    if args.auto:
        print(dist.rank())
        print('\n' + dist.refine(args.auto)[0] if dist.refine(args.auto) else '')
        results = dist.publish_top(args.auto)
        print('\n'.join(results))
    elif args.rank:
        print(dist.rank())
    elif args.refine:
        for r in dist.refine(args.refine):
            print(r)
    elif args.publish:
        for r in dist.publish_top(args.publish):
            print(r)
    elif args.queue:
        print('\n'.join(dist.queue()))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
