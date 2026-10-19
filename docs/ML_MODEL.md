# Machine-learning forecasting

## Data and features

`build_dataset` bins each generated request trace into ten-second windows.
Each row predicts the rate in window `t` from windows strictly before `t`.
Features are the last 60 counts, rolling mean/std/max over 3, 6, 12, and 30
windows, EWMA levels at alpha 0.2 and 0.6, the last difference, the last-to-
rolling-mean ratio, and sine/cosine encodings of the 30- and 60-window cycles.
Rows are `float32`; the trace seed is retained as a group label.

The default training command uses seeds 1000--1199 and all four scenarios with
randomized parameters. Dataset files are content-addressed under `data/` and
can scale to millions of rows by supplying more seeds.

## Models and leakage controls

`HGBForecaster` uses scikit-learn histogram gradient boosting and supports both
mean regression and a 0.9 quantile model (`hgb_q90`). `GRUForecaster` uses the
TensorFlow/Keras stack with a 64-unit GRU. Every model's runtime
`predict` method constructs features from the supplied history only.

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
the accompanying CSV; they must be regenerated after changing dependencies or
training data. ML is useful when randomized traces contain repeatable
multi-window structure that the feature set can learn. On scenarios where the
rate is smooth or weakly predictable, EWMA can match or beat ML while being
cheaper, easier to inspect, and available without a model file. The project
does not claim ML superiority unless the printed table demonstrates it on the
relevant test distribution.

The following values are from the evaluated run in this repository (MAE in
requests/second; standard test set):

| Scenario | EWMA | HGB | HGB q90 | EWMA trend |
|---|---:|---:|---:|---:|
| moderate | 0.5018 | 0.5726 | 0.9175 | 0.5391 |
| high_load | 1.5391 | 1.5439 | 2.8153 | 1.6687 |
| extreme | 1.9831 | 1.2447 | 2.2767 | 2.2174 |
| periodic | 0.7686 | 0.7612 | 1.3071 | 0.7175 |

This table shows the honest conclusion: HGB helps materially on extreme
spikes, while EWMA matches or beats it on moderate, high-load, and periodic
traffic. The q90 model is intentionally conservative and should be judged by
its under-prediction rate and pinball loss rather than ordinary MAE alone.
