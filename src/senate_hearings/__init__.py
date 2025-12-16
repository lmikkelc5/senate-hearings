"""
senate_hearings

Scrape and clean U.S. Senate hearing transcripts from govinfo.gov.
Public API is re-exported here for convenient imports.
"""

from __future__ import annotations

# --------------------
# Scraping / parsing helpers
# --------------------
from .helper_funcs import (
    get_fully_expanded_html,
    extract_hearing_links,
    get_session_from_url,
    get_text,
    to_html_url,
    get_category_text,
    extract_main_text,
    get_date,
    extract_hearing_title,
    get_month,
    get_day,
    get_year,
    load_processed,
)

# --------------------
# Keyword / KeyBERT helpers
# --------------------
from .keybert_funcs import (
    is_banned_candidate,
    mmr_select,
    normalize_keyword,
    filter_and_normalize_keywords,
    trim_candidates_by_frequency,
)

__all__ = [
    # helper_funcs
    "get_fully_expanded_html",
    "extract_hearing_links",
    "get_session_from_url",
    "get_text",
    "to_html_url",
    "get_category_text",
    "extract_main_text",
    "get_date",
    "extract_hearing_title",
    "get_month",
    "get_day",
    "get_year",
    "load_processed",

    # keybert_funcs
    "is_banned_candidate",
    "mmr_select",
    "normalize_keyword",
    "filter_and_normalize_keywords",
    "trim_candidates_by_frequency",
]
