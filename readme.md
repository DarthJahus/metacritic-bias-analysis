# Metacritic Bias Analysis

Analyze biases of game review outlets vs Metascore and User Scores on Metacritic.

## Features
- Scrape Metacritic critic and user reviews (dynamic scrolling included)
- Store reviews in a local CSV database (`metacritic_db.csv`)
- Compute outlet biases vs professional reviews and player scores
- Highlight top 10% most biased outlets vs players

## Requirements
- Python 3.10+
- Packages:
  ```bash
  pip install playwright beautifulsoup4
  playwright install chromium
  ```

## Usage
```bash
python main.py
```
1. **Scrape or update database** from a text file with Metacritic game links: Select option `1` and provide the path to your links file.
2. **Show bias statistics**: Run the script and select option `2`.

## Notes
* User Scores (out of 10) are converted to a 0–100 scale.
* Duplicate reviews are updated, never duplicated.
* Positive bias = outlet rates higher than the reference score; negative bias = lower.

## Results
As of `2025-11-18`, **11646 reviews analyzed**.

```
                     GLOBAL STATISTICS
----------------------------------------------------------------
Average outlet bias vs PRO      :  +0.09 (std: 4.07)
Average outlet bias vs PLAYERS  : +14.50 (std: 9.04)

                   Total outlets:   507
          Total reviews analyzed: 11646
===============================================================
          TOP 10% MOST BIASED OUTLETS VS. PLAYERS
===============================================================
Outlet                         | Rev  | Avg Bias vs Players   |
---------------------------------------------------------------
Forbes                         | 27   |                +40.85 |
The Games Machine              | 92   |                +31.08 |
Hobby Consolas                 | 80   |                +30.57 |
God is a Geek                  | 88   |                +30.15 |
Ragequit.gr                    | 22   |                +30.14 |
Impulsegamer                   | 91   |                +30.05 |
Atomix                         | 62   |                +29.45 |
Digital Chumps                 | 81   |                +29.42 |
Gamersky                       | 54   |                +28.83 |
PlayStation LifeStyle          | 53   |                +28.66 |
PSX Brasil                     | 39   |                +28.54 |
LevelUp                        | 51   |                +28.35 |
Playstation Official Magazine  | 37   |                +28.30 |
LaPS4                          | 27   |                +28.15 |
Jeuxvideo.com                  | 109  |                +27.85 |
Twinfinite                     | 73   |                +27.74 |
GameSpace                      | 28   |                +27.43 |
GAMES.CH                       | 50   |                +27.40 |
Daily Star                     | 30   |                +27.40 |
Windows Central                | 27   |                +27.30 |
IGN Italia                     | 102  |                +27.05 |
3DJuegos                       | 49   |                +26.98 |
Player 2                       | 33   |                +26.94 |
Softpedia                      | 48   |                +26.94 |
MeuPlayStation                 | 36   |                +26.89 |
Areajugones                    | 58   |                +26.72 |
Attack of the Fanboy           | 42   |                +26.71 |
TierraGamer                    | 43   |                +26.67 |
Gamers' Temple                 | 26   |                +26.50 |
VG247                          | 34   |                +26.00 |
Critical Hit                   | 29   |                +26.00 |
TrueGaming                     | 26   |                +25.92 |
===============================================================
90th percentile threshold : 25.70 points difference
===============================================================
```
