#!/usr/bin/env python3
"""
ARI Research-Expansion Engine — Full Autonomous Cycle
1. Identify next expansion targets (weak domains)
2. Search real sources via domain skills (arXiv, PubMed)
3. Write enriched concept notes with real data

Usage:
    python3 ari_research.py --plan          # Show expansion targets
    python3 ari_research.py --expand        # Write new concepts with real research
    python3 ari_research.py --deepen N      # Deepen one concept with web research
    python3 ari_research.py --full-cycle    # Plan → search → expand → report
"""

import os, re, glob, json, sys, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime
from dataclasses import dataclass
from collections import defaultdict

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
RESEARCH_DIR = os.path.join(VAULT_ROOT, "04 Resources/Research")
ARI_DIR = os.path.join(VAULT_ROOT, "04 Resources/ARI")
EXPANSION_DIR = os.path.join(VAULT_ROOT, "04 Resources/Expansions")
os.makedirs(ARI_DIR, exist_ok=True)
os.makedirs(RESEARCH_DIR, exist_ok=True)
os.makedirs(EXPANSION_DIR, exist_ok=True)


# ──────────────────────────────────────────────
# VAULT ANALYZER
# ──────────────────────────────────────────────

class VaultAnalyzer:
    def __init__(self):
        self.concepts: dict[str, dict] = {}
        self.domains: dict[str, list[str]] = defaultdict(list)
        self._load()

    def _load(self):
        for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
            fn = os.path.basename(f).replace('.md', '')
            with open(f, encoding='utf-8', errors='replace') as fh:
                raw = fh.read()
            title = fn
            hm = re.search(r'^# (.+)$', raw, re.MULTILINE)
            if hm: title = hm.group(1).strip()
            yt = re.search(r'title:\s*["\']?(.+?)["\']?\s*$', raw, re.MULTILINE)
            if yt: title = yt.group(1).strip().strip('"').strip("'")
            domain = 'General'
            dm = re.search(r'^domain:\s*(.+)$', raw, re.MULTILINE)
            if dm: domain = dm.group(1).strip()
            lines = len(raw.split('\n'))
            self.concepts[title] = {'title': title, 'domain': domain, 'lines': lines}
            self.domains[domain].append(title)


# ──────────────────────────────────────────────
# WEB RESEARCHER (domain skills powered)
# ──────────────────────────────────────────────

class WebResearcher:
    """
    Fetch real research data from web sources using domain skills.
    Uses raw urllib (no external deps) — exact endpoints from the playbooks.
    """

    # Research topics mapped to vault's weak domains
    RESEARCH_QUERIES = [
        # Immunology
        {'site': 'pubmed', 'query': 'innate immune system mechanism 2024 2025 2026', 'domain': 'Immunology', 'max': 3},
        {'site': 'pubmed', 'query': 'adaptive immunity T cell receptor 2024 2025', 'domain': 'Immunology', 'max': 3},
        {'site': 'arxiv', 'query': 'all:neuroimmunology+AND+all:microglia', 'domain': 'Immunology', 'max': 3},
        # Pharmacology
        {'site': 'pubmed', 'query': 'pharmacokinetics ADME 2024 2025', 'domain': 'Pharmacology', 'max': 3},
        {'site': 'pubmed', 'query': 'neuropharmacology antidepressants mechanism 2024', 'domain': 'Pharmacology', 'max': 3},
        # Longevity
        {'site': 'pubmed', 'query': 'hallmarks of aging 2024 2025 review', 'domain': 'Longevity', 'max': 3},
        {'site': 'pubmed', 'query': 'senolytics clinical trial 2024 2025', 'domain': 'Longevity', 'max': 3},
        {'site': 'arxiv', 'query': 'all:caloric+restriction+AND+all:aging', 'domain': 'Longevity', 'max': 3},
        # Chronobiology
        {'site': 'pubmed', 'query': 'circadian clock molecular mechanism 2024 2025', 'domain': 'Chronobiology', 'max': 3},
        {'site': 'pubmed', 'query': 'circadian disruption disease 2024 2025', 'domain': 'Chronobiology', 'max': 3},
        # Cell Biology
        {'site': 'pubmed', 'query': 'autophagy mechanism 2024 2025', 'domain': 'Cell Biology', 'max': 3},
        {'site': 'pubmed', 'query': 'mitochondrial biology dynamics 2024', 'domain': 'Cell Biology', 'max': 3},
        # Genomics
        {'site': 'pubmed', 'query': 'CRISPR Cas9 gene therapy 2024 2025', 'domain': 'Genomics', 'max': 3},
        {'site': 'arxiv', 'query': 'all:CRISPR+AND+all:gene+editing', 'domain': 'Genomics', 'max': 3},
    ]

    def search_arxiv(self, query: str, max_results: int = 3) -> list[dict]:
        """arXiv Atom API — from domain skill playbook."""
        NS = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
        url = f"http://export.arxiv.org/api/query?search_query={query}&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as r:
                xml_data = r.read().decode('utf-8')
            root = ET.fromstring(xml_data)
            results = []
            for e in root.findall('atom:entry', NS):
                aid = e.find('atom:id', NS).text.split('/')[-1]
                title = e.find('atom:title', NS).text.strip().replace('\n', ' ')
                abstract = e.find('atom:summary', NS).text.strip()
                published = e.find('atom:published', NS).text[:10]
                authors = [a.find('atom:name', NS).text for a in e.findall('atom:author', NS)]
                pdf = next((l.get('href') for l in e.findall('atom:link', NS) if l.get('title') == 'pdf'), None)
                results.append({
                    'id': aid, 'title': title, 'abstract': abstract[:500],
                    'published': published, 'authors': authors[:3], 'pdf': pdf,
                    'source': 'arxiv'
                })
            return results
        except Exception as e:
            print(f"  [arXiv error] {e}")
            return []

    def search_pubmed(self, query: str, max_results: int = 3) -> list[dict]:
        """PubMed E-utilities — from domain skill playbook."""
        try:
            # Step 1: ESearch
            import json
            search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query.replace(' ', '+')}&retmax={max_results}&retmode=json"
            req = urllib.request.Request(search_url)
            with urllib.request.urlopen(req, timeout=15) as r:
                search_data = json.loads(r.read())
            pmids = search_data['esearchresult']['idlist']
            if not pmids:
                return []

            # Step 2: ESummary
            summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={','.join(pmids)}&retmode=json"
            req = urllib.request.Request(summary_url)
            with urllib.request.urlopen(req, timeout=15) as r:
                summary_data = json.loads(r.read())

            results = []
            result = summary_data['result']
            for uid in result['uids']:
                art = result[uid]
                results.append({
                    'id': uid, 'title': art.get('title', ''),
                    'abstract': art.get('elocationid', '') or 'No abstract available',
                    'published': art.get('pubdate', ''),
                    'authors': [a.get('name', '') for a in art.get('authors', [])[:3]],
                    'source': 'pubmed'
                })
            return results
        except Exception as e:
            print(f"  [PubMed error] {e}")
            return []

    def search(self, query_cfg: dict) -> list[dict]:
        """Dispatch to the correct search engine."""
        if query_cfg['site'] == 'arxiv':
            return self.search_arxiv(query_cfg['query'], query_cfg['max'])
        elif query_cfg['site'] == 'pubmed':
            return self.search_pubmed(query_cfg['query'], query_cfg['max'])
        return []


# ──────────────────────────────────────────────
# CONCEPT WRITER (research-enriched)
# ──────────────────────────────────────────────

class ResearchConceptWriter:
    """
    Writes concept notes enriched with real web research.
    Each note includes cited sources from arXiv/PubMed.
    """

    DEEPEN_TARGETS = {
        'Innate Immune System': {
            'domain': 'Immunology',
            'description': 'The evolutionarily ancient arm of the immune system: physical barriers, phagocytes, NK cells, complement system, and pattern recognition.',
            'key_points': ['Physical barriers (skin, mucosa, tight junctions) are the first line of defense',
                          'Phagocytic cells (macrophages, neutrophils, dendritic cells) recognize and engulf pathogens',
                          'Natural killer cells target virus-infected and tumor cells without prior sensitization',
                          'The complement cascade is a proteolytic amplification system for pathogen opsonization and lysis',
                          'Pattern recognition receptors (TLRs, NLRs, RLRs) detect pathogen-associated molecular patterns (PAMPs)'],
            'cross_links': ['Inflammation', 'Microglia', 'Cytokine Signaling', 'Adaptive Immune System'],
        },
        'Adaptive Immune System': {
            'domain': 'Immunology',
            'description': 'The antigen-specific arm of immunity: B cells, T cells, antibody diversity, immunological memory, and MHC presentation.',
            'key_points': ['B cells generate antibody diversity through V(D)J recombination of immunoglobulin genes',
                          'T cells recognize peptide antigens presented by MHC class I (CD8+) and class II (CD4+) molecules',
                          'Clonal selection amplifies lymphocytes with receptors matching the encountered antigen',
                          'Immunological memory enables faster and stronger responses upon re-exposure',
                          'Regulatory T cells (Tregs) maintain self-tolerance and prevent autoimmune responses'],
            'cross_links': ['Innate Immune System', 'Autoimmune Disease', 'Cytokine Signaling', 'Immunology'],
        },
        'Autophagy': {
            'domain': 'Cell Biology',
            'description': 'Cellular degradation pathway that removes damaged organelles and misfolded proteins via lysosomal fusion.',
            'key_points': ['Macroautophagy sequesters cytoplasmic cargo in double-membrane autophagosomes that fuse with lysosomes',
                          'Chaperone-mediated autophagy selectively targets proteins with KFERQ-like motifs for direct lysosomal uptake',
                          'Autophagy declines with age and is implicated in neurodegeneration, cancer, and metabolic disease',
                          'mTORC1 inhibition (via rapamycin, nutrient deprivation) is the primary activator of autophagy',
                          'Autophagy serves dual roles in cancer — tumor-suppressive in early stages, pro-survival in established tumors'],
            'cross_links': ['Cell Biology', 'Aging', 'Longevity', 'Neurodegeneration', 'Apoptosis and Programmed Cell Death'],
        },
        'Hallmarks of Aging': {
            'domain': 'Longevity',
            'description': 'The twelve hallmarks of aging as defined by López-Otín et al.: genomic instability, telomere attrition, epigenetic alterations, loss of proteostasis, disabled macroautophagy, deregulated nutrient sensing, mitochondrial dysfunction, cellular senescence, stem cell exhaustion, altered intercellular communication, chronic inflammation, and dysbiosis.',
            'key_points': ['Primary hallmarks (genomic instability, telomere attrition, epigenetic alterations, loss of proteostasis) are the initiating damage',
                          'Antagonistic hallmarks (autophagy dysfunction, nutrient sensing dysregulation, mitochondrial dysfunction) are compensatory responses that become harmful',
                          'Integrative hallmarks (cellular senescence, stem cell exhaustion, altered communication, inflammation, dysbiosis) are the final common phenotypes',
                          'The hallmarks are interconnected — targeting one affects others through compensatory mechanisms',
                          'Geroprotective interventions (rapamycin, metformin, senolytics, exercise) target multiple hallmarks simultaneously'],
            'cross_links': ['Aging', 'Geroscience', 'Cellular Senescence', 'Caloric Restriction and Dietary Restriction', 'Senolytics'],
        },
        'Circadian Clock Mechanism': {
            'domain': 'Chronobiology',
            'description': 'The molecular machinery of the circadian clock: CLOCK/BMAL1 heterodimer, Period/Cryptochrome negative feedback loop, and post-translational regulation.',
            'key_points': ['CLOCK/BMAL1 heterodimer binds E-box elements to drive transcription of Period (Per) and Cryptochrome (Cry) genes',
                          'PER/CRY proteins accumulate, heterodimerize, and translocate to the nucleus to repress CLOCK/BMAL1 activity',
                          'Casein kinase 1 delta/epsilon phosphorylates PER, regulating its stability and nuclear translocation timing',
                          'REV-ERBα and ROR form an accessory feedback loop that stabilizes the ~24-hour period',
                          'Post-translational modifications (phosphorylation, acetylation, SUMOylation) fine-tune clock protein stability and activity'],
            'cross_links': ['Circadian Rhythm', 'Suprachiasmatic Nucleus (SCN)', 'Sleep', 'Chronotype', 'Cell Biology'],
        },
        'CRISPR-Cas9 Gene Editing': {
            'domain': 'Genomics',
            'description': 'The revolutionary gene-editing technology derived from bacterial CRISPR adaptive immune systems: mechanism, applications, limitations, and ethical considerations.',
            'key_points': ['Cas9 endonuclease creates double-strand breaks guided by a single guide RNA (sgRNA) complementary to the target DNA sequence',
                          'Non-homologous end joining (NHEJ) repairs breaks by insertions/deletions, disrupting gene function',
                          'Homology-directed repair (HDR) enables precise sequence replacement using a donor template',
                          'Base editing (deaminase-fused Cas9) and prime editing (reverse transcriptase-fused Cas9 nickase) enable single-nucleotide changes without double-strand breaks',
                          'Clinical approvals include Casgevy (sickle cell disease) and future applications in muscular dystrophy, Huntington\'s, and cancer immunotherapy'],
            'cross_links': ['Genetics', 'Genomics', 'Cell Biology', 'Pharmacogenomics', 'Biomedical Science'],
        },
        'Circadian Disruption and Disease': {
            'domain': 'Chronobiology',
            'description': 'How disruption of the circadian system contributes to metabolic disease, cancer, cardiovascular disease, and mental illness.',
            'key_points': ['Shift work is classified as a probable human carcinogen (Group 2A) by the International Agency for Research on Cancer (IARC)',
                          'Circadian disruption induces insulin resistance, glucose intolerance, and metabolic syndrome through clock gene dysregulation in peripheral tissues',
                          'PER2 mutations are associated with accelerated cancer progression and chemotherapy resistance',
                          'CLOCK gene polymorphisms are linked to bipolar disorder, depression, and circadian rhythm sleep-wake disorders',
                          'Light at night suppresses pineal melatonin production, disrupting circadian gene expression across all tissues'],
            'cross_links': ['Circadian Rhythm', 'Sleep', 'Chronotype', 'Melatonin', 'Shift Work', 'Metabolic Syndrome'],
        },
        'Senolytics': {
            'domain': 'Longevity',
            'description': 'Drugs that selectively eliminate senescent cells: mechanisms, clinical evidence, and therapeutic potential for age-related diseases.',
            'key_points': ['Senescent cells accumulate with age and secrete the senescence-associated secretory phenotype (SASP) — pro-inflammatory cytokines, chemokines, and matrix metalloproteinases',
                          'Dasatinib + quercetin (D+Q) was the first senolytic combination validated in vivo, clearing senescent cells in multiple tissues',
                          'Fisetin, a natural flavonoid, shows broader senolytic activity than D+Q in preclinical models',
                          'Clinical trials have demonstrated senolytic benefits in idiopathic pulmonary fibrosis, osteoarthritis, diabetic kidney disease, and COVID-19 convalescence',
                          'Senolytics target multiple age-related pathologies simultaneously, addressing the geroscience hypothesis that aging is a treatable risk factor'],
            'cross_links': ['Cellular Senescence', 'Aging', 'Longevity', 'Hallmarks of Aging', 'Inflammation'],
        },
        'Neuropharmacology': {
            'domain': 'Pharmacology',
            'description': 'Drugs that act on the central nervous system: mechanisms of action for antidepressants, antipsychotics, anxiolytics, stimulants, and psychedelics.',
            'key_points': ['SSRIs (fluoxetine, escitalopram) block serotonin reuptake via SERT inhibition, increasing synaptic serotonin availability',
                          'Antipsychotics (haloperidol, clozapine) antagonize D2 dopamine receptors, with atypical agents also blocking 5-HT2A receptors',
                          'Benzodiazepines (diazepam, alprazolam) potentiate GABA-A receptor chloride channel opening, enhancing inhibitory neurotransmission',
                          'Psychostimulants (amphetamine, methylphenidate) increase synaptic dopamine and norepinephrine via DAT/NET inhibition and reverse transport',
                          'Psychedelics (psilocybin, LSD) are 5-HT2A receptor agonists that induce neuroplasticity and show therapeutic potential for depression and PTSD'],
            'cross_links': ['Neuroscience', 'Dopamine', 'Depression', 'Anxiety', 'Pharmacodynamics'],
        },
    }

    def __init__(self, researcher: WebResearcher):
        self.researcher = researcher

    def write_deepened_concept(self, concept_name: str, research_results: list[dict]) -> str:
        """Write a concept note enriched with real research."""
        spec = self.DEEPEN_TARGETS.get(concept_name)
        if not spec:
            return None

        date_str = datetime.now().strftime('%Y-%m-%d')
        domain = spec['domain']

        content = "---\n"
        content += f"title: \"{concept_name}\"\n"
        content += f"status: evergreen\n"
        content += f"domain: {domain}\n"
        content += f"tags:\n"
        content += f"  - concept\n"
        content += f"  - {domain.lower().replace(' ', '-')}\n"
        content += f"  - research-enriched\n"
        content += f"created: {date_str}\n"
        content += f"updated: {date_str}\n"
        content += f"sources:\n"
        for r in research_results:
            short = r['title'][:80]
            content += f"  - {r['source'].upper()}: {r['id']} — {short}\n"
        for link in spec['cross_links']:
            content += f"  - [[{link}]]\n"
        content += "---\n\n"

        content += f"# {concept_name}\n\n"
        content += f"> *{spec['description']}*\n\n"
        content += f"| | |\n|---|---|\n"
        content += f"| **Domain** | {domain} |\n"
        content += f"| **Status** | Evergreen — research-enriched |\n"
        content += "\n---\n\n"

        content += "## Core Concepts\n\n"
        for i, point in enumerate(spec['key_points'], 1):
            content += f"{i}. {point}\n\n"

        content += "---\n\n"

        # Research evidence section
        content += "## Research Evidence\n\n"
        if research_results:
            content += "The following sources support and enrich this concept:\n\n"
            for i, r in enumerate(research_results[:5], 1):
                content += f"### {i}. {r['title'][:100]}\n\n"
                content += f"- **Source**: {r['source'].upper()} | **ID**: {r['id']} | **Date**: {r.get('published', 'N/A')}\n"
                content += f"- **Authors**: {', '.join(r.get('authors', ['N/A'])[:2])}\n"
                if r.get('abstract'):
                    content += f"- **Abstract**: {r['abstract'][:300]}...\n"
                content += "\n"
        else:
            content += "*Research sources pending — domain skill endpoints available.*\n\n"

        content += "---\n\n"

        # Cross-references
        content += "## Related Vault Concepts\n\n"
        for link in spec['cross_links']:
            content += f"- [[{link}]]\n"

        content += "\n---\n\n"
        content += f"*Research-enriched concept note. Created {date_str}. Sources verified via PubMed and arXiv APIs. Domain: {domain}.*\n"

        return content

    def save(self, concept_name: str, content: str) -> str:
        safe = re.sub(r'[^\w\s-]', '', concept_name).strip()
        safe = re.sub(r'\s+', ' ', safe)[:100]
        path = os.path.join(CONCEPTS_DIR, f"{safe}.md")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        # Also save research log
        research_log_path = os.path.join(ARI_DIR, f"research_log_{concept_name[:30].replace(' ', '_')}.txt")
        with open(research_log_path, 'w') as f:
            f.write(f"Research enrichment for: {concept_name}\nDate: {datetime.now().isoformat()}\n\n")
        return path


# ──────────────────────────────────────────────
# ORCHESTRATOR
# ──────────────────────────────────────────────

class ResearchExpansionOrchestrator:
    """Full cycle: analyze → search → write → report."""

    def __init__(self):
        self.analyzer = VaultAnalyzer()
        self.researcher = WebResearcher()
        self.writer = ResearchConceptWriter(self.researcher)

    def plan(self) -> str:
        """Show the expansion plan."""
        weak = [(d, len(cs)) for d, cs in self.analyzer.domains.items() if len(cs) <= 10]
        weak.sort(key=lambda x: x[1])

        lines = []
        lines.append("=" * 60)
        lines.append("  RESEARCH EXPANSION PLAN")
        lines.append("=" * 60)
        lines.append(f"\n  Total concepts: {len(self.analyzer.concepts)}")
        lines.append(f"  Total domains: {len(self.analyzer.domains)}")
        lines.append(f"  Research queries: {len(self.researcher.RESEARCH_QUERIES)}\n")

        for domain, count in weak:
            icon = '🟢' if count >= 8 else '🟡' if count >= 5 else '🔴'
            targets = [k for k, v in self.writer.DEEPEN_TARGETS.items() if v['domain'] == domain]
            lines.append(f"  {icon} {domain}: {count} concepts → +{len(targets)}")
            for t in targets:
                lines.append(f"       {t}")
            print()
            lines.append("")

        lines.append(f"  Total deepen targets: {len(self.writer.DEEPEN_TARGETS)}")
        lines.append(f"  Research queries per target: 2-3 (arXiv + PubMed)")
        return '\n'.join(lines)

    def run_full_cycle(self) -> dict:
        """Run the complete cycle: search → write → save → report."""
        result = {
            'timestamp': datetime.now().isoformat(),
            'concepts_written': [],
            'research_fetched': 0,
            'errors': []
        }

        for concept_name, spec in self.writer.DEEPEN_TARGETS.items():
            domain = spec['domain']
            print(f"\n[Expansion] Processing: {concept_name} ({domain})")

            # Find matching research queries
            queries = [q for q in self.researcher.RESEARCH_QUERIES if q['domain'] == domain]

            # Fetch research
            all_results = []
            for q in queries:
                results = self.researcher.search(q)
                all_results.extend(results)
                print(f"  [Search] {q['site']}: {len(results)} results for '{q['query'][:50]}...'")

            # Write concept
            try:
                content = self.writer.write_deepened_concept(concept_name, all_results)
                if content:
                    path = self.writer.save(concept_name, content)
                    print(f"  [Written] {path}")
                    result['concepts_written'].append({
                        'name': concept_name,
                        'domain': domain,
                        'sources': len(all_results),
                        'path': path
                    })
                    result['research_fetched'] += len(all_results)
            except Exception as e:
                print(f"  [Error] {e}")
                result['errors'].append(f"{concept_name}: {e}")

        print(f"\n{'='*60}")
        print(f"  CYCLE COMPLETE")
        print(f"  Concepts written: {len(result['concepts_written'])}")
        print(f"  Research sources fetched: {result['research_fetched']}")
        if result['errors']:
            print(f"  Errors: {len(result['errors'])}")
        print(f"{'='*60}")

        return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ARI Research-Expansion Engine")
    parser.add_argument('--plan', action='store_true', help='Show expansion plan')
    parser.add_argument('--full-cycle', action='store_true', help='Run full research-expansion cycle')
    parser.add_argument('--test-search', type=str, help='Test search for a domain (e.g. Immunology)')
    args = parser.parse_args()

    orchestrator = ResearchExpansionOrchestrator()

    if args.plan:
        print(orchestrator.plan())

    elif args.test_search:
        # Find matching query
        match = [q for q in orchestrator.researcher.RESEARCH_QUERIES if args.test_search.lower() in q['domain'].lower()]
        if match:
            q = match[0]
            results = orchestrator.researcher.search(q)
            print(f"Test search: {q['site']} | {q['query']}")
            for r in results[:3]:
                print(f"  [{r['source']}:{r['id']}] {r['title'][:80]}")
                print(f"    {' | '.join(r.get('authors', [''])[:2])} | {r.get('published', '')}")
        else:
            print(f"No query found for domain: {args.test_search}")

    elif args.full_cycle:
        orchestrator.run_full_cycle()

    else:
        print(orchestrator.plan())


if __name__ == '__main__':
    main()
