"""Frozen, per-object score profiles with noncompensating critical gates.

Scores are diagnostics and candidate-selection aids. They cannot certify
scientific meaning, native editability, or a complete slide by themselves.
"""

import math

from .common import identity


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _validate_profile(profile):
    if (profile.get("schema_version") != "score-profile-1"
            or not isinstance(profile.get("profile_id"), str) or not profile["profile_id"]
            or not isinstance(profile.get("source_hash"), str) or len(profile["source_hash"]) != 64
            or not isinstance(profile.get("scope_id"), str) or not profile["scope_id"]):
        raise ValueError("A source- and scope-bound score profile is required")
    metrics = profile.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("Score profile needs a nonempty fixed metric set")
    if profile.get('appearance_policy') == 'semantic_hd_replace':
        pixel_only = {'ssim', 'psnr', 'mse_rgb_01', 'residual_rgb_255', 'color_delta_e',
                      'internal_edge_f1', 'texture_histogram_tv'}
        if set(metrics) & pixel_only:
            raise ValueError('Semantic HD replacement uses meaning/clarity/style objectives; source-pixel metrics belong in diagnostics, not promotion gates')
    for name, spec in metrics.items():
        if (not isinstance(name, str) or not name or not isinstance(spec, dict)
                or set(spec) - {"direction", "bounds", "weight", "hard_min", "hard_max",
                                "max_regression"}):
            raise ValueError("Invalid or unknown metric profile field")
        low_high = spec.get("bounds")
        if (spec.get("direction") not in ("higher", "lower")
                or not isinstance(low_high, list) or len(low_high) != 2
                or not all(_number(v) for v in low_high) or low_high[0] >= low_high[1]
                or not _number(spec.get("weight")) or spec["weight"] <= 0):
            raise ValueError("Metric needs fixed finite bounds, direction and positive weight")
        for key in ("hard_min", "hard_max", "max_regression"):
            if key in spec and (not _number(spec[key]) or (key == "max_regression" and spec[key] < 0)):
                raise ValueError("Metric hard gates must be finite and valid")
        if ("hard_min" in spec and "hard_max" in spec
                and spec["hard_min"] > spec["hard_max"]):
            raise ValueError("Contradictory hard gates")
    important = profile.get("important_metrics", {})
    if not isinstance(important, dict) or not set(important) <= set(metrics):
        raise ValueError("Important metrics must name measured profile entries")
    for spec in important.values():
        if (not isinstance(spec, dict) or set(spec) != {"min_gain", "composite_tolerance"}
                or not all(_number(v) and v >= 0 for v in spec.values())):
            raise ValueError("Important-metric promotion needs fixed nonnegative gains/tolerances")
    if not isinstance(profile.get("calibration_evidence"), list) or not profile["calibration_evidence"]:
        raise ValueError("Score bounds need documented pre-candidate calibration evidence")
    return metrics, important


def _measure(vector, metrics):
    if not isinstance(vector, dict) or set(vector) != set(metrics):
        return None, ["MISSING_OR_EXTRA_METRIC"]
    normalized, failures = {}, []
    for name, spec in metrics.items():
        raw = vector[name]
        if not _number(raw):
            failures.append(name + ":NONFINITE_OR_MISSING")
            continue
        low, high = spec["bounds"]
        if not low <= raw <= high:
            failures.append(name + ":OUT_OF_FROZEN_CALIBRATION")
            continue
        normalized[name] = ((raw - low) / (high - low) if spec["direction"] == "higher"
                            else (high - raw) / (high - low))
        if ("hard_min" in spec and raw < spec["hard_min"]
                or "hard_max" in spec and raw > spec["hard_max"]):
            failures.append(name + ":HARD_THRESHOLD")
    return (normalized if not failures else None), failures


def evaluate(profile, batch):
    """Evaluate one immutable comparison set; never infer bounds from candidates."""
    metrics, important = _validate_profile(profile)
    if (batch.get("schema_version") != "score-batch-1"
            or batch.get("profile_hash") != identity(profile)
            or batch.get("source_hash") != profile["source_hash"]
            or batch.get("scope_id") != profile["scope_id"]):
        raise ValueError("Comparison batch is bound to another source, scope or profile")
    baseline = batch.get("baseline")
    candidates = batch.get("candidates")
    if (not isinstance(baseline, dict) or not isinstance(candidates, list)
            or not candidates or any(not isinstance(item, dict) for item in candidates)):
        raise ValueError("One measured baseline and candidate list are required")
    base_norm, base_failures = _measure(baseline.get("vector"), metrics)
    if base_failures:
        raise ValueError("Baseline is missing, nonfinite or outside frozen calibration")
    weights = {name: spec["weight"] for name, spec in metrics.items()}
    denominator = sum(weights.values())
    def score(values):
        return sum(values[name] * weights[name] for name in metrics) / denominator
    base_score = score(base_norm)
    rows = []
    seen_ids = set()
    for item in candidates:
        candidate_id = item.get("id")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in seen_ids:
            raise ValueError("Candidate IDs must be distinct and nonempty")
        seen_ids.add(candidate_id)
        norm, failures = _measure(item.get("vector"), metrics)
        if norm is not None:
            for name, spec in metrics.items():
                if "max_regression" in spec and base_norm[name] - norm[name] > spec["max_regression"] + 1e-12:
                    failures.append(name + ":BASELINE_REGRESSION")
        row = {"id": candidate_id, "raw": item.get("vector"),
               "normalized": norm, "failures": failures}
        if failures:
            row["decision"] = "REJECTED_NONCOMPENSATING_GATE"
            row["composite"] = None
        else:
            total = score(norm)
            delta = total - base_score
            gains = {name: norm[name] - base_norm[name] for name in metrics}
            priority = [name for name, policy in important.items()
                        if gains[name] >= policy["min_gain"] - 1e-12
                        and delta >= -policy["composite_tolerance"] - 1e-12]
            row.update(composite=total, composite_delta=delta, metric_gains=gains,
                       important_metric_improvements=priority,
                       decision="PROMOTABLE_SCORE_ONLY" if delta > 1e-12 or priority else "NO_MEASURED_IMPROVEMENT")
        rows.append(row)
    promotable = [row for row in rows if row["decision"] == "PROMOTABLE_SCORE_ONLY"]
    selected = max(promotable, key=lambda row: (row["composite"],
                                                max((row["metric_gains"][m] for m in row["important_metric_improvements"]),
                                                    default=0))) if promotable else None
    return {"schema_version": "score-comparison-1", "profile_hash": identity(profile),
            "source_hash": profile["source_hash"], "scope_id": profile["scope_id"],
            "baseline": {"id": baseline.get("id"), "raw": baseline["vector"],
                         "normalized": base_norm, "composite": base_score},
            "candidates": rows, "selected_score_candidate_id": selected["id"] if selected else None,
            "status": "SCORE_CANDIDATE_ONLY" if selected else "NO_PROMOTABLE_SCORE_CANDIDATE",
            "scope": "fixed-profile component scoring; scientific, native and full-slide gates remain separate"}
