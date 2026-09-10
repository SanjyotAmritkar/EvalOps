"""Promote production traces into a replayable regression Dataset (Phase 8, CP 8.2).

One backend operation. It reads :class:`~evalops.domain.ProductionTrace` rows
and writes exactly one :class:`~evalops.domain.Dataset` plus one
:class:`~evalops.domain.DatasetCase` per selected trace, in request order,
preserving provenance:

* ``trace.input``            -> ``DatasetCase.input``
* ``trace.reference_output`` -> ``DatasetCase.expected_output``
* ``trace.id``               -> ``DatasetCase.source_trace_id``
* origin                     -> :attr:`CaseOrigin.PROMOTED_TRACE`

It never mutates a ``ProductionTrace`` and never substitutes ``trace.output``
as an oracle: a trace with no reference yields a case with
``expected_output=None``. If the ``DatasetCase`` model itself ever required a
reference, its :class:`DomainValidationError` would propagate and the whole
promotion would roll back -- the conflict is reported, not papered over.

The promoted ``Dataset`` is an ordinary ``Dataset``: it flows through the
existing Experiment -> Eval Runner -> statistical evidence -> release gate path
with no trace-specific handling anywhere downstream.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from evalops import domain
from evalops.db import (
    DatasetRepository,
    ProductionTraceRepository,
    ProjectRepository,
    RecordNotFound,
)
from evalops.domain.enums import CaseOrigin
from evalops.errors import ConfigError

#: Promotion always creates the first version of a dataset name; a repeat name
#: is a RecordConflict (409). Callers pick a fresh name or manage versions
#: through the normal dataset API.
_PROMOTED_VERSION = 1


def promote_traces_to_dataset(
    session: Session,
    *,
    project_id: str,
    trace_ids: Sequence[str],
    name: str,
) -> domain.Dataset:
    """Build one ``Dataset`` from the named production traces, in request order.

    The caller owns the transaction -- this never commits. The ``Dataset`` and
    all of its cases are added in a single flush, so any failure rolls the
    whole promotion back and every ``ProductionTrace`` row is left untouched.

    Raises:

    * :class:`~evalops.errors.ConfigError` (HTTP 422) -- an empty selection, a
      duplicate trace id, or a trace that belongs to another project.
    * :class:`~evalops.db.RecordNotFound` (HTTP 404) -- the project, or any
      selected trace id, is unknown.
    * :class:`~evalops.domain.errors.DomainValidationError` (HTTP 422) -- an
      invalid ``Dataset`` / ``DatasetCase`` (e.g. a blank name, or a reference
      the model requires but the trace lacks -- never invented).
    * :class:`~evalops.db.RecordConflict` (HTTP 409) -- ``(project, name,
      version)`` already exists.
    """
    ids = list(trace_ids)
    if not ids:
        raise ConfigError("at least one trace id is required to build a dataset")
    duplicates = sorted({tid for tid in ids if ids.count(tid) > 1})
    if duplicates:
        raise ConfigError(f"duplicate trace id(s) in the selection: {duplicates}")

    if ProjectRepository(session).get(project_id) is None:
        raise RecordNotFound(f"project {project_id!r} not found")

    traces = ProductionTraceRepository(session)
    cases: list[domain.DatasetCase] = []
    for tid in ids:
        trace = traces.get(tid)
        if trace is None:
            raise RecordNotFound(f"production trace {tid!r} not found")
        if trace.project_id != project_id:
            raise ConfigError(
                f"production trace {tid!r} belongs to project {trace.project_id!r}, "
                f"not {project_id!r}"
            )
        cases.append(
            domain.DatasetCase(
                input=trace.input,
                # The reference, if the caller recorded one -- never trace.output.
                expected_output=trace.reference_output,
                origin=CaseOrigin.PROMOTED_TRACE,
                source_trace_id=trace.id,
            )
        )

    dataset = domain.Dataset(
        project_id=project_id,
        name=name,
        version=_PROMOTED_VERSION,
        cases=tuple(cases),
    )
    return DatasetRepository(session).add(dataset)
