#!/usr/bin/env python3
# from pathlib import Path
# all_files = Path('.').glob("./results/*_stats.csv")

import os, glob
import pandas as pd

all_files = glob.glob(os.path.join("./results/*_stats.csv"))

all_df = []
for f in all_files:
    df = pd.read_csv(f, sep=',')
    df['file'] = f.split('/')[-1]
    all_df.append(df)
merged_df = pd.concat(all_df, ignore_index=True, sort=True)
merged_df.to_csv("./results/stats.csv")
