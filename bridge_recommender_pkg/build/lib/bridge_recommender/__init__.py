"""Bridge Recommender — find structural knowledge gaps in any vault."""
from .scanner import load_vault, load_existing_bridges, find_bridge_candidates, find_concept_gaps, compute_domain_phi, generate_rationale

__version__ = "1.0.0"
