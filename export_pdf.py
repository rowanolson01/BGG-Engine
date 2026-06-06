from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
import io

def build_pdf(summary, comp_table, missing_df, risks_df, numeric_flags, components, concept):
    """
    Builds a 3-page PDF report from engine output.
    Page 1: Concept + Market Signals + Executive Summary + Performance Range
    Page 2: Design Advisor + Recommended Additions + Biggest Risks
    Page 3: Comparable Games table
    Returns a BytesIO buffer ready for Streamlit download.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )

    # --- Type styles ---
    title_style    = ParagraphStyle("title",    fontSize=22, fontName="Helvetica-Bold", spaceAfter=4, spaceBefore=0, leading=26)
    subtitle_style = ParagraphStyle("subtitle", fontSize=9,  fontName="Helvetica", textColor=colors.grey, spaceAfter=14, spaceBefore=0)
    h2_style       = ParagraphStyle("h2",       fontSize=13, fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=5)
    h3_style       = ParagraphStyle("h3",       fontSize=10, fontName="Helvetica-Bold", spaceBefore=5,  spaceAfter=2)
    body_style     = ParagraphStyle("body",     fontSize=9,  fontName="Helvetica", spaceAfter=4, leading=14)
    caption_style  = ParagraphStyle("caption",  fontSize=8,  fontName="Helvetica", textColor=colors.grey, spaceAfter=4)
    bullet_style   = ParagraphStyle("bullet",   fontSize=9,  fontName="Helvetica", leftIndent=14, spaceAfter=3, leading=13)
    impact_style   = ParagraphStyle("impact",   fontSize=8,  fontName="Helvetica-Bold", textColor=colors.HexColor("#2d6a4f"), spaceAfter=0)

    def hr():
        return HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=8, spaceBefore=8)

    def impact_label(lift):
        # Converts raw lift value into a plain-English impact tier for the recommendations table
        if lift >= 0.15: return "Transformative"
        if lift >= 0.10: return "Recommended"
        if lift >= 0.07: return "Worth Considering"
        if lift >= 0.04: return "Low Priority"
        return "Minimal Signal"

    def kpi_table(rows):
        # 4-column header table used for the market signals section
        t = Table(rows, colWidths=[1.7*inch]*4)
        t.setStyle(TableStyle([
            ("FONTNAME",     (0,0), (-1,0),  "Helvetica"),
            ("FONTSIZE",     (0,0), (-1,0),  8),
            ("TEXTCOLOR",    (0,0), (-1,0),  colors.grey),
            ("FONTNAME",     (0,1), (-1,1),  "Helvetica-Bold"),
            ("FONTSIZE",     (0,1), (-1,1),  12),
            ("FONTNAME",     (0,2), (-1,2),  "Helvetica"),
            ("FONTSIZE",     (0,2), (-1,2),  8),
            ("TEXTCOLOR",    (0,2), (-1,2),  colors.grey),
            ("ALIGN",        (0,0), (-1,-1), "LEFT"),
            ("VALIGN",       (0,0), (-1,-1), "TOP"),
            ("BOTTOMPADDING",(0,0), (-1,-1), 6),
        ]))
        return t

    # --- Unpack components and concept ---
    r_label, r_icon, r_val        = components["rating"]
    c_label, c_icon, c_val        = components["commercial"]
    e_label, e_icon, e_val        = components["engagement"]
    diff_label, diff_icon, spread  = components["difficulty"]
    r_l, _, _ = components["rating"]
    c_l, _, _ = components["commercial"]
    d_l, _, _ = components["difficulty"]

    pool = summary["pool_size"]
    confidence = "High" if pool >= 300 else "Medium" if pool >= 150 else "Low"

    mechanics_str = ", ".join(concept["mechanics"]) if concept["mechanics"] else "None"
    themes_str    = ", ".join(concept["themes"])    if concept["themes"]    else "None"
    players_str   = f"{concept['min_players']}-{concept['max_players']}"
    playtime_str  = f"{concept['playtime']} min"
    weight_str    = str(concept["weight"])

    flags_list = numeric_flags.to_dict("records")

    # --- Generate verdict text based on quality + risk + input signals ---
    high_quality   = summary["median_rating"] >= 7.0
    no_major_risks = risks_df.empty or risks_df["drag"].max() < 0.15
    inputs_ok      = not any(row["outside_iqr"] for row in flags_list)

    if high_quality and d_l == "High":
        verdict = "Strong design space entering a competitive market with established flagship titles. Players will likely respond well -- the commercial challenge is real but the creative foundation is solid."
    elif high_quality and no_major_risks and inputs_ok:
        verdict = "Strong concept with favorable signals across the board. Numeric inputs align with winners and no major feature risks detected."
    elif high_quality and not inputs_ok:
        verdict = "Good quality potential, but numeric inputs sit outside the winner range. Adjusting complexity or playtime could improve expected performance."
    elif high_quality:
        verdict = "Above average quality potential. Some feature risks present but nothing severe -- targeted additions could push this into top-performer territory."
    elif r_l == "Average" and d_l != "High":
        verdict = "Solid average concept in an accessible market. Feature additions from the recommendations below could meaningfully differentiate it."
    elif d_l == "High":
        verdict = "Concept faces real headwinds in a crowded market. Consider differentiation through unique mechanics or feature additions."
    else:
        verdict = "Current concept underperforms historical comparables. Mechanical repositioning or targeted feature additions would meaningfully improve expected performance."

    story = []

    # ── PAGE 1: Header / Concept / Market Signals / Executive Summary ──────────

    story.append(Paragraph("BGG Market Intelligence Engine", title_style))
    story.append(Paragraph(
        f"Analyzing 12,055 published games  |  Confidence: {confidence}  |  {pool} comparable games",
        subtitle_style
    ))
    story.append(hr())

    # Proposed concept inputs
    story.append(Paragraph("Proposed Concept", h2_style))
    ct = Table(
        [["Mechanics", mechanics_str], ["Themes", themes_str],
         ["Players", players_str], ["Playtime", playtime_str], ["Complexity", weight_str]],
        colWidths=[1.2*inch, 5.55*inch]
    )
    ct.setStyle(TableStyle([
        ("FONTNAME",      (0,0), (0,-1),  "Helvetica-Bold"),
        ("FONTNAME",      (1,0), (1,-1),  "Helvetica"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(ct)
    story.append(hr())

    # 4-signal market overview
    story.append(Paragraph("Market Intelligence Report", h2_style))
    story.append(kpi_table([
        ["Quality Potential",      "Commercial Potential",       "Engagement Potential",       "Market Competition"],
        [r_label,                  c_label,                      e_label,                      diff_label],
        [f"Median rating {r_val}", f"Median {c_val:,} owned",   f"Median {e_val:,} ratings",  f"Spread: {spread}x"],
    ]))
    story.append(hr())

    # Executive summary -- plain English interpretation of the signals
    story.append(Paragraph("Executive Summary", h2_style))
    story.append(Paragraph(
        f"This concept resembles <b>{pool} published games</b>, with a median rating of "
        f"<b>{summary['median_rating']}</b> among comparable titles. Quality potential is "
        f"<b>{r_l.lower()}</b> and commercial potential is <b>{c_l.lower()}</b>, "
        f"in a market with <b>{d_l.lower()}</b> competition.",
        body_style
    ))
    story.append(Paragraph(
        f"Expected performance places this concept at approximately the "
        f"<b>{summary['median_rating_percentile']}th percentile</b> within its comparable market segment.",
        body_style
    ))

    # Strengths -- numeric inputs inside winner IQR + strong rating signal
    strengths = []
    for row in flags_list:
        if not row["outside_iqr"]:
            fname = "Complexity" if row["field"] == "GameWeight" else "Playtime"
            strengths.append(f"{fname} aligns closely with successful comparable games (winner median: {row['winner_median']})")
    if r_l in ("Strong", "Very Strong", "Exceptional"):
        strengths.append("Rating potential is strong relative to the broader board game market")
    if strengths:
        story.append(Paragraph("<b>Strengths:</b>", body_style))
        for s in strengths:
            story.append(Paragraph(f"- {s}", bullet_style))

    # Concerns -- feature risks + numeric inputs outside winner IQR + high competition flag
    concerns = []
    if not risks_df.empty:
        top_risk = risks_df.iloc[0]
        concerns.append(f"<b>{top_risk['feature']}</b> appears more often among lower performers (drag: {top_risk['drag']})")
    for row in flags_list:
        if row["outside_iqr"]:
            fname = "Complexity" if row["field"] == "GameWeight" else "Playtime"
            concerns.append(f"{fname} ({row['your_value']}) falls outside the winner range [{row['winner_q1']} - {row['winner_q3']}]")
    if d_l == "High":
        concerns.append("This is a competitive market segment -- top performers capture a disproportionate share of ownership")
    if concerns:
        story.append(Paragraph("<b>Primary concerns:</b>", body_style))
        for c in concerns:
            story.append(Paragraph(f"- {c}", bullet_style))

    if not missing_df.empty:
        top = missing_df.iloc[0]
        story.append(Paragraph(
            f"<b>Highest-impact addition:</b> {top['feature']} (+{round(top['lift']*100,1)}% lift among top performers)",
            body_style
        ))

    # Projected performance range table -- quartile view of the comparable pool
    story.append(Paragraph("Projected Performance Range", h2_style))
    pt = Table(
        [["", "Rating", "Copies Owned", "User Ratings"],
         ["Median",     str(summary["median_rating"]),        f"{summary['projected_owned_med']:,}",    f"{summary['projected_ratings_med']:,}"],
         ["Top 25%",    str(summary["projected_rating_q75"]), f"{summary['projected_owned_q75']:,}+",   f"{summary['projected_ratings_q75']:,}+"],
         ["Bottom 25%", str(summary["projected_rating_q25"]), f"<{summary['projected_owned_q25']:,}",   f"<{summary['projected_ratings_q25']:,}"]],
        colWidths=[1.0*inch, 1.5*inch, 2.0*inch, 2.0*inch]
    )
    pt.setStyle(TableStyle([
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTNAME",      (0,0), (0,-1),  "Helvetica-Bold"),
        ("FONTNAME",      (1,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("BACKGROUND",    (0,0), (-1,0),  colors.HexColor("#f0f0f0")),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, colors.HexColor("#f9f9f9")]),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.lightgrey),
        ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
    ]))
    story.append(pt)
    story.append(hr())

    # ── PAGE 2: Design Advisor / Recommended Additions / Biggest Risks ─────────
    story.append(PageBreak())

    # Verdict + prioritized recommendations
    story.append(Paragraph("Design Advisor", h2_style))
    story.append(Paragraph(f"<b>Verdict:</b> {verdict}", body_style))
    story.append(Spacer(1, 6))

    if not missing_df.empty:
        top = missing_df.iloc[0]
        story.append(Paragraph("<b>If you could add one thing:</b>", body_style))
        story.append(Paragraph(
            f"<b>{top['feature']}</b> -- appears in {round(top['winner_freq']*100,1)}% of top performers "
            f"vs {round(top['comp_freq']*100,1)}% of comparable games. Potential lift: +{round(top['lift']*100,1)}%",
            bullet_style
        ))
        if len(missing_df) >= 2:
            row2 = missing_df.iloc[1]
            story.append(Paragraph("<b>If you could add two things:</b>", body_style))
            story.append(Paragraph(f"Add <b>{top['feature']}</b> and <b>{row2['feature']}</b>.", bullet_style))
        if len(missing_df) >= 3:
            row3 = missing_df.iloc[2]
            story.append(Paragraph("<b>If you could add three things:</b>", body_style))
            story.append(Paragraph(f"Add <b>{top['feature']}</b>, <b>{row2['feature']}</b>, and <b>{row3['feature']}</b>.", bullet_style))

    if not risks_df.empty:
        feature_risks = risks_df[risks_df["drag"] > 0.02]
        if not feature_risks.empty:
            story.append(Spacer(1, 6))
            story.append(Paragraph("<b>Biggest concern:</b>", body_style))
            for _, row in feature_risks.head(2).iterrows():
                story.append(Paragraph(
                    f"- <b>{row['feature']}</b> correlates with weaker performers in this segment (drag: {round(row['drag']*100,1)}%)",
                    bullet_style
                ))

    story.append(hr())

    # Recommended additions table -- features not in concept with positive lift, sorted by lift
    story.append(Paragraph("Recommended Additions", h2_style))
    if missing_df.empty:
        story.append(Paragraph("No strong additions detected for this concept.", body_style))
    else:
        add_rows = [["Feature", "Impact", "Winner Freq", "Comp Freq", "Lift"]]
        for _, row in missing_df.iterrows():
            add_rows.append([
                str(row["feature"]),
                impact_label(row["lift"]),
                f"{round(row['winner_freq']*100,1)}%",
                f"{round(row['comp_freq']*100,1)}%",
                f"+{round(row['lift']*100,1)}%",
            ])
        add_t = Table(add_rows, colWidths=[2.4*inch, 1.1*inch, 0.9*inch, 0.9*inch, 0.7*inch])
        add_t.setStyle(TableStyle([
            ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
            ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
            ("FONTNAME",      (1,1), (1,-1),  "Helvetica-Bold"),
            ("TEXTCOLOR",     (1,1), (1,-1),  colors.HexColor("#2d6a4f")),
            ("FONTSIZE",      (0,0), (-1,-1), 8),
            ("BACKGROUND",    (0,0), (-1,0),  colors.HexColor("#f0f0f0")),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, colors.HexColor("#f9f9f9")]),
            ("GRID",          (0,0), (-1,-1), 0.3, colors.lightgrey),
            ("ALIGN",         (2,0), (-1,-1), "CENTER"),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
        ]))
        story.append(add_t)

    story.append(hr())

    # Risks -- concept features overrepresented in bottom quartile + numeric flags
    story.append(Paragraph("Biggest Risks", h2_style))
    has_risks = False
    if not risks_df.empty:
        feature_risks = risks_df[risks_df["drag"] > 0.02]
        for _, row in feature_risks.iterrows():
            has_risks = True
            story.append(Paragraph(f"<b>{row['feature']}</b>", h3_style))
            story.append(Paragraph(
                f"Appears more frequently among lower-performing comparable games ({round(row['drag']*100,1)}% drag).",
                caption_style
            ))
    for row in flags_list:
        if row["outside_iqr"]:
            has_risks = True
            fname = "Complexity Weight" if row["field"] == "GameWeight" else "Playtime"
            story.append(Paragraph(f"<b>{fname}</b>", h3_style))
            story.append(Paragraph(
                f"Your value of {row['your_value']} falls outside the winner range "
                f"[{row['winner_q1']} - {row['winner_q3']}] (winner median: {row['winner_median']}).",
                caption_style
            ))
    if not has_risks:
        story.append(Paragraph("No significant risks detected for this concept.", body_style))

    # ── PAGE 3: Comparable Games ───────────────────────────────────────────────
    story.append(PageBreak())

    story.append(Paragraph(f"Comparable Games (pool of {pool})", h2_style))
    story.append(Paragraph("Games most similar to your concept, ranked by similarity score.", caption_style))
    story.append(Spacer(1, 6))

    comp_display = comp_table.head(20).copy()
    comp_display.columns = ["Name", "Avg Rating", "Owned", "# Ratings", "Similarity"]

    table_data = [["Name", "Avg Rating", "Owned", "# Ratings", "Similarity"]]
    for _, row in comp_display.iterrows():
        table_data.append([
            str(row["Name"])[:45],
            str(round(float(row["Avg Rating"]), 2)),
            f"{int(float(row['Owned'])):,}",
            f"{int(float(row['# Ratings'])):,}",
            str(round(float(row["Similarity"]), 3)),
        ])

    comp_t = Table(table_data, colWidths=[3.0*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.9*inch])
    comp_t.setStyle(TableStyle([
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("BACKGROUND",    (0,0), (-1,0),  colors.HexColor("#f0f0f0")),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, colors.HexColor("#f9f9f9")]),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.lightgrey),
        ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
    ]))
    story.append(comp_t)

    doc.build(story)
    buffer.seek(0)
    return buffer