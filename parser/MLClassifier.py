import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report

# Load your labeled data
df = pd.read_csv("training_lines.csv")

# Filter only rows with non-empty labels
df = df[df["label"].notnull() & (df["label"].str.strip() != "")]

# Convert booleans to integers
df["is_bold"] = df["is_bold"].astype(int)
df["is_upper"] = df["is_upper"].astype(int)

# Feature columns to use
feature_cols = ["avg_font_size", "is_bold", "is_upper", "text_length"]
X = df[feature_cols]

# Encode labels as numbers
label_encoder = LabelEncoder()
y = label_encoder.fit_transform(df["label"])

# Split into train and test
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, stratify=y, random_state=42
)

# Train the classifier
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Predict on test data
y_pred = model.predict(X_test)

# Fix: classification_report may crash if some labels are missing in test split
all_labels = label_encoder.transform(label_encoder.classes_)

print("✅ Classification Report:\n")
print(
    classification_report(
        y_test,
        y_pred,
        labels=all_labels,
        target_names=label_encoder.classes_,
        zero_division=0
    )
)

# Optional: save the trained model for later use
import joblib
joblib.dump((model, label_encoder), "line_classifier.pkl")
print("✅ Model saved as 'line_classifier.pkl'")
