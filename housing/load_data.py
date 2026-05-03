from sklearn.datasets import fetch_california_housing
from sklearn.model_selection import train_test_split


def load_data():
    X, y = fetch_california_housing(return_X_y=True)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    return X_train, X_test, y_train, y_test