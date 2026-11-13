"""Project P03: Legal Compliance & Contract Review Agent."""

from .ontology import (
    Clause,
    Contract,
    LegalAction,
    LegalLink,
    LegalOntologyRegistry,
    Obligation,
    Regulation,
)
from .llm_wiki import LegalLLMWiki
from .fde_pipeline import LegalFDEPipeline
from .api import app, create_app

__all__ = [
    "Clause",
    "Contract",
    "LegalAction",
    "LegalLink",
    "LegalOntologyRegistry",
    "Obligation",
    "Regulation",
    "LegalLLMWiki",
    "LegalFDEPipeline",
    "app",
    "create_app",
]
