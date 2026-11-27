# Machine-learning forecasting

## Data and features

`build_dataset` bins each generated request trace into ten-second windows.
Each row predicts the rate in window `t` from windows strictly before `t`.
Features are the last 60 counts, rolling mean/std/max over 3, 6, 12, and 30
windows, EWMA levels at alpha 0.2 and 0.6, the last difference, the last-to-
rolling-mean ratio, and sine/cosine encodings of the 30- and 60-window cycles.
Rows are `float32`; the trace seed is retained as a group label.

The default training command uses seeds 1000--1199 and all registered scenarios with
randomized parameters. Dataset files are content-addressed under `data/` and
can scale to millions of rows by supplying more seeds.

## Models and leakage controls

`HGBForecaster` uses a scikit-learn histogram gradient-boosting estimator.
`hgb_q90` is trained with quantile loss at 0.9 and can provide a conservative
rate forecast. `GRUForecaster` is optional and requires TensorFlow/Keras.
EWMA, EWMA-with-trend, seasonal-naive, and persistence forecasters are
available without model artifacts. Every model's runtime `predict` method
constructs features from the supplied history only. Missing trained artifacts
raise a clear error; there is no implicit EWMA fallback.

Training and validation are split by complete seed groups: no seed appears in
both side of the split. Evaluation uses standard seeds 0--19 without
randomization and an unseen randomized set of seeds 2000--2019.

## Training and evaluation

```bash
python -m experiments.train_forecasters
python -m experiments.eval_forecasters
```

Training prints dataset size, row counts, elapsed time, and validation MAE.
Evaluation writes `results/forecast_eval.csv` and prints MAE, sMAPE,
under-prediction rate, and q90 pinball loss per scenario and dataset.

## Results and honest interpretation

The authoritative results are the table printed by the evaluation command and
the accompanying CSV; they must be regenerated after changing training data.
Accuracy is judged on unseen complete seed groups, never on training rows.
Compare `hgb` and `hgb_q90` against statistical baselines using MAE and sMAPE,
and inspect under-prediction rate and pinball loss for `hgb_q90`. A lower forecast error
does not automatically mean a better capacity policy: also compare cold
starts, queue timeouts, and cost in the simulation results. The project does
not claim model superiority unless held-out metrics demonstrate it for the
target traffic distribution.
