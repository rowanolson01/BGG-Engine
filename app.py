import streamlit as st
import pandas as pd
import numpy as np
from main import load_data, score_similarity, analyze_market
from export_pdf import build_pdf

st.set_page_config(page_title="BGG Market Intelligence Engine", layout="wide")

# ── Data loading ───────────────────────────────────────────────────────────────
# Cached so the database query and CSV reads only run once per session

@st.cache_data
def get_data():
    """Load the main game dataset and summary stats from SQLite."""
    df, summary = load_data()
    return df, summary

@st.cache_data
def get_column_options():
    """Read column headers from CSVs to populate sidebar multiselects."""
    mechanics = [c for c in pd.read_csv("data/mechanics.csv", nrows=0).columns if c != "BGGId"]
    themes    = [c for c in pd.read_csv("data/themes.csv",    nrows=0).columns if c != "BGGId"]
    subcats   = [c for c in pd.read_csv("data/subcategories.csv", nrows=0).columns if c != "BGGId"]
    return mechanics, themes, subcats

# ── Label helpers ──────────────────────────────────────────────────────────────
# These convert raw numeric values into plain-English labels for display.
# Thresholds are calibrated to BGG's actual rating distribution, not relative rankings.

def stars(lift):
    """Unicode star rating for Streamlit display -- not used in PDF export."""
    if lift >= 0.15: return "★★★★★"
    if lift >= 0.10: return "★★★★☆"
    if lift >= 0.07: return "★★★☆☆"
    if lift >= 0.04: return "★★☆☆☆"
    return "★☆☆☆☆"

def rating_label(median_rating):
    """Absolute BGG rating scale -- 7.0+ is genuinely good in this market."""
    if median_rating >= 8.0: return "Exceptional", "🟢"
    if median_rating >= 7.5: return "Very Strong",  "🟢"
    if median_rating >= 7.0: return "Strong",       "🟢"
    if median_rating >= 6.0: return "Average",      "🟡"
    return                          "Limited",      "🔴"

def owned_label(median_owned):
    """Commercial potential based on median copies owned in comparable pool."""
    if median_owned >= 10000: return "Exceptional", "🟢"
    if median_owned >= 5000:  return "Very Strong",  "🟢"
    if median_owned >= 2000:  return "Strong",       "🟢"
    if median_owned >= 750:   return "Moderate",     "🟡"
    return                           "Limited",      "🔴"

def engagement_label(median_ratings):
    """Engagement potential based on median number of user ratings."""
    if median_ratings >= 5000: return "Exceptional", "🟢"
    if median_ratings >= 2000: return "Very Strong",  "🟢"
    if median_ratings >= 750:  return "Strong",       "🟢"
    if median_ratings >= 250:  return "Average",      "🟡"
    return                            "Limited",      "🔴"

def outlook_components(summary, comparable):
    """
    Builds the four market signal components shown in the hero section.
    Market competition is measured by ownership spread (90th pct / median) --
    a high spread means a few blockbusters dominate and the ceiling is hard to reach.
    """
    r_label, r_icon = rating_label(summary["median_rating"])
    c_label, c_icon = owned_label(summary["projected_owned_med"])
    e_label, e_icon = engagement_label(summary["projected_ratings_med"])

    owned_spread = comparable["NumOwned"].quantile(0.90) / max(comparable["NumOwned"].median(), 1)
    if owned_spread >= 8:   diff_label, diff_icon = "High",   "🔴"
    elif owned_spread >= 4: diff_label, diff_icon = "Medium", "🟡"
    else:                   diff_label, diff_icon = "Low",    "🟢"

    rating_norm = (summary["median_rating"] - 5.0) / (9.0 - 5.0)

    return {
        "rating":     (r_label, r_icon, summary["median_rating"]),
        "commercial": (c_label, c_icon, summary["projected_owned_med"]),
        "engagement": (e_label, e_icon, summary["projected_ratings_med"]),
        "difficulty": (diff_label, diff_icon, round(owned_spread, 1)),
        "rating_norm": rating_norm,
    }

# ── Text generation ────────────────────────────────────────────────────────────

def generate_summary(summary, missing_df, risks_df, numeric_flags, components):
    """
    Builds the plain-English executive summary shown in the Streamlit app.
    Pulls from signals: rating label, commercial label, competition level,
    numeric flag results, feature risks, and the top missing driver.
    """
    lines = []
    pool = summary["pool_size"]

    r_label, _, r_val    = components["rating"]
    c_label, _, c_val    = components["commercial"]
    d_label, _, d_spread = components["difficulty"]

    lines.append(
        f"This concept resembles **{pool} published games**, with a median rating of **{r_val}** "
        f"among comparable titles. Quality potential is **{r_label.lower()}** and commercial "
        f"potential is **{c_label.lower()}**, in a market with **{d_label.lower()}** competition."
    )
    lines.append(
        f"Expected performance places this concept at approximately the "
        f"**{summary['median_rating_percentile']}th percentile** within its comparable market segment."
    )
    lines.append("")

    # Strengths: numeric inputs inside winner IQR + strong rating signal
    strengths = []
    for row in numeric_flags:
        if not row["outside_iqr"]:
            fname = "Complexity" if row["field"] == "GameWeight" else "Playtime"
            strengths.append(f"{fname} aligns closely with successful comparable games (winner median: {row['winner_median']})")
    if r_label in ("Strong", "Very Strong", "Exceptional"):
        strengths.append("Rating potential is strong relative to the broader board game market")
    if strengths:
        lines.append("**Strengths:**")
        for s in strengths:
            lines.append(f"- {s}")
        lines.append("")

    # Concerns: feature risks + numeric inputs outside winner IQR + high competition
    concerns = []
    if not risks_df.empty:
        top_risk = risks_df.iloc[0]
        concerns.append(f"**{top_risk['feature']}** appears more often among lower performers (drag: {top_risk['drag']})")
    for row in numeric_flags:
        if row["outside_iqr"]:
            fname = "Complexity" if row["field"] == "GameWeight" else "Playtime"
            concerns.append(f"{fname} ({row['your_value']}) falls outside the winner range [{row['winner_q1']} – {row['winner_q3']}]")
    if d_label == "High":
        concerns.append("This is a competitive market segment -- top performers capture a disproportionate share of ownership")
    if concerns:
        lines.append("**Primary concerns:**")
        for c in concerns:
            lines.append(f"- {c}")
        lines.append("")

    if not missing_df.empty:
        top = missing_df.iloc[0]
        lines.append(f"**Highest-impact addition:** {top['feature']} (+{round(top['lift']*100,1)}% lift among top performers)")

    return "\n".join(lines)

def generate_advisor(missing_df, risks_df, numeric_flags, components, summary):
    """
    Generates the Design Advisor verdict and prioritized recommendation list.
    Verdict logic: quality signal (median rating >= 7.0) is the primary gate,
    then market difficulty and numeric input flags modify the framing.
    Recommendations are the top 3 missing drivers by lift.
    Concerns are feature risks with drag > 2% plus numeric flags outside IQR.
    """
    d_label, _, _ = components["difficulty"]
    r_label, _, _ = components["rating"]

    high_quality   = summary["median_rating"] >= 7.0
    no_major_risks = risks_df.empty or risks_df["drag"].max() < 0.15
    inputs_ok      = not any(row["outside_iqr"] for row in numeric_flags)

    if high_quality and d_label == "High":
        verdict = "Strong design space entering a competitive market with established flagship titles. Players will likely respond well -- the commercial challenge is real but the creative foundation is solid."
    elif high_quality and no_major_risks and inputs_ok:
        verdict = "Strong concept with favorable signals across the board. Numeric inputs align with winners and no major feature risks detected."
    elif high_quality and not inputs_ok:
        verdict = "Good quality potential, but numeric inputs sit outside the winner range. Adjusting complexity or playtime could improve expected performance."
    elif high_quality:
        verdict = "Above average quality potential. Some feature risks present but nothing severe -- targeted additions could push this into top-performer territory."
    elif r_label == "Average" and d_label != "High":
        verdict = "Solid average concept in an accessible market. Feature additions from the recommendations below could meaningfully differentiate it."
    elif d_label == "High":
        verdict = "Concept faces real headwinds in a crowded market. Consider differentiation through unique mechanics or feature additions."
    else:
        verdict = "Current concept underperforms historical comparables. Mechanical repositioning or targeted feature additions would meaningfully improve expected performance."

    additions = []
    if not missing_df.empty:
        for _, row in missing_df.head(3).iterrows():
            additions.append((row["feature"], row["winner_freq"], row["comp_freq"], row["lift"]))

    concern_lines = []
    if not risks_df.empty:
        for _, row in risks_df[risks_df["drag"] > 0.02].head(2).iterrows():
            concern_lines.append(f"**{row['feature']}** correlates with weaker performers in this segment (drag: {round(row['drag']*100,1)}%)")
    for row in numeric_flags:
        if row["outside_iqr"]:
            fname = "Complexity" if row["field"] == "GameWeight" else "Playtime"
            concern_lines.append(f"**{fname}** ({row['your_value']}) sits outside the range where comparable winners cluster [{row['winner_q1']} – {row['winner_q3']}]")

    return verdict, additions, concern_lines

# ── App init ───────────────────────────────────────────────────────────────────

df, db_summary = get_data()
mechanics_options, themes_options, subcats_options = get_column_options()

# ── Sidebar inputs ─────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Define Your Game Concept")
    selected_mechanics = st.multiselect("Mechanics", mechanics_options)
    selected_themes    = st.multiselect("Themes", themes_options)
    selected_subcats   = st.multiselect("Subcategories", subcats_options)
    st.divider()
    min_players = st.number_input("Min Players", min_value=1, max_value=10, value=2)
    max_players = st.number_input("Max Players", min_value=1, max_value=20, value=4)
    playtime    = st.number_input("Playtime (minutes)", min_value=5, max_value=600, value=90)
    weight      = st.slider("Complexity Weight", min_value=1.0, max_value=5.0, value=3.0, step=0.1)
    top_n       = st.slider("Comparable Pool Size", min_value=50, max_value=500, value=200, step=50)
    st.divider()
    run = st.button("Run Analysis", type="primary", use_container_width=True)

st.title("BGG Market Intelligence Engine")
st.caption(f"Analyzing {db_summary['total_games'].iloc[0]:,} published games · Earliest {db_summary['earliest_year'].iloc[0]} · Latest {db_summary['latest_year'].iloc[0]}")

if not run:
    st.info("Define your game concept in the sidebar and click **Run Analysis** to get started.")
    st.stop()

if not selected_mechanics and not selected_themes:
    st.warning("Enter at least one mechanic or theme to run the analysis.")
    st.stop()

# ── Run engine ─────────────────────────────────────────────────────────────────

concept = {
    "mechanics":   selected_mechanics,
    "themes":      selected_themes + selected_subcats,
    "min_players": min_players,
    "max_players": max_players,
    "playtime":    playtime,
    "weight":      weight,
}

with st.spinner("Scoring similarity across 12,000+ games..."):
    df_scored = score_similarity(df, concept)

summary, comp_table, missing_df, risks_df, numeric_flags, winners, comparable = analyze_market(df_scored, concept, top_n)
flags_list = numeric_flags.to_dict("records")
components = outlook_components(summary, comparable)

r_label, r_icon, r_val       = components["rating"]
c_label, c_icon, c_val       = components["commercial"]
e_label, e_icon, e_val       = components["engagement"]
diff_label, diff_icon, spread = components["difficulty"]

# ── HERO ───────────────────────────────────────────────────────────────────────

st.divider()

pool = summary["pool_size"]
if pool >= 300:   confidence, conf_icon = "High",   "🟢"
elif pool >= 150: confidence, conf_icon = "Medium", "🟡"
else:             confidence, conf_icon = "Low",    "🔴"

st.markdown("## Market Intelligence Report")
st.caption(f"Based on {pool} comparable published games · Confidence: {conf_icon} {confidence}")

h1, h2, h3, h4 = st.columns(4)
h1.metric("Quality Potential",    f"{r_icon} {r_label}",     f"Median rating {r_val}")
h2.metric("Commercial Potential", f"{c_icon} {c_label}",     f"Median {c_val:,} owned")
h3.metric("Engagement Potential", f"{e_icon} {e_label}",     f"Median {e_val:,} ratings")
h4.metric("Market Competition",   f"{diff_icon} {diff_label}", f"Spread: {spread}x")

# ── PDF EXPORT ─────────────────────────────────────────────────────────────────

pdf_buffer = build_pdf(summary, comp_table, missing_df, risks_df, numeric_flags, components, concept)
st.download_button(
    label="📄 Export Report as PDF",
    data=pdf_buffer,
    file_name="bgg_market_report.pdf",
    mime="application/pdf"
)

# ── EXECUTIVE SUMMARY ──────────────────────────────────────────────────────────

st.divider()
st.subheader("Executive Summary")
summary_text = generate_summary(summary, missing_df, risks_df, flags_list, components)
st.markdown(summary_text)

# ── PERFORMANCE RANGE ──────────────────────────────────────────────────────────

st.divider()
st.subheader("Projected Performance Range")

p1, p2, p3 = st.columns(3)

with p1:
    st.markdown("**Rating**")
    st.markdown(f"### {summary['median_rating']}")
    st.caption(f"Likely range: {summary['projected_rating_q25']} – {summary['projected_rating_q75']}")
    st.progress(min(1.0, (summary['median_rating'] - 4.0) / 6.0))

with p2:
    st.markdown("**Copies Owned**")
    st.markdown(f"### {summary['projected_owned_med']:,}")
    st.caption(f"Top 25%: {summary['projected_owned_q75']:,}+  ·  Bottom 25%: <{summary['projected_owned_q25']:,}")
    owned_pct = min(1.0, summary["projected_owned_med"] / max(comparable["NumOwned"].quantile(0.90), 1))
    st.progress(owned_pct)

with p3:
    st.markdown("**User Ratings**")
    st.markdown(f"### {summary['projected_ratings_med']:,}")
    st.caption(f"Top 25%: {summary['projected_ratings_q75']:,}+  ·  Bottom 25%: <{summary['projected_ratings_q25']:,}")
    ratings_pct = min(1.0, summary["projected_ratings_med"] / max(comparable["NumUserRatings"].quantile(0.90), 1))
    st.progress(ratings_pct)

# ── DESIGN ADVISOR ─────────────────────────────────────────────────────────────

st.divider()
st.subheader("Design Advisor")
verdict, additions, concern_lines = generate_advisor(missing_df, risks_df, flags_list, components, summary)
st.markdown(f"**Verdict:** {verdict}")
st.markdown("")

if additions:
    st.markdown("**If you could add one thing:**")
    top = additions[0]
    st.info(
        f"**{top[0]}**\n\n"
        f"Appears in {round(top[1]*100,1)}% of top performers vs {round(top[2]*100,1)}% of comparable games. "
        f"Potential lift: +{round(top[3]*100,1)}%"
    )
    if len(additions) >= 2:
        st.markdown("**If you could add two things:**")
        st.markdown(f"Add **{additions[0][0]}** and **{additions[1][0]}**.")
    if len(additions) >= 3:
        st.markdown("**If you could add three things:**")
        st.markdown(f"Add **{additions[0][0]}**, **{additions[1][0]}**, and **{additions[2][0]}**.")

if concern_lines:
    st.markdown("")
    st.markdown("**Biggest concern:**")
    for c in concern_lines:
        st.markdown(f"- {c}")

# ── RECOMMENDATIONS + RISKS ────────────────────────────────────────────────────

st.divider()
rec_col, risk_col = st.columns(2)

with rec_col:
    st.subheader("Recommended Additions")
    if missing_df.empty:
        st.info("No strong additions detected for this concept.")
    else:
        for _, row in missing_df.iterrows():
            st.markdown(f"**{row['feature']}** {stars(row['lift'])}")
            st.caption(
                f"Appears in {round(row['winner_freq']*100,1)}% of top performers "
                f"vs {round(row['comp_freq']*100,1)}% of comparable games. "
                f"Potential lift: +{round(row['lift']*100,1)}%"
            )

with risk_col:
    st.subheader("Biggest Risks")
    has_risks = False

    if not risks_df.empty:
        feature_risks = risks_df[risks_df["drag"] > 0.02]
        for _, row in feature_risks.iterrows():
            has_risks = True
            st.warning(f"**{row['feature']}** — appears more frequently among lower-performing comparable games ({round(row['drag']*100,1)}% drag)")

    for row in flags_list:
        if row["outside_iqr"]:
            has_risks = True
            fname = "Complexity" if row["field"] == "GameWeight" else "Playtime"
            st.warning(f"**{fname}** — your value of {row['your_value']} falls outside the winner range [{row['winner_q1']} – {row['winner_q3']}] (winner median: {row['winner_median']})")

    if not has_risks:
        st.success("No significant risks detected for this concept.")

# ── NUMERIC FLAGS ──────────────────────────────────────────────────────────────

st.divider()
st.subheader("Numeric Input Check")
n1, n2 = st.columns(2)
for i, row in enumerate(flags_list):
    col = n1 if i == 0 else n2
    fname = "Complexity Weight" if row["field"] == "GameWeight" else "Playtime"
    if row["outside_iqr"]:
        col.warning(f"**{fname}:** {row['your_value']} — outside winner IQR [{row['winner_q1']} – {row['winner_q3']}]")
    else:
        col.success(f"**{fname}:** {row['your_value']} — inside winner IQR [{row['winner_q1']} – {row['winner_q3']}]")

# ── RATING DISTRIBUTION ────────────────────────────────────────────────────────

st.divider()
st.subheader("Rating Distribution of Comparable Games")
st.bar_chart(comparable["AvgRating"].round(1).value_counts().sort_index())

# ── COMPARABLE GAMES ───────────────────────────────────────────────────────────

st.divider()
st.subheader(f"Comparable Games (pool of {summary['pool_size']})")
st.caption("Games most similar to your concept, ranked by similarity score.")
comp_display = comp_table.head(20).copy()
comp_display.columns = ["Name", "Avg Rating", "Owned", "# Ratings", "Similarity"]
comp_display["Owned"]      = comp_display["Owned"].apply(lambda x: f"{int(x):,}")
comp_display["# Ratings"]  = comp_display["# Ratings"].apply(lambda x: f"{int(x):,}")
comp_display["Similarity"] = comp_display["Similarity"].round(3)
comp_display["Avg Rating"] = comp_display["Avg Rating"].round(2)
st.dataframe(comp_display, use_container_width=True, hide_index=True)