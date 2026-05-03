
import json
import numpy as np
from sklearn.datasets import fetch_california_housing
from sklearn.model_selection import train_test_split
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

# Load data — same split as frozen load_data tool (test_size=0.2, random_state=42)
X, y = fetch_california_housing(return_X_y=True)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print(f"Train size: {X_train.shape}, Test size: {X_test.shape}")

# Ridge regression with scaling
pipe = Pipeline([
    ("scaler", StandardScaler()),
    ("ridge", Ridge(alpha=1.0))
])
pipe.fit(X_train, y_train)
y_pred = pipe.predict(X_test).tolist()

print(f"Sample predictions: {y_pred[:5]}")
print(json.dumps({"y_pred": y_pred}))
