# housing

> Steering prompt for the Dojo.ml agent and the source of truth for tool
> generation. Edit freely between runs — `dojo task setup` reads this file to
> generate `load_data` and `evaluate`, and the agent reads it at the start of
> each run.

## Goal
(describe the research goal)

## Task type
regression

## Dataset
<!--
Describe where the data lives and how to load it. The AI uses this to write
load_data + evaluate. A few examples:

- sklearn loader:
    Use `sklearn.datasets.fetch_california_housing(return_X_y=True)`.
    Features and target both come back as numpy arrays — no column names.
    https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_california_housing.html

- Local CSV:
    `./data/housing.csv` — features are every column except `MedHouseVal`,
    target is `MedHouseVal`.

- URL:
    Download `https://example.com/data.csv` on first call (cache to `./data/`).
-->
TODO — describe the dataset here.

## Target
<!--
What is the model predicting? A single sentence is enough.
For sklearn-style (X, y) datasets, just describe the target — there is no
column name.
-->
TODO — describe the target.

## Success
<!--
How do you know the agent did well? RMSE under some threshold, beating a
linear baseline, etc. The agent reads this and uses it to plan experiments.
-->
TODO — describe what success looks like.

## Contract (do not edit — generated tools are pinned to this)
- The agent owns `train()` and any model / hyperparameter logic, called via
  `run_experiment_code`.
- `load_data` and `evaluate` are frozen tools the agent calls but cannot
  modify. The dict returned by `evaluate` is the only metric source of truth.

## Notes
- Bullet hypotheses you've ruled out, things you've tried, references to past
  runs. The agent reads this section every run.
