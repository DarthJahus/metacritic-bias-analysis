# Metacritic Bias Analysis

Analyze biases of game review outlets compared to Metascore and User Scores on Metacritic.

## Features
- Scrape Metacritic critic and user reviews (dynamic scrolling included)
- Store reviews in a local CSV database (`metacritic_db.csv`)
- Compute outlet biases vs professional reviews (Metascore) and player scores
- Statistical analysis including:
  - **Average absolute bias**: Mean difference from reference scores
  - **Median absolute bias**: Typical (middle) difference from reference scores
  - **Standard deviation**: Consistency measure (how widely scores vary)
- Identify outlets with extreme bias and high volatility
- Filter analysis to top 80% of outlets by review count (excludes low-volume outliers)

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
2. **Show bias statistics**: Select option `2` to generate comprehensive bias analysis.

## Understanding the Metrics

- **|x|Avg (Average Absolute Bias)**: How far outlet scores differ from the reference on average
- **|x|Med (Median Absolute Bias)**: The typical difference — half of reviews differ by less, half by more
- **SD (Standard Deviation)**: Measures consistency — lower values mean more predictable scoring patterns

**Extremeness**: Outlets with the highest average absolute bias (consistently far from player scores)  
**Volatility**: Outlets with the highest standard deviation (most unpredictable scoring)

## Notes
- User Scores (out of 10) are converted to a 0–100 scale for comparison
- Duplicate reviews are updated, never duplicated
- Positive bias = outlet rates higher than the reference score; negative bias = lower
- Analysis excludes the bottom 20% of outlets by review count to focus on established reviewers

## Results
As of `2025-11-22`, **15432 reviews analyzed**.

See [results.latest.txt](results.latest.txt) and [results_latest.csv](results_latest.csv).
