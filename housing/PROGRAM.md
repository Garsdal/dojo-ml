# housing

> Steering prompt for the Dojo.ml agent and the source of truth for tool
> generation. Edit freely between runs — `dojo task setup` reads this file to
> generate `load_data` and `evaluate`, and the agent reads it at the start of
> each run.

## Goal
Get the lowest possible mae score on the test set of the california housing dataset

## Task type
regression

## Dataset
- sklearn loader:
    Use `sklearn.datasets.fetch_california_housing(return_X_y=True)`.
    Features and target both come back as numpy arrays — no column names.
    https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_california_housing.html

## Target
The y loaded from the dataset above

## Success
Start simple and iterate. The success is improvement over iterations

## Contract (do not edit — generated tools are pinned to this)
- The agent owns `train()` and any model / hyperparameter logic, called via
  `run_experiment_code`.
- `load_data` and `evaluate` are frozen tools the agent calls but cannot
  modify. The dict returned by `evaluate` is the only metric source of truth.

## Notes
- Bullet hypotheses you've ruled out, things you've tried, references to past
  runs. The agent reads this section every run.
