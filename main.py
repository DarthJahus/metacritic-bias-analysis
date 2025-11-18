#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Metacritic Bias Analyzer - Version Playwright
- Charge un fichier de liens Metacritic
- Scrape ou met à jour une base CSV locale (avec scrolling dynamique)
- Calcule les biais des outlets vs Metascore et vs UserScore

NOTES:
- Le script nécessite "playwright" et "beautifulsoup4".
- Installation : pip install playwright beautifulsoup4
- Puis : playwright install chromium
- La base est un fichier CSV nommé "metacritic_db.csv".
- Les UserScores (sur 10) sont convertis *10 pour homogénéité.
- Les doublons sont mis à jour, jamais dupliqués.
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
# Utilitaires de base de données
# ------------------------------------------------------------
def load_db():
    """Charge la base de données CSV."""
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_db(rows):
    """Sauvegarde la base de données CSV."""
    with open(DB_FILE, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "link", "metascore", "outlet", "outlet_id", "outlet_score",
            "user_score", "review_count_outlets", "review_count_users"
        ])
        writer.writeheader()
        writer.writerows(rows)


# ------------------------------------------------------------
# Scraping Metacritic avec Playwright
# ------------------------------------------------------------
def clean_link(url: str) -> str:
    """Nettoie un lien Metacritic jusqu'au nom du jeu."""
    base = url.split("?")[0].strip()
    if base.endswith("/"):
        base = base[:-1]
    # Enlève tout après le nom du jeu (critic-reviews, user-reviews, etc.)
    parts = base.split("/")
    if len(parts) >= 5:  # https://www.metacritic.com/game/titre
        base = "/".join(parts[:5])
    return base


def fetch_page_with_playwright(url: str, scroll: bool = False):
    """
    Récupère une page avec Playwright.
    Si scroll=True, scrolle jusqu'à charger tout le contenu dynamique.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Charger la page
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)  # Attendre le rendu initial

            if scroll:
                print(f"  Scrolling automatique en cours...")
                previous_count = 0
                no_change_count = 0
                max_no_change = 3  # Arrêter après 3 scrolls sans changement

                while no_change_count < max_no_change:
                    # Scroll jusqu'en bas
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)  # Attendre le chargement

                    # Compter les reviews
                    current_count = page.locator('div[data-testid="product-review"]').count()

                    if current_count > previous_count:
                        print(f"    → {current_count} reviews chargées")
                        previous_count = current_count
                        no_change_count = 0
                    else:
                        no_change_count += 1

                print(f"  ✓ Scrolling terminé : {previous_count} reviews trouvées")

            html = page.content()
            browser.close()
            return html

    except PlaywrightTimeoutError:
        print(f"  ⚠ Timeout lors du chargement de {url}")
        return None
    except Exception as e:
        print(f"  ⚠ Erreur Playwright : {e}")
        return None


def scrape_metacritic_game(url: str):
    """Scrape la page Metacritic principale + critic-reviews."""
    cleaned = clean_link(url)

    # Page principale pour Metascore et User Score
    print(f"  Récupération de {cleaned}...")
    html_main = fetch_page_with_playwright(cleaned, scroll=False)
    if not html_main:
        return []

    soup_main = BeautifulSoup(html_main, "html.parser")

    # Extraction du Metascore - cherche dans la section avec data-testid="critic-path"
    metascore = None
    review_count_outlets = None

    # Méthode : via le lien critic-path
    critic_link = soup_main.find("a", attrs={"data-testid": "critic-path"})
    if critic_link:
        # Nombre de reviews
        reviews_text = critic_link.get_text(strip=True)
        import re
        match = re.search(r'(\d+)', reviews_text)
        if match:
            review_count_outlets = int(match.group(1))

        # Le metascore est dans le même bloc parent
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

    # Extraction du User Score
    user_score = None
    review_count_users = None
    user_link = soup_main.find("a", attrs={"data-testid": "user-path"})
    if user_link:
        # Nombre de user reviews
        reviews_text = user_link.get_text(strip=True)
        import re
        match = re.search(r'([\d,]+)', reviews_text)
        if match:
            review_count_users = int(match.group(1).replace(',', ''))

        # Le user score est dans le même bloc parent
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
                                user_score = float(score_text) * 10  # Conversion sur 100
                        except ValueError:
                            pass

    print(
        f"  Metascore: {metascore}, User Score: {user_score}, Reviews: {review_count_outlets} critics / {review_count_users} users")

    # Scrape critic-reviews page AVEC SCROLLING
    critic_url = cleaned.rstrip("/") + "/critic-reviews/"
    print(f"  Récupération des reviews: {critic_url}...")
    html_crit = fetch_page_with_playwright(critic_url, scroll=True)
    if not html_crit:
        return []

    soup_crit = BeautifulSoup(html_crit, "html.parser")

    # Extraction des reviews individuelles
    reviews = soup_crit.find_all("div", attrs={"data-testid": "product-review"})
    rows = []

    print(f"  Traitement de {len(reviews)} review(s)...")

    for review_block in reviews:
        # Outlet name et ID
        outlet_link = review_block.find("a", class_="c-siteReviewHeader_publicationName")
        if not outlet_link:
            continue

        outlet_name = outlet_link.get_text(strip=True)
        href = outlet_link.get("href", "")
        outlet_id = None
        if "/publication/" in href:
            outlet_id = href.split("/publication/")[-1].strip("/")

        # Score de l'outlet - cherche d'abord si c'est TBD
        score_div = review_block.find("div", class_="c-siteReviewScore")
        if not score_div:
            continue

        score_span = score_div.find("span", attrs={"data-v-e408cafe": ""})
        if not score_span:
            continue

        score_text = score_span.get_text(strip=True).lower()

        # Ignorer les reviews TBD
        if score_text == "tbd":
            print(f"    ⊘ {outlet_name}: score TBD, ignoré")
            continue

        try:
            outlet_score = int(score_text)
        except ValueError:
            print(f"    ⚠ {outlet_name}: score invalide '{score_text}', ignoré")
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

    print(f"  ✓ {len(rows)} review(s) valide(s) extraite(s)")
    return rows


# ------------------------------------------------------------
# Mise à jour base avec de nouveaux liens
# ------------------------------------------------------------
def update_from_links_file(file_path: str):
    """Charge un fichier de liens et met à jour la base."""
    db = load_db()
    new_rows_count = 0

    links = list()
    with open(file_path, encoding="utf-8") as f:
        for l in f.readlines():
            if l.strip() and l.strip() not in links:
                links.append(l.strip())
            else:
                print(f"Ligne ignorée : {l.strip('\n')}")

    print(f"\n{len(links)} lien(s) à traiter.\n")

    for i, link in enumerate(links, 1):
        print(f"[{i}/{len(links)}] Traitement de {link}")

        # Delay entre les scrapes
        if i > 1:
            time.sleep(SCRAPE_DELAY)

        rows = scrape_metacritic_game(link)
        if not rows:
            print("  ⚠ Aucune donnée récupérée.\n")
            continue

        cleaned = rows[0]["link"]

        # Suppression des anciennes entrées du même jeu
        old_count = len(db)
        db = [r for r in db if r["link"] != cleaned]
        removed = old_count - len(db)

        if removed > 0:
            print(f"  ✓ {removed} ancienne(s) entrée(s) supprimée(s).")

        # Ajout des nouvelles entrées
        db.extend(rows)
        new_rows_count += len(rows)
        print(f"  ✓ {len(rows)} review(s) ajoutée(s).\n")

    save_db(db)
    print(f"✓ Terminé. {new_rows_count} ligne(s) ajoutée(s) ou mise(s) à jour.")


# ------------------------------------------------------------
# Statistiques par outlet
# ------------------------------------------------------------
def compute_stats():
    """Calcule et affiche les statistiques de biais par outlet."""
    db = load_db()
    if not db:
        print("Base vide.")
        return

    outlets = {}
    for r in db:
        outlet_id = r.get("outlet_id")
        outlet_name = r.get("outlet")

        # On utilise outlet_id comme clé unique
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

        # Outlet vs Metascore
        outlets[outlet_id]["meta"].append(oscr - ms)

        # Outlet vs UserScore
        try:
            us = float(r["user_score"])
            outlets[outlet_id]["user"].append(oscr - us)
        except (ValueError, TypeError):
            pass

    # Tri par nombre de reviews (pour afficher les plus actifs d'abord)
    sorted_outlets = sorted(
        outlets.items(),
        key=lambda x: len(x[1]["meta"]),
        reverse=True
    )

    # Préparation des données pour le tableau
    table_data = []
    for outlet_id, values in sorted_outlets:
        meta_diffs = values["meta"]
        user_diffs = values["user"]
        outlet_name = values["name"]

        if not meta_diffs:
            continue

        # Calcul des stats
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

    # Affichage du tableau
    print("\n" + "=" * 120)
    print("STATISTIQUES DES BIAIS PAR OUTLET")
    print("=" * 120)
    print(f"{'Outlet':<30} | {'Nbr':<4} | {'Biais vs PRO':^21} | {'Biais vs Joueurs':^21} |")
    print(f"{'':30} | {'Rev':<4} | {'Moy':>9} | {'Méd':>9} | {'Moy':>9} | {'Méd':>9} |")
    print("-" * 120)

    # Calcul du seuil du 90e centile AVANT l'affichage
    user_means_for_threshold = [r['user_mean'] for r in table_data if r['user_mean'] is not None]
    threshold_90 = None
    if user_means_for_threshold:
        user_means_abs = sorted([abs(x) for x in user_means_for_threshold], reverse=True)
        percentile_90_idx = int(len(user_means_abs) * 0.1)
        threshold_90 = user_means_abs[percentile_90_idx] if percentile_90_idx < len(user_means_abs) else user_means_abs[
            -1]

    # Codes ANSI pour couleur rouge
    RED = '\033[91m'
    RESET = '\033[0m'

    for row in table_data:
        outlet = row["outlet"][:29]  # Tronque si trop long
        nb = row["nb_reviews"]
        meta_m = f"{row['meta_mean']:+.2f}"
        meta_med = f"{row['meta_median']:+.2f}"

        if row["user_mean"] is not None:
            user_m_val = row['user_mean']
            # Colorer en rouge si dans le 90e centile
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

    # Calcul des statistiques globales
    all_meta_means = [r['meta_mean'] for r in table_data]
    all_user_means = [r['user_mean'] for r in table_data if r['user_mean'] is not None]

    print(f"\n{'STATISTIQUES GLOBALES':^120}")
    print("-" * 120)

    if all_meta_means:
        global_meta_mean = stats.mean(all_meta_means)
        global_meta_std = stats.stdev(all_meta_means) if len(all_meta_means) > 1 else 0
        print(f"Biais moyen des outlets vs PRO      : {global_meta_mean:+.2f} (écart-type: {global_meta_std:.2f})")

    if all_user_means:
        global_user_mean = stats.mean(all_user_means)
        global_user_std = stats.stdev(all_user_means) if len(all_user_means) > 1 else 0
        print(f"Biais moyen des outlets vs JOUEURS  : {global_user_mean:+.2f} (écart-type: {global_user_std:.2f})")

    print(f"\nTotal outlets: {len(table_data)} | Total reviews analysées: {sum(r['nb_reviews'] for r in table_data)}")
    print("\nLégende: Biais positif = outlet note plus haut | Biais négatif = outlet note plus bas")
    print("=" * 120)

    # Calcul du 90e centile pour le biais vs Joueurs
    if all_user_means:
        # Trier les biais (valeurs absolues pour trouver les plus extrêmes)
        user_means_abs = sorted([abs(x) for x in all_user_means], reverse=True)
        percentile_90_idx = int(len(user_means_abs) * 0.1)  # Top 10%
        threshold_90 = user_means_abs[percentile_90_idx] if percentile_90_idx < len(user_means_abs) else user_means_abs[
            -1]

        # Filtrer les outlets dans le 90e centile
        top_10_biased = [
            row for row in table_data
            if row['user_mean'] is not None and row["nb_reviews"] > 20 and abs(row['user_mean']) >= threshold_90
        ]

        # Trier par biais absolu décroissant
        top_10_biased.sort(key=lambda x: abs(x['user_mean']), reverse=True)

        if top_10_biased:
            print("\n" + "=" * 120)
            print("OUTLETS DANS LE 90e CENTILE - BIAIS VS JOUEURS (Top 10% les plus biaisés, avec plus de 20 reviews)")
            print("=" * 120)
            print(f"{'Outlet':<30} | {'Nbr':<4} | {'Biais Moy vs Joueurs':>21} | {'Type de biais':<15} |")
            print(f"{'':30} | {'Rev':<4} | {'':>21} | {'':^15} |")
            print("-" * 120)

            for row in top_10_biased:
                outlet = row["outlet"][:29]
                nb = row["nb_reviews"]
                user_m = row['user_mean']
                bias_type = "Plus généreux" if user_m > 0 else "Plus sévère"

                print(f"{outlet:<30} | {nb:<4} | {user_m:>+21.2f} | {bias_type:<15} |")

            print("=" * 120)
            print(f"Seuil du 90e centile : {threshold_90:.2f} points de différence")
            print("=" * 120)


# ------------------------------------------------------------
# Menu principal
# ------------------------------------------------------------
def main():
    print("\n" + "=" * 60)
    print("    METACRITIC BIAS ANALYZER (Playwright)")
    print("=" * 60)
    print("\n1 = Charger fichier de liens / scraper / mettre à jour base")
    print("2 = Afficher statistiques par outlet")
    print("3 = Quitter")
    choice = input("\nVotre choix : ").strip()

    if choice == "1":
        path = input("\nChemin du fichier de liens : ").strip()
        if os.path.exists(path):
            update_from_links_file(path)
        else:
            print(f"❌ Fichier introuvable : {path}")
    elif choice == "2":
        compute_stats()
    elif choice == "3":
        print("Au revoir !")
    else:
        print("❌ Choix invalide.")


if __name__ == "__main__":
    main()
