#!/usr/bin/env python3
"""
Vault Expansion Engine — Batch concept expansion for weak domains.

Scans the vault, identifies the thinnest domains, and generates
expansion plans for each: which concepts are missing, what their
structure should be, and what they should connect to.

Usage:
    python3 expand_vault.py --plan           # Show expansion plan for all weak domains
    python3 expand_vault.py --write N        # Write the planned concepts for domain N
    python3 expand_vault.py --all            # Write ALL planned concepts across all domains
    python3 expand_vault.py --dry-run        # Show what would be written
"""

import os, re, glob, json, sys
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
PUB_DIR = os.path.join(VAULT_ROOT, "04 Resources/Publications")
ARI_DIR = os.path.join(VAULT_ROOT, "04 Resources/ARI")
EXPANSION_DIR = os.path.join(VAULT_ROOT, "04 Resources/Expansions")
os.makedirs(EXPANSION_DIR, exist_ok=True)


@dataclass
class ConceptTarget:
    """A concept that should exist but doesn't."""
    domain: str
    title: str
    aliases: list[str]
    sources: list[str]
    description: str
    key_points: list[str]
    cross_links: list[str]
    priority: int = 3  # 1-5, 1 = highest


class VaultAnalyzer:
    """Analyze the vault to find expansion opportunities."""

    def __init__(self):
        self.concepts: dict[str, dict] = {}  # title -> metadata
        self.domains: dict[str, list[str]] = defaultdict(list)
        self._load()

    def _load(self):
        for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
            fn = os.path.basename(f).replace('.md', '')
            with open(f, encoding='utf-8', errors='replace') as fh:
                raw = fh.read()

            # Title from H1
            title = fn
            hm = re.search(r'^# (.+)$', raw, re.MULTILINE)
            if hm:
                title = hm.group(1).strip()
            yt = re.search(r'title:\s*["\']?(.+?)["\']?\s*$', raw, re.MULTILINE)
            if yt:
                title = yt.group(1).strip().strip('"').strip("'")

            # Domain
            domain = 'General'
            dm = re.search(r'^domain:\s*(.+)$', raw, re.MULTILINE)
            if dm:
                domain = dm.group(1).strip()

            # Lines
            lines = len(raw.split('\n'))

            # Aliases
            aliases = []
            in_alias = False
            for line in raw.split('\n'):
                if line.startswith('aliases:'):
                    in_alias = True
                    continue
                if in_alias:
                    m = re.match(r'\s*-\s*(.+)$', line)
                    if m:
                        aliases.append(m.group(1).strip().strip('"\''))
                    else:
                        in_alias = False

            # Tags
            tags = []
            tg = re.search(r'^tags:\s*(.+)$', raw, re.MULTILINE)
            if tg:
                tags_raw = tg.group(1)
                if tags_raw.startswith('['):
                    tags = [t.strip().strip('"\'').strip('#') for t in tags_raw.strip('[]').split(',') if t.strip()]
                elif tags_raw.startswith('#'):
                    tags = [t.strip('# ') for t in tags_raw.split()]

            self.concepts[title] = {
                'title': title, 'domain': domain, 'lines': lines,
                'aliases': aliases, 'tags': tags, 'file': fn
            }
            self.domains[domain].append(title)

    def get_weak_domains(self, threshold: int = 10) -> list[tuple[str, int]]:
        """Return domains below threshold, sorted by thinness."""
        weak = [(d, len(cs)) for d, cs in self.domains.items() if len(cs) <= threshold]
        weak.sort(key=lambda x: x[1])
        return weak

    def get_concepts_in_domain(self, domain: str) -> list[dict]:
        """Get all concept metadata for a domain."""
        return [self.concepts[t] for t in self.domains.get(domain, []) if t in self.concepts]


class ExpansionPlanner:
    """Generate expansion plans for weak domains."""

    # Domain expansion blueprints: what concepts should exist in each thin domain
    DOMAIN_EXPANSIONS = {
        'Immunology': {
            'target_count': 12,
            'concepts': [
                ConceptTarget(
                    domain='Immunology',
                    title='Innate Immune System',
                    aliases=['Innate Immunity', 'Natural Immunity', 'First-Line Defense'],
                    sources=['Immunology', 'Inflammation', 'Microglia'],
                    description='The evolutionarily ancient arm of the immune system: physical barriers, phagocytes, NK cells, complement system, and the immediate response to pathogens.',
                    key_points=['Physical barriers (skin, mucosa, tight junctions)', 'Phagocytic cells (macrophages, neutrophils, dendritic cells)', 'Natural killer cells and their role in tumor surveillance', 'Complement cascade and opsonization', 'PRRs and PAMPs — pattern recognition'],
                    cross_links=['Inflammation', 'Microglia', 'Cytokines', 'Cell Biology'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Immunology',
                    title='Adaptive Immune System',
                    aliases=['Adaptive Immunity', 'Acquired Immunity', 'Specific Immunity'],
                    sources=['Immunology', 'Innate Immune System'],
                    description='The antigen-specific arm: B cells, T cells, antibody production, immunological memory, and MHC presentation.',
                    key_points=['B cells and antibody diversity through V(D)J recombination', 'T cell subtypes and their functions', 'MHC class I and II presentation', 'Clonal selection and immunological memory', 'Vaccination as artificial adaptive immunity'],
                    cross_links=['Immunology', 'Innate Immune System', 'Vaccination', 'Autoimmune Disease'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Immunology',
                    title='Cytokine Signaling',
                    aliases=['Cytokines', 'Interleukins', 'Chemokines', 'Cytokine Storm'],
                    sources=['Immunology', 'Inflammation', 'Microglia'],
                    description='The molecular messengers of the immune system: interleukins, interferons, chemokines, and TNF superfamily.',
                    key_points=['Interleukin families and their primary functions', 'Type I and type II interferons in antiviral defense', 'Chemokine gradients and cell trafficking', 'Cytokine storms and pathological inflammation', 'Therapeutic cytokine modulation (anti-TNF, JAK inhibitors)'],
                    cross_links=['Inflammation', 'Immunology', 'Microglia', 'Autoimmune Disease'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Immunology',
                    title='Autoimmune Disease',
                    aliases=['Autoimmunity', 'Self-Reactivity', 'Autoimmune Disorders'],
                    sources=['Immunology', 'Adaptive Immune System', 'Cytokine Signaling'],
                    description='Breakdown of self-tolerance leading to immune attack on self-tissue: mechanisms, common conditions, and therapeutic approaches.',
                    key_points=['Central vs peripheral tolerance mechanisms', 'Molecular mimicry and epitope spreading', 'Type 1 diabetes, MS, RA, lupus as model diseases', 'Role of regulatory T cells (Tregs)', 'Immunosuppressive therapies and their risks'],
                    cross_links=['Immunology', 'Adaptive Immune System', 'Inflammation', 'Cytokine Signaling'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Immunology',
                    title='Neuroimmunology',
                    aliases=['Brain-Immune Interactions', 'Neuroinflammation'],
                    sources=['Immunology', 'Neuroscience', 'Microglia', 'Inflammation'],
                    description='The bidirectional communication between the nervous and immune systems: microglia, cytokine signaling across the BBB, and neuroinflammation in disease.',
                    key_points=['Microglia as brain-resident immune cells', 'Cytokine penetration across the blood-brain barrier', 'Vagus nerve inflammatory reflex', 'Neuroinflammation in Alzheimer\'s, Parkinson\'s, depression', 'The glymphatic system as immune clearance'],
                    cross_links=['Microglia', 'Inflammation', 'Glymphatic System', 'Alzheimer\'s Disease', 'Depression'],
                    priority=1,
                ),
            ]
        },
        'Pharmacology': {
            'target_count': 10,
            'concepts': [
                ConceptTarget(
                    domain='Pharmacology',
                    title='Pharmacokinetics',
                    aliases=['ADME', 'Drug Kinetics'],
                    sources=[],
                    description='What the body does to a drug: absorption, distribution, metabolism, and excretion (ADME).',
                    key_points=['Absorption routes and bioavailability', 'Volume of distribution and protein binding', 'Phase I and II metabolism (CYP450 system)', 'Renal and hepatic clearance', 'Half-life and steady-state concentration'],
                    cross_links=['Pharmacology', 'Physiology', 'Cell Biology'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Pharmacology',
                    title='Pharmacodynamics',
                    aliases=['Drug Action', 'Receptor Pharmacology'],
                    sources=[],
                    description='What a drug does to the body: receptor binding, dose-response relationships, efficacy, and potency.',
                    key_points=['Receptor types and signaling pathways', 'Agonists, antagonists, partial agonists, inverse agonists', 'Dose-response curves and ED50', 'Therapeutic index and safety margin', 'Tolerance, sensitization, and dependence'],
                    cross_links=['Pharmacology', 'Pharmacokinetics', 'Neurotransmitters', 'Dopamine'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Pharmacology',
                    title='Drug Development Pipeline',
                    aliases=['Drug Discovery', 'Clinical Trials', 'FDA Approval'],
                    sources=[],
                    description='The process from target discovery to market: preclinical research, clinical trial phases, regulatory approval, and post-market surveillance.',
                    key_points=['Target identification and validation', 'Lead compound optimization', 'Phase I-III clinical trial design', 'Regulatory submission and approval', 'Phase IV post-market surveillance'],
                    cross_links=['Pharmacology', 'Research Methods', 'Statistics'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Pharmacology',
                    title='Neuropharmacology',
                    aliases=['Psychopharmacology', 'CNS Drugs'],
                    sources=['Neuroscience', 'Dopamine', 'Neurotransmitters'],
                    description='Drugs that act on the central nervous system: mechanisms of action for antidepressants, antipsychotics, anxiolytics, stimulants, and psychedelics.',
                    key_points=['SSRIs and monoamine hypothesis of depression', 'Antipsychotic D2 blockade and dopamine hypothesis', 'Benzodiazepines and GABA-A modulation', 'Psychostimulants: dopamine and norepinephrine reuptake', 'Psychedelics: 5-HT2A agonism and therapeutic potential'],
                    cross_links=['Neuroscience', 'Dopamine', 'Depression', 'Anxiety'],
                    priority=1,
                ),
            ]
        },
        'Longevity': {
            'target_count': 10,
            'concepts': [
                ConceptTarget(
                    domain='Longevity',
                    title='Hallmarks of Aging',
                    aliases=['Aging Hallmarks', 'López-Otín Hallmarks'],
                    sources=['Aging', 'Longevity', 'Geroscience'],
                    description='The 12 hallmarks of aging as defined by López-Otín et al.: genomic instability, telomere attrition, epigenetic alterations, loss of proteostasis, disabled macroautophagy, deregulated nutrient sensing, mitochondrial dysfunction, cellular senescence, stem cell exhaustion, altered intercellular communication, chronic inflammation, and dysbiosis.',
                    key_points=['Primary hallmarks (damage: genomic, telomeric, epigenetic, proteostatic)', 'Antagonistic hallmarks (response: autophagy, nutrient sensing, mitochondrial)', 'Integrative hallmarks (phenotype: senescence, stem cells, communication)', 'The hallmarks are interconnected — targeting one affects others', 'Interventions that target multiple hallmarks simultaneously'],
                    cross_links=['Aging', 'Geroscience', 'Cellular Senescence', 'Mitochondria', 'Oxidative Stress'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Longevity',
                    title='Caloric Restriction and Dietary Restriction',
                    aliases=['CR', 'Fasting', 'Time-Restricted Feeding', 'Dietary Restriction'],
                    sources=['Longevity', 'Metabolism', 'Aging'],
                    description='The most robust lifespan-extending intervention across species: mechanisms of dietary restriction including mTOR inhibition, AMPK activation, and sirtuin upregulation.',
                    key_points=['CR extends lifespan in yeast, worms, flies, mice, and primates', 'mTOR inhibition as the primary mechanism', 'AMPK activation and NAD+/sirtuin pathway', 'Time-restricted feeding without caloric reduction', 'Human evidence: cardiovascular, cognitive, and metabolic benefits'],
                    cross_links=['Longevity', 'Metabolism', 'Aging', 'Hallmarks of Aging'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Longevity',
                    title='Senolytics',
                    aliases=['Senolytic Drugs', 'Senescence Clearance'],
                    sources=['Aging', 'Cellular Senescence', 'Longevity'],
                    description='Drugs that selectively eliminate senescent cells: mechanisms, clinical evidence, and therapeutic potential for age-related diseases.',
                    key_points=['Senescent cells accumulate with age and secrete SASP factors', 'Dasatinib + quercetin (D+Q) as first senolytic combination', 'Fisetin as a natural senolytic with broader activity', 'Clinical trials in osteoarthritis, kidney disease, and COVID', 'Senolytics as a therapeutic strategy for multimorbidity'],
                    cross_links=['Cellular Senescence', 'Aging', 'Longevity', 'Inflammation'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Longevity',
                    title='Epigenetic Clocks and Biological Age',
                    aliases=['DNA Methylation Age', 'Horvath Clock', 'GrimAge'],
                    sources=['Aging', 'Epigenetics', 'Longevity'],
                    description='DNA methylation-based biomarkers that estimate biological age more accurately than chronological age: the Horvath clock, Hannum clock, GrimAge, and their applications.',
                    key_points=['Horvath clock: 353 CpG sites across multiple tissues', 'GrimAge incorporates smoking history + 7 DNAm surrogates', 'Epigenetic age acceleration predicts mortality and disease risk', 'Interventions that reverse epigenetic age (caloric restriction, exercise)', 'Limitations: population-specific, tissue-specific, and technical noise'],
                    cross_links=['Aging', 'Longevity', 'Epigenetics', 'Hallmarks of Aging'],
                    priority=2,
                ),
            ]
        },
        'Chronobiology': {
            'target_count': 8,
            'concepts': [
                ConceptTarget(
                    domain='Chronobiology',
                    title='Circadian Clock Mechanism',
                    aliases=['Molecular Clock', 'TTFL', 'Transcription-Translation Feedback Loop'],
                    sources=['Circadian Rhythm', 'Sleep'],
                    description='The molecular machinery of the circadian clock: CLOCK/BMAL1 heterodimer, Period/Cryptochrome negative feedback loop, and post-translational regulation.',
                    key_points=['CLOCK/BMAL1 as positive limb driving Per and Cry transcription', 'PER/CRY heterodimer as negative limb repressing CLOCK/BMAL1', 'Casein kinase phosphorylation regulates PER stability and timing', 'REV-ERBα and ROR as accessory loops stabilizing the clock', 'The 24-hour period emerges from delay in the feedback loop'],
                    cross_links=['Circadian Rhythm', 'Sleep', 'Genetics', 'Cell Biology'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Chronobiology',
                    title='Suprachiasmatic Nucleus (SCN)',
                    aliases=['SCN', 'Master Clock', 'Central Pacemaker', 'Hypothalamic Clock'],
                    sources=['Circadian Rhythm', 'Hypothalamus', 'Neuroscience'],
                    description='The master pacemaker in the anterior hypothalamus: 20,000 neurons that coordinate all peripheral clocks through neural and hormonal signals.',
                    key_points=['SCN receives direct retinal input via the retinohypothalamic tract', 'Gap junction coupling synchronizes SCN neurons', 'SCN projects to pineal gland regulating melatonin', 'Peripheral clocks are subordinate but can be desynchronized', 'SCN lesions abolish circadian rhythms in behavior and physiology'],
                    cross_links=['Circadian Rhythm', 'Hypothalamus', 'Melatonin', 'Sleep', 'Neuroscience'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Chronobiology',
                    title='Chronotype',
                    aliases=['Morningness-Eveningness', 'Circadian Preference', 'Lark vs Owl'],
                    sources=['Circadian Rhythm', 'Sleep', 'Genetics'],
                    description='Individual differences in circadian timing: genetic basis, age-related changes, social jetlag, and health consequences of circadian misalignment.',
                    key_points=['PER3 polymorphism associated with morningness-eveningness', 'Adolescents shift toward evening type due to pubertal changes', 'Social jetlag: discrepancy between biological and social time', 'Evening types have higher risk of metabolic and mental health disorders', 'Chronotype-based chronotherapy for depression and insomnia'],
                    cross_links=['Circadian Rhythm', 'Sleep', 'Social Jetlag', 'Delayed Sleep Phase Disorder', 'Genetics'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Chronobiology',
                    title='Circadian Disruption and Disease',
                    aliases=['Circadian Misalignment', 'Clock Dysfunction'],
                    sources=['Circadian Rhythm', 'Chronotype', 'Sleep'],
                    description='How disruption of the circadian system contributes to metabolic disease, cancer, cardiovascular disease, and mental illness.',
                    key_points=['Shift work classified as probable carcinogen by IARC', 'Circadian disruption and metabolic syndrome (insulin resistance, obesity)', 'PER2 mutations associated with accelerated cancer progression', 'Clock gene polymorphisms in bipolar disorder and depression', 'Light at night suppresses melatonin and disrupts circadian gene expression'],
                    cross_links=['Circadian Rhythm', 'Sleep', 'Shift Work', 'Melatonin', 'Metabolic Syndrome'],
                    priority=2,
                ),
            ]
        },
        'Genomics': {
            'target_count': 15,
            'concepts': [
                ConceptTarget(
                    domain='Genomics',
                    title='CRISPR-Cas9 Gene Editing',
                    aliases=['CRISPR', 'Genome Editing', 'Cas9'],
                    sources=['Genetics', 'Genomics'],
                    description='The revolutionary gene-editing technology derived from bacterial immune systems: mechanism, applications, limitations, and ethical considerations.',
                    key_points=['Cas9 nuclease creates double-strand breaks guided by sgRNA', 'NHEJ repair knocks out genes; HDR enables precise editing', 'Off-target effects and delivery challenges', 'Therapeutic applications: sickle cell, beta-thalassemia, DMD', 'Base editing and prime editing as next-generation tools'],
                    cross_links=['Genetics', 'Genomics', 'Cell Biology', 'Biomedical Science'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Genomics',
                    title='GWAS — Genome-Wide Association Studies',
                    aliases=['GWAS', 'Genome-Wide Association', 'SNP Associations'],
                    sources=['Genetics', 'Statistics', 'Causal Inference'],
                    description='Large-scale studies linking genetic variants to traits and diseases: design, statistical challenges, heritability estimation, and biological interpretation.',
                    key_points=['Millions of SNPs tested across thousands of individuals', 'Multiple testing correction (Bonferroni, FDR)', 'Linkage disequilibrium and fine-mapping', 'Missing heritability problem and proposed solutions', 'Mendelian randomization as causal follow-up to GWAS'],
                    cross_links=['Genetics', 'Statistics', 'Causal Inference', 'Mendelian Randomization'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Genomics',
                    title='Epigenomics',
                    aliases=['Epigenetics', 'Epigenome', 'Chromatin'],
                    sources=['Genetics', 'Genomics', 'Cell Biology'],
                    description='Genome-wide study of epigenetic modifications: DNA methylation, histone modifications, chromatin accessibility, and their role in gene regulation.',
                    key_points=['DNA methylation at CpG islands silences promoters', 'Histone acetylation opens chromatin; methylation can activate or repress', 'ATAC-seq for genome-wide chromatin accessibility', 'Epigenetic changes are reversible and environmentally responsive', 'Epigenetic clocks measure biological age'],
                    cross_links=['Genetics', 'Genomics', 'Cell Biology', 'Epigenetic Clocks'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Genomics',
                    title='Polygenic Risk Scores',
                    aliases=['PRS', 'Polygenic Score', 'Genetic Risk Score'],
                    sources=['Genetics', 'Genomics', 'Statistics'],
                    description='A quantitative measure of genetic predisposition to a trait or disease, aggregating the effects of thousands of common variants.',
                    key_points=['PRS = weighted sum of risk alleles across GWAS-significant SNPs', 'Predictive power increases with GWAS sample size', 'Clinical applications in breast cancer, coronary artery disease, T2D', 'Ethical concerns: discrimination, psychological impact, equity', 'Integration with non-genetic risk factors for precision medicine'],
                    cross_links=['Genetics', 'GWAS', 'Statistics', 'Mendelian Randomization'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Genomics',
                    title='Pharmacogenomics',
                    aliases=['PGx', 'Personalized Medicine', 'Pharmacogenetics'],
                    sources=['Genetics', 'Pharmacology', 'Genomics'],
                    description='How genetic variation affects drug response: CYP450 polymorphisms, HLA associations, and clinical implementation of pharmacogenetic testing.',
                    key_points=['CYP2D6, CYP2C19, CYP2C9 polymorphisms affect drug metabolism', 'HLA-B*5701 screening for abacavir hypersensitivity', 'TPMT and NUDT15 testing for thiopurine toxicity', 'Warfarin dosing algorithms incorporating VKORC1 and CYP2C9', 'Barriers to clinical adoption: evidence, cost, workflow integration'],
                    cross_links=['Genetics', 'Pharmacology', 'Genomics', 'Drug Development Pipeline'],
                    priority=2,
                ),
            ]
        },
        'Cell Biology': {
            'target_count': 20,
            'concepts': [
                ConceptTarget(
                    domain='Cell Biology',
                    title='Cell Signaling Pathways',
                    aliases=['Signal Transduction', 'Cell Communication'],
                    sources=['Cell Biology', 'Molecular Biology'],
                    description='How cells receive and respond to extracellular signals: receptor types, second messengers, signaling cascades, and signal integration.',
                    key_points=['Receptor tyrosine kinases and MAPK cascade', 'GPCR signaling: cAMP, IP3/DAG, and β-arrestin pathways', 'JAK-STAT signaling in cytokine response', 'Wnt, Notch, and Hedgehog in development', 'Signal amplification, desensitization, and crosstalk'],
                    cross_links=['Cell Biology', 'Molecular Biology', 'Endocrine System', 'Neuroscience'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Cell Biology',
                    title='Autophagy',
                    aliases=['Self-Eating', 'Cellular Recycling'],
                    sources=['Cell Biology', 'Molecular Biology', 'Aging'],
                    description='The cellular degradation process that removes damaged organelles and misfolded proteins: mechanism, regulation, and role in health and disease.',
                    key_points=['Macroautophagy: autophagosome formation and lysosomal fusion', 'Chaperone-mediated autophagy targets specific proteins', 'Autophagy declines with age and contributes to neurodegeneration', 'mTOR inhibition activates autophagy', 'Rapamycin and other autophagy-inducing compounds'],
                    cross_links=['Cell Biology', 'Aging', 'Longevity', 'Neurodegeneration', 'mTOR'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Cell Biology',
                    title='Apoptosis and Programmed Cell Death',
                    aliases=['Cell Death', 'Intrinsic Apoptosis', 'Extrinsic Apoptosis'],
                    sources=['Cell Biology', 'Molecular Biology'],
                    description='The regulated process of programmed cell death: intrinsic (mitochondrial) and extrinsic (death receptor) pathways, caspases, and BCL-2 family regulation.',
                    key_points=['Intrinsic pathway: mitochondrial outer membrane permeabilization', 'BCL-2 family: pro-apoptotic vs anti-apoptotic members', 'Extrinsic pathway: Fas/TRAIL death receptors and DISC formation', 'Caspase cascade: initiators (8, 9) and executioners (3, 7)', 'Apoptosis evasion in cancer and therapeutic strategies'],
                    cross_links=['Cell Biology', 'Cancer', 'Mitochondria', 'Cellular Senescence'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Cell Biology',
                    title='Mitochondrial Biology',
                    aliases=['Mitochondria', 'Mitochondrial Function', 'Mitochondrial Dynamics'],
                    sources=['Cell Biology', 'Mitochondria', 'Oxidative Stress'],
                    description='Mitochondrial structure, function, and dynamics: oxidative phosphorylation, mitochondrial DNA, fission/fusion, mitophagy, and role in aging and disease.',
                    key_points=['Electron transport chain and ATP synthesis', 'mtDNA: maternal inheritance, heteroplasmy, threshold effect', 'Mitochondrial fission (Drp1) and fusion (Mfn1/2, OPA1)', 'Mitophagy as quality control', 'Mitochondrial dysfunction in aging, neurodegeneration, and metabolic disease'],
                    cross_links=['Mitochondria', 'Oxidative Stress', 'Cell Biology', 'Aging', 'Metabolism'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Cell Biology',
                    title='Stem Cell Biology',
                    aliases=['Stem Cells', 'Pluripotency', 'Adult Stem Cells'],
                    sources=['Cell Biology', 'Developmental Biology'],
                    description='Self-renewal, differentiation, and potency of stem cells: embryonic, adult, and induced pluripotent stem cells, and their therapeutic applications.',
                    key_points=['Embryonic stem cells: pluripotency and the inner cell mass', 'Adult stem cells: hematopoietic, mesenchymal, neural, intestinal', 'Yamanaka factors (Oct4, Sox2, Klf4, c-Myc) for iPSC generation', 'Organoids as 3D culture models', 'Therapeutic: bone marrow transplant, CAR-T, retinal repair'],
                    cross_links=['Cell Biology', 'Regenerative Medicine', 'Cancer Stem Cells', 'Aging'],
                    priority=2,
                ),
            ]
        },
        'Economics': {
            'target_count': 8,
            'concepts': [
                ConceptTarget(
                    domain='Economics',
                    title='Supply and Demand',
                    aliases=['Market Equilibrium', 'Price Mechanism', 'Law of Supply and Demand'],
                    sources=['Finance', 'Markets & Asset Classes'],
                    description='The fundamental model of price determination in competitive markets: downward-sloping demand, upward-sloping supply, equilibrium, elasticity, and market efficiency.',
                    key_points=['Demand curves slope downward — higher price reduces quantity demanded (substitution + income effects)', 'Supply curves slope upward — higher price increases quantity supplied (marginal cost increases with output)', 'Equilibrium clears the market at the price where quantity demanded equals quantity supplied', 'Elasticity measures responsiveness: price elasticity of demand determines tax incidence and revenue effects', 'Market efficiency requires perfect information, no externalities, and competitive structure — violations create market failures'],
                    cross_links=['Finance', 'Markets & Asset Classes', 'Behavioral Finance & Market Psychology', 'Game Theory'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Economics',
                    title='Business Cycles',
                    aliases=['Economic Cycles', 'Boom-Bust', 'Recession and Expansion'],
                    sources=['Finance', 'Macro Trading'],
                    description='The recurring pattern of expansion, peak, contraction, and trough in aggregate economic activity: causes, measurement, and policy responses.',
                    key_points=['Business cycles consist of expansion (rising GDP, employment), peak, contraction (recession), and trough', 'NBER defines recessions as significant decline in economic activity spread across the economy lasting >3 months', 'Leading indicators (yield curve, building permits, consumer confidence) predict turning points', 'Monetary policy (interest rates, QE) and fiscal policy (government spending, taxes) are the primary stabilization tools', 'Financial crises often precede severe recessions — credit crunches amplify downturns through the financial accelerator'],
                    cross_links=['Finance', 'Macro Trading', 'Federal Reserve', 'Interest Rates'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Economics',
                    title='Game Theory',
                    aliases=['Strategic Interaction', 'Nash Equilibrium', 'Prisoner\'s Dilemma'],
                    sources=['Game Theory'],
                    description='The mathematical framework for analyzing strategic interactions where the payoff to each participant depends on the choices of all participants.',
                    key_points=['Nash equilibrium: no player can improve their payoff by unilaterally changing strategy', 'Prisoner\'s dilemma shows how rational individuals may fail to cooperate even when cooperation benefits all', 'Repeated games enable cooperation through trigger strategies (tit-for-tat) and reputation effects', 'Auctions, bargaining, and market design are direct applications of game theory to economic institutions', 'Behavioral game theory incorporates psychological realism (fairness, reciprocity, bounded rationality)'],
                    cross_links=['Finance', 'Behavioral Finance & Market Psychology', 'AI Agents', 'Multi-Agent Systems'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Economics',
                    title='Market Structure and Competition',
                    aliases=['Market Power', 'Monopoly', 'Oligopoly', 'Perfect Competition'],
                    sources=['Finance', 'Markets & Asset Classes'],
                    description='The taxonomy of market structures based on number of firms, product differentiation, and barriers to entry: from perfect competition to monopoly.',
                    key_points=['Perfect competition: many firms, identical products, price takers, zero economic profit in long run', 'Monopoly: single firm, barriers to entry, price maker, deadweight loss from reduced output', 'Oligopoly: few firms, strategic interdependence, collusion vs competition (Cournot, Bertrand, Stackelberg)', 'Monopolistic competition: many firms, differentiated products, brand loyalty creates limited pricing power', 'Antitrust policy regulates mergers, price fixing, and abuse of dominant position'],
                    cross_links=['Finance', 'Markets & Asset Classes', 'Game Theory'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Economics',
                    title='Monetary Policy and Central Banking',
                    aliases=['Central Banks', 'Interest Rate Policy', 'Quantitative Easing'],
                    sources=['Finance', 'Macro Trading'],
                    description='The management of money supply and interest rates by central banks to achieve price stability, maximum employment, and financial stability.',
                    key_points=['Central banks use policy interest rates (fed funds rate, ECB refi rate) as primary tool', 'Quantitative easing (QE) expands central bank balance sheet when policy rates hit zero lower bound', 'Inflation targeting (typically 2%) is the dominant monetary policy framework globally', 'Forward guidance shapes market expectations about future policy rates', 'Central bank independence from political pressure is crucial for credible inflation control'],
                    cross_links=['Finance', 'Macro Trading', 'Business Cycles', 'Inflation'],
                    priority=1,
                ),
            ]
        },
        'Biology': {
            'target_count': 8,
            'concepts': [
                ConceptTarget(
                    domain='Biology',
                    title='Cell Theory and Cellular Organization',
                    aliases=['Cell Doctrine', 'Cell Structure', 'Prokaryotes and Eukaryotes'],
                    sources=['Cell Biology', 'Neuroscience'],
                    description='The foundational principle that all living organisms are composed of cells: cell structure, organelles, and the distinction between prokaryotic and eukaryotic organization.',
                    key_points=['All living organisms are composed of one or more cells — the cell is the basic unit of life', 'All cells arise from pre-existing cells through division (omnis cellula e cellula)', 'Eukaryotic cells contain membrane-bound organelles (nucleus, mitochondria, ER, Golgi) enabling compartmentalization', 'Prokaryotic cells (bacteria, archaea) lack a nucleus and organelles, with DNA in a nucleoid region', 'Cell size is limited by surface area-to-volume ratio — diffusion becomes inefficient beyond ~100 µm'],
                    cross_links=['Cell Biology', 'Neuroscience', 'Molecular Biology', 'Genetics'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Biology',
                    title='Evolution by Natural Selection',
                    aliases=['Darwinian Evolution', 'Adaptation', 'Fitness'],
                    sources=['Neuroscience', 'Genetics', 'Genomics'],
                    description='The central organizing principle of biology: heritable variation, differential reproductive success, and adaptation across generations.',
                    key_points=['Natural selection requires heritable variation and differential reproductive success — three conditions for evolution', 'Fitness is relative reproductive success, not absolute survival — an organism that lives long but reproduces little has low fitness', 'Adaptation is the process by which populations become better suited to their environment over generations', 'Speciation occurs when populations become reproductively isolated and diverge genetically', 'Evolution operates at multiple levels: gene, individual, kin, and group selection'],
                    cross_links=['Neuroscience', 'Genetics', 'Genomics', 'Aging'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Biology',
                    title='Molecular Biology: Central Dogma',
                    aliases=['DNA to RNA to Protein', 'Gene Expression', 'Transcription and Translation'],
                    sources=['Genetics', 'Cell Biology'],
                    description='The flow of genetic information in biological systems: DNA replication, transcription to RNA, translation to protein, and regulation at each step.',
                    key_points=['DNA stores genetic information as a double helix with complementary base pairing (A-T, G-C)', 'Transcription: RNA polymerase synthesizes messenger RNA (mRNA) from a DNA template', 'Translation: ribosomes read mRNA codons and assemble amino acids into polypeptide chains', 'Gene expression is regulated at multiple levels: chromatin accessibility, transcription factors, RNA processing, translation, and post-translational modification', 'Epigenetic modifications (DNA methylation, histone acetylation) regulate gene expression without changing DNA sequence'],
                    cross_links=['Genetics', 'Genomics', 'Cell Biology', 'Epigenetics'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Biology',
                    title='Metabolism and Bioenergetics',
                    aliases=['Cellular Respiration', 'Photosynthesis', 'Energy Metabolism'],
                    sources=['Cell Biology', 'Physiology', 'Mitochondria'],
                    description='The chemical processes by which organisms extract, store, and use energy: glycolysis, the citric acid cycle, oxidative phosphorylation, and photosynthesis.',
                    key_points=['Glycolysis breaks down glucose to pyruvate in the cytoplasm, producing 2 ATP and 2 NADH per glucose', 'The citric acid cycle (Krebs cycle) in the mitochondrial matrix oxidizes acetyl-CoA to CO2, producing NADH and FADH2', 'Oxidative phosphorylation uses the electron transport chain to create a proton gradient that drives ATP synthesis (chemiosmosis)', 'Photosynthesis in chloroplasts uses light energy to fix CO2 into carbohydrates, releasing oxygen as a byproduct', 'Metabolic rate scales with body size (Kleiber\'s law: metabolic rate ∝ mass^0.75) and is regulated by thyroid hormone'],
                    cross_links=['Cell Biology', 'Mitochondria', 'Physiology', 'Exercise Physiology'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Biology',
                    title='Developmental Biology',
                    aliases=['Embryology', 'Morphogenesis', 'Pattern Formation'],
                    sources=['Cell Biology', 'Genetics', 'Neuroscience'],
                    description='The processes by which a single fertilized egg develops into a complex multicellular organism: cell division, differentiation, morphogenesis, and pattern formation.',
                    key_points=['Fertilization initiates embryonic development, followed by cleavage (rapid cell division without growth)', 'Gastrulation establishes the three germ layers: ectoderm (nervous system, skin), mesoderm (muscle, bone, blood), endoderm (gut, lungs)', 'Pattern formation is controlled by morphogen gradients — concentration-dependent signals that specify cell fate', 'Hox genes determine body segment identity along the anterior-posterior axis, conserved across all bilaterians', 'Stem cells maintain the capacity for both self-renewal and differentiation throughout life'],
                    cross_links=['Cell Biology', 'Genetics', 'Neuroscience', 'Stem Cell Biology'],
                    priority=2,
                ),
            ]
        },
        'Computer Science': {
            'target_count': 8,
            'concepts': [
                ConceptTarget(
                    domain='Computer Science',
                    title='Data Structures and Algorithms',
                    aliases=['Algorithms', 'Data Organization', 'Computational Complexity'],
                    sources=['Software Engineering', 'Machine Learning'],
                    description='The fundamental building blocks of computation: organizing data (arrays, trees, hash tables, graphs) and algorithms for processing it (sorting, searching, graph traversal, dynamic programming).',
                    key_points=['Arrays and linked lists: contiguous vs distributed memory, O(1) random access vs O(n) traversal', 'Hash tables provide O(1) average-case lookup using a hash function to map keys to buckets', 'Trees (binary search, balanced AVL/red-black, B-trees) enable O(log n) search, insert, and delete', 'Graphs represent relationships: adjacency list vs matrix, BFS for shortest paths, DFS for connectivity', 'Big O notation classifies algorithm efficiency: O(1), O(log n), O(n), O(n log n), O(n²) are the most common classes'],
                    cross_links=['Software Engineering', 'Machine Learning', 'AI', 'Database Systems'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Computer Science',
                    title='Computational Complexity Theory',
                    aliases=['P vs NP', 'Complexity Classes', 'NP-Completeness'],
                    sources=['Software Engineering', 'Mathematics'],
                    description='The classification of computational problems by their inherent difficulty: P (efficiently solvable), NP (verifiable in polynomial time), and the boundary between them.',
                    key_points=['P is the class of problems solvable in polynomial time — practically efficient', 'NP is the class of problems whose solutions can be verified in polynomial time', 'NP-complete problems are the hardest in NP — if any NP-complete problem is in P, then P = NP', 'The P vs NP question is the most important open problem in theoretical computer science ($1M Clay prize)', 'NP-hard problems are at least as hard as NP-complete but may not be in NP themselves (e.g., the halting problem)'],
                    cross_links=['Software Engineering', 'Mathematics', 'AI'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Computer Science',
                    title='Operating Systems',
                    aliases=['OS', 'Kernel', 'Process Management', 'Memory Management'],
                    sources=['Software Engineering'],
                    description='The software layer that manages hardware resources and provides services to applications: process scheduling, memory management, file systems, and I/O.',
                    key_points=['Processes are independent execution units with isolated address spaces; threads share address space within a process', 'Scheduling algorithms (round-robin, priority, multi-level feedback) determine which process runs when', 'Virtual memory maps each process\'s virtual address space to physical memory through page tables', 'File systems organize persistent data: inodes, directories, journaling for crash recovery', 'System calls provide the interface between user-space applications and the kernel'],
                    cross_links=['Software Engineering', 'Computer Architecture', 'Database Systems'],
                    priority=2,
                ),
                ConceptTarget(
                    domain='Computer Science',
                    title='Database Systems',
                    aliases=['Relational Databases', 'SQL', 'Transactions', 'ACID'],
                    sources=['Software Engineering'],
                    description='Systems for storing, querying, and managing structured data: relational model, SQL, transactions, indexing, and distributed databases.',
                    key_points=['The relational model organizes data into tables (relations) with rows (tuples) and columns (attributes)', 'SQL provides declarative querying: SELECT, JOIN, GROUP BY, and subqueries express complex data operations', 'ACID transactions (Atomicity, Consistency, Isolation, Durability) guarantee reliable data modification', 'Indexes (B-trees, hash indexes) accelerate query execution by enabling fast row lookup without full table scans', 'Distributed databases (Spanner, CockroachDB) provide ACID transactions across multiple nodes using consensus protocols like Paxos/Raft'],
                    cross_links=['Software Engineering', 'Distributed Systems', 'Data Modeling & Schema Design'],
                    priority=2,
                ),
            ]
        },
        'Nutrition': {
            'target_count': 6,
            'concepts': [
                ConceptTarget(
                    domain='Nutrition',
                    title='Macronutrients and Energy Balance',
                    aliases=['Macros', 'Caloric Balance', 'Carbohydrates Proteins Fats'],
                    sources=['Physiology', 'Metabolism'],
                    description='The three primary energy-providing nutrients: carbohydrates (4 kcal/g), proteins (4 kcal/g), and fats (9 kcal/g), and the thermodynamics of energy balance.',
                    key_points=['Carbohydrates are the preferred fuel source: glucose is metabolized through glycolysis and oxidative phosphorylation', 'Dietary proteins provide essential amino acids that cannot be synthesized endogenously (9 of 20)', 'Fats provide the most concentrated energy (9 kcal/g) and are essential for absorption of fat-soluble vitamins', 'Energy balance = energy intake − energy expenditure; sustained surplus leads to fat storage, deficit to fat mobilization', 'Basal metabolic rate accounts for 60-75% of total energy expenditure and is primarily determined by lean body mass'],
                    cross_links=['Physiology', 'Exercise Physiology', 'Metabolism', 'Longevity'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Nutrition',
                    title='Micronutrients and Vitamins',
                    aliases=['Vitamins', 'Minerals', 'Essential Nutrients'],
                    sources=['Physiology', 'Cell Biology'],
                    description='Essential vitamins and minerals required in small amounts for normal physiological function: roles, deficiency syndromes, and dietary sources.',
                    key_points=['Fat-soluble vitamins (A, D, E, K) are stored in adipose tissue and liver — toxicity possible with megadoses', 'Water-soluble vitamins (B-complex, C) are excreted in urine when intake exceeds requirements — toxicity rare', 'Essential minerals (calcium, iron, zinc, magnesium, potassium, sodium) serve structural, catalytic, and signaling roles', 'Vitamin D is synthesized in skin upon UV exposure — deficiency affects ~40% of populations at northern latitudes', 'Iron deficiency is the most common micronutrient deficiency globally, causing anemia in ~30% of the population'],
                    cross_links=['Physiology', 'Cell Biology', 'Medicine'],
                    priority=1,
                ),
                ConceptTarget(
                    domain='Nutrition',
                    title='Dietary Patterns and Health Outcomes',
                    aliases=['Mediterranean Diet', 'Diet-Health Relationship', 'Nutritional Epidemiology'],
                    sources=['Longevity', 'Physiology', 'Medicine'],
                    description='The relationship between overall dietary patterns (not individual nutrients) and health outcomes: cardiovascular disease, metabolic health, longevity, and cognitive function.',
                    key_points=['The Mediterranean diet (high in olive oil, fish, vegetables, whole grains) consistently shows the strongest evidence for reduced cardiovascular mortality', 'Ultra-processed foods are associated with increased all-cause mortality, independent of nutrient composition', 'Dietary fiber from whole plants reduces risk of colorectal cancer, cardiovascular disease, and type 2 diabetes', 'Caloric restriction and intermittent fasting improve metabolic health markers and extend lifespan in animal models', 'The gut microbiome mediates many diet-health effects — fiber fermentation produces short-chain fatty acids with anti-inflammatory properties'],
                    cross_links=['Longevity', 'Physiology', 'Medicine', 'Caloric Restriction and Dietary Restriction'],
                    priority=2,
                ),
            ]
        },
    }

    def __init__(self, analyzer: VaultAnalyzer):
        self.analyzer = analyzer

    def get_plan(self) -> list[tuple[str, int, list[ConceptTarget]]]:
        """Generate expansion plan for all mapped domains."""
        plan = []
        for domain, spec in self.DOMAIN_EXPANSIONS.items():
            current = len(self.analyzer.domains.get(domain, []))
            if current < spec['target_count']:
                plan.append((domain, current, spec['concepts']))
        return plan

    def write_concept(self, target: ConceptTarget) -> str:
        """Write one concept note to the correct format."""
        date_str = datetime.now().strftime('%Y-%m-%d')

        content = "---\n"
        content += f"title: \"{target.title}\"\n"
        content += f"aliases:\n"
        for alias in target.aliases:
            content += f"  - {alias}\n"
        content += f"status: growing\n"
        content += f"domain: {target.domain}\n"
        content += f"tags:\n"
        content += f"  - concept\n"
        content += f"  - expansion\n"
        content += f"  - {target.domain.lower().replace(' ', '-')}\n"
        content += f"created: {date_str}\n"
        content += f"sources:\n"
        for s in target.sources:
            content += f"  - [[{s}]]\n"
        content += "---\n\n"

        content += f"# {target.title}\n\n"

        # Opening definition
        content += f"| | |\n|---|---|\n"
        content += f"| **Definition** | {target.description} |\n"
        content += f"| **Domain** | {target.domain} |\n"
        content += "| **Status** | Growing — expansion target |\n"
        content += "\n---\n\n"

        # Key points
        content += "## Key Concepts\n\n"
        for i, point in enumerate(target.key_points, 1):
            content += f"{i}. {point}\n\n"

        content += "---\n\n"

        # Cross-references
        content += "## Related Concepts\n\n"
        for link in target.cross_links[:5]:
            content += f"- [[{link}]]\n"

        content += "\n---\n\n"
        content += f"*Vault expansion concept. Created {date_str}. {target.domain} domain expansion target. Part of systematic knowledge deepening.*\n"

        return content

    def save_concept(self, target: ConceptTarget, content: str) -> str:
        """Save concept to the Concepts directory."""
        safe = re.sub(r'[^\w\s-]', '', target.title).strip()
        safe = re.sub(r'\s+', ' ', safe)[:100]
        path = os.path.join(CONCEPTS_DIR, f"{safe}.md")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def save_plan_doc(self, plan: list[tuple[str, int, list[ConceptTarget]]]) -> str:
        """Save the full expansion plan as a note."""
        content = "---\n"
        content += "title: Vault Expansion Plan — Concept Deepening\n"
        content += f"date: {datetime.now().strftime('%Y-%m-%d')}\n"
        content += "status: growing\n"
        content += "tags:\n"
        content += "  - expansion\n"
        content += "  - vault-growth\n"
        content += "  - plan\n"
        content += "---\n\n"
        content += "# Vault Expansion Plan — Concept Deepening\n\n"
        content += f"Generated {datetime.now().strftime('%Y-%m-%d')}. Systematic expansion of the 7 thinnest domains.\n\n"

        for domain, current, concepts in plan:
            content += f"## {domain} — {current} → {current + len(concepts)} concepts\n\n"
            for c in concepts:
                content += f"### {c.title}\n"
                content += f"- **Priority**: {'★' * c.priority}\n"
                content += f"- **Description**: {c.description}\n"
                content += f"- **Connects to**: {', '.join(c.cross_links)}\n\n"
            content += "---\n\n"

        content += "*Systematic expansion across weak domains. Each new concept increases vault Φ by creating new cross-domain edges.*\n"

        path = os.path.join(EXPANSION_DIR, f"Vault Expansion Plan {datetime.now().strftime('%Y-%m-%d')}.md")
        with open(path, 'w') as f:
            f.write(content)
        return path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Vault Expansion Engine")
    parser.add_argument('--plan', action='store_true', help='Show expansion plan')
    parser.add_argument('--write', type=str, help='Write concepts for a domain')
    parser.add_argument('--write-all', action='store_true', help='Write all planned concepts')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be written without writing')
    parser.add_argument('--domains', action='store_true', help='List weak domains')
    args = parser.parse_args()

    analyzer = VaultAnalyzer()
    planner = ExpansionPlanner(analyzer)
    plan = planner.get_plan()

    if args.domains or args.plan:
        print("=" * 60)
        print("  VAULT EXPANSION PLAN")
        print("=" * 60)
        print(f"\n  Total concepts: {len(analyzer.concepts)}")
        print(f"  Total domains: {len(analyzer.domains)}")
        print()

        for domain, current, concepts in plan:
            status_icon = '🟢' if current >= 10 else '🟡' if current >= 5 else '🔴'
            print(f"  {status_icon} {domain}: {current} → {current + len(concepts)} (+{len(concepts)})")
            for c in concepts:
                print(f"       {'★' * c.priority} {c.title}")
            print()

        print(f"  Total planned: {sum(len(c) for _, _, c in plan)} new concepts")
        return

    if args.write:
        for domain, current, concepts in plan:
            if domain.lower() == args.write.lower():
                print(f"[Expansion] Writing {len(concepts)} concepts for {domain}...")
                for c in concepts:
                    content = planner.write_concept(c)
                    path = CONCEPTS_DIR  # just check path
                    safe = re.sub(r'[^\w\s-]', '', c.title).strip()
                    safe = re.sub(r'\s+', ' ', safe)[:100]
                    path = os.path.join(CONCEPTS_DIR, f"{safe}.md")
                    if not args.dry_run:
                        with open(path, 'w') as f:
                            f.write(content)
                    print(f"  {'[DRY RUN]' if args.dry_run else '[WRITTEN]'} {safe} ({c.domain}, priority {c.priority})")
                print(f"\n  Plan saved to expansions/")
                return

        print(f"Unknown domain: {args.write}")
        return

    if args.write_all or args.dry_run:
        total = 0
        for domain, current, concepts in plan:
            print(f"[Expansion] {'[DRY RUN]' if args.dry_run else 'Writing'} {len(concepts)} concepts for {domain}...")
            for c in concepts:
                content = planner.write_concept(c)
                safe = re.sub(r'[^\w\s-]', '', c.title).strip()
                safe = re.sub(r'\s+', ' ', safe)[:100]
                path = os.path.join(CONCEPTS_DIR, f"{safe}.md")
                if not args.dry_run:
                    with open(path, 'w') as f:
                        f.write(content)
                print(f"  {'[DRY RUN]' if args.dry_run else '[WRITTEN]'} {safe}")
                total += 1
            print()

        # Save the plan document
        if not args.dry_run:
            plan_path = planner.save_plan_doc(plan)
            print(f"[Expansion] Plan: {plan_path}")

        print(f"[Expansion] Total: {total} new concepts across {len(plan)} domains")


if __name__ == '__main__':
    main()
