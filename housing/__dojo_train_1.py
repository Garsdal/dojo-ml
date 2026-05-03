
from load_data import load_data
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import cross_val_score

def train():
    X_train, X_test, y_train, _ = load_data()

    # Small grid search via CV (fast)
    best_score = np.inf
    best_params = {}

    param_grid = [
        {"max_leaf_nodes": n, "min_samples_leaf": m, "learning_rate": lr, "l2_regularization": reg}
        for n in [47, 63, 80]
        for m in [10, 20, 30]
        for lr in [0.03, 0.05]
        for reg in [0.0, 0.1]
    ]

    for params in param_grid:
        model = HistGradientBoostingRegressor(
            max_iter=800,
            loss="squared_error",
            random_state=42,
            **params
        )
        scores = cross_val_score(model, X_train, y_train, cv=5, scoring="neg_mean_absolute_error", n_jobs=-1)
        mean_mae = -scores.mean()
        if mean_mae < best_score:
            best_score = mean_mae
            best_params = params

    print(f"Best CV MAE: {best_score:.4f} with params: {best_params}")

    # Retrain on full training set with best params
    final_model = HistGradientBoostingRegressor(
        max_iter=1000,
        loss="squared_error",
        random_state=42,
        **best_params
    )
    final_model.fit(X_train, y_train)
    preds = final_model.predict(X_test)
    return preds.tolist()
