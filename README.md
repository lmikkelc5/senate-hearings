# senate-hearings

Scrape, clean, and analyze U.S. Senate hearing transcripts from
[govinfo.gov](https://www.govinfo.gov/).

This package provides Python utilities for collecting Senate hearing metadata
and transcript text, expanding dynamically loaded content, and preparing
hearing data for analysis, NLP, and visualization workflows.

---

## Features

- Scrape Senate hearing metadata and transcript text
- Expand dynamically loaded “Show more” / accordion content
- Clean and normalize long transcript documents
- Extract structured fields (date, committee, title, text, etc.)
- Designed to support downstream NLP and dashboarding

---

## Documentation & demos

These links will be filled in as the project evolves.

### Full documentation (GitHub Pages)
Link coming soon

### Interactive EDA (Streamlit)
Link coming soon

### Source code (GitHub)
https://github.com/lmikkelc5/senate-hearings

### Tutorial (Github)

## Installation

Basic installation:

```bash
pip install senate-hearings   #package
pip install senate-hearings[app]   # Streamlit demo dependencies
pip install senate-hearings[nlp]   # NLP / keyword extraction dependencies
pip install senate-hearings[viz]   # Visualization dependencies
