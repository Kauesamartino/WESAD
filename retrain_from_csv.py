"""
retrain_from_csv.py — Retreina o modelo a partir do CSV de features pré-gerado.
Usado quando o dataset WESAD não está disponível na VM.
"""
import pandas as pd
from pipeline import train

df = pd.read_csv("features_dataset.csv")
print(f"Dataset carregado: {len(df)} janelas, labels={df['label'].value_counts().to_dict()}")
train(df)
print("Modelo retreinado e salvo com sucesso.")
