"""BluePyEModel e-feature score validation shared by Task 2 and Task 3."""

import json
import logging
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import entitysdk
from entitysdk.registration.validation_result import register_validation_result
from entitysdk.types import ID

L = logging.getLogger(__name__)

OVERALL_RESULT_NAME = "E-feature score validation"
PROTOCOL_RESULT_PREFIX = "E-feature validation"


@dataclass(frozen=True)
class ResolvedValidationSettings:
    """Validation protocols and scoring after all defaults are applied."""

    validation_protocols: list[str]
    validation_protocols_only: bool
    validation_function: str
    validation_threshold: float


def flagged_validation_protocols(features_path: Path) -> list[str]:
    """Return the protocols flagged ``validation`` in a fitness-calculator configuration.

    Task 1 flags the amplitudes marked ``is_validation``; these protocols are excluded
    from the optimisation even when Task 2 lists no validation protocols.
    """
    data = json.loads(features_path.read_text(encoding="utf-8"))
    return [p["name"] for p in data.get("protocols", []) if p.get("validation")]


def aggregate(scores: list[float], validation_function: str) -> float:
    """Aggregate e-feature scores the way BluePyEModel's validation functions do."""
    from numpy import max as np_max, mean as np_mean  # ruff: ignore[import-outside-top-level]

    if not scores:
        msg = "Cannot aggregate an empty list of scores."
        raise ValueError(msg)
    if validation_function == "max_score":
        return float(np_max(scores))
    if validation_function == "mean_score":
        return float(np_mean(scores))
    msg = f"Unknown validation function {validation_function!r}."
    raise ValueError(msg)


def summarise_model(model: Any, settings: ResolvedValidationSettings) -> dict:
    """Build the per-protocol and overall validation summary of a scored BPEM EModel."""
    from bluepyemodel.tools.utils import (  # ruff: ignore[import-outside-top-level]
        get_protocol_name,
    )

    all_scores = {**model.scores, **model.scores_validation}
    protocols: dict[str, dict] = {}
    for feature_name, score in sorted(all_scores.items()):
        protocol = get_protocol_name(feature_name)
        entry = protocols.setdefault(
            protocol,
            {"validation": feature_name in model.scores_validation, "features": {}},
        )
        entry["features"][feature_name] = {
            "score": float(score),
            "model_value": model.features.get(feature_name),
        }
    for entry in protocols.values():
        entry["score"] = aggregate(
            [f["score"] for f in entry["features"].values()], settings.validation_function
        )
        entry["passed"] = entry["score"] < settings.validation_threshold

    overall_scores = (
        list(model.scores_validation.values())
        if settings.validation_protocols_only
        else list(all_scores.values())
    )
    overall_score = aggregate(overall_scores, settings.validation_function)
    return {
        "passed": overall_score < settings.validation_threshold,
        "score": overall_score,
        "settings": {
            "validation_protocols": settings.validation_protocols,
            "validation_protocols_only": settings.validation_protocols_only,
            "validation_function": settings.validation_function,
            "validation_threshold": settings.validation_threshold,
        },
        "protocols": protocols,
    }


def score_model(
    access_point: Any,
    *,
    seed: int,
    settings: ResolvedValidationSettings,
    mapper: Any = map,
    cell_evaluator: Any = None,
) -> tuple[dict, Any]:
    """Score the stored model of ``seed`` and write the verdict back to ``final.json``.

    Like ``bluepyemodel.validation.validation.validate``, but the verdict honours
    ``validation_protocols_only``. Must run from the BluePyEModel working directory.
    """
    from bluepyemodel.evaluation.evaluation import (  # ruff: ignore[import-outside-top-level]
        compute_responses,
        get_evaluator_from_access_point,
    )
    from bluepyemodel.validation.validation import (  # ruff: ignore[import-outside-top-level]
        compute_scores,
    )

    if cell_evaluator is None:
        cell_evaluator = get_evaluator_from_access_point(
            access_point, include_validation_protocols=True
        )
    models = compute_responses(
        access_point, cell_evaluator=cell_evaluator, map_function=mapper, seeds=[seed]
    )
    if len(models) != 1:
        msg = f"Expected one optimised model to validate for seed {seed}, got {len(models)}."
        raise RuntimeError(msg)
    model = models[0]
    compute_scores(model, settings.validation_protocols)
    summary = summarise_model(model, settings)
    model.passed_validation = bool(summary["passed"])
    access_point.store_or_update_emodel(model)
    L.info(
        "E-model validation %s (score=%.3f, threshold=%.3f).",
        "passed" if summary["passed"] else "failed",
        summary["score"],
        settings.validation_threshold,
    )
    return summary, cell_evaluator


def score_model_worker(
    access_point_factory: Callable[..., Any],
    access_point_kwargs: dict,
    working_dir: Path,
    seed: int,
    settings: ResolvedValidationSettings,
) -> dict:
    """Build the access point in ``working_dir`` and score the model; return the summary."""
    import neuron  # ruff: ignore[import-outside-top-level]

    from obi_one.utils.filesystem import chdir  # ruff: ignore[import-outside-top-level]

    with chdir(working_dir):
        # NEURON only auto-loads compiled mechanisms from the cwd at import time.
        neuron.load_mechanisms(str(working_dir))
        access_point = access_point_factory(**access_point_kwargs)
        summary, _ = score_model(access_point, seed=seed, settings=settings)
    return summary


def score_model_isolated(
    *,
    access_point_factory: Callable[..., Any],
    access_point_kwargs: dict,
    working_dir: Path,
    seed: int,
    settings: ResolvedValidationSettings,
) -> dict:
    """Run :func:`score_model` in a freshly spawned process.

    Cells left in NEURON by earlier evaluators (e.g. the optimisation) change the
    variable-step integration of later simulations, so scores of the same parameters
    depend on what ran before in the process. A spawned process starts from a clean
    NEURON state. ``access_point_factory`` must be a picklable top-level function.
    """
    with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as pool:
        return pool.submit(
            score_model_worker,
            access_point_factory,
            access_point_kwargs,
            working_dir,
            seed,
            settings,
        ).result()


def register_validation_results(
    *,
    client: entitysdk.Client,
    summary: dict,
    validated_entity_id: ID,
    authorized_public: bool,
    name_suffix: str = "",
    figure_files: list[Path] | None = None,
) -> list[str]:
    """Register overall and per-validation-protocol results; return the new IDs.

    entitysdk skips results whose name already exists on the entity.
    """
    generated: list[str] = []
    overall = register_validation_result(
        client=client,
        name=f"{OVERALL_RESULT_NAME}{name_suffix}",
        passed=bool(summary["passed"]),
        validated_entity_id=validated_entity_id,
        authorized_public=authorized_public,
        figure_files=figure_files,
        details_text=json.dumps(summary, indent=2),
    )
    if overall is not None:
        generated.append(str(overall.id))
    for protocol, entry in summary["protocols"].items():
        if not entry["validation"]:
            continue
        result = register_validation_result(
            client=client,
            name=f"{PROTOCOL_RESULT_PREFIX}: {protocol}{name_suffix}",
            passed=bool(entry["passed"]),
            validated_entity_id=validated_entity_id,
            authorized_public=authorized_public,
            details_text=json.dumps(
                {"protocol": protocol, "settings": summary["settings"], **entry}, indent=2
            ),
        )
        if result is not None:
            generated.append(str(result.id))
    return generated
