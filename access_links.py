import pandas as pd
import helper_funcs

df = pd.read_csv("senate_data.csv")

#add the session column
df["session"] = df["details_url"].apply(helper_funcs.get_session_from_url)

#fix links
df["details_url"] = df["details_url"].apply(helper_funcs.to_html_url)
df["text_url"] = df["text_url"].apply(helper_funcs.to_html_url)

#add the text column
df['text'] = df['text_url'].apply(helper_funcs.get_text)

print(df.head())

