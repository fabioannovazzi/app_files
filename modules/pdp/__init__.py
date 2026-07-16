from __future__ import annotations

from .adapters import NullAdapter, RetailerAdapter
from .adapters.amazon import AmazonAdapter
from .adapters.chewy import ChewyAdapter
from .adapters.guestinresidence import GuestInResidenceAdapter
from .adapters.lorealparis import LorealParisAdapter
from .adapters.purina import PurinaAdapter
from .adapters.sephora import SephoraAdapter
from .adapters.tikicat import TikiCatAdapter
from .adapters.ulta import UltaAdapter
from .adapters.vince import VinceAdapter
from .engine import PDPParser
from .fetcher import HTMLFetcher
from .models import (
    BatchParseResult,
    EvidenceBlob,
    FetchResult,
    ParentProduct,
    ParseResult,
    RawEvidence,
    Variant,
)
from .profile import PDPProfile
from .profile_loader import (
    CONFIG_ROOT,
    ProfileSummary,
    iter_profile_summaries,
    load_profile,
)
from .storage import EvidenceStorage

__all__ = [
    "AmazonAdapter",
    "BatchParseResult",
    "CONFIG_ROOT",
    "ChewyAdapter",
    "EvidenceBlob",
    "EvidenceStorage",
    "FetchResult",
    "GuestInResidenceAdapter",
    "HTMLFetcher",
    "LorealParisAdapter",
    "NullAdapter",
    "PDPParser",
    "PDPProfile",
    "ParentProduct",
    "ParseResult",
    "ProfileSummary",
    "PurinaAdapter",
    "RawEvidence",
    "RetailerAdapter",
    "SephoraAdapter",
    "TikiCatAdapter",
    "UltaAdapter",
    "Variant",
    "VinceAdapter",
    "iter_profile_summaries",
    "load_profile",
]
