import pandas as pd

df = pd.read_csv("data/metrics_dataset_v2.csv")

print("Dataset shape:", df.shape)
print("\nColumns:", df.columns.tolist())

features = ["request_rate", "error_ratio", "p95_latency_seconds"]
print("\nFeature statistics:")
print(df[features].describe().to_string())

print("\nPer-service counts:")
print(df.groupby("service").size().to_string())

print("\nUnique values per feature:")
print(df[features].nunique().to_string())

print("\nError ratio distribution:")
print(df["error_ratio"].value_counts().head(10).to_string())
