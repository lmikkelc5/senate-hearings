import pandas as pd

big_df = pd.read_csv("senate_data_with_text.csv")
session = [119, 118, 117, 116, 115, 114, 113, 112, 111, 110, 109, 108, 107, 106, 105, 104]

for item in session:
    df = big_df[big_df["session"] == item]
    df.to_csv(f"data/session_{item}.csv", index=False)
    print(f'saved session {item}')