from __future__ import annotations
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    ElementClickInterceptedException,
)
from pathlib import Path
import time
import os

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

def click_all_more_buttons(driver, timeout=10, sleep_after_click=0.25) -> bool:
    """
    Click any 'More'/'Show more' style controls until none remain.
    Returns True if it clicked at least one; False otherwise.
    """
    clicked_any = False
    while True:
        try:
            candidates = driver.find_elements(By.XPATH, X_MORE)
            # visible & not disabled
            candidates = [c for c in candidates if c.is_displayed() and not c.get_attribute("disabled")]
            if not candidates:
                break
            did_click = False
            for el in candidates:
                did_click |= _safe_click(driver, el, sleep_after_click)
            if did_click:
                clicked_any = True
                WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(0.2)
            else:
                break
        except Exception:
            break
    return clicked_any

def expand_all_toggles(driver, sleep_after_click=0.25) -> None:
    """Expand common Bootstrap/accordion toggles."""
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
            expanded = (t.get_attribute("aria-expanded") or "").lower()
            if expanded == "true":
                continue
        except Exception:
            pass
        _safe_click(driver, t, sleep_after_click)

def get_fully_expanded_html(
    url: str,
    *,
    headless: bool = True,
    max_scroll_rounds: int = 6,
    wait_seconds: int = 25,
    sleep_after_click: float = 0.25,
    save_to: str | None = None,
    ensure_dir: bool = True,
) -> str:
    """
    Load the page, expand all accordions/panels and 'More' controls,
    scroll to trigger lazy loads, and return the final rendered HTML.
    Optionally save it to `save_to`.
    """
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1600,2000")
    opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_argument("user-agent=ExpandedHTMLBot/1.0")

    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(url)

        # Wait for base content (JS will build panels afterwards)
        WebDriverWait(driver, wait_seconds).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
        )

        last_height = 0
        for _ in range(max_scroll_rounds):
            expand_all_toggles(driver, sleep_after_click)
            clicked = click_all_more_buttons(driver, sleep_after_click=sleep_after_click)

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.6)
            new_height = driver.execute_script("return document.body.scrollHeight;")

            if new_height == last_height and not clicked:
                break
            last_height = new_height

        # Final pass
        expand_all_toggles(driver, sleep_after_click)
        click_all_more_buttons(driver, sleep_after_click=sleep_after_click)
        time.sleep(0.3)

        html = driver.page_source

        if save_to:
            if ensure_dir:
                Path(os.path.dirname(save_to) or ".").mkdir(parents=True, exist_ok=True)
            Path(save_to).write_text(html, encoding="utf-8")

        return html
    finally:
        driver.quit()

# # Quick local test:
# if __name__ == "__main__":
#     u = "https://www.govinfo.gov/committee/senate-agriculture"
#     h = get_fully_expanded_html(u, headless=True, save_to="senate_html/senate-agriculture.html")
#     print("HTML length:", len(h))
