import pandas as pd
import helper_funcs

sessions = [119, 118, 117, 116, 115, 114, 113, 112, 111, 110, 109, 108, 107, 106, 105, 104]

#add loop
for session in sessions:
    df = pd.read_csv(f"data/session_{session}.csv")


    #Clean text
    df['text'] = df['text'].apply(helper_funcs.extract_main_text)

    #get date

    df.to_csv(f"data/cleaned/session_{session}_cleaned.csv", index=False)