import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix
import joblib
import json
import numpy as np

# === Config ===
DATA_PATH = Path("training_lines_v2.csv")   # <-- your new file
MODEL_PATH = Path("line_classifier_v2.pkl")
LABELS_JSON = Path("label_mapping_v2.json")
REPORT_TXT = Path("classification_report_v2.txt")

# === Load ===
df = pd.read_csv(DATA_PATH)

# Keep only rows with a non-empty label
df = df[df["label"].notnull() & (df["label"].astype(str).str.strip() != "")]
if df.empty:
    raise ValueError("No labeled rows found after filtering.")

# Ensure expected feature columns exist
for col in ["avg_font_size", "is_bold", "is_upper", "text_length"]:
    if col not in df.columns:
        raise ValueError(f"Missing expected column: {col}")

# Coerce booleans to ints and handle NaNs
df["is_bold"] = df["is_bold"].fillna(0).astype(int)
df["is_upper"] = df["is_upper"].fillna(0).astype(int)
df["avg_font_size"] = pd.to_numeric(df["avg_font_size"], errors="coerce").fillna(0.0)
df["text_length"] = pd.to_numeric(df["text_length"], errors="coerce").fillna(0).astype(int)

# Features / labels
feature_cols = ["avg_font_size", "is_bold", "is_upper", "text_length"]
X = df[feature_cols].values
y_raw = df["label"].astype(str).values

# Encode labels
label_encoder = LabelEncoder()
y = label_encoder.fit_transform(y_raw)

# Show class distribution (useful sanity check)
unique, counts = np.unique(y_raw, return_counts=True)
print("Class distribution:")
for cls, cnt in zip(unique, counts):
    print(f"  {cls:>8} : {cnt}")

# Train-test split (handle small/rare classes gracefully)
try:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
except ValueError:
    # Fall back to non-stratified split if a class has only 1 sample in the dataset
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

# Train (use a slightly larger forest + class balancing)
model = RandomForestClassifier(
    n_estimators=300,
    random_state=42,
    class_weight="balanced",
    n_jobs=-1
)
model.fit(X_train, y_train)

# Predict
y_pred = model.predict(X_test)

# Robust report: include all labels even if some are missing in test
all_labels = list(range(len(label_encoder.classes_)))
report = classification_report(
    y_test,
    y_pred,
    labels=all_labels,
    target_names=label_encoder.classes_,
    zero_division=0
)
cm = confusion_matrix(y_test, y_pred, labels=all_labels)

print("\n✅ Classification Report:\n")
print(report)
print("Confusion matrix (rows=true, cols=pred):")
print(cm)

# Save artifacts
joblib.dump((model, label_encoder), MODEL_PATH)
with open(LABELS_JSON, "w", encoding="utf-8") as f:
    json.dump({"classes": label_encoder.classes_.tolist()}, f, indent=2, ensure_ascii=False)
with open(REPORT_TXT, "w", encoding="utf-8") as f:
    f.write(report + "\n\nConfusion matrix (rows=true, cols=pred):\n")
    f.write(np.array2string(cm))

print(f"\n✅ Model saved to: {MODEL_PATH}")
print(f"✅ Label mapping saved to: {LABELS_JSON}")
print(f"✅ Report saved to: {REPORT_TXT}")
