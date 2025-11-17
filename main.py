#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Metacritic Bias Analyzer
- Charge un fichier de liens Metacritic
- Scrape ou met à jour une base CSV locale
- Calcule les biais des outlets vs Metascore et vs UserScore

NOTES:
- Le script nécessite "requests" et "beautifulsoup4".
- La base est un fichier CSV nommé "metacritic_db.csv".
- Les UserScores (sur 10) sont convertis *10 pour homogénéité.
- Les doublons sont mis à jour, jamais dupliqués.
"""

import csv
import os
import statistics as stats
from bs4 import BeautifulSoup
import requests
import time

SCRAPE_DELAY = 3
MAX_RETRIES = 3
RETRY_DELAY = 3

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
# Scraping Metacritic
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


def fetch_with_retry(url: str, headers: dict, max_retries: int = MAX_RETRIES) -> str:
    """Récupère une URL avec retry en cas d'échec."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"  Tentative {attempt + 1}/{max_retries} échouée: {e}")
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
            else:
                print(f"  Échec après {max_retries} tentatives.")
                return None


def scrape_metacritic_game(url: str):
    """Scrape la page Metacritic principale + critic-reviews."""
    cleaned = clean_link(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    # Page principale pour Metascore et User Score
    print(f"  Récupération de {cleaned}...")
    html_main = fetch_with_retry(cleaned, headers)
    if not html_main:
        return []

    soup_main = BeautifulSoup(html_main, "html.parser")

    # Extraction du Metascore - cherche dans la section avec data-testid="critic-path"
    metascore = None
    review_count_outlets = None

    # Méthode 1 : via le lien critic-path
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

    print(f"  Metascore: {metascore}, User Score: {user_score}, Reviews: {review_count_outlets} critics / {review_count_users} users")

    # Scrape critic-reviews page
    critic_url = cleaned.rstrip("/") + "/critic-reviews/"
    print(f"  Récupération des reviews: {critic_url}...")
    html_crit = fetch_with_retry(critic_url, headers)
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

    for row in table_data:
        outlet = row["outlet"][:29]  # Tronque si trop long
        nb = row["nb_reviews"]
        meta_m = f"{row['meta_mean']:+.2f}"
        meta_med = f"{row['meta_median']:+.2f}"

        if row["user_mean"] is not None:
            user_m = f"{row['user_mean']:+.2f}"
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


# ------------------------------------------------------------
# Menu principal
# ------------------------------------------------------------
def main():
    print("\n" + "=" * 60)
    print("    METACRITIC BIAS ANALYZER")
    print("=" * 60)
    print("\n1 = Charger fichier de liens / scraper / mettre à jour base")
    print("2 = Afficher statistiques par outlet")
    print("3 = Tester le parsing sur un fichier HTML local")
    print("4 = Quitter")
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
        test_html_parsing()
    elif choice == "4":
        print("Au revoir !")
    else:
        print("❌ Choix invalide.")


def test_html_parsing():
    """Test le parsing sur un fichier HTML local."""
    path = input("\nChemin du fichier HTML à tester : ").strip()
    if not os.path.exists(path):
        print(f"❌ Fichier introuvable : {path}")
        return

    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")

    print("\n" + "=" * 60)
    print("TEST DE PARSING HTML")
    print("=" * 60)

    # Test extraction reviews
    reviews = soup.find_all("div", attrs={"data-testid": "product-review"})
    print(f"\n✓ {len(reviews)} reviews trouvées\n")

    for i, review_block in enumerate(reviews[:5], 1):  # Affiche les 5 premières
        outlet_link = review_block.find("a", class_="c-siteReviewHeader_publicationName")
        if outlet_link:
            outlet_name = outlet_link.get_text(strip=True)
            href = outlet_link.get("href", "")
            outlet_id = href.split("/publication/")[-1].strip("/") if "/publication/" in href else "N/A"

            score_div = review_block.find("div", class_="c-siteReviewScore")
            if score_div:
                score_span = score_div.find("span", attrs={"data-v-e408cafe": ""})
                score = score_span.get_text(strip=True) if score_span else "N/A"
            else:
                score = "N/A"

            print(f"{i}. {outlet_name}")
            print(f"   ID: {outlet_id}")
            print(f"   Score: {score}\n")

    if len(reviews) > 5:
        print(f"... et {len(reviews) - 5} autre(s) review(s)\n")


if __name__ == "__main__":
    main()