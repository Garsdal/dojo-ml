# --- injected tool arguments ---

# --- tool code ---
import json
from sklearn.datasets import fetch_california_housing
from sklearn.model_selection import train_test_split

X, y = fetch_california_housing(return_X_y=True)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

result = {
    "X_train": X_train.tolist(),
    "X_test": X_test.tolist(),
    "y_train": y_train.tolist(),
    "y_test": y_test.tolist()
}
print(json.dumps(result))
