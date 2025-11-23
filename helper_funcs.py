from __future__ import annotations
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    ElementClickInterceptedException,
    TimeoutException,
)
from pathlib import Path
import time
import os
import pandas as pd
from bs4 import BeautifulSoup
import re
from datetime import datetime

# Case-insensitive match for any <a> or <button> whose visible text contains "more"
X_MORE = (
    "//*[self::a or self::button]"
    "[contains(translate(normalize-space(string(.)),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'more')]"
)

def _safe_click(driver, el, sleep_after_click: float = 0.25) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.1)
        el.click()
        time.sleep(sleep_after_click)
        return True
    except (ElementClickInterceptedException, StaleElementReferenceException):
        try:
            driver.execute_script("arguments[0].click();", el)
            time.sleep(sleep_after_click)
            return True
        except Exception:
            return False
    except Exception:
        return False

def click_all_more_buttons(
    driver,
    timeout=10,
    sleep_after_click: float = 0.25,
) -> bool:
    """
    Click 'More'/'Show more' style controls until none remain.
    Skip links that would navigate to a different page.
    """
    clicked_any = False
    while True:
        try:
            candidates = driver.find_elements(By.XPATH, X_MORE)

            # visible & not disabled
            filtered = []
            for c in candidates:
                if not c.is_displayed() or c.get_attribute("disabled"):
                    continue

                # if it's an <a> with a real href (not just "#..."), treat as nav and skip
                try:
                    if c.tag_name.lower() == "a":
                        href = (c.get_attribute("href") or "").strip()
                        if href and not href.startswith("#"):
                            continue
                except Exception:
                    pass

                filtered.append(c)

            candidates = filtered

            if not candidates:
                break

            did_click = False
            for el in candidates:
                if _safe_click(driver, el, sleep_after_click):
                    did_click = True

            if did_click:
                clicked_any = True
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(0.2)
            else:
                break
        except Exception:
            break

    return clicked_any

def expand_all_toggles(driver, sleep_after_click=0.25) -> None:
    """Expand common Bootstrap/accordion toggles, but skip real navigation links."""
    toggles = driver.find_elements(
        By.CSS_SELECTOR,
        (
            '[data-toggle="collapse"],'
            '.accordion-toggle,'
            '.panel-title a,'
            'a[aria-controls],'
            'button[aria-controls]'
        ),
    )
    for t in toggles:
        try:
            # if it's already expanded, skip
            expanded = (t.get_attribute("aria-expanded") or "").lower()
            if expanded == "true":
                continue

            # ⚠️ key part: if this element has an href that is NOT just "#...",
            # it's a navigation link, not an in-page toggle → skip it
            href = (t.get_attribute("href") or "").strip()
            if href and not href.startswith("#"):
                continue
        except Exception:
            pass

        _safe_click(driver, t, sleep_after_click)

BASE = "https://www.govinfo.gov"

def _normalize_date_from_text(text: str):
    """
    Find a date like 'July 22, 2009' in text and return:
        (raw_date_str, 'YYYY-MM-DD') or (None, None)
    """
    if not text:
        return None, None

    m = re.search(r"[A-Z][a-z]+ \d{1,2}, \d{4}", text)
    if not m:
        return None, None

    raw = m.group(0)
    try:
        dt = datetime.strptime(raw, "%B %d, %Y")
        return raw, dt.date().isoformat()
    except ValueError:
        return raw, None

def extract_hearing_links(html_text: str) -> pd.DataFrame:
    """
    Extract:
      - title           : hearing title (best effort)
      - details_url     : https://www.govinfo.gov/app/details/CHRG-...
      - text_url        : https://www.govinfo.gov/app/text/CHRG-...
      - hearing_number  : e.g. 'S. Hrg. 114-123' (if found nearby)
      - date_raw        : 'Month d, yyyy' from nearby text
      - date_iso        : normalized 'YYYY-MM-DD'
      - committee       : committee name if parsable from nearby text
      - subcommittee    : subcommittee name if parsable from nearby text
    from a saved govinfo CHRG/committee HTML page.
    """

    soup = BeautifulSoup(html_text, "html.parser")

    hearings = []
    seen_ids = set()

    # Find ALL detail links for CHRG hearings
    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "/app/details/CHRG-" not in href and "/app/details/chrg-" not in href:
            continue

        # Extract the CHRG id, e.g. 'CHRG-119shrg12345'
        m_id = re.search(r"/app/details/([^/?#]+)", href)
        if not m_id:
            continue

        chrg_id = m_id.group(1)
        if chrg_id in seen_ids:
            continue
        seen_ids.add(chrg_id)

        # ---- DETAILS URL ----
        details_url = href if href.startswith("http") else f"{BASE}/app/details/{chrg_id}"

        # ---- Locate a reasonable container around this link ----
        container = a
        # walk up until we hit a list item / row-like container or a generic div
        while container.parent is not None and container.name not in ("li", "tr", "div", "section", "article"):
            container = container.parent

        # Fallback
        if container is None:
            container = a.parent

        # Get all text in this container once (for date, hearing number, etc.)
        text_block = container.get_text(" ", strip=True)

        # ---- TEXT URL ----
        # Look first inside the same container
        text_url = None
        text_link = container.find("a", string=lambda x: x and x.strip().lower() == "text")
        if text_link and text_link.get("href"):
            thref = text_link["href"]
            text_url = thref if thref.startswith("http") else BASE + thref
        else:
            # Fallback: guess app/text/<CHRG_ID>
            text_url = f"{BASE}/app/text/{chrg_id}"

        # ---- TITLE ----
        # Try to find a nicer title than just 'Details':
        # 1) Look for a "non-button" <a> in this container whose href points
        #    to the same CHRG id but text is not 'Details', 'PDF', 'Text'.
        title = None
        for a2 in container.find_all("a", href=True):
            if chrg_id not in a2["href"]:
                continue
            t = a2.get_text(strip=True)
            if t and t.lower() not in ("details", "pdf", "text", "share"):
                title = t
                break

        # 2) Fallback: first heading-like tag
        if not title:
            heading = container.find(["h1", "h2", "h3", "h4", "h5"])
            if heading:
                title = heading.get_text(" ", strip=True)

        # 3) Last fallback: use text_block, but strip button labels
        if not title:
            temp = re.sub(r"\b(Details|PDF|Text|Share)\b", "", text_block)
            title = temp.strip()

        # ---- HEARING NUMBER ----
        hearing_number = None
        patterns = [
            r"\b[SH]\.\s*Hrg\.\s*[0-9A-Za-z\-–]+",        # S. Hrg. 114-123, H. Hrg. 115-12
            r"\bH\.A\.S\.C\.\s*No\.\s*[0-9A-Za-z\-–]+",   # H.A.S.C. No. ...
            r"\bS\.\s*Prt\.\s*[0-9A-Za-z\-–]+",           # S. Prt. ...
        ]
        for pat in patterns:
            m_h = re.search(pat, text_block)
            if m_h:
                hearing_number = m_h.group(0)
                break

        # ---- DATE (raw + ISO) ----
        date_raw, date_iso = _normalize_date_from_text(text_block)

        # ---- COMMITTEE / SUBCOMMITTEE ----
        committee = None
        subcommittee = None

        # Try explicit labels if present
        m_comm = re.search(r"Committee:\s*(.*?)(?:;|$)", text_block)
        if m_comm:
            committee = m_comm.group(1).strip() or None

        m_sub = re.search(r"Subcommittee:\s*(.*?)(?:;|$)", text_block)
        if m_sub:
            subcommittee = m_sub.group(1).strip() or None

        hearings.append(
            {
                "title":          title,
                "details_url":    details_url,
                "text_url":       text_url,
                "hearing_number": hearing_number,
                "date_raw":       date_raw,
                "date_iso":       date_iso,
                "committee":      committee,
                "subcommittee":   subcommittee,
            }
        )

    if not hearings:
        print("No hearings found in this HTML file (no CHRG detail links).")

    return pd.DataFrame(hearings)
