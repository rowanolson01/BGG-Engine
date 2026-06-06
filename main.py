import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB_PATH = Path("data/bgg.db")

# ── Database utilities ─────────────────────────────────────────────────────────

def load_query(filename):
    """Read a .sql file and return the query string. utf-8-sig strips Windows BOM."""
    with open(filename, "r", encoding="utf-8-sig") as f:
        return f.read().strip()

def load_data():
    """
    Connect to SQLite, run the summary and main queries, return both as DataFrames.
    query_main.sql joins games + mechanics + themes + subcategories and filters
    on NumUserRatings >= 50, NumOwned >= 100, and YearPublished >= 1950.
    """
    conn = sqlite3.connect(DB_PATH)
    summary = pd.read_sql_query(load_query("query_summary.sql"), conn)
    df      = pd.read_sql_query(load_query("query_main.sql"),    conn)
    conn.close()
    return df, summary

# ── Similarity engine ──────────────────────────────────────────────────────────

def score_similarity(df, concept):
    """
    Scores every game in the dataset against a proposed concept.
    Returns the full DataFrame sorted by similarity_score descending.

    Similarity is a weighted combination of:
      - Jaccard similarity on mechanics (50%)
      - Jaccard similarity on themes/categories (15%)
      - Normalized distance on complexity weight (15%)
      - Normalized distance on playtime (10%)
      - Player count overlap (10%)

    Jaccard is computed via matrix multiplication across the full dataset
    at once (vectorized) rather than row-by-row, keeping runtime under 1s.
    """
    df = df.copy()

    # Identify mechanic and theme columns by reading CSV headers
    mechanics_ref = pd.read_csv("data/mechanics.csv", nrows=0).columns.tolist()
    themes_ref    = pd.read_csv("data/themes.csv",    nrows=0).columns.tolist()

    mechanic_cols = [c for c in mechanics_ref if c != "BGGId" and c in df.columns]
    theme_cols    = [c for c in themes_ref    if c != "BGGId" and c in df.columns]

    def vectorized_jaccard(df_binary, concept_features, all_cols):
        """
        Computes Jaccard similarity between the concept and every row in df_binary.
        Jaccard = |intersection| / |union|
        Uses matrix multiplication: intersection = binary_matrix @ concept_vector
        """
        concept_vec = pd.Series(0, index=all_cols)
        valid = [f for f in concept_features if f in all_cols]
        concept_vec[valid] = 1
        intersection = df_binary[all_cols].values @ concept_vec.values
        game_sums    = df_binary[all_cols].sum(axis=1).values
        concept_sum  = concept_vec.sum()
        union        = game_sums + concept_sum - intersection
        return pd.Series(np.where(union == 0, 0, intersection / union), index=df.index)

    def numeric_sim(series, target, range_val):
        """Normalized distance: 1 = identical, 0 = opposite ends of the range."""
        if range_val == 0:
            return pd.Series(1.0, index=series.index)
        return 1 - (series - target).abs() / range_val

    def player_overlap(df, concept_min, concept_max):
        """Proportion of player count range that overlaps with the concept range."""
        overlap = (df["MaxPlayers"].clip(upper=concept_max) - df["MinPlayers"].clip(lower=concept_min)).clip(lower=0)
        span = df.apply(lambda r: max(r["MaxPlayers"], concept_max) - min(r["MinPlayers"], concept_min), axis=1)
        return np.where(span == 0, 1.0, overlap / span)

    df["sim_mechanics"] = vectorized_jaccard(df, set(concept["mechanics"]), mechanic_cols)
    df["sim_themes"]    = vectorized_jaccard(df, set(concept["themes"]),    theme_cols)

    weight_range   = df["GameWeight"].max()  - df["GameWeight"].min()
    playtime_range = df["MfgPlaytime"].max() - df["MfgPlaytime"].min()

    df["sim_weight"]   = numeric_sim(df["GameWeight"],  concept["weight"],   weight_range)
    df["sim_playtime"] = numeric_sim(df["MfgPlaytime"], concept["playtime"], playtime_range)
    df["sim_players"]  = player_overlap(df, concept["min_players"], concept["max_players"])

    df["similarity_score"] = (
        df["sim_mechanics"] * 0.50 +
        df["sim_themes"]    * 0.15 +
        df["sim_weight"]    * 0.15 +
        df["sim_playtime"]  * 0.10 +
        df["sim_players"]   * 0.10
    )

    return df.sort_values("similarity_score", ascending=False)

# ── Market analysis ────────────────────────────────────────────────────────────

def analyze_market(df, concept, top_n=200):
    """
    Takes the similarity-scored DataFrame and a concept dict, returns all
    data structures needed to render the report.

    Steps:
    1. Take top_n most similar games as the comparable pool.
    2. Score each comparable on a blended success metric (rating + owned + ratings).
    3. Split into winners (top 25%) and bottom (bottom 25%) by success score.
    4. Identify negative risks: concept features overrepresented in bottom vs winners.
    5. Identify positive missing drivers: non-concept features with positive lift
       in winners vs all comparables. Excludes features already flagged as risks.
    6. Check numeric inputs (weight, playtime) against winner IQR.
    7. Return summary dict, comp table, missing drivers, risks, numeric flags,
       winners DataFrame, and full comparable DataFrame.
    """
    comparable = df.head(top_n).copy()

    # Blended success score: rewards games that are both well-rated AND widely owned
    comparable["log_ratings"] = np.log1p(comparable["NumUserRatings"])
    comparable["log_owned"]   = np.log1p(comparable["NumOwned"])

    def normalize(series):
        mn, mx = series.min(), series.max()
        return (series - mn) / (mx - mn + 1e-9)

    comparable["norm_rating"]      = normalize(comparable["AvgRating"])
    comparable["norm_log_ratings"] = normalize(comparable["log_ratings"])
    comparable["norm_log_owned"]   = normalize(comparable["log_owned"])
    comparable["success_score"]    = (
        comparable["norm_rating"]      * 0.40 +
        comparable["norm_log_owned"]   * 0.40 +
        comparable["norm_log_ratings"] * 0.20
    )

    cutoff_top = comparable["success_score"].quantile(0.75)
    cutoff_bot = comparable["success_score"].quantile(0.25)
    winners = comparable[comparable["success_score"] >= cutoff_top]
    bottom  = comparable[comparable["success_score"] <  cutoff_bot]

    # Identify all feature columns across mechanics, themes, and subcategories
    mechanics_ref = pd.read_csv("data/mechanics.csv",     nrows=0).columns.tolist()
    themes_ref    = pd.read_csv("data/themes.csv",        nrows=0).columns.tolist()
    subcats_ref   = pd.read_csv("data/subcategories.csv", nrows=0).columns.tolist()

    mechanic_cols    = [c for c in mechanics_ref if c != "BGGId" and c in comparable.columns]
    theme_cols       = [c for c in themes_ref    if c != "BGGId" and c in comparable.columns]
    subcat_cols      = [c for c in subcats_ref   if c != "BGGId" and c in comparable.columns]
    all_feature_cols = mechanic_cols + theme_cols + subcat_cols
    concept_features = set(concept["mechanics"] + concept["themes"])

    # Risks: concept features more common in bottom performers than winners
    # Built first so we can exclude them from recommendations (no contradictions)
    risks = []
    for col in all_feature_cols:
        if col not in concept_features:
            continue
        winner_freq = winners[col].mean()
        bottom_freq = bottom[col].mean()
        if bottom_freq > winner_freq:
            risks.append({
                "feature":     col,
                "winner_freq": round(winner_freq, 3),
                "bottom_freq": round(bottom_freq, 3),
                "drag":        round(bottom_freq - winner_freq, 3)
            })

    risks_df = pd.DataFrame(risks).sort_values("drag", ascending=False) if risks else pd.DataFrame(columns=["feature","winner_freq","bottom_freq","drag"])
    risk_features = set(risks_df["feature"].tolist()) if not risks_df.empty else set()

    # Missing positive drivers: features not in concept, not already flagged as risks,
    # with positive lift (more common in winners than comparables overall)
    missing = []
    for col in all_feature_cols:
        if col in concept_features:
            continue
        if col in risk_features:
            continue
        winner_freq = winners[col].mean()
        comp_freq   = comparable[col].mean()
        lift        = winner_freq - comp_freq
        if lift > 0 and winner_freq >= 0.10:
            missing.append({
                "feature":     col,
                "winner_freq": round(winner_freq, 3),
                "comp_freq":   round(comp_freq, 3),
                "lift":        round(lift, 3)
            })

    missing_df = pd.DataFrame(missing).sort_values("lift", ascending=False).head(10) if missing else pd.DataFrame()

    # Numeric flags: check concept weight and playtime against winner IQR
    numeric_flags = []
    for field, concept_val in [("GameWeight", concept["weight"]), ("MfgPlaytime", concept["playtime"])]:
        w_median = winners[field].median()
        w_q1     = winners[field].quantile(0.25)
        w_q3     = winners[field].quantile(0.75)
        outside  = not (w_q1 <= concept_val <= w_q3)
        numeric_flags.append({
            "field":         field,
            "your_value":    concept_val,
            "winner_median": round(w_median, 1),
            "winner_q1":     round(w_q1, 1),
            "winner_q3":     round(w_q3, 1),
            "outside_iqr":   outside
        })

    # Summary dict: all projected performance metrics used by the UI and PDF
    summary = {
        "pool_size":             len(comparable),
        "avg_rating":            round(comparable["AvgRating"].mean(), 2),
        "median_rating":         round(comparable["AvgRating"].median(), 2),
        "avg_rated":             int(comparable["NumUserRatings"].mean()),
        "median_rated":          int(comparable["NumUserRatings"].median()),
        "avg_owned":             int(comparable["NumOwned"].mean()),
        "winner_count":          len(winners),
        "winner_avg_rating":     round(winners["AvgRating"].mean(), 2),
        "projected_rating_q25":  round(comparable["AvgRating"].quantile(0.25), 2),
        "projected_rating_q75":  round(comparable["AvgRating"].quantile(0.75), 2),
        "projected_owned_med":   int(comparable["NumOwned"].median()),
        "projected_owned_q25":   int(comparable["NumOwned"].quantile(0.25)),
        "projected_owned_q75":   int(comparable["NumOwned"].quantile(0.75)),
        "projected_ratings_med": int(comparable["NumUserRatings"].median()),
        "projected_ratings_q25": int(comparable["NumUserRatings"].quantile(0.25)),
        "projected_ratings_q75": int(comparable["NumUserRatings"].quantile(0.75)),
        # Percentile of median rating within the comparable pool (anchor for the executive summary)
        "median_rating_percentile": round((comparable["AvgRating"] <= comparable["AvgRating"].median()).mean() * 100),
    }

    comp_table = comparable[["Name","AvgRating","NumOwned","NumUserRatings","similarity_score"]].copy()

    return summary, comp_table, missing_df, risks_df, pd.DataFrame(numeric_flags), winners, comparable