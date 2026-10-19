"""Leakage-safe feature construction for machine-learning forecasters."""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from warmlambda.core.config import SimConfig
from warmlambda.core.forecaster import bin_trace_to_windows
from warmlambda.core.traffic import generate_trace


def feature_names(k: int = 60) -> list[str]:
    """Return the stable column names used by the feature vector."""
    names = [f"lag_{index + 1}" for index in range(k)]
    for width in (3, 6, 12, 30):
        names.extend([f"rolling_{width}_mean", f"rolling_{width}_std", f"rolling_{width}_max"])
    names.extend(["ewma_0.2", "ewma_0.6", "last_difference", "last_to_mean_ratio"])
    for period in (30, 60):
        names.extend([f"cycle_{period}_sin", f"cycle_{period}_cos"])
    return names


def counts_to_features(counts: np.ndarray, window_index: int, k: int = 60) -> np.ndarray:
    """Create one row using only counts strictly before ``window_index``."""
    history = counts[:window_index]
    lags = np.zeros(k, dtype=np.float32)
    recent = history[-k:]
    if len(recent):
        lags[-len(recent):] = recent
    values: list[float] = list(lags)
    for width in (3, 6, 12, 30):
        sample = history[-width:] if len(history) else np.empty(0)
        values.extend(
            [
                float(sample.mean()) if len(sample) else 0.0,
                float(sample.std()) if len(sample) else 0.0,
                float(sample.max()) if len(sample) else 0.0,
            ]
        )
    for alpha in (0.2, 0.6):
        level = 0.0
        for value in history:
            level = alpha * float(value) + (1.0 - alpha) * level
        values.append(level)
    last = float(history[-1]) if len(history) else 0.0
    previous = float(history[-2]) if len(history) > 1 else last
    rolling_mean = float(history[-30:].mean()) if len(history) else 0.0
    values.extend([last - previous, last / rolling_mean if rolling_mean > 0 else 0.0])
    for period in (30, 60):
        angle = 2.0 * np.pi * window_index / period
        values.extend([float(np.sin(angle)), float(np.cos(angle))])
    return np.asarray(values, dtype=np.float32)


def _build_one_trace(args: tuple[int, tuple[str, ...], SimConfig, float, int, bool]) -> tuple[int, np.ndarray]:
    """Worker function kept at module scope for Windows multiprocessing."""
    seed, scenarios, cfg, window_s, k, randomize = args
    chunks = []
    for scenario in scenarios:
        trace = generate_trace(scenario, cfg, seed, randomize=randomize)
        chunks.append(np.asarray(bin_trace_to_windows(trace, cfg.duration_s, window_s), dtype=np.float32))
    return seed, np.concatenate(chunks)


def _cache_path(seeds: Iterable[int], scenarios: Iterable[str], cfg: SimConfig, window_s: float, k: int, randomize: bool) -> Path:
    payload = {
        "seeds": list(seeds),
        "scenarios": list(scenarios),
        "duration_s": cfg.duration_s,
        "mean_exec_s": cfg.mean_exec_s,
        "window_s": window_s,
        "k": k,
        "randomize": randomize,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return Path(__file__).resolve().parents[2] / "data" / f"dataset_{digest}.npz"


def build_dataset(
    seeds: Iterable[int],
    scenarios: Iterable[str],
    cfg: SimConfig,
    window_s: float = 10.0,
    k: int = 60,
    randomize: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Build or load a cached supervised forecasting dataset.

    Each trace contributes one row per window.  The target is that window's
    rate; every feature is calculated from earlier windows only.
    """
    seed_list = list(seeds)
    scenario_list = tuple(scenarios)
    path = _cache_path(seed_list, scenario_list, cfg, window_s, k, randomize)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        cached = np.load(path, allow_pickle=False)
        meta = json.loads(str(cached["meta"].item()))
        print(f"[ml_dataset] Loaded {len(cached['y']):,} rows from {path}")
        return cached["X"], cached["y"], cached["groups"], meta

    args = [(seed, scenario_list, cfg, window_s, k, randomize) for seed in seed_list]
    workers = min(max(mp.cpu_count() - 1, 1), len(args)) if args else 1
    with mp.Pool(workers) as pool:
        traces = pool.map(_build_one_trace, args)

    rows: list[np.ndarray] = []
    targets: list[float] = []
    groups: list[int] = []
    windows_per_trace = int(np.ceil(cfg.duration_s / window_s))
    for seed, combined_counts in traces:
        # Each scenario has a contiguous block of windows.
        for scenario_index in range(len(scenario_list)):
            start = scenario_index * windows_per_trace
            counts = combined_counts[start:start + windows_per_trace]
            for window_index, target_count in enumerate(counts):
                rows.append(counts_to_features(counts, window_index, k))
                targets.append(float(target_count) / window_s)
                groups.append(seed)

    X = np.asarray(rows, dtype=np.float32)
    y = np.asarray(targets, dtype=np.float32)
    group_array = np.asarray(groups, dtype=np.int64)
    meta = {
        "features": X.shape[1],
        "feature_names": feature_names(k),
        "feature_definition": "lags, rolling statistics, EWMAs, difference, ratio, cyclic index",
        "window_s": window_s,
        "k": k,
        "seeds": seed_list,
        "scenarios": list(scenario_list),
        "randomize": randomize,
    }
    np.savez_compressed(path, X=X, y=y, groups=group_array, meta=json.dumps(meta))
    print(f"[ml_dataset] Built {len(y):,} rows and cached them at {path}")
    return X, y, group_array, meta
