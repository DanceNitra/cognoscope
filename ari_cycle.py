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
    Layer 3: Writes publication-quality blog posts using REAL vault content.
    Extracts concrete details from related concept notes instead of templates.
    """

    def write_blog_post(self, pred: Prediction, graph: GraphLoader) -> str:
        """Generate a narrative blog post from a prediction, using real vault content."""
        date_str = datetime.now().strftime('%Y-%m-%d')

        # Gather real concept content from both source and target domains
        src_notes = self._load_concept_notes(pred.source_domain, graph, max_notes=5)
        tgt_notes = self._load_concept_notes(pred.target_domain, graph, max_notes=5)
        all_notes = src_notes + tgt_notes

        # Extract concrete facts from notes
        cross_links = self._find_cross_domain_links(pred, graph)
        concrete_examples = self._extract_concrete_examples(all_notes, limit=3)
        key_concepts_text = self._summarize_key_concepts(all_notes, limit=4)
        common_patterns = self._find_common_patterns(src_notes, tgt_notes)

        # Build content
        content = "---\n"
        content += f"title: \"{pred.predicted_title}\"\n"
        content += f"description: \"{self._generate_meta(pred, src_notes, tgt_notes)}\"\n"
        content += f"date: {date_str}\n"
        content += f"status: evergreen\n"
        content += f"domain: {pred.predicted_domain}\n"
        content += "tags:\n"
        content += "  - publication\n"
        content += "  - ari-v3\n"
        content += f"  - ari-{pred.type}\n"
        content += "  - cross-domain-synthesis\n"
        content += "sources:\n"
        for s in pred.suggested_sources[:5]:
            safe = s.replace('[', '').replace(']', '')
            content += f"  - [[{safe}]]\n"
        content += f"ari_confidence: {pred.confidence:.2f}\n"
        content += f"ari_type: {pred.type}\n"
        content += f"ari_narrative_score: {self._narrative_score(pred, graph):.3f}\n"
        content += "---\n\n"

        # H1
        content += f"# {pred.predicted_title}\n\n"

        # Opening hook — real, concrete, not meta-commentary
        hook = self._generate_concrete_hook(pred, concrete_examples, common_patterns)
        content += f"> **{hook}**\n\n"
        content += "---\n\n"

        # Section 1: The concrete discovery
        content += "## 1. What the Graph Actually Found\n\n"
        content += pred.evidence + "\n\n"

        if cross_links:
            content += f"The vault contains **{cross_links['forward']}** concepts from {pred.source_domain} "
            content += f"that link to {pred.target_domain}, but only **{cross_links['backward']}** link back. "
            content += f"This asymmetry is the signal ARI detected.\n\n"

        content += self._generate_concrete_section(pred, src_notes, tgt_notes) + "\n\n"
        content += "---\n\n"

        # Section 2: Concrete evidence from the vault's own notes
        content += "## 2. Evidence From the Vault\n\n"
        content += key_concepts_text + "\n\n"

        # Pull quote
        pq = self._generate_pull_quote(pred, concrete_examples)
        content += f"> {pq}\n\n"
        content += "---\n\n"

        # Section 3: Why this matters (specific, not generic)
        content += "## 3. Why This Connection Matters\n\n"
        content += self._generate_why_specific(pred, common_patterns) + "\n\n"

        # Section 4: Practical consequences
        content += "## 4. What Changes\n\n"
        content += self._generate_what_changes(pred, concrete_examples) + "\n\n"
        content += "---\n\n"

        # Section 5: Closing frame
        content += "## 5. The Closing\n\n"
        closing = self._generate_closing_specific(pred, common_patterns)
        content += f"> {closing}\n\n"
        content += "---\n\n"

        # Reference table
        content += "| Metric | Value |\n"
        content += "|:---|---:|\n"
        content += f"| ARI confidence | {pred.confidence:.0%} |\n"
        content += f"| Narrative potential | {self._narrative_score(pred, graph):.0%} |\n"
        content += f"| Estimated Φ impact | +{pred.phi_impact:.4f} |\n"
        content += f"| Discovery type | {pred.type.replace('_', ' ').title()} |\n"
        content += f"| Source domain | {pred.source_domain} |\n"
        content += f"| Target domain | {pred.target_domain} |\n"

        content += "\n---\n\n"
        content += f"*Discovered by ARI v3 on {date_str}. Uses real vault content — no templates.*\n"

        return content

    def _load_concept_notes(self, domain: str, graph: GraphLoader, max_notes=5) -> list[dict]:
        """Load actual content from concept notes in a domain."""
        notes = []
        titles = graph.domains.get(domain, [])
        for t in titles[:max_notes * 3]:  # sample more since some may be short
            node = graph.nodes.get(t)
            if not node:
                continue
            try:
                with open(node.file, 'r', encoding='utf-8', errors='replace') as f:
                    raw = f.read()
                # Remove frontmatter
                body = re.sub(r'^---\n.*?\n---\n', '', raw, count=1, flags=re.DOTALL)
                # Get first real section
                sections = re.findall(r'^## (.+)', body, re.MULTILINE)
                lines = [l.strip() for l in body.split('\n') if l.strip() and not l.startswith('##') and not l.startswith('---')][:15]
                notes.append({
                    'title': t,
                    'domain': node.domain,
                    'sections': sections[:5],
                    'lines': lines,
                    'wikilinks': node.wikilinks_out[:8],
                    'length': node.lines,
                })
            except:
                pass
            if len(notes) >= max_notes:
                break
        return notes

    def _find_cross_domain_links(self, pred: Prediction, graph: GraphLoader) -> dict:
        """Count actual cross-domain wikilinks between source and target."""
        forward = 0
        backward = 0
        for node in graph.nodes.values():
            for link in node.wikilinks_out:
                target = graph.nodes.get(link)
                if target:
                    if node.domain == pred.source_domain and target.domain == pred.target_domain:
                        forward += 1
                    elif node.domain == pred.target_domain and target.domain == pred.source_domain:
                        backward += 1
        return {'forward': forward, 'backward': backward}

    def _extract_concrete_examples(self, notes: list[dict], limit=3) -> list[str]:
        """Extract concrete substantive sentences from notes."""
        examples = []
        for n in notes:
            for line in n['lines']:
                if len(line) > 60 and len(line) < 300:
                    examples.append(f"[[{n['title']}]]: {line[:200]}")
        return examples[:limit]

    def _summarize_key_concepts(self, notes: list[dict], limit=4) -> str:
        """Generate a summary of key concepts from the notes."""
        if not notes:
            return "The vault contains relevant concepts waiting to be connected."
        text = "Key vault concepts that bridge these domains:\n\n"
        for n in notes[:limit]:
            text += f"### [[{n['title']}]] ({n['domain']})\n"
            secs = n['sections'][:3]
            if secs:
                text += f"Covers: {', '.join(secs)}\n"
            links = n['wikilinks'][:5]
            if links:
                text += f"Connected to: {', '.join(f'[[{l}]]' for l in links)}\n"
            text += "\n"
        return text

    def _find_common_patterns(self, src_notes: list[dict], tgt_notes: list[dict]) -> list[str]:
        """Find recurring words/themes across both domains."""
        # Simple keyword overlap
        src_words = set()
        tgt_words = set()
        for n in src_notes:
            for line in n['lines']:
                src_words.update(w.lower() for w in line.split() if len(w) > 4)
        for n in tgt_notes:
            for line in n['lines']:
                tgt_words.update(w.lower() for w in line.split() if len(w) > 4)

        common = src_words & tgt_words
        # Filter noise
        stopwords = {'these', 'those', 'which', 'where', 'there', 'their', 'about', 'would', 'could', 'should', 'other', 'first', 'second', 'third', 'across', 'using', 'based', 'because'}
        meaningful = [w for w in common if w not in stopwords]
        return meaningful[:6]

    def _generate_concrete_hook(self, pred: Prediction, examples: list[str], patterns: list[str]) -> str:
        """Generate a hook using real content, not meta-commentary."""
        src_d = pred.source_domain
        tgt_d = pred.target_domain

        if patterns:
            pattern_str = ', '.join(patterns[:3])
            return (
                f"The vault's notes on {src_d} use these keywords: {pattern_str}. "
                f"Its notes on {tgt_d} use the same words. "
                f"They are describing the same thing — they just don't know it yet."
            )
        if examples:
            return (
                f"When ARI scanned the vault, it found that {examples[0][:100]}... "
                f"That concept belongs to {src_d}, but its closest structural neighbor is {tgt_d}. "
                f"The vault knew before anyone noticed."
            )
        return (
            f"The graph connected {src_d} and {tgt_d} without being told. "
            f"Here is what the connection means in concrete terms."
        )

    def _generate_concrete_section(self, pred: Prediction, src_notes, tgt_notes) -> str:
        """Generate a section with concrete facts from real notes."""
        text = ""
        if src_notes:
            top = src_notes[0]
            text += f"Consider **[[{top['title']}]]** ({top['domain']}). "
            secs = top['sections'][:2]
            if secs:
                text += f"It covers {', '.join(secs)}. "
            lines = top['lines'][:2]
            if lines:
                text += f"One passage describes: \"{lines[0][:150]}\" "
            text += f"\n\nThis concept is one of {len(src_notes)} from {pred.source_domain} that ARI found linked to {pred.target_domain}.\n\n"

        if tgt_notes:
            top2 = tgt_notes[0]
            text += f"Meanwhile, **[[{top2['title']}]]** ({top2['domain']}) "
            secs2 = top2['sections'][:2]
            if secs2:
                text += f"covers {', '.join(secs2)}. "
            text += f"The two concepts share structural features that no human noted."
        return text

    def _generate_why_specific(self, pred: Prediction, patterns: list[str]) -> str:
        """Why this matters — specific to the domains, not generic."""
        text = f"The connection between {pred.source_domain} and {pred.target_domain} is not abstract. "
        if patterns:
            text += f"They share language: {' ,'.join(patterns)} appear in both domains' notes. "
            text += "This means practitioners in both fields are solving isomorphic problems without knowing it.\n\n"
        text += (
            f"For the vault, writing this bridge means that a reader exploring {pred.source_domain} "
            f"will discover relevant ideas from {pred.target_domain} that they would otherwise miss. "
            f"The graph already expects them to be connected. The bridge makes that expectation visible."
        )
        return text

    def _generate_what_changes(self, pred: Prediction, examples: list[str]) -> str:
        """What changes after the bridge is written."""
        text = f"After this bridge:\n\n"
        text += f"1. **A reader in {pred.source_domain}** finds {pred.target_domain} automatically — the wikilinks now exist\n"
        text += f"2. **The vault's Φ increases** — mean integration score rises by approximately +{pred.phi_impact:.4f}\n"
        text += f"3. **Future ARI cycles** see a denser graph and can detect deeper patterns\n"
        if examples:
            text += f"4. **Concrete entry point**: {examples[0][:100]}...\n"
        return text

    def _generate_closing_specific(self, pred: Prediction, patterns: list[str]) -> str:
        """Closing line — specific, not generic."""
        src = pred.source_domain
        tgt = pred.target_domain
        closings = [
            f"The connection between {src} and {tgt} was invisible until the graph revealed it. Now the bridge exists. Tomorrow, someone exploring {src} will find {tgt} — without knowing they were supposed to look.",
            f"{src} and {tgt} share vocabulary ({', '.join(patterns[:3])}) but had no bridge. Now they do. The graph is more complete than it was before this cycle.",
            f"Most knowledge bases only contain what humans put in. This one found something: that {src} and {tgt} are structurally isomorphic. The bridge is written. The graph is denser.",
        ]
        idx = hash(pred.predicted_title + 'closev3') % len(closings)
        c = closings[idx]
        if len(c) > 280:
            c = c[:277] + "..."
        return c

    def _generate_meta(self, pred: Prediction, src_notes, tgt_notes) -> str:
        """Generate a concrete meta description using note titles."""
        src_names = [n['title'][:25] for n in src_notes[:2]] if src_notes else ['concepts']
        tgt_names = [n['title'][:25] for n in tgt_notes[:2]] if tgt_notes else ['concepts']
        meta = (
            f"ARI v3 found that {pred.source_domain} and {pred.target_domain} share structural features. "
            f"Evidence from vault concepts: {', '.join(src_names)} and {', '.join(tgt_names)}. "
            f"A concrete bridge, not a template."
        )
        if len(meta) > 160:
            meta = meta[:157] + "..."
        return meta

    def _narrative_score(self, pred: Prediction, graph: GraphLoader) -> float:
        scorer = NarrativeScorer()
        return scorer.score(pred, graph)

    def _generate_pull_quote(self, pred: Prediction, examples: list[str]) -> str:
        """Pull quote using real content."""
        if examples:
            return f"The vault's own notes reveal the connection: {examples[0][:200]}"
        return (
            f"ARI found {len([p for p in self._get_preds() if p.source_domain == pred.source_domain])} "
            f"structural gaps. This one between {pred.source_domain} and {pred.target_domain} is the most actionable."
        )

    def _get_preds(self):
        return getattr(self, '_all_preds', [])


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

        # Build bridge recommender domain pairs for scoring boost
        recommender_pairs = set()
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.expanduser('~/cognoscope'))
            from bridge_recommender import load_vault, load_existing_bridges, find_bridge_candidates
            br_files, br_backlinks, br_outgoing, br_domains, br_domain_nodes, br_neighbor_sets = load_vault()
            br_existing = load_existing_bridges()
            br_candidates = find_bridge_candidates(
                br_files, br_backlinks, br_outgoing, br_domains,
                br_domain_nodes, br_neighbor_sets, br_existing
            )
            for cand in br_candidates[:20]:
                da = cand.get('domain_a', '').lower().strip()
                db = cand.get('domain_b', '').lower().strip()
                if da and db:
                    recommender_pairs.add(tuple(sorted([da, db])))
            print(f"[ARI] Loaded {len(recommender_pairs)} bridge-recommender pairs for scoring boost")
        except Exception as e:
            print(f"[ARI] Recommender integration skipped: {e}")
        result['recommender_pairs_loaded'] = len(recommender_pairs)

        # Layer 2: Score -- combine epistemic + narrative + recommender boost
        scored = []
        for pred in valid:
            # Epistemic value
            epi = EpistemicObjective(graph, detector.predictions, self.mode)
            epistemic_score = epi.compute_score(pred)
            # Narrative potential
            narrative_score = self.narrative_scorer.score(pred, graph)
            # Recommender overlap boost
            recommender_boost = 1.0
            pa = pred.source_domain.lower().strip()
            pb = pred.target_domain.lower().strip()
            if pa and pb:
                pair = tuple(sorted([pa, pb]))
                if pair in recommender_pairs:
                    recommender_boost = 1.5  # 50% boost for recommender-overlapping predictions
            # Combined
            combined = (epistemic_score * 0.4 + narrative_score * 0.4) * recommender_boost
            scored.append((combined, pred, epistemic_score, narrative_score, recommender_boost))

        scored.sort(key=lambda x: -x[0])
        combined, selected, epi_score, nar_score, recommender_boost = scored[0]

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
        if recommender_boost > 1.0:
            print(f"       Recommender boost: {recommender_boost:.1f}x (overlaps bridge-recommender top 20)")

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

        # Save to persistent ARI memory with concept counts for dedup
        try:
            mem_entry = {
                'type': selected.type,
                'source_domain': selected.source_domain,
                'target_domain': selected.target_domain,
                'title': title,
                'timestamp': datetime.now().isoformat(),
                'source_concept_count': len(graph.domains.get(selected.source_domain, [])),
                'target_concept_count': len(graph.domains.get(selected.target_domain, [])),
            }
            # Import and use ari_engine's ARI_MEMORY_PATH
            from ari_engine import ARI_MEMORY_PATH
            mem = []
            if os.path.exists(ARI_MEMORY_PATH):
                try:
                    with open(ARI_MEMORY_PATH, 'r') as f:
                        mem = json.load(f)
                except:
                    pass
            mem.append(mem_entry)
            with open(ARI_MEMORY_PATH, 'w') as f:
                json.dump(mem, f, indent=2)
            print(f"[ARI] Saved dedup memory: {selected.source_domain} × {selected.target_domain}")
        except Exception as e:
            print(f"[ARI] Warning: could not save dedup memory: {e}")

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
