"""Generic views for the core app — currently just the health check."""

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET


@never_cache
@csrf_exempt
@require_GET
def health(_request):
    """Liveness check used by docker-compose healthcheck and external monitors.

    Intentionally minimal — does NOT touch the database, cache, or external
    services. A 200 here means "Gunicorn process is alive and accepting
    requests"; readiness/dependency checks should live elsewhere.
    """
    return JsonResponse({"status": "ok"})
