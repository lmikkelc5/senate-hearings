import streamlit as st
from src.data import load_processed

df = load_processed("data/processed/hearings.csv")
st.dataframe(df)