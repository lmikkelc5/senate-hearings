import pandas as pd
import helper_funcs

df = pd.read_csv("data/senate_data.csv")

#add the session column
df["session"] = df["details_url"].apply(helper_funcs.get_session_from_url)

#fix links
df["details_url"] = df["details_url"].apply(helper_funcs.to_html_url)
df["text_url"] = df["text_url"].apply(helper_funcs.to_html_url)

# get other info


#add the text column
df['text'] = df['text_url'].apply(helper_funcs.get_text)

df.to_csv("data/senate_data_with_text.csv", index=False)


