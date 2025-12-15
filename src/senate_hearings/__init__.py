"""
senate_hearings

Scrape and clean U.S. Senate hearing transcripts from govinfo.gov.
Public API is re-exported here for convenient imports.
"""

from __future__ import annotations

# If all these functions currently live in ONE module file, e.g. helper_funcs.py:
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
)

__all__ = [
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
]