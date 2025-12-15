import pandas as pd

def load_processed(path: str) -> pd.DataFrame:
    return pd.read_csv(path)
