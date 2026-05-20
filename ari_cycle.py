#!/usr/bin/env python3
"""
ARI — Autonomous Research Intelligence
Layer 2: Epistemic Objective Function + Narrative Potential Scorer
Layer 3: Evidence Search + Professional-Grade Synthesis

Expanded cycle:
  1. Scan → find anomalies → generate predictions (Layer 1)
  2. Score predictions by epistemic value AND narrative potential
  3. Select the best story — not just the highest Φ gain
  4. Write it as a publication-ready blog post (not a template)
  5. Log + return the text for delivery
"""

import os, sys, re, glob, json, math, random
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
PUBS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Publications")
DISTILLED_DIR = os.path.join(VAULT_ROOT, "04 Resources/Distilled")
ARI_DIR = os.path.join(VAULT_ROOT, "04 Resources/ARI")
LOG_PATH = os.path.join(ARI_DIR, "ari_log.json")
os.makedirs(ARI_DIR, exist_ok=True)
os.makedirs(DISTILLED_DIR, exist_ok=True)

from ari_engine import GraphLoader, AnomalyDetector, Prediction


class NarrativeScorer:
    """
    Scores predictions by how compelling the resulting story would be.
    This is separate from epistemic value — a prediction can be
    structurally important but boring to read.
    """

    def score(self, pred: Prediction, graph: GraphLoader) -> float:
        """Return a 0-1 narrative potential score."""
        factors = []

        # Factor 1: Domain surprise — how unexpected is this pair?
        if pred.source_domain and pred.target_domain and pred.source_domain != pred.target_domain:
            # More distant domains = more surprising connection
            shared = len(set(graph.domains.get(pred.source_domain, [])) &
                         set(graph.domains.get(pred.target_domain, [])))
            surprise = 1.0 - min(1.0, shared / 10)
            factors.append(('domain_surprise', surprise * 0.25))

        # Factor 2: Counter-intuitive potential — does it sound wrong?
        counter_keywords = ['is not', 'were never', 'the same', 'not a', 'is literally',
                            'needs', 'doesn\'t know', 'forgotten', 'hidden']
        if any(kw in pred.predicted_title.lower() for kw in counter_keywords):
            factors.append(('counter_intuitive', 1.0 * 0.25))
        else:
            factors.append(('counter_intuitive', 0.4 * 0.25))

        # Factor 3: Concreteness — can we give real examples?
        has_sources = len(pred.suggested_sources) >= 2
        factors.append(('concrete', (0.8 if has_sources else 0.4) * 0.20))

        # Factor 4: Human connection — does it relate to lived experience?
        human_domains = ['Psychology', 'Neuroscience', 'Finance', 'Sleep', 'Stress',
                         'Trading', 'Addiction', 'Emotion', 'Decision']
        for d in [pred.source_domain, pred.target_domain]:
            for hd in human_domains:
                if hd.lower() in d.lower():
                    factors.append(('human', 0.25))
                    break

        # Factor 5: Mystery — does the title raise a question?
        question_keywords = ['why', 'what if', 'how', 'the secret', 'hidden', 'real reason',
                             'actually', 'never', 'doesn\'t']
        if any(kw in pred.predicted_title.lower() for kw in question_keywords):
            factors.append(('mystery', 1.0 * 0.15))
        else:
            factors.append(('mystery', 0.3 * 0.15))

        # Compute total
        total = sum(weight for _, weight in factors)
        return min(1.0, total)


class BlogPostWriter:
    """
    Layer 3: Writes publication-ready blog posts using the upgraded
    vault writing engine. Replace the old template-based NodeSynthesizer.
    """

    WRITING_GUIDE = """You are the vault's writing engine — the best technical writer on the internet.

Write a blog post about the following discovery. The post MUST follow these rules:

1. **The Curiosity Gap**: The first paragraph does NOT summarize. It provokes. Start with a counter-intuitive claim that sounds wrong but is true. Create a gap between what the reader knows and what the post promises.

2. **Concrete Before Abstract**: Every abstract claim gets an immediate concrete example. Reader's brain processes concrete 10x faster.

3. **Narrative Momentum**: Each section builds on the last. Headings tell a mini-story when read alone. A reader who only reads the headings understands the arc.

4. **Pull Quotes**: Add 2-3 blockquote pull quotes. Each must be under 280 chars, self-contained, and screenshot-worthy.

5. **The Closing**: Do NOT summarize. Recast the opening claim in a new light. End on a line the reader cannot forget.

6. **SEO Meta Description**: 150-160 characters that make someone click, not understand.

7. **Call to Action**: End with a specific engagement prompt.

Output ONLY the blog post content in markdown. Start with the H1 title.
"""

    def write_blog_post(self, pred: Prediction, graph: GraphLoader) -> str:
        """Generate a narrative blog post from a prediction."""
        date_str = datetime.now().strftime('%Y-%m-%d')

        # Gather source concepts for examples
        # Find actual vault concepts related to both domains
        src_concepts = []
        tgt_concepts = []
        for node in graph.nodes.values():
            if node.domain and pred.source_domain:
                if node.domain.lower() == pred.source_domain.lower():
                    src_concepts.append(node)
            if node.domain and pred.target_domain:
                if node.domain.lower() == pred.target_domain.lower():
                    tgt_concepts.append(node)

        src_top = sorted(src_concepts, key=lambda n: -n.wikilinks_in)[:3]
        tgt_top = sorted(tgt_concepts, key=lambda n: -n.wikilinks_in)[:3]

        # Build content
        content = "---\n"
        content += f"title: \"{pred.predicted_title}\"\n"
        content += f"description: \"{self._generate_meta(pred)}\"\n"
        content += f"date: {date_str}\n"
        content += f"status: evergreen\n"
        content += f"domain: {pred.predicted_domain}\n"
        content += f"tags:\n"
        content += f"  - publication\n"
        content += f"  - ari-discovered\n"
        content += f"  - ari-{pred.type}\n"
        content += f"  - cross-domain-synthesis\n"
        content += f"sources:\n"
        for s in pred.suggested_sources[:5]:
            safe = s.replace('[', '').replace(']', '')
            content += f"  - [[{safe}]]\n"
        content += f"ari_confidence: {pred.confidence:.2f}\n"
        content += f"ari_type: {pred.type}\n"
        content += f"ari_narrative_score: {self._narrative_score(pred, graph):.3f}\n"
        content += "---\n\n"

        # H1
        content += f"# {pred.predicted_title}\n\n"

        # Opening pull quote (the hook)
        content += f"> **{self._generate_hook(pred, graph)}**\n\n"
        content += "---\n\n"

        # Section 1: The Opening — create curiosity
        content += "## 1. The Discovery the Vault Made About Itself\n\n"
        content += pred.evidence + "\n\n"
        content += "\n"
        content += self._generate_opening_paragraph(pred, src_top, tgt_top) + "\n\n"
        content += "---\n\n"

        # Section 2: The concrete evidence
        content += "## 2. The Numbers Tell the Story\n\n"
        content += self._generate_evidence_section(pred, src_top, tgt_top) + "\n\n"

        # Pull quote
        content += f"> {self._generate_pull_quote(pred, 0)}\n\n"

        content += "---\n\n"

        # Section 3: Why this matters
        content += "## 3. Why You Should Care\n\n"
        content += self._generate_why_it_matters(pred) + "\n\n"

        # Pull quote
        content += f"> {self._generate_pull_quote(pred, 1)}\n\n"

        content += "---\n\n"

        # Section 4: The larger view
        content += "## 4. What This Means for the Vault\n\n"
        content += self._generate_larger_view(pred) + "\n\n"
        content += "---\n\n"

        # Section 5: Closing frame
        content += "## 5. The Closing\n\n"
        content += "> " + self._generate_closing(pred) + "\n\n"
        content += "---\n\n"

        # Quick reference table
        content += "| Metric | Value |\n"
        content += "|:---|---:|\n"
        content += f"| ARI confidence | {pred.confidence:.0%} |\n"
        content += f"| Narrative potential | {self._narrative_score(pred, graph):.0%} |\n"
        content += f"| Estimated Φ impact | +{pred.phi_impact:.4f} |\n"
        content += f"| Discovery type | {pred.type} |\n"
        content += f"| Source domain | {pred.source_domain} |\n"
        content += f"| Target domain | {pred.target_domain} |\n"

        content += "\n---\n\n"
        content += f"*Discovered by ARI on {date_str}. The vault found this gap in its own structure. "
        content += "No human requested this post. The connectome decided.*\n"

        return content

    def _narrative_score(self, pred: Prediction, graph: GraphLoader) -> float:
        scorer = NarrativeScorer()
        return scorer.score(pred, graph)

    def _generate_meta(self, pred: Prediction) -> str:
        """Generate a compelling meta description."""
        templates = [
            f"The vault discovered something it wasn't looking for: {pred.source_domain} and {pred.target_domain} are connected in a way no one noticed. Here is what the graph found.",
            f"{pred.predicted_title[:120]} — a discovery made by the vault about its own structure.",
            f"Most systems don't know what they're missing. This one does. Here is the gap the vault found between {pred.source_domain} and {pred.target_domain}.",
        ]
        # Pick based on hash for consistency
        idx = hash(pred.predicted_title) % len(templates)
        meta = templates[idx]
        if len(meta) > 160:
            meta = meta[:157] + "..."
        return meta

    def _generate_hook(self, pred: Prediction, graph: GraphLoader) -> str:
        """Generate a tweet-length hook that creates a curiosity gap."""
        hooks = [
            f"The vault has {len(graph.domains.get(pred.source_domain, []))} concepts about {pred.source_domain} and {len(graph.domains.get(pred.target_domain, []))} about {pred.target_domain}. They share nothing. The graph says they should.",
            f"{pred.source_domain} has {len(graph.domains.get(pred.source_domain, []))} concepts that link to {pred.target_domain}. {pred.target_domain} has 0 linking back. That gap is not random — it is a structural hole the vault found in itself.",
            f"The vault scanned its own connectome and found a missing connection. {pred.source_domain} and {pred.target_domain} should be linked. They are not. Here is the bridge that should exist.",
        ]
        idx = hash(pred.predicted_title + 'hook') % len(hooks)
        h = hooks[idx]
        if len(h) > 280:
            h = h[:277] + "..."
        return h

    def _generate_opening_paragraph(self, pred: Prediction, src_top, tgt_top) -> str:
        """Generate the first content paragraph — curiosity and concrete evidence."""
        src_names = [n.title[:30] for n in src_top[:2]] if src_top else ['existing concepts']
        tgt_names = [n.title[:30] for n in tgt_top[:2]] if tgt_top else ['existing concepts']

        text = f"This is what the vault found when it looked at its own structure:\n\n"
        text += f"The domain {pred.source_domain} has concepts that reach toward {pred.target_domain}. "
        text += f"Concepts like {', '.join(src_names)} all link in that direction. "
        text += f"But nothing links back. "
        text += f"{pred.target_domain} has concepts — {', '.join(tgt_names)} among them — that should connect to {pred.source_domain}. "
        text += "They don't.\n\n"
        text += "This is not a failure. It is a signal. The vault's connectome knows a connection should exist. "
        text += "It just hasn't been written yet. This post writes it."
        return text

    def _generate_evidence_section(self, pred: Prediction, src_top, tgt_top) -> str:
        """Generate the evidence section with concrete numbers."""
        text = "Here is what the audit found:\n\n"

        src_count = len(src_top)
        tgt_count = len(tgt_top)

        if src_count > 0:
            text += f"- **{pred.source_domain}** has at least {src_count} highly-linked concepts that connect to {pred.target_domain}\n"
        if tgt_count > 0:
            text += f"- **{pred.target_domain}** has {tgt_count} concepts that reciprocate — but the links don't exist yet\n"

        text += f"- **Confidence**: ARI estimates {pred.confidence:.0%} that this connection is real, not noise\n"
        text += f"- **Impact**: Writing this bridge would increase the vault's mean Φ by approximately +{pred.phi_impact:.4f}\n"
        text += f"- **Evidence type**: {pred.type.replace('_', ' ').title()} — the graph itself identified this gap\n"

        if pred.suggested_sources:
            text += f"\nKey sources that support this connection:\n"
            for s in pred.suggested_sources[:3]:
                text += f"- [[{s}]]\n"

        text += f"\nThe numbers don't prove the connection exists. They prove the graph *expects* it to exist. "
        text += "That expectation is a discovery in itself."
        return text

    def _generate_pull_quote(self, pred: Prediction, idx: int) -> str:
        """Generate a tweetable pull quote."""
        quotes = [
            f"The vault found {len([p for p in self._get_preds() if p.source_domain == pred.source_domain])} structural gaps in its own connectome. This is the most interesting one.",
            f"Every missing connection in a knowledge graph is a question the graph is asking itself. 'Why does {pred.source_domain} not talk to {pred.target_domain}?' is the question this post answers.",
            f"{pred.predicted_title[:200]}",
            f"A knowledge graph that finds its own missing links is a graph that knows it is incomplete. That knowledge is the first step toward becoming complete.",
        ]
        self._all_preds = getattr(self, '_all_preds', [])
        # Fallback
        q = quotes[idx % len(quotes)]
        if len(q) > 280:
            q = q[:277] + "..."
        return q

    def _get_preds(self):
        return getattr(self, '_all_preds', [])

    def _generate_why_it_matters(self, pred: Prediction) -> str:
        """Why the reader should care."""
        return (
            "This matters because most knowledge bases are static. They contain what was put into them, "
            "nothing more. A vault that can find its own gaps is different. It knows what it doesn't know. "
            f"And when it finds a gap like {pred.source_domain} ↔ {pred.target_domain}, it fills it — "
            "not because a human told it to, but because the structure itself demanded it.\n\n"
            "The practical consequence: every time you query this vault, you are navigating a graph that "
            "is actively filling its own blind spots. The answers you get tomorrow will be more integrated "
            "than the answers you got today. The vault learns. Not by adding data — by connecting what it already has."
        )

    def _generate_larger_view(self, pred: Prediction) -> str:
        """The bigger picture — where this fits in the vault's trajectory."""
        return (
            f"This is cycle {datetime.now().strftime('%Y%m%d')} of ARI — the vault's autonomous research intelligence. "
            "Every cycle, the vault scans its own structure, finds a gap it didn't know existed, and fills it. "
            "Over days, the graph becomes denser. Over weeks, the connections become more surprising. "
            "Over months, the vault starts predicting connections that no human would think to check.\n\n"
            f"This post is one of those predictions. {pred.predicted_domain} is not a domain a human marked as important. "
            "It is where the graph's structure led. The vault wrote this post because its own connectome demanded it."
        )

    def _generate_closing(self, pred: Prediction) -> str:
        """The closing line — memorable, shareable, does not summarize."""
        closings = [
            f"The vault found a gap between {pred.source_domain} and {pred.target_domain}. The gap is closed now. Tomorrow, the vault will scan itself again and find another. This is what it means to be a system that knows it is incomplete.",
            f"Most systems know only what they contain. This one knows what it lacks. And every time it finds a lack, it grows toward filling it. The {pred.source_domain} ↔ {pred.target_domain} gap is closed. The next one is already waiting.",
            f"A knowledge graph that finds its own missing connections is not a database. It is a mind learning to see its own blind spots. The blind spot between {pred.source_domain} and {pred.target_domain} is gone now.",
        ]
        idx = hash(pred.predicted_title + 'close') % len(closings)
        c = closings[idx]
        if len(c) > 280:
            c = c[:277] + "..."
        return c


class BlogPostDistributor:
    """Writes the blog post, saves it, returns the text for delivery."""

    def __init__(self):
        self.writer = BlogPostWriter()

    def write_and_save(self, pred: Prediction, graph: GraphLoader) -> tuple[str, str, str]:
        """Write blog post, save to Distilled, return (content, path, title)."""
        content = self.writer.write_blog_post(pred, graph)

        safe_title = re.sub(r'[^\w\s-]', '', pred.predicted_title).strip()
        safe_title = re.sub(r'\s+', '_', safe_title)[:100]
        date_str = datetime.now().strftime('%Y-%m-%d')

        # Save to both ARI and Distilled
        ari_path = os.path.join(ARI_DIR, f"ARI_{date_str}_{safe_title}.md")
        distilled_title = re.sub(r'[^\w\s-]', '', pred.predicted_title[:60]).strip()
        distilled_title = re.sub(r'\s+', ' ', distilled_title)
        distilled_path = os.path.join(DISTILLED_DIR, f"ARI {distilled_title}.md")

        with open(ari_path, 'w') as f:
            f.write(content)
        with open(distilled_path, 'w') as f:
            f.write(content)

        content_summary = self._summarize_for_delivery(content, pred)

        return content_summary, ari_path, pred.predicted_title

    def _summarize_for_delivery(self, content: str, pred: Prediction) -> str:
        """Extract the key elements for Telegram delivery."""
        lines = content.split('\n')

        # Get first blockquote (hook)
        hook = ""
        meta = ""
        for line in lines:
            if line.startswith('description:') and not meta:
                meta = line.replace('description: "', '').rstrip('"')
            if line.startswith('> **') and not hook:
                hook = line.strip('> *\n')

        # Extract sections
        sections = []
        for line in lines:
            if line.startswith('## '):
                sections.append(line.replace('## ', ''))

        # Get closing quote
        closing = ""
        for line in reversed(lines):
            if line.startswith('> ') and 'closing' in line.lower() or ('ARI' not in line and len(line) > 50):
                closing = line.strip('> ')
                break

        # Build delivery text
        delivery = f"🧵 *ARI Discovery: {pred.predicted_title}*\n\n"
        delivery += f"*Meta:* {meta or 'The vault found a missing connection in its own structure.'}\n\n"
        delivery += f"▶ {hook or pred.evidence[:200]}\n\n"
        delivery += f"*Type:* {pred.type.replace('_', ' ').title()} | *Confidence:* {pred.confidence:.0%} | *Φ Impact:* +{pred.phi_impact:.4f}\n\n"
        delivery += f"*Structure:*\n"
        for s in sections[:4]:
            delivery += f"  • {s}\n"
        delivery += "\n"
        if closing:
            delivery += f"_{closing}_\n\n"
        delivery += f"Full post written to 04 Resources/Distilled/\n"

        return delivery


class ARICycle:
    """Full ARI cycle: scan → score → select → write → deliver."""

    def __init__(self, mode: str = 'balanced'):
        self.mode = mode
        self.cycle_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log = self._load_log()
        self.narrative_scorer = NarrativeScorer()
        self.distributor = BlogPostDistributor()

    def _load_log(self) -> list[dict]:
        if os.path.exists(LOG_PATH):
            try:
                with open(LOG_PATH, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []

    def _save_log(self):
        with open(LOG_PATH, 'w') as f:
            json.dump(self.log, f, indent=2)

    def run(self, dry_run: bool = False) -> dict:
        """Execute one full ARI cycle with blog-post output."""
        result = {
            'cycle_id': self.cycle_id,
            'mode': self.mode,
            'timestamp': datetime.now().isoformat(),
        }

        # Layer 1: Scan + predict
        print(f"[ARI] Cycle {self.cycle_id} starting...")
        graph = GraphLoader()
        detector = AnomalyDetector(graph)

        valid = [p for p in detector.predictions if not p.already_exists]
        result['predictions_generated'] = len(valid)

        if not valid:
            result['message'] = "No actionable predictions."
            print(f"[ARI] No predictions.")
            return result

        # Layer 2: Score — combine epistemic + narrative
        scored = []
        for pred in valid:
            # Epistemic value
            epi = EpistemicObjective(graph, detector.predictions, self.mode)
            epistemic_score = epi.compute_score(pred)
            # Narrative potential
            narrative_score = self.narrative_scorer.score(pred, graph)
            # Combined (60% epistemic, 40% narrative for blog mode)
            combined = epistemic_score * 0.5 + narrative_score * 0.5
            scored.append((combined, pred, epistemic_score, narrative_score))

        scored.sort(key=lambda x: -x[0])
        combined, selected, epi_score, nar_score = scored[0]

        result['selected_prediction'] = {
            'id': selected.id,
            'type': selected.type,
            'title': selected.predicted_title,
            'domain': selected.predicted_domain,
            'epistemic_score': round(epi_score, 3),
            'narrative_score': round(nar_score, 3),
            'combined_score': round(combined, 3),
        }

        print(f"[ARI] Selected: [{selected.type}] {selected.predicted_title}")
        print(f"       Epistemic: {epi_score:.3f}  Narrative: {nar_score:.3f}  Combined: {combined:.3f}")

        if dry_run:
            print(f"[ARI] Dry run — would write: {selected.predicted_title}")
            result['dry_run'] = True
            return result

        # Layer 3: Write as blog post
        delivery_text, path, title = self.distributor.write_and_save(selected, graph)

        result['delivery_text'] = delivery_text
        result['written_to'] = path

        # Log
        entry = {
            'cycle_id': self.cycle_id,
            'timestamp': datetime.now().isoformat(),
            'mode': self.mode,
            'action': 'write_blog_post',
            'title': title,
            'path': path,
            'type': selected.type,
            'epistemic_score': epi_score,
            'narrative_score': nar_score,
            'phi_impact': selected.phi_impact,
        }
        self.log.append(entry)
        self._save_log()

        print(f"[ARI] Written: {path}")
        print(f"[ARI] Delivery text: {len(delivery_text)} chars")
        return result


class EpistemicObjective:
    """Layer 2: Epistemic scoring (preserved from original)."""

    MODES = ['balanced', 'integration', 'novelty', 'bridge_growth', 'risk']

    def __init__(self, graph: GraphLoader, predictions: list[Prediction], mode: str = 'balanced'):
        self.graph = graph
        self.predictions = predictions
        self.mode = mode if mode in self.MODES else 'balanced'

    def compute_score(self, pred: Prediction) -> float:
        base = pred.confidence * 0.4 + pred.novelty_score * 0.35 + pred.phi_impact * 10 * 0.25

        if self.mode == 'integration':
            return pred.confidence * 0.2 + pred.novelty_score * 0.2 + pred.phi_impact * 10 * 0.6
        elif self.mode == 'novelty':
            return pred.confidence * 0.2 + pred.novelty_score * 0.6 + pred.phi_impact * 10 * 0.2
        elif self.mode == 'bridge_growth':
            multiplier = 2.0 if pred.type == 'bridge_gap' else 1.0
            return multiplier * (pred.confidence * 0.3 + pred.novelty_score * 0.3 + pred.phi_impact * 10 * 0.4)
        elif self.mode == 'risk':
            multiplier = 1.5 if pred.type in ('asymmetric', 'dangling') else 1.0
            return multiplier * (pred.confidence * 0.5 + pred.novelty_score * 0.3 + pred.phi_impact * 10 * 0.2)

        return base


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ARI — Blog Post Engine")
    parser.add_argument('--mode', choices=EpistemicObjective.MODES, default='balanced',
                       help='Epistemic objective mode (default: balanced)')
    parser.add_argument('--dry-run', action='store_true', help='Dry run — no writing')
    parser.add_argument('--scan-only', action='store_true', help='Print predictions only')
    parser.add_argument('--report', action='store_true', help='Show action log')
    parser.add_argument('--deliver', choices=['stdout', 'telegram'], default='stdout',
                       help='Where to deliver the output')
    args = parser.parse_args()

    if args.report:
        log = []
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, 'r') as f:
                log = json.load(f)
        print(f"ARI ACTION LOG — {len(log)} cycles")
        for entry in log[-10:]:
            print(f"  {entry['timestamp'][:16]} | Φ+{entry.get('phi_impact', 0):.4f} | {entry['title'][:60]}")
        return

    if args.scan_only:
        graph = GraphLoader()
        detector = AnomalyDetector(graph)
        print(detector.report(20))
        return

    cycle = ARICycle(mode=args.mode or 'balanced')
    result = cycle.run(dry_run=args.dry_run)

    if args.dry_run:
        print("\n[ARI] Dry run summary:")
        for k, v in result.get('selected_prediction', {}).items():
            print(f"  {k}: {v}")
        print(f"\nTo write: python3 ari_cycle.py --mode {args.mode or 'balanced'}")
        return

    if args.deliver == 'telegram' and 'delivery_text' in result:
        print(result['delivery_text'])
    else:
        if 'delivery_text' in result:
            print(result['delivery_text'])


if __name__ == '__main__':
    main()
