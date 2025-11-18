#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Metacritic Bias Analyzer - Playwright Version
- Loads a file with Metacritic links
- Scrapes or updates a local CSV database (with dynamic scrolling)
- Calculates outlet biases vs Metascore and vs UserScore

NOTES:
- Requires "playwright" and "beautifulsoup4".
- Install: pip install playwright beautifulsoup4
- Then: playwright install chromium
- The database is a CSV file named "metacritic_db.csv".
- UserScores (out of 10) are converted *10 for consistency.
- Duplicates are updated, never duplicated.
"""

import csv
import os
import statistics as stats
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time

SCRAPE_DELAY = 3
MAX_RETRIES = 3

DB_FILE = "metacritic_db.csv"


# ------------------------------------------------------------
# Database utilities
# ------------------------------------------------------------
def load_db():
    """Load the CSV database."""
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_db(rows):
    """Save the CSV database."""
    with open(DB_FILE, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "link", "metascore", "outlet", "outlet_id", "outlet_score",
            "user_score", "review_count_outlets", "review_count_users"
        ])
        writer.writeheader()
        writer.writerows(rows)


# ------------------------------------------------------------
# Scraping Metacritic with Playwright
# ------------------------------------------------------------
def clean_link(url: str) -> str:
    """Clean a Metacritic link to the game base URL."""
    base = url.split("?")[0].strip()
    if base.endswith("/"):
        base = base[:-1]
    # Remove anything after the game name (critic-reviews, user-reviews, etc.)
    parts = base.split("/")
    if len(parts) >= 5:  # https://www.metacritic.com/game/title
        base = "/".join(parts[:5])
    return base


def fetch_page_with_playwright(url: str, scroll: bool = False):
    """
    Fetch a page using Playwright.
    If scroll=True, scrolls to load all dynamic content.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Load page
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)  # Wait for initial rendering

            if scroll:
                print(f"  Auto-scrolling...")
                previous_count = 0
                no_change_count = 0
                max_no_change = 3  # Stop after 3 scrolls without change

                while no_change_count < max_no_change:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)

                    current_count = page.locator('div[data-testid="product-review"]').count()

                    if current_count > previous_count:
                        print(f"    → {current_count} reviews loaded")
                        previous_count = current_count
                        no_change_count = 0
                    else:
                        no_change_count += 1

                print(f"  ✓ Scrolling finished: {previous_count} reviews found")

            html = page.content()
            browser.close()
            return html

    except PlaywrightTimeoutError:
        print(f"  ⚠ Timeout while loading {url}")
        return None
    except Exception as e:
        print(f"  ⚠ Playwright error: {e}")
        return None


def scrape_metacritic_game(url: str):
    """Scrape the main Metacritic page + critic-reviews."""
    cleaned = clean_link(url)

    # Main page for Metascore and User Score
    print(f"  Fetching {cleaned}...")
    html_main = fetch_page_with_playwright(cleaned, scroll=False)
    if not html_main:
        return []

    soup_main = BeautifulSoup(html_main, "html.parser")

    # Extract Metascore
    metascore = None
    review_count_outlets = None

    critic_link = soup_main.find("a", attrs={"data-testid": "critic-path"})
    if critic_link:
        reviews_text = critic_link.get_text(strip=True)
        import re
        match = re.search(r'(\d+)', reviews_text)
        if match:
            review_count_outlets = int(match.group(1))

        parent = critic_link.find_parent("div", class_="c-productScoreInfo_scoreContent")
        if parent:
            score_div = parent.find("div", class_="c-productScoreInfo_scoreNumber")
            if score_div:
                score_span = score_div.find("span", attrs={"data-v-e408cafe": ""})
                if score_span:
                    try:
                        score_text = score_span.text.strip()
                        if score_text.lower() != "tbd":
                            metascore = int(score_text)
                    except ValueError:
                        pass

    # Extract User Score
    user_score = None
    review_count_users = None
    user_link = soup_main.find("a", attrs={"data-testid": "user-path"})
    if user_link:
        reviews_text = user_link.get_text(strip=True)
        import re
        match = re.search(r'([\d,]+)', reviews_text)
        if match:
            review_count_users = int(match.group(1).replace(',', ''))

        parent = user_link.find_parent("div", class_="c-productScoreInfo_scoreContent")
        if parent:
            score_div = parent.find("div", class_="c-productScoreInfo_scoreNumber")
            if score_div:
                user_score_div = score_div.find("div", class_="c-siteReviewScore_user")
                if user_score_div:
                    user_score_span = user_score_div.find("span", attrs={"data-v-e408cafe": ""})
                    if user_score_span:
                        try:
                            score_text = user_score_span.text.strip()
                            if score_text.lower() != "tbd":
                                user_score = float(score_text) * 10
                        except ValueError:
                            pass

    print(
        f"  Metascore: {metascore}, User Score: {user_score}, Reviews: {review_count_outlets} critics / {review_count_users} users")

    # Scrape critic-reviews page WITH SCROLLING
    critic_url = cleaned.rstrip("/") + "/critic-reviews/"
    print(f"  Fetching reviews: {critic_url}...")
    html_crit = fetch_page_with_playwright(critic_url, scroll=True)
    if not html_crit:
        return []

    soup_crit = BeautifulSoup(html_crit, "html.parser")

    reviews = soup_crit.find_all("div", attrs={"data-testid": "product-review"})
    rows = []

    print(f"  Processing {len(reviews)} review(s)...")

    for review_block in reviews:
        outlet_link = review_block.find("a", class_="c-siteReviewHeader_publicationName")
        if not outlet_link:
            continue

        outlet_name = outlet_link.get_text(strip=True)
        href = outlet_link.get("href", "")
        outlet_id = None
        if "/publication/" in href:
            outlet_id = href.split("/publication/")[-1].strip("/")

        score_div = review_block.find("div", class_="c-siteReviewScore")
        if not score_div:
            continue

        score_span = score_div.find("span", attrs={"data-v-e408cafe": ""})
        if not score_span:
            continue

        score_text = score_span.get_text(strip=True).lower()
        if score_text == "tbd":
            print(f"    ⊘ {outlet_name}: score TBD, skipped")
            continue

        try:
            outlet_score = int(score_text)
        except ValueError:
            print(f"    ⚠ {outlet_name}: invalid score '{score_text}', skipped")
            continue

        rows.append({
            "link": cleaned,
            "metascore": metascore,
            "outlet": outlet_name,
            "outlet_id": outlet_id,
            "outlet_score": outlet_score,
            "user_score": user_score,
            "review_count_outlets": review_count_outlets,
            "review_count_users": review_count_users,
        })

    print(f"  ✓ {len(rows)} valid review(s) extracted")
    return rows


# ------------------------------------------------------------
# Update database from links
# ------------------------------------------------------------
def update_from_links_file(file_path: str):
    """Load a links file and update the database."""
    db = load_db()
    new_rows_count = 0

    links = list()
    with open(file_path, encoding="utf-8") as f:
        for l in f.readlines():
            if l.strip() and l.strip() not in links:
                links.append(l.strip())
            else:
                print(f"Ignored line: {l.strip()}")

    print(f"\n{len(links)} link(s) to process.\n")

    for i, link in enumerate(links, 1):
        print(f"[{i}/{len(links)}] Processing {link}")

        if i > 1:
            time.sleep(SCRAPE_DELAY)

        rows = scrape_metacritic_game(link)
        if not rows:
            print("  ⚠ No data retrieved.\n")
            continue

        cleaned = rows[0]["link"]

        old_count = len(db)
        db = [r for r in db if r["link"] != cleaned]
        removed = old_count - len(db)

        if removed > 0:
            print(f"  ✓ {removed} old entry(ies) removed.")

        db.extend(rows)
        new_rows_count += len(rows)
        print(f"  ✓ {len(rows)} review(s) added.\n")

    save_db(db)
    print(f"✓ Done. {new_rows_count} row(s) added or updated.")


# ------------------------------------------------------------
# Compute statistics per outlet
# ------------------------------------------------------------
def compute_stats():
    """Calculate and display bias statistics per outlet."""
    db = load_db()
    if not db:
        print("Database is empty.")
        return

    outlets = {}
    for r in db:
        outlet_id = r.get("outlet_id")
        outlet_name = r.get("outlet")
        if not outlet_id:
            continue

        if outlet_id not in outlets:
            outlets[outlet_id] = {
                "name": outlet_name,
                "meta": [],
                "user": []
            }

        try:
            ms = float(r["metascore"])
            oscr = float(r["outlet_score"])
        except (ValueError, TypeError):
            continue

        outlets[outlet_id]["meta"].append(oscr - ms)

        try:
            us = float(r["user_score"])
            outlets[outlet_id]["user"].append(oscr - us)
        except (ValueError, TypeError):
            pass

    sorted_outlets = sorted(
        outlets.items(),
        key=lambda x: len(x[1]["meta"]),
        reverse=True
    )

    table_data = []
    for outlet_id, values in sorted_outlets:
        meta_diffs = values["meta"]
        user_diffs = values["user"]
        outlet_name = values["name"]

        if not meta_diffs:
            continue

        nb_reviews = len(meta_diffs)
        meta_mean = stats.mean(meta_diffs)
        meta_median = stats.median(meta_diffs)

        if user_diffs:
            user_mean = stats.mean(user_diffs)
            user_median = stats.median(user_diffs)
        else:
            user_mean = None
            user_median = None

        table_data.append({
            "outlet": outlet_name,
            "nb_reviews": nb_reviews,
            "meta_mean": meta_mean,
            "meta_median": meta_median,
            "user_mean": user_mean,
            "user_median": user_median
        })

    print("\n" + "=" * 120)
    print("BIAS STATISTICS PER OUTLET")
    print("=" * 120)
    print(f"{'Outlet':<30} | {'Nbr':<4} | {'Bias vs PRO':^21} | {'Bias vs Players':^21} |")
    print(f"{'':30} | {'Rev':<4} | {'Mean':>9} | {'Med':>9} | {'Mean':>9} | {'Med':>9} |")
    print("-" * 120)

    user_means_for_threshold = [r['user_mean'] for r in table_data if r['user_mean'] is not None]
    threshold_90 = None
    if user_means_for_threshold:
        user_means_abs = sorted([abs(x) for x in user_means_for_threshold], reverse=True)
        percentile_90_idx = int(len(user_means_abs) * 0.1)
        threshold_90 = user_means_abs[percentile_90_idx] if percentile_90_idx < len(user_means_abs) else user_means_abs[-1]

    RED = '\033[91m'
    RESET = '\033[0m'

    for row in table_data:
        outlet = row["outlet"][:29]
        nb = row["nb_reviews"]
        meta_m = f"{row['meta_mean']:+.2f}"
        meta_med = f"{row['meta_median']:+.2f}"

        if row["user_mean"] is not None:
            user_m_val = row['user_mean']
            if threshold_90 and abs(user_m_val) >= threshold_90:
                user_m = f"{' '*3}{RED}{user_m_val:+.2f}{RESET}"
            else:
                user_m = f"{user_m_val:+.2f}"
            user_med = f"{row['user_median']:+.2f}"
        else:
            user_m = "N/A"
            user_med = "N/A"

        print(f"{outlet:<30} | {nb:<4} | {meta_m:>9} | {meta_med:>9} | {user_m:>9} | {user_med:>9} |")

    print("=" * 120)

    all_meta_means = [r['meta_mean'] for r in table_data]
    all_user_means = [r['user_mean'] for r in table_data if r['user_mean'] is not None]

    print(f"\n{'GLOBAL STATISTICS':^120}")
    print("-" * 120)

    if all_meta_means:
        global_meta_mean = stats.mean(all_meta_means)
        global_meta_std = stats.stdev(all_meta_means) if len(all_meta_means) > 1 else 0
        print(f"Average outlet bias vs PRO      : {global_meta_mean:+.2f} (std: {global_meta_std:.2f})")

    if all_user_means:
        global_user_mean = stats.mean(all_user_means)
        global_user_std = stats.stdev(all_user_means) if len(all_user_means) > 1 else 0
        print(f"Average outlet bias vs PLAYERS  : {global_user_mean:+.2f} (std: {global_user_std:.2f})")

    print(f"\nTotal outlets: {len(table_data)} | Total reviews analyzed: {sum(r['nb_reviews'] for r in table_data)}")
    print("\nLegend: Positive bias = outlet rates higher | Negative bias = outlet rates lower")
    print("=" * 120)

    if all_user_means:
        user_means_abs = sorted([abs(x) for x in all_user_means], reverse=True)
        percentile_90_idx = int(len(user_means_abs) * 0.1)
        threshold_90 = user_means_abs[percentile_90_idx] if percentile_90_idx < len(user_means_abs) else user_means_abs[-1]

        top_10_biased = [
            row for row in table_data
            if row['user_mean'] is not None and row["nb_reviews"] > 20 and abs(row['user_mean']) >= threshold_90
        ]

        top_10_biased.sort(key=lambda x: abs(x['user_mean']), reverse=True)

        if top_10_biased:
            print("\n" + "=" * 120)
            print("TOP 10% MOST BIASED OUTLETS - VS PLAYERS (min 20 reviews)")
            print("=" * 120)
            print(f"{'Outlet':<30} | {'Nbr':<4} | {'Avg Bias vs Players':>21} | {'Bias Type':<15} |")
            print(f"{'':30} | {'Rev':<4} | {'':>21} | {'':^15} |")
            print("-" * 120)

            for row in top_10_biased:
                outlet = row["outlet"][:29]
                nb = row["nb_reviews"]
                user_m = row['user_mean']
                bias_type = "More generous" if user_m > 0 else "More severe"

                print(f"{outlet:<30} | {nb:<4} | {user_m:>+21.2f} | {bias_type:<15} |")

            print("=" * 120)
            print(f"90th percentile threshold : {threshold_90:.2f} points difference")
            print("=" * 120)


# ------------------------------------------------------------
# Main menu
# ------------------------------------------------------------
def main():
    print("\n" + "=" * 60)
    print("    METACRITIC BIAS ANALYZER (Playwright)")
    print("=" * 60)
    print("\n1 = Load links file / scrape / update database")
    print("2 = Show statistics per outlet")
    print("3 = Quit")
    choice = input("\nYour choice: ").strip()

    if choice == "1":
        path = input("\nPath to links file: ").strip()
        if os.path.exists(path):
            update_from_links_file(path)
        else:
            print(f"❌ File not found: {path}")
    elif choice == "2":
        compute_stats()
    elif choice == "3":
        print("Goodbye!")
    else:
        print("❌ Invalid choice.")


if __name__ == "__main__":
    main()
