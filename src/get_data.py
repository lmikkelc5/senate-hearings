import sys
from pathlib import Path
SITE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SITE_DIR))
from senate_hearings import helper_funcs
from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
import requests
import glob
import time
import re

###get_html.ipynb converted to .py script###
#get response
url = 'https://www.govinfo.gov/browse/committee'
r = requests.get(url)
print(r.status_code)

#create soup
soup = BeautifulSoup(r.content, "html.parser")
base_url = 'https://www.govinfo.gov'

#find all senate commitee pages
divs = soup.find_all('div', id = 'senate-col')
links = []
links = divs[0].find_all('a')

#create dictionary of links and committee name
page_links = {'committee_name':[], 'url':[]}
for link in links:
    committee = link.text
    page_links['committee_name'].append(committee)
    partial_url = link['href']
    page_links['url'].append(base_url + partial_url)

print(page_links)

#loop through each link and access the page 
links = page_links['url']
print(links)
count = 0
for link in links:
    #get url and soup
    url = link
    print(url)
    committee = page_links['committee_name'][count]

    #use helper functions
    html = helper_funcs.get_fully_expanded_html(url, headless=True, save_to=f"../data/senate_html/{committee.lower()}.html")
    count += 1
    print(count)

###get_links.py converted to .py script###
all_dfs = []
list_of_html_files = glob.glob("../data/senate_html/*.html")

for file in list_of_html_files:
    with open(file, "r", encoding="utf-8") as f:
        html_text = f.read()

    df = helper_funcs.extract_hearing_links(html_text)
    all_dfs.append(df)

# Combine into one DataFrame
final_df = pd.concat(all_dfs, ignore_index=True)


###access_links.py converted to .py script###
df2 = final_df

#add the session column
df2["session"] = df2["details_url"].apply(helper_funcs.get_session_from_url)

#fix links
df2["details_url"] = df2["details_url"].apply(helper_funcs.to_html_url)
df2["text_url"] = df2["text_url"].apply(helper_funcs.to_html_url)

#add the text column
df2['text'] = df2['text_url'].apply(helper_funcs.get_text)


###split_csv.py converted to .py script###
big_df = df2
session = [119, 118, 117, 116, 115, 114, 113, 112, 111, 110, 109, 108, 107, 106, 105, 104]

for item in session:
    df3 = big_df[big_df["session"] == item]
    df3.to_csv(f"../data/uncleaned_data/session_{item}.csv", index=False)
    print(f'saved session {item}')


###clean_extract_data.ipynb converted to .py script###
sessions = [119, 118] #, 117, 116, 115, 114, 113, 112, 111, 110, 109, 108, 107, 106, 105, 104]

for session in sessions:
    df4 = pd.read_csv(f"../data/uncleaned_data/session_{session}.csv")

    #Clean text
    df4['text'] = df4['text'].apply(helper_funcs.extract_main_text)

    #get date
    df4['date'] = df4['text'].apply(helper_funcs.get_date)
    df4['month'] = df4['date'].apply(helper_funcs.get_month)
    df4['day'] = df4['date'].apply(helper_funcs.get_day)
    df4['year'] = df4['date'].apply(helper_funcs.get_year)

    #get heading
    df4['title'] = df4['text'].apply(helper_funcs.extract_hearing_title)

    #reorder columns
    df4 = df4[[c for c in df4.columns if c != "text"] + ["text"]]

    #delete unwanted columns
    df4 = df4.drop('details_url', axis=1)
    df4 = df4.drop('text_url', axis=1)

    df4.to_csv(f"../data/cleaned/session_{session}_cleaned.csv", index=False)
    print(f"saved session {session}")