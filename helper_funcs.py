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
import requests

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


def extract_hearing_links(html_text: str) -> pd.DataFrame:
    """
    From a saved govinfo HTML page, extract for each hearing:

      - details_url : https://www.govinfo.gov/app/details/CHRG-...
      - text_url    : https://www.govinfo.gov/app/text/CHRG-...

    Returns a DataFrame with columns:
        details_url, text_url
    """
    soup = BeautifulSoup(html_text, "html.parser")

    hearings = []
    seen_ids = set()

    # Find all CHRG detail links
    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "/app/details/CHRG-" not in href and "/app/details/chrg-" not in href:
            continue

        # Extract the CHRG id (e.g. CHRG-119shrg12345)
        m_id = re.search(r"/app/details/([^/?#]+)", href)
        if not m_id:
            continue

        chrg_id = m_id.group(1)
        if chrg_id in seen_ids:
            continue
        seen_ids.add(chrg_id)

        # Normalize URLs
        details_url = f"{BASE}/app/details/{chrg_id}"
        text_url    = f"{BASE}/app/text/{chrg_id}"

        hearings.append(
            {
                "details_url": details_url,
                "text_url": text_url,
            }
        )

    if not hearings:
        print("No hearings found in this HTML file (no CHRG detail links).")

    return pd.DataFrame(hearings)

def get_session_from_url(url: str) -> str | None:
    m = re.search(r"CHRG-(\d{3})", url)
    return m.group(1) if m else None

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})

def get_text(url: str, retries=5):
    delay = 1
    for i in range(retries):
        try:
            print(f"Fetching: {url}")
            r = session.get(url, timeout=20)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            pre = soup.find("pre")
            return pre.get_text("\n") if pre else None

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            print(f"Connection error: {e} (retrying in {delay}s)")
            time.sleep(delay)
            delay *= 2     # exponential backoff

    print("Failed after retries")
    return None
    
def to_html_url(app_text_url: str) -> str:
    # Grab the last segment: CHRG-119shrg61295
    pkg = app_text_url.rstrip("/").split("/")[-1]
    granule = pkg  # main part uses the same ID
    return f"https://www.govinfo.gov/content/pkg/{pkg}/html/{granule}.htm"

def get_category_text(url: str) -> str | None:
    # Get the page
    response = requests.get(url, timeout=15)
    response.raise_for_status()   # throw error if request failed

    # Parse HTML
    soup = BeautifulSoup(response.text, "html.parser")

    # Find the target div
    target = soup.find("div", id="tooltip-spanid", attrs={"data-id": "Category"})
    if not target:
        return None

    # The value sits in its <p> child
    p_tag = target.find("p")
    if not p_tag:
        return None

    return p_tag.get_text(strip=True)

def extract_main_text(raw, remove_all_caps_headings=False):
    """
    Cleans structured transcript-like text by removing:
      - Bracketed metadata ([Senate Hearing...], [GRAPHICS...], etc.)
      - Page numbers, section headings, numbering
      - (Optionally) ALL CAPS headings
      - Excessive whitespace
      - Repeated underscores, equal signs, separators
      - Lines that are mostly formatting
      - Speaker labels like 'STATEMENT OF ...', 'Chairman Chambliss.'
    Returns plain, readable text.
    """

    text = raw

    # 1. Remove bracketed metadata blocks like [SENATE HEARING 109...]
    text = re.sub(r"\[[^\]]*\]", "", text)

    # 2. Remove lines that are just formatting (====, ----, ____ etc.)
    text = re.sub(r"^[=\-\_]{3,}.*$", "", text, flags=re.MULTILINE)

    # 3. Remove page numbers and roman numeral section markers
    text = re.sub(r"^\s*\(?\d+\)?\s*$", "", text, flags=re.MULTILINE)

    # 4. (OPTIONAL) Remove ALL CAPS headings (committees, titles, CONTENTS, etc.)
    # This is what was killing your screenshot block. Only run it if requested.
    if remove_all_caps_headings:
        text = re.sub(r"^[A-Z0-9 \.\,\-\(\)']{8,}$", "", text, flags=re.MULTILINE)

    # 5. Remove speaker labels like:
    #    CHAIRMAN CHAMBLISS.
    #    STATEMENT OF MARK E. KEENUM
    text = re.sub(r"^[A-Z][A-Z \.\-\,']{3,}:\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^STATEMENT OF.*$", "", text, flags=re.MULTILINE)

    # 6. Remove superfluous whitespace
    text = re.sub(r"\n{2,}", "\n\n", text)       # collapse huge blocks
    text = re.sub(r"[ \t]+", " ", text)         # compress spaces

    # 7. Strip leading/trailing whitespace
    text = text.strip()

    return text

def get_date(text):
    pattern = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b")
    matches = pattern.findall(text)
    if len(matches) == 0:
        return "na"
    
    return matches[0]

def extract_hearing_title(raw_text):
    """
    Extracts hearing titles consisting of one or more consecutive ALL-CAPS lines.
    Returns the full multi-line title block.
    """

    # Match one or more ALL-CAPS lines in a row
    pattern = re.compile(
        r"(?:^[A-Z0-9\.\-· \u00b7,'&]{10,}$\n?)+",
        re.MULTILINE
    )

    match = pattern.search(raw_text)
    if not match:
        return None

    # Clean up trailing newline
    return match.group(0).strip().replace("\n", "")

def get_month(date):
    date = str(date)
    if "January" in date:
        return 1
    elif "February" in date:
        return 2
    elif "March" in date:
        return 3
    elif "April" in date:
        return 4
    elif "May" in date:
        return 5
    elif "June" in date:
        return 6
    elif "July" in date:
        return 7
    elif "August" in date:
        return 8
    elif "September" in date:
        return 9
    elif "October" in date:
        return 10
    elif "November" in date:
        return 11
    elif "February" in date:
        return 12
    else:
        return None

def get_day(date):
    date = str(date)
    pattern = re.compile(r"(\d{1,2})")
    match = pattern.search(date)
    if match:
        return int(match.group(1))
    return 'na'

def get_year(date):
    date = str(date)
    pattern = re.compile(r"(\d{4})")
    match = pattern.search(date)
    if match:
        return int(match.group(1))
    return 'na'