import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from src.data import load_processed

st.title("Senate Hearings Explorer")

# Existing table view for latest cleaned session
df_latest = load_processed("data/cleaned/session_119_cleaned.csv")
st.subheader("Latest Session Data (119)")
st.dataframe(df_latest)

# Keyword time-series chart across all sessions
st.subheader("Keyword Mentions Over Time")
all_df = load_processed("data/cleaned/all_sessions_keywords_filtered.csv")

# Ensure date is parsed; drop invalid dates
all_df["date"] = pd.to_datetime(all_df["date"], errors="coerce")
all_df = all_df.dropna(subset=["date"])  # rows with NaT dates removed

keyword = st.text_input("Enter a keyword (case-insensitive)", value="USDA")
match_type = st.radio("Match type", ["contains", "exact"], index=0)
granularity = st.selectbox("Time granularity", ["Day", "Month", "Year"], index=1)

if keyword:
	# Normalize keyword for matching
	needle = keyword.strip().lower()

	# Collect top-kw columns for matching
	kw_cols = [c for c in all_df.columns if c.startswith("kw_")]

	# Build a boolean match per row across kw_1..kw_10 and the aggregated 'keywords' text
	def row_matches(row):
		# check kw_1..kw_10
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
		# Group by chosen granularity and count occurrences per period
		if granularity == "Day":
			grouped = filtered.groupby(filtered["date"].dt.date).size().rename("count").reset_index()
			grouped.rename(columns={"date": "period"}, inplace=True)
		elif granularity == "Month":
			period = filtered["date"].dt.to_period("M").dt.to_timestamp()
			grouped = filtered.groupby(period).size().rename("count").reset_index()
			grouped.rename(columns={"date": "period"}, inplace=True)
		else:  # Year
			period = filtered["date"].dt.to_period("Y").dt.to_timestamp()
			grouped = filtered.groupby(period).size().rename("count").reset_index()
			grouped.rename(columns={"date": "period"}, inplace=True)

		# Sort by time and render line chart
		grouped = grouped.rename(columns={"date": "period"}).sort_values("period")
		chart_df = grouped.set_index("period")["count"]
		st.line_chart(chart_df)

		st.caption("Counts reflect hearings where the keyword appears in top extracted terms.")
