import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from collections import Counter
from itertools import combinations

from src.data import load_processed

st.title("Senate Hearings Explorer")

# Existing table view for latest cleaned session
df_latest = load_processed("data/cleaned/all_sessions_keywords_filtered.csv")
st.subheader("Latest Processed Hearings Data 2023-Current Day")
st.dataframe(df_latest)

# Keyword time-series chart across all sessions
st.subheader("Keyword Mentions Over Time")
all_df = load_processed("data/cleaned/all_sessions_keywords_filtered.csv")

# Ensure date is parsed; drop invalid dates
all_df["date"] = pd.to_datetime(all_df["date"], errors="coerce")
all_df = all_df.dropna(subset=["date"])  # rows with NaT dates removed

# Limit analysis to 2023 through current date
min_date = pd.Timestamp(2023, 1, 1)
max_date = pd.Timestamp.today().normalize()
all_df = all_df[(all_df["date"] >= min_date) & (all_df["date"] <= max_date)]

# --- Keyword cleaning (mirrors EDA notebook) ---
banned_substrings = [
	'senate committee', 'house committee', 'committee hearing', 'hearing committee',
	'committee judiciary', 'committee finance', 'finance committee', 'committee health',
	'committee presiding', 'special committee', 'members subcommittee', 'members senate',
	'committee aging', 'use committee', 'committee thank', 'committees',
	'committee met', 'members committee', 'committee members', 'members congress', 'subcommittee', 'committee',
	'opening statement', 'testimony', 'testified', 'chairman', 'ranking member', 'senator',
	'representative', 'congressman', 'congresswoman', 'good morning', 'good afternoon',
	'thank you', 'distinguished', 'witness', 'panel', 'hearing adjourned', 'hearing today', 'today hearing',
	'chair durbin', 'questions chair', 'chief counsel',
	'senate', 'states senate', 'congress session', 'eighteenth congress', 'congress',
	'2023 senate', '2024 budget', 'senate office', 'senate eighteenth', 'hearings',
	'congressional', 'pdf washington', 'dc committee', 'act 2023', 'gov document', 'docs fcc', 'statement fcc',
	'board directors', 'briefing', 'justices', 'government publishing',
	'republican staff', 'chair warren', 'document fcc', 'filing', 'secretary state', 'judiciary', 'policymakers',
	'menendez', 'sanders', 'murkowski',
	'federal', 'bipartisan', 'administrations', 'assessed'
]

normalize_map = {
	'president budget': "president's budget",
	"president's budget": "president's budget",
	'presidents budget': "president's budget",
	'white house budget': "president's budget",
	'epa': 'EPA', 'fcc': 'FCC', 'federal reserve': 'Federal Reserve',
	'veterans affairs': 'Veterans Affairs', 'va': 'Veterans Affairs',
	'department of energy': 'DOE', 'doe': 'DOE',
	'department of transportation': 'DOT', 'dot': 'DOT',
	'department of defense': 'DoD', 'dod': 'DoD',
	'department of homeland security': 'Homeland Security', 'dhs': 'Homeland Security',
	'centers for disease control': 'CDC', 'cdc': 'CDC',
	'food and drug administration': 'FDA', 'fda': 'FDA',
	'department agriculture': 'USDA',
	'bipartisan infrastructure': 'Bipartisan Infrastructure',
	'bipartisan support': 'Bipartisan Support',
	'federal funding': 'Federal Funding', 'federal agencies': 'Federal Agencies',
	'natural gas': 'Natural Gas', 'health plans': 'Health Plans',
	'tax cuts': 'Tax Cuts', 'tribal programs': 'Tribal Programs'
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


# Compute cleaned keywords column once and guard against non-list values
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

# Keyword input (dropdown only)
suggested = st.selectbox("Choose a keyword (Top 20)", ["(choose)"] + top_keywords, index=0)
match_type = st.radio("Match type", ["contains", "exact"], index=0)

# Use dropdown selection only
active_keyword = suggested if suggested != "(choose)" else ""

if active_keyword:
	# Normalize keyword for matching
	needle = active_keyword.lower()

	# Build a boolean match per row across kw_1..kw_10 and the aggregated 'keywords' text
	def row_matches(row):
		# check kw_1..kw_10
		kw_cols = [c for c in all_df.columns if c.startswith("kw_")]
		for c in kw_cols:
			val = str(row.get(c, "")).lower()
			if match_type == "exact" and val == needle:
				return True
			if match_type == "contains" and needle in val:
				return True
		# also check 'keywords' aggregated string
		agg = str(row.get("keywords", "")).lower()
		if match_type == "exact":
			# exact across aggregated list: split by ';' and trim
			parts = [p.strip() for p in agg.split(";")]
			return needle in parts
		else:
			return needle in agg

	matches = all_df.apply(row_matches, axis=1)
	filtered = all_df.loc[matches, ["date"]]

	if filtered.empty:
		st.info("No mentions found for the given keyword.")
	else:
		# Group by month and count occurrences per period
		period = filtered["date"].dt.to_period("M").dt.to_timestamp()
		grouped = filtered.assign(period=period).groupby("period").size().reset_index(name="count")

		# Sort by time and render line chart
		grouped = grouped.sort_values("period")
		chart_df = grouped.set_index("period")["count"]
		st.line_chart(chart_df)

		st.caption("Counts reflect hearings where the keyword appears in top extracted terms.")


# --- EDA-style visuals ---
st.subheader("EDA Graphics")

# Time trends for top keywords (monthly)
topN = 10
df_time = all_df.dropna(subset=["date"]).copy()
month_col = df_time["date"].dt.to_period("M").dt.to_timestamp()
kw_exploded = df_time.assign(month=month_col).explode("clean_kws")
kw_exploded = kw_exploded[kw_exploded["clean_kws"].notna() & (kw_exploded["clean_kws"] != "")]
overall_counts = kw_exploded["clean_kws"].value_counts().head(topN).index.tolist()
trend = (
	kw_exploded[kw_exploded["clean_kws"].isin(overall_counts)]
	.groupby(["month", "clean_kws"])
	.size()
	.reset_index(name="count")
)
trend_pivot = trend.pivot(index="month", columns="clean_kws", values="count").fillna(0)
st.write("Top keyword usage over time (monthly, top 10 overall):")
st.line_chart(trend_pivot)

# Co-occurrence heatmap (Top 20)
st.write("Keyword co-occurrence heatmap (top 20 keywords):")
M = 20
topM = kw_exploded["clean_kws"].value_counts().head(M).index.tolist()
co_counts = {(a, b): 0 for a in topM for b in topM}
for kws in all_df["clean_kws"]:
	if not isinstance(kws, list):
		continue
	kws = [k for k in set(kws) if k in topM]
	for a, b in combinations(sorted(kws), 2):
		co_counts[(a, b)] += 1
		co_counts[(b, a)] += 1
	for k in kws:
		co_counts[(k, k)] += 1
mat = pd.DataFrame(index=topM, columns=topM, data=0)
for (a, b), v in co_counts.items():
	mat.at[a, b] = v
fig_co, ax_co = plt.subplots(figsize=(12, 10))
sns.heatmap(mat, cmap="Blues", linewidths=0.5, ax=ax_co)
ax_co.set_title(f"Keyword Co-occurrence (Top {M})")
st.pyplot(fig_co)

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

# Document word count distribution (if text available)
if "text" in all_df.columns:
	word_counts = all_df["text"].fillna("").str.split().str.len()
	fig_wc, ax_wc = plt.subplots(figsize=(10, 5))
	word_counts.plot(kind="hist", bins=50, ax=ax_wc)
	ax_wc.set_title("Document Word Count Distribution")
	ax_wc.set_xlabel("Words")
	ax_wc.set_ylabel("Documents")
	st.pyplot(fig_wc)

# Correlation and association heatmaps for top 10 keywords
st.write("Correlation heatmaps for top 10 keywords:")
all_kws_series = pd.Series([
	k
	for kws in all_df["clean_kws"]
	for k in (kws if isinstance(kws, list) else [])
])
top10 = all_kws_series.value_counts().head(10).index.tolist()
presence = pd.DataFrame({
	kw: all_df["clean_kws"].apply(lambda ks: int(kw in (set(ks) if isinstance(ks, list) else set())))
    for kw in top10
})

# Pearson correlation
corr = presence.corr(method="pearson")
mask_corr = np.triu(np.ones_like(corr, dtype=bool), k=1)
fig_corr, ax_corr = plt.subplots(figsize=(10, 8))
sns.heatmap(corr, mask=mask_corr, annot=True, fmt=".2f", cmap="coolwarm", vmin=-1, vmax=1, square=True, cbar_kws={"shrink": 0.8}, ax=ax_corr)
ax_corr.set_title("Pearson Correlation (Top 10 Keyword Presence)")
st.pyplot(fig_corr)

# Normalized PMI
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
sns.heatmap(npmi_mat.astype(float), mask=mask_npmi, annot=True, fmt=".2f", cmap="viridis", vmin=-1, vmax=1, square=True, cbar_kws={"shrink": 0.8}, ax=ax_npmi)
ax_npmi.set_title("Normalized PMI (Top 10 Keywords)")
st.pyplot(fig_npmi)

# Phi (same as Pearson for binary)
phi = corr.copy()
mask_phi = np.triu(np.ones_like(phi, dtype=bool), k=1)
fig_phi, ax_phi = plt.subplots(figsize=(10, 8))
sns.heatmap(phi, mask=mask_phi, annot=True, fmt=".2f", cmap="coolwarm", vmin=-1, vmax=1, square=True, cbar_kws={"shrink": 0.8}, ax=ax_phi)
ax_phi.set_title("Phi Coefficient (Top 10 Keywords)")
st.pyplot(fig_phi)

# Top keyword pairs tables (NPMI and Pearson)
def upper_triangle_pairs(mat_df: pd.DataFrame):
	pairs = []
	for i, a in enumerate(mat_df.index):
		for j, b in enumerate(mat_df.columns):
			if j <= i:
				continue
			val = float(mat_df.loc[a, b])
			pairs.append((a, b, val))
	return pairs

npmi_pairs = upper_triangle_pairs(npmi_mat)
npmi_top_df = pd.DataFrame(sorted(npmi_pairs, key=lambda x: x[2], reverse=True), columns=["keyword_a", "keyword_b", "npmi"]).head(15)
corr_pairs = upper_triangle_pairs(corr)
corr_top_df = pd.DataFrame(sorted(corr_pairs, key=lambda x: x[2], reverse=True), columns=["keyword_a", "keyword_b", "pearson"]).head(15)
st.write("Top keyword pairs by NPMI:")
st.dataframe(npmi_top_df)
st.write("Top keyword pairs by Pearson:")
st.dataframe(corr_top_df)
