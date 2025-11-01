# congress_scrape.py
from __future__ import annotations
import os, re, time, random, json
from dataclasses import dataclass, asdict
from typing import Optional, Dict

import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

@dataclass
class HearingRecord:
    url: str
    title: Optional[str]
    date_text: Optional[str]
    date_iso: Optional[str]
    committee: Optional[str]
    transcript: str

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
DATE_LINE_PAT = re.compile(rf"(?:Date\s*:\s*)?((?:{MONTHS})\s+\d{{1,2}},\s+\d{{4}})", re.I)
DATE_PAT = re.compile(rf"({MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})", re.I)
COMMITTEE_PAT = re.compile(r"(?:Committee|Subcommittee)\s*:\s*(.+)", re.I)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")

def _polite_delay():
    time.sleep(2 + random.random())  # robots ~2s

def _iso_from_date_text(date_text: str) -> Optional[str]:
    if not date_text:
        return None
    m = DATE_PAT.search(date_text.strip())
    if not m:
        return None
    month_name, day, year = m.group(1), int(m.group(2)), int(m.group(3))
    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
    }
    mm = month_map[month_name.lower()]
    return f"{year:04d}-{mm:02d}-{day:02d}"

def _extract_structured_fields(main_text: str) -> Dict[str, Optional[str]]:
    lines = [ln.strip() for ln in main_text.splitlines() if ln.strip()]
    title = None
    date_text = None
    committee = None
    if lines:
        title = lines[0] if len(lines[0]) >= 5 else (lines[1] if len(lines) > 1 else lines[0])
    search_slice = "\n".join(lines[:80])
    m_date = DATE_LINE_PAT.search(search_slice) or DATE_PAT.search(search_slice)
    if m_date:
        date_text = m_date.group(1) if m_date.lastindex else m_date.group(0)
    for ln in lines[:100]:
        m_com = COMMITTEE_PAT.search(ln)
        if m_com:
            committee = m_com.group(1).strip()
            break
    return {"title": title, "date_text": date_text, "committee": committee}

def _make_chrome(headless: bool = False):
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--lang=en-US")
    opts.add_argument("--window-size=1366,900")
    opts.add_argument(f"user-agent={UA}")
    # soften automation fingerprints
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opts)
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
    except Exception:
        pass
    return driver

def _passed_cloudflare(driver) -> bool:
    try:
        title = (driver.title or "").lower()
        if "just a moment" in title:
            return False
        body_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
        if "cloudflare" in body_text and ("checking your browser" in body_text or "enable cookies" in body_text):
            return False
        return True
    except Exception:
        return False

def _nudge_page(driver):
    """Small human-like interactions to help CF complete."""
    try:
        ActionChains(driver).move_by_offset(5, 5).perform()
    except Exception:
        pass
    try:
        driver.execute_script("window.scrollTo(0, Math.min(200, document.body.scrollHeight));")
    except Exception:
        pass

def _grab_text_from_dom(driver) -> str:
    for sel in ("#main", "main", "article", "#content"):
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            t = el.text.strip()
            if t:
                return t
        except Exception:
            continue
    return driver.find_element(By.TAG_NAME, "body").text.strip()

def _requests_with_cookies(driver, url: str) -> Optional[str]:
    """Use Selenium cookies in a requests session to fetch the static /text HTML."""
    try:
        s = requests.Session()
        s.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.congress.gov/",
        })
        for c in driver.get_cookies():
            # Only set cookie name/value; requests will handle domain/path broadly enough
            s.cookies.set(c.get("name"), c.get("value"))
        r = s.get(url, timeout=60)
        if r.status_code == 200 and "Just a moment" not in r.text:
            soup = BeautifulSoup(r.text, "html.parser")
            container = soup.select_one("#main") or soup.select_one("main") or soup.select_one("article") or soup.select_one("#content")
            if container:
                return container.get_text("\n", strip=True)
            return soup.get_text("\n", strip=True)
        return None
    except Exception:
        return None

def fetch_hearing(
    url: str,
    *,
    headless: bool = False,
    timeout_s: int = 300,
    save_txt: Optional[str] = None,
    save_json: Optional[str] = None,
) -> HearingRecord:
    """
    Robust fetch:
      1) Visit homepage to get CF cookies.
      2) Go to target; actively nudge, refresh, and re-nav until CF clears.
      3) If still stuck, reuse cookies with requests to fetch the static HTML.
    """
    driver = _make_chrome(headless=headless)
    try:
        _polite_delay()
        driver.get("https://www.congress.gov/")
        time.sleep(1.5 + random.random())

        driver.get(url)

        start = time.time()
        phase_deadline = start + timeout_s

        # Phase A: wait up to ~60s with nudges
        sub_deadline = min(phase_deadline, start + 60)
        while time.time() < sub_deadline:
            if _passed_cloudflare(driver):
                break
            _nudge_page(driver)
            time.sleep(2 + random.random())
        # Phase B: try refresh loops
        tries = 0
        while time.time() < phase_deadline and not _passed_cloudflare(driver):
            tries += 1
            driver.refresh()
            time.sleep(3 + random.random())
            _nudge_page(driver)
            if tries % 2 == 0:
                # bounce via homepage again
                driver.get("https://www.congress.gov/")
                time.sleep(2 + random.random())
                driver.get(url)
                time.sleep(3 + random.random())

        if _passed_cloudflare(driver):
            # Wait briefly for primary containers, then grab
            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#main"))
                )
            except Exception:
                pass  # fall through
            main_text = _grab_text_from_dom(driver)
        else:
            # Fallback: cookie reuse via requests
            html_text = _requests_with_cookies(driver, url)
            if not html_text:
                raise TimeoutError("Cloudflare interstitial did not clear; cookie+requests fallback failed.")
            main_text = html_text

        fields = _extract_structured_fields(main_text)
        date_iso = _iso_from_date_text(fields.get("date_text") or "")

        rec = HearingRecord(
            url=url,
            title=fields.get("title"),
            date_text=fields.get("date_text"),
            date_iso=date_iso,
            committee=fields.get("committee"),
            transcript=main_text,
        )

        if save_txt:
            os.makedirs(os.path.dirname(os.path.abspath(save_txt)), exist_ok=True)
            with open(save_txt, "w", encoding="utf-8") as f:
                f.write(rec.transcript)

        if save_json:
            os.makedirs(os.path.dirname(os.path.abspath(save_json)), exist_ok=True)
            with open(save_json, "w", encoding="utf-8") as f:
                json.dump(asdict(rec), f, ensure_ascii=False, indent=2)

        return rec

    finally:
        driver.quit()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python congress_scrape.py <url> [save_txt] [save_json]")
        raise SystemExit(2)
    url_ = sys.argv[1]
    save_txt_ = sys.argv[2] if len(sys.argv) >= 3 else None
    save_json_ = sys.argv[3] if len(sys.argv) >= 4 else None
    rec = fetch_hearing(url_, headless=False, timeout_s=300, save_txt=save_txt_, save_json=save_json_)
    print(f"Title: {rec.title}")
    print(f"Date:  {rec.date_text} (ISO: {rec.date_iso})")
    print(f"Committee: {rec.committee}")
    print("\nTranscript preview:\n", rec.transcript[:1200])
