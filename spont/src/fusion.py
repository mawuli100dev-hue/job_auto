import pandas as pd

df1 = pd.read_csv("data/offres_spontanees/offres_spontanees_2026-09-14_154406.csv")
df2 = pd.read_csv("data/offres_spontanees/offres_spontanees_2026-09-14_160226.csv")

df = pd.concat([df1, df2], ignore_index=True)

df.to_csv("data/offres_spontanees/fusion.csv", index=False)

print(f"Fusion terminée : {len(df)} lignes")