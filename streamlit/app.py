import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from itertools import combinations

from src.data import load_processed


# ---------- Page Title ----------
st.title("Senate Hearings Explorer")


# ---------- Load Data ----------
all_df = load_processed("data/cleaned/all_sessions_keywords_filtered.csv")

# Ensure date is parsed; drop invalid dates
all_df["date"] = pd.to_datetime(all_df["date"], errors="coerce")
all_df = all_df.dropna(subset=["date"])  # rows with NaT dates removed

# Limit analysis to 2023 through current date
min_date = pd.Timestamp(2023, 1, 1)
max_date = pd.Timestamp.today().normalize()
all_df = all_df[(all_df["date"] >= min_date) & (all_df["date"] <= max_date)]

# Show a quick preview table
st.subheader("Processed Hearings 2023–Today")
st.dataframe(all_df)


# ---------- Keyword Cleaning (mirrors EDA) ----------
banned_substrings = [
	"senate committee",
	"house committee",
	"committee hearing",
	"hearing committee",
	"committee judiciary",
	"committee finance",
	"finance committee",
	"committee health",
	"committee presiding",
	"special committee",
	"members subcommittee",
	"members senate",
	"committee aging",
	"use committee",
	"committee thank",
	"committees",
	"committee met",
	"members committee",
	"committee members",
	"members congress",
	"subcommittee",
	"committee",
	"opening statement",
	"testimony",
	"testified",
	"chairman",
	"ranking member",
	"senator",
	"representative",
	"congressman",
	"congresswoman",
	"good morning",
	"good afternoon",
	"thank you",
	"distinguished",
	"witness",
	"panel",
	"hearing adjourned",
	"hearing today",
	"today hearing",
	"chair durbin",
	"questions chair",
	"chief counsel",
	"senate",
	"states senate",
	"congress session",
	"eighteenth congress",
	"congress",
	"2023 senate",
	"2024 budget",
	"senate office",
	"senate eighteenth",
	"hearings",
	"congressional",
	"pdf washington",
	"dc committee",
	"act 2023",
	"gov document",
	"docs fcc",
	"statement fcc",
	"board directors",
	"briefing",
	"justices",
	"government publishing",
	"republican staff",
	"chair warren",
	"document fcc",
	"filing",
	"secretary state",
	"judiciary",
	"policymakers",
	"menendez",
	"sanders",
	"murkowski",
	"federal",
	"bipartisan",
	"administrations",
	"assessed",
]

normalize_map = {
	"president budget": "president's budget",
	"president's budget": "president's budget",
	"presidents budget": "president's budget",
	"white house budget": "president's budget",
	"epa": "EPA",
	"fcc": "FCC",
	"federal reserve": "Federal Reserve",
	"veterans affairs": "Veterans Affairs",
	"va": "Veterans Affairs",
	"department of energy": "DOE",
	"doe": "DOE",
	"department of transportation": "DOT",
	"dot": "DOT",
	"department of defense": "DoD",
	"dod": "DoD",
	"department of homeland security": "Homeland Security",
	"dhs": "Homeland Security",
	"centers for disease control": "CDC",
	"cdc": "CDC",
	"food and drug administration": "FDA",
	"fda": "FDA",
	"department agriculture": "USDA",
	"bipartisan infrastructure": "Bipartisan Infrastructure",
	"bipartisan support": "Bipartisan Support",
	"federal funding": "Federal Funding",
	"federal agencies": "Federal Agencies",
	"natural gas": "Natural Gas",
	"health plans": "Health Plans",
	"tax cuts": "Tax Cuts",
	"tribal programs": "Tribal Programs",
}


def is_banned(k: str) -> bool:
	kl = k.lower()
	if kl.strip() == "":
		return True
	for sub in banned_substrings:
		if sub in kl:
			return True
	return False


def norm(k: str) -> str:
	kl = k.lower()
	return normalize_map.get(kl, k)


def build_clean_keywords(df: pd.DataFrame) -> pd.Series:
	kw_cols_local = [c for c in df.columns if c.startswith("kw_")]
	clean_kws = []
	for _, row in df.iterrows():
		kws = []
		for c in kw_cols_local:
			v = row.get(c, "")
			if isinstance(v, str) and v.strip() != "" and not is_banned(v):
				kws.append(norm(v))
		clean_kws.append(kws)
	return pd.Series(clean_kws)


# Compute cleaned keywords column and ensure list type
all_df["clean_kws"] = build_clean_keywords(all_df).apply(
	lambda x: x if isinstance(x, list) else []
)

# Build top-20 keyword list from cleaned keywords
top_kw_series = pd.Series([
	kw
	for kws in all_df["clean_kws"]
	for kw in (kws if isinstance(kws, list) else [])
]).value_counts()
top_keywords = top_kw_series.head(20).index.tolist()


# ---------- Keyword Mentions (Monthly) ----------
st.subheader("Keyword Mentions Over Time")
selected_kw = st.selectbox("Choose a keyword (Top 20)", ["(choose)"] + top_keywords, index=0)
match_type = st.radio("Match type", ["contains", "exact"], index=0, horizontal=True)

active_keyword = selected_kw if selected_kw != "(choose)" else ""

if active_keyword:
	needle = active_keyword.lower()
	kw_cols = [c for c in all_df.columns if c.startswith("kw_")]

	def row_matches(row: pd.Series) -> bool:
		# kw_1..kw_10
		for c in kw_cols:
			val = str(row.get(c, "")).lower()
			if match_type == "exact" and val == needle:
				return True
			if match_type == "contains" and needle in val:
				return True
		# aggregated keywords
		agg = str(row.get("keywords", "")).lower()
		if match_type == "exact":
			parts = [p.strip() for p in agg.split(";")]
			return needle in parts
		return needle in agg

	matches = all_df.apply(row_matches, axis=1)
	filtered = all_df.loc[matches, ["date"]]

	if filtered.empty:
		st.info("No mentions found for the selected keyword.")
	else:
		period = filtered["date"].dt.to_period("M").dt.to_timestamp()
		grouped = filtered.assign(period=period).groupby("period").size().reset_index(name="count")
		grouped = grouped.sort_values("period")
		st.line_chart(grouped.set_index("period")["count"])
		st.caption("Counts reflect hearings where the keyword appears in top extracted terms.")


# ---------- EDA Graphics ----------
st.subheader("EDA Graphics")

# Time trends for top keywords (monthly)
topN = 10
df_time = all_df.copy()
month_col = df_time["date"].dt.to_period("M").dt.to_timestamp()
kw_exploded = df_time.assign(month=month_col).explode("clean_kws")
kw_exploded = kw_exploded[
	kw_exploded["clean_kws"].apply(lambda v: isinstance(v, str) and v.strip() != "")
]
overall_counts = kw_exploded["clean_kws"].value_counts().head(topN).index.tolist()
trend = (
	kw_exploded[kw_exploded["clean_kws"].isin(overall_counts)]
	.groupby(["month", "clean_kws"]).size()
	.reset_index(name="count")
)
trend_pivot = trend.pivot(index="month", columns="clean_kws", values="count").fillna(0)
st.write("Top keyword usage over time (monthly, top 10 overall):")
st.line_chart(trend_pivot)

# Top keyword counts bar chart (Top 25)
st.write("Top keyword counts:")
topK = 25
kw_counts = kw_exploded["clean_kws"].value_counts().head(topK).sort_values()
fig_bar, ax_bar = plt.subplots(figsize=(10, 6))
kw_counts.plot(kind="barh", ax=ax_bar)
ax_bar.set_title("Top Keyword Counts")
ax_bar.set_xlabel("Count")
ax_bar.set_ylabel("Keyword")
st.pyplot(fig_bar)

# Correlations for top 10 keywords
st.write("Correlation heatmaps for top 10 keywords:")
all_kws_series = pd.Series([
	k
	for kws in all_df["clean_kws"]
	for k in (kws if isinstance(kws, list) else [])
])
top10 = all_kws_series.value_counts().head(10).index.tolist()
presence = pd.DataFrame({
	kw: all_df["clean_kws"].apply(
		lambda ks: int(kw in (set(ks) if isinstance(ks, list) else set()))
	)
	for kw in top10
})


def upper_triangle_pairs(mat_df: pd.DataFrame):
	pairs = []
	for i, a in enumerate(mat_df.index):
		for j, b in enumerate(mat_df.columns):
			if j <= i:
				continue
			val = float(mat_df.loc[a, b])
			pairs.append((a, b, val))
	return pairs


# Pearson correlation: interpretation + heatmap and table
corr_interp = (
	"Pearson correlation: measures linear correlation of binary presence per keyword. "
	"Range [-1, 1]: 1 = always together, 0 = independent, -1 = never together. "
	"Common keywords can inflate values; compare with NPMI for robustness."
)
st.markdown(corr_interp)
corr = presence.corr(method="pearson")
mask_corr = np.triu(np.ones_like(corr, dtype=bool), k=1)
fig_corr, ax_corr = plt.subplots(figsize=(10, 8))
sns.heatmap(
	corr,
	mask=mask_corr,
	annot=True,
	fmt=".2f",
	cmap="coolwarm",
	vmin=-1,
	vmax=1,
	square=True,
	cbar_kws={"shrink": 0.8},
	ax=ax_corr,
)
ax_corr.set_title("Pearson Correlation (Top 10 Keyword Presence)")
corr_pairs = upper_triangle_pairs(corr)
corr_top_df = pd.DataFrame(
	sorted(corr_pairs, key=lambda x: x[2], reverse=True),
	columns=["keyword_a", "keyword_b", "pearson"],
).head(15)
st.pyplot(fig_corr)
st.dataframe(corr_top_df, use_container_width=True)

# Normalized PMI: interpretation + heatmap and table
npm_interp = (
	"NPMI: how much two keywords co-occur beyond chance, normalized to [-1, 1]. "
	"1 = strong association, 0 ≈ chance, negative = co-occur less than expected. "
	"More robust to popularity than Pearson; prefer pairs with adequate support."
)
st.markdown(npm_interp)
n_docs = len(presence)
p = presence.sum(axis=0) / n_docs
joint = (presence.T @ presence) / n_docs


def npmi(a: str, b: str) -> float:
	pab = joint.loc[a, b]
	pa = p[a]
	pb = p[b]
	if pab == 0 or pa == 0 or pb == 0:
		return 0.0
	pmi = np.log(pab / (pa * pb))
	return float(pmi / (-np.log(pab)))


npmi_mat = pd.DataFrame(index=top10, columns=top10, dtype=float)
for a in top10:
	for b in top10:
		npmi_mat.loc[a, b] = npmi(a, b)
mask_npmi = np.triu(np.ones_like(npmi_mat, dtype=bool), k=1)
fig_npmi, ax_npmi = plt.subplots(figsize=(10, 8))
sns.heatmap(
	npmi_mat.astype(float),
	mask=mask_npmi,
	annot=True,
	fmt=".2f",
	cmap="viridis",
	vmin=-1,
	vmax=1,
	square=True,
	cbar_kws={"shrink": 0.8},
	ax=ax_npmi,
)
ax_npmi.set_title("Normalized PMI (Top 10 Keywords)")
npmi_pairs = upper_triangle_pairs(npmi_mat)
npmi_top_df = pd.DataFrame(
	sorted(npmi_pairs, key=lambda x: x[2], reverse=True),
	columns=["keyword_a", "keyword_b", "npmi"],
).head(15)
st.pyplot(fig_npmi)
st.dataframe(npmi_top_df, use_container_width=True)

# Phi (binary Pearson): interpretation + heatmap (no table)
phi_interp = (
	"Phi coefficient: Pearson correlation specialized for binary variables; "
	"numerically identical to Pearson here. Use as a quick confirmation."
)
st.markdown(phi_interp)
phi = corr.copy()
mask_phi = np.triu(np.ones_like(phi, dtype=bool), k=1)
fig_phi, ax_phi = plt.subplots(figsize=(10, 8))
sns.heatmap(
	phi,
	mask=mask_phi,
	annot=True,
	fmt=".2f",
	cmap="coolwarm",
	vmin=-1,
	vmax=1,
	square=True,
	cbar_kws={"shrink": 0.8},
	ax=ax_phi,
)
ax_phi.set_title("Phi Coefficient (Top 10 Keywords)")
st.pyplot(fig_phi)