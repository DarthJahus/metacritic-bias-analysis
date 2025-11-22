#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Metacritic Bias Analyzer - Playwright Version (Patched v3)
- Scrapes Metacritic links
- Computes outlet biases vs Metascore (PRO) and vs UserScore (PLAYERS)
- Prints summaries, detailed tables, and saves results to CSV
"""

import csv
import os
import statistics as stats
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time

SCRAPE_DELAY = 3
DB_FILE = "metacritic_db.csv"


# -----------------------------
# Database utilities
# -----------------------------
def load_db():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def save_db(rows):
    with open(DB_FILE, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "link", "metascore", "outlet", "outlet_id", "outlet_score",
            "user_score", "review_count_outlets", "review_count_users"
        ])
        writer.writeheader()
        writer.writerows(rows)


# -----------------------------
# Scraping
# -----------------------------
def clean_link(url: str) -> str:
    base = url.split("?")[0].strip()
    if base.endswith("/"):
        base = base[:-1]
    parts = base.split("/")
    if len(parts) >= 5:
        base = "/".join(parts[:5])
    return base


def fetch_page_with_playwright(url: str, scroll: bool = False):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0")
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            if scroll:
                previous_count = 0
                no_change = 0
                while no_change < 3:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)
                    current = page.locator('div[data-testid="product-review"]').count()
                    if current > previous_count:
                        previous_count = current
                        no_change = 0
                    else:
                        no_change += 1

            html = page.content()
            browser.close()
            return html

    except PlaywrightTimeoutError:
        print(f"  ⚠ Timeout while loading {url}")
    except Exception as e:
        print(f"  ⚠ Playwright error: {e}")
    return None


def scrape_metacritic_game(url: str):
    cleaned = clean_link(url)
    html_main = fetch_page_with_playwright(cleaned)
    if not html_main:
        return []

    soup_main = BeautifulSoup(html_main, "html.parser")

    metascore = None
    review_count_outlets = None
    critic_link = soup_main.find("a", attrs={"data-testid": "critic-path"})
    if critic_link:
        import re
        txt = critic_link.get_text(strip=True)
        m = re.search(r'(\d+)', txt)
        if m:
            review_count_outlets = int(m.group(1))
        parent = critic_link.find_parent("div", class_="c-productScoreInfo_scoreContent")
        if parent:
            score_div = parent.find("div", class_="c-productScoreInfo_scoreNumber")
            if score_div:
                score_span = score_div.find("span", attrs={"data-v-e408cafe": ""})
                if score_span:
                    try:
                        t = score_span.text.strip()
                        if t.lower() != "tbd":
                            metascore = int(t)
                    except:
                        pass

    user_score = None
    review_count_users = None
    user_link = soup_main.find("a", attrs={"data-testid": "user-path"})
    if user_link:
        import re
        txt = user_link.get_text(strip=True)
        m = re.search(r'([\d,]+)', txt)
        if m:
            review_count_users = int(m.group(1).replace(',', ''))
        parent = user_link.find_parent("div", class_="c-productScoreInfo_scoreContent")
        if parent:
            score_div = parent.find("div", class_="c-productScoreInfo_scoreNumber")
            if score_div:
                user_score_div = score_div.find("div", class_="c-siteReviewScore_user")
                if user_score_div:
                    span = user_score_div.find("span", attrs={"data-v-e408cafe": ""})
                    if span:
                        try:
                            t = span.text.strip()
                            if t.lower() != "tbd":
                                user_score = float(t) * 10
                        except:
                            pass

    critic_url = cleaned + "/critic-reviews/"
    html_crit = fetch_page_with_playwright(critic_url, scroll=True)
    if not html_crit:
        return []

    soup_crit = BeautifulSoup(html_crit, "html.parser")
    reviews = soup_crit.find_all("div", attrs={"data-testid": "product-review"})

    rows = []
    for block in reviews:
        link = block.find("a", class_="c-siteReviewHeader_publicationName")
        if not link:
            continue

        outlet_name = link.get_text(strip=True)
        href = link.get("href", "")
        outlet_id = None
        if "/publication/" in href:
            outlet_id = href.split("/publication/")[-1].strip("/")

        score_div = block.find("div", class_="c-siteReviewScore")
        if not score_div:
            continue
        span = score_div.find("span", attrs={"data-v-e408cafe": ""})
        if not span:
            continue

        t = span.get_text(strip=True).lower()
        if t == "tbd":
            continue
        try:
            outlet_score = int(t)
        except:
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

    return rows


# -----------------------------
# Update from links file
# -----------------------------
def update_from_links_file(file_path: str):
    db = load_db()
    new_rows = 0

    links = []
    with open(file_path, encoding="utf-8") as f:
        for l in f:
            ls = l.strip()
            if ls and ls not in links:
                links.append(ls)

    for i, link in enumerate(links, 1):
        if i > 1:
            time.sleep(SCRAPE_DELAY)
        rows = scrape_metacritic_game(link)
        if not rows:
            continue
        cleaned = rows[0]["link"]
        db = [r for r in db if r["link"] != cleaned]
        db.extend(rows)
        new_rows += len(rows)

    save_db(db)
    print(f"✓ Done. {new_rows} row(s) added or updated.")


# -----------------------------
# Statistics
# -----------------------------
def compute_stats():
    db = load_db()
    if not db:
        print("Database empty.")
        return

    outlets = {}

    for r in db:
        oid = r.get("outlet_id")
        if not oid:
            continue
        name = r.get("outlet")
        if oid not in outlets:
            outlets[oid] = {"name": name, "meta": [], "user": []}
        try:
            ms = float(r["metascore"])
            oscr = float(r["outlet_score"])
        except:
            continue
        outlets[oid]["meta"].append(oscr - ms)
        try:
            us = float(r["user_score"])
            outlets[oid]["user"].append(oscr - us)
        except:
            pass

    table = []
    for oid, val in outlets.items():
        name = val["name"]
        meta_diffs = val["meta"]
        user_diffs = val["user"]
        if not meta_diffs:
            continue
        nb = len(meta_diffs)

        # Bias vs PRO
        abs_meta_avg = stats.mean([abs(x) for x in meta_diffs])
        abs_meta_med = stats.median([abs(x) for x in meta_diffs])
        sd_meta = stats.stdev(meta_diffs) if len(meta_diffs) > 1 else 0.0

        # Bias vs PLAYERS
        if user_diffs:
            abs_user_avg = stats.mean([abs(x) for x in user_diffs])
            abs_user_med = stats.median([abs(x) for x in user_diffs])
            sd_user = stats.stdev(user_diffs) if len(user_diffs) > 1 else 0.0
        else:
            abs_user_avg = abs_user_med = sd_user = None

        table.append({
            "outlet": name,
            "nb_reviews": nb,
            "abs_meta_avg": abs_meta_avg,
            "abs_meta_med": abs_meta_med,
            "sd_meta": sd_meta,
            "abs_user_avg": abs_user_avg,
            "abs_user_med": abs_user_med,
            "sd_user": sd_user
        })

    # -----------------------------
    # GLOBAL SUMMARY (vs PLAYERS)
    # -----------------------------
    all_user_avg = [r["abs_user_avg"] for r in table if r["abs_user_avg"] is not None]
    all_user_med = [r["abs_user_med"] for r in table if r["abs_user_med"] is not None]
    print("\n" + "=" * 120)
    print("GLOBAL SUMMARY [vs PLAYERS]")
    print("=" * 120)
    if all_user_avg:
        mean_all = stats.mean(all_user_avg)
        med_all = stats.median(all_user_med)
        print(f"Average outlet |Bias| vs PLAYERS: {mean_all:+.2f}")
        print(f"Median outlet |Bias| vs PLAYERS: {med_all:+.2f}")
    print(f"Total outlets: {len(table)}")
    print(f"Total reviews: {sum(r['nb_reviews'] for r in table)}")

    # -----------------------------
    # TOP-20 Extremeness & Volatility (vs PLAYERS)
    # -----------------------------
    sorted_by_reviews = sorted(table, key=lambda x: x["nb_reviews"])
    cutoff_index = int(len(sorted_by_reviews) * 0.20)
    filtered_table = sorted_by_reviews[cutoff_index:]

    # Extremeness
    print("\n" + "=" * 120)
    print("EXTREMENESS (avg |Bias|) - Top 20 [vs PLAYERS]")
    print("=" * 120)
    ext_sorted = sorted([r for r in filtered_table if r["abs_user_avg"] is not None],
                        key=lambda x: x["abs_user_avg"], reverse=True)
    print(f"{'Outlet':<30} | {'|x|Avg':>6} | {'|x|Med':>6} | {'SD':>6}")
    print("-" * 60)
    for r in ext_sorted[:20]:
        print(f"{r['outlet'][:30]:<30} | {r['abs_user_avg']:>6.2f} | {r['abs_user_med']:>6.2f} | {r['sd_user']:>6.2f}")
    if ext_sorted:
        top = ext_sorted[0]
        print(f"> '{top['outlet']}' has the biggest gap from player scores: their reviews differ by {top['abs_user_avg']:.1f} points on average. "
              f"Half their reviews are within {top['abs_user_med']:.1f} points of players, half are further away. "
              f"Their consistency varies with a standard deviation of {top['sd_user']:.1f}.")

    # Volatility
    print("\n" + "=" * 120)
    print("VOLATILITY (bias SD) - Top 20 [vs PLAYERS]")
    print("=" * 120)
    vol_sorted = sorted([r for r in filtered_table if r["sd_user"] is not None],
                        key=lambda x: x["sd_user"], reverse=True)
    print(f"{'Outlet':<30} | {'SD':>6}")
    print("-" * 40)
    for r in vol_sorted[:20]:
        print(f"{r['outlet'][:30]:<30} | {r['sd_user']:>6.2f}")
    if vol_sorted:
        top = vol_sorted[0]
        print(f"> '{top['outlet']}' is the most inconsistent compared to players: "
              f"their score differences vary widely, with a standard deviation of {top['sd_user']:.1f} points.")

    # Detailed table
    print("\n" + "=" * 120)
    print("BIAS STATISTICS PER OUTLET")
    print("=" * 120)
    print("Legend: |x|Avg = average absolute bias, |x|Med = median absolute bias, SD = standard deviation")
    print("-" * 120)
    print(f"{'Outlet':<30} | {'Rev':<4} | {'Bias vs PRO':^24} | {'Bias vs PLAYERS':^24} |")
    print(f"{'':30} | {'':<4} | {'|x|Avg':>6} | {'|x|Med':>6} | {'SD':>6} | {'|x|Avg':>6} | {'|x|Med':>6} | {'SD':>6} |")
    print("-" * 120)

    table.sort(key=lambda r: r['nb_reviews'], reverse=True)
    for r in table:
        outlet = r["outlet"][:29]
        nb = r["nb_reviews"]
        meta_avg = f"{r['abs_meta_avg']:.2f}"
        meta_med = f"{r['abs_meta_med']:.2f}"
        sd_meta = f"{r['sd_meta']:.2f}"

        if r["abs_user_avg"] is not None:
            user_avg = f"{r['abs_user_avg']:.2f}"
            user_med = f"{r['abs_user_med']:.2f}"
            sd_user = f"{r['sd_user']:.2f}"
        else:
            user_avg = user_med = sd_user = "N/A"

        print(f"{outlet:<30} | {nb:<4} | {meta_avg:>6} | {meta_med:>6} | {sd_meta:>6} | "
              f"{user_avg:>6} | {user_med:>6} | {sd_user:>6} |")

    if table:
        top = table[0]
        if top["abs_user_avg"] is not None:
            print(f"> '{top['outlet']}' (with the most reviews) differs from player scores by {top['abs_user_avg']:.1f} points on average. "
                  f"The typical difference (median) is {top['abs_user_med']:.1f} points, "
                  f"with a consistency measure (SD) of {top['sd_user']:.1f}.")

    # Save CSV
    csv_filename = f"results_{datetime.now().strftime('%Y-%m-%d')}.csv"
    with open(csv_filename, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["outlet", "nb_reviews",
                      "abs_meta_avg", "abs_meta_med", "sd_meta",
                      "abs_user_avg", "abs_user_med", "sd_user"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(table)
    print(f"\n✓ Detailed stats saved to CSV: {csv_filename}")

# -----------------------------
# Main
# -----------------------------
def main():
    print("\n" + "=" * 60)
    print("    METACRITIC BIAS ANALYZER (Playwright) v3")
    print("=" * 60)
    print("\n1 = Load links file / scrape / update database")
    print("2 = Show statistics per outlet")
    print("3 = Quit")

    choice = input("\nYour choice: ").strip()
    if choice == "1":
        path = input("Path to links file: ").strip()
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
