import math
from load_data import load_data


def evaluate(y_pred):
    _, _, _, y_test = load_data()
    n = len(y_test)
    ss_res = sum((yt - yp) ** 2 for yt, yp in zip(y_test, y_pred))
    ss_tot = sum((yt - (sum(y_test) / n)) ** 2 for yt in y_test)
    rmse = math.sqrt(ss_res / n)
    r2 = 1.0 - ss_res / ss_tot if ss_tot != 0 else 0.0
    mae = sum(abs(yt - yp) for yt, yp in zip(y_test, y_pred)) / n
    return {"rmse": rmse, "r2": r2, "mae": mae}