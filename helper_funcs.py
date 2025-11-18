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

def get_fully_expanded_html(
    url: str,
    *,
    headless: bool = True,
    max_scroll_rounds: int = 3,
    wait_seconds: int = 10,
    sleep_after_click: float = 0.1,
    save_to: str | None = None,
    ensure_dir: bool = True,
    overall_timeout: int = 30,   # HARD cap in seconds per page
) -> str:
    """
    Load the page, expand all accordions/panels and 'More' controls,
    scroll to trigger lazy loads, and return the final rendered HTML.
    Optionally save it to `save_to`.

    This version has:
    - A global timeout (`overall_timeout`) for the whole operation
    - Limits inside the click loop to avoid pathological pages
    """
    start_time = time.time()

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
        driver.set_page_load_timeout(wait_seconds)

        try:
            driver.get(url)
        except TimeoutException:
            # Page never fully finishes loading; take what we have
            html = driver.page_source
            if save_to:
                if ensure_dir:
                    Path(os.path.dirname(save_to) or ".").mkdir(parents=True, exist_ok=True)
                Path(save_to).write_text(html, encoding="utf-8")
            return html

        try:
            WebDriverWait(driver, wait_seconds).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
            )
        except TimeoutException:
            # No body → bail early
            html = driver.page_source
            if save_to:
                if ensure_dir:
                    Path(os.path.dirname(save_to) or ".").mkdir(parents=True, exist_ok=True)
                Path(save_to).write_text(html, encoding="utf-8")
            return html

        last_height = 0
        for _ in range(max_scroll_rounds):
            if time.time() - start_time > overall_timeout:
                break

            expand_all_toggles(driver, sleep_after_click)
            click_all_more_buttons(
                driver,
                timeout=5,
                sleep_after_click=sleep_after_click,
                max_loops=5,
                max_total_clicks=50,
            )

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            new_height = driver.execute_script("return document.body.scrollHeight;")

            if new_height == last_height:
                # nothing more is loading; no need to keep trying
                break
            last_height = new_height

        # One last quick pass (but honor the total timeout)
        if time.time() - start_time <= overall_timeout:
            expand_all_toggles(driver, sleep_after_click)
            click_all_more_buttons(
                driver,
                timeout=5,
                sleep_after_click=sleep_after_click,
                max_loops=3,
                max_total_clicks=20,
            )
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
