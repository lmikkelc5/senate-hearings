from bs4 import BeautifulSoup
import requests
import time
import re
import pandas as pd
from helper_funcs import extract_hearing_links
import glob

all_dfs = []
list_of_html_files = glob.glob("data/senate_html/*.html")

for file in list_of_html_files:
    with open(file, "r", encoding="utf-8") as f:
        html_text = f.read()

    df = extract_hearing_links(html_text)
    all_dfs.append(df)

# Combine into one DataFrame
final_df = pd.concat(all_dfs, ignore_index=True)
print(final_df)

final_df.to_csv("data/senate_data.csv", index=False)
