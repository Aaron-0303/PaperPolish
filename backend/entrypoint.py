import os
from threading import Lock

import main as core

TENCENT_MAAS_API_ROOT = os.getenv("TENCENT_MAAS_API_ROOT", "https://tokenhub.tencentmaas.com").rstrip("/")
_REMOTE_ROUTE_LOCK = Lock()
_original_remote_polish = core.remote_polish


def _uses_tencent_maas(model: str) -> bool:
    return model.strip().lower().startswith("hy-mt2")


def remote_polish_with_provider(req):
    """Route Hy-MT2 cloud model names to Tencent MaaS; keep other models on the existing API host."""
    target_base = TENCENT_MAAS_API_ROOT if _uses_tencent_maas(req.model) else core.REMOTE_API_BASE
    with _REMOTE_ROUTE_LOCK:
        previous_base = core.REMOTE_API_BASE
        core.REMOTE_API_BASE = target_base
        try:
            return _original_remote_polish(req)
        finally:
            core.REMOTE_API_BASE = previous_base


core.remote_polish = remote_polish_with_provider
app = core.app
