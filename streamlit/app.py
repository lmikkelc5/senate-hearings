import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st
from src.data import load_processed

df = load_processed("data/cleaned/session_119_cleaned.csv")
st.dataframe(df)
