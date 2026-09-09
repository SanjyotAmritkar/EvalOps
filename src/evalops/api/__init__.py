"""HTTP API over the EvalOps persistence layer (FastAPI).

The application lives in :mod:`evalops.api.main` (``evalops.api.main:app``);
import it from there. This package's ``__init__`` deliberately stays free of
heavy imports so submodules like :mod:`evalops.api.schemas` can be imported
(e.g. by the Celery worker) without pulling in the FastAPI app and routes.
"""
