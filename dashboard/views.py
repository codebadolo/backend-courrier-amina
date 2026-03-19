# dashboard/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import logging

from .services.stats_service import StatsService

logger = logging.getLogger(__name__)


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def stats(self, request):
        try:
            period     = request.query_params.get("period", "month")
            start_date = request.query_params.get("start_date")
            end_date   = request.query_params.get("end_date")
            svc        = StatsService(request.user, request)
            data       = svc.get_stats(period, start_date, end_date)
            data.update({"period": period, "start_date": start_date, "end_date": end_date})
            return Response(data)
        except Exception as e:
            logger.error(f"Erreur stats: {e}", exc_info=True)
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=["get"])
    def trends(self, request):
        try:
            period     = request.query_params.get("period", "month")
            start_date = request.query_params.get("start_date")
            end_date   = request.query_params.get("end_date")
            svc        = StatsService(request.user, request)
            return Response(svc.get_trends(period, start_date, end_date))
        except Exception as e:
            logger.error(f"Erreur trends: {e}", exc_info=True)
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=["get"])
    def performance(self, request):
        try:
            if request.user.role not in ("admin", "direction", "chef"):
                return Response({"error": "Accès non autorisé"}, status=403)
            period     = request.query_params.get("period", "month")
            start_date = request.query_params.get("start_date")
            end_date   = request.query_params.get("end_date")
            svc        = StatsService(request.user, request)
            return Response(svc.get_performance(period, start_date, end_date))
        except Exception as e:
            logger.error(f"Erreur performance: {e}", exc_info=True)
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=["get"])
    def role_dashboard(self, request):
        try:
            period     = request.query_params.get("period", "month")
            start_date = request.query_params.get("start_date")
            end_date   = request.query_params.get("end_date")
            svc        = StatsService(request.user, request)
            data       = svc.get_dashboard_stats(period, start_date, end_date)
            data["user"] = {
                "id":      request.user.id,
                "nom":     f"{request.user.prenom} {request.user.nom}",
                "role":    request.user.role,
                "service": request.user.service.nom if request.user.service else None,
            }
            return Response(data)
        except Exception as e:
            logger.error(f"Erreur role_dashboard: {e}", exc_info=True)
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=["get"])
    def widgets(self, request):
        role = request.user.role
        WIDGETS = {
            "admin": [
                {"id": "kpi_principaux",       "title": "KPIs Principaux",          "size": "large",  "order": 1},
                {"id": "volume_courriers",      "title": "Volume par type",          "size": "medium", "order": 2},
                {"id": "performance_services",  "title": "Performance des services", "size": "large",  "order": 3},
                {"id": "performance_agents",    "title": "Top agents",               "size": "medium", "order": 4},
                {"id": "tendances",             "title": "Tendances",                "size": "large",  "order": 5},
                {"id": "delais_traitement",     "title": "Délais de traitement",     "size": "medium", "order": 6},
                {"id": "courriers_urgents",     "title": "Courriers urgents",        "size": "small",  "order": 7},
                {"id": "evolution_mensuelle",   "title": "Évolution 12 mois",        "size": "large",  "order": 8},
            ],
            "direction": [
                {"id": "stats_globales",        "title": "Statistiques globales",    "size": "large",  "order": 1},
                {"id": "performance_services",  "title": "Performance des services", "size": "large",  "order": 2},
                {"id": "top_services",          "title": "Top services",             "size": "medium", "order": 3},
                {"id": "tendances",             "title": "Évolution mensuelle",      "size": "large",  "order": 4},
                {"id": "repartition_types",     "title": "Répartition par type",     "size": "medium", "order": 5},
            ],
            "chef": [
                {"id": "stats_service",         "title": "Statistiques du service",  "size": "large",  "order": 1},
                {"id": "performance_agents",    "title": "Performance des agents",   "size": "large",  "order": 2},
                {"id": "repartition_priorites", "title": "Priorités",                "size": "medium", "order": 3},
                {"id": "a_traiter_aujourdhui",  "title": "À traiter aujourd'hui",    "size": "small",  "order": 4},
                {"id": "courriers_urgents",     "title": "Courriers urgents",        "size": "medium", "order": 5},
                {"id": "charge_travail",        "title": "Charge de travail",        "size": "medium", "order": 6},
            ],
            "collaborateur": [
                {"id": "stats_personnelles",    "title": "Mes statistiques",         "size": "large",  "order": 1},
                {"id": "prochaines_echeances",  "title": "Prochaines échéances",     "size": "medium", "order": 2},
                {"id": "evolution_activite",    "title": "Mon activité",             "size": "medium", "order": 3},
                {"id": "performance_mensuelle", "title": "Ma performance mensuelle", "size": "medium", "order": 4},
            ],
            "agent_service": [
                {"id": "stats_personnelles",    "title": "Mes statistiques",         "size": "large",  "order": 1},
                {"id": "prochaines_echeances",  "title": "Mes échéances",            "size": "medium", "order": 2},
                {"id": "evolution_activite",    "title": "Mon activité",             "size": "medium", "order": 3},
            ],
            "agent_courrier": [
                {"id": "stats_quotidiennes",    "title": "Aujourd'hui",              "size": "large",  "order": 1},
                {"id": "a_imputer",             "title": "À imputer",                "size": "small",  "order": 2},
                {"id": "evolution_reception",   "title": "Évolution des réceptions", "size": "large",  "order": 3},
                {"id": "repartition_canaux",    "title": "Canaux de réception",      "size": "medium", "order": 4},
                {"id": "derniers_courriers",    "title": "Derniers courriers reçus", "size": "large",  "order": 5},
            ],
            "archiviste": [
                {"id": "stats_archivage",       "title": "Statistiques d'archivage", "size": "large",  "order": 1},
                {"id": "repartition_archives",  "title": "Archives par type",        "size": "medium", "order": 2},
                {"id": "archives_par_mois",     "title": "Archives par mois",        "size": "large",  "order": 3},
                {"id": "documents_a_archiver",  "title": "Documents à archiver",     "size": "large",  "order": 4},
            ],
        }
        return Response({
            "role":             role,
            "widgets":          WIDGETS.get(role, WIDGETS["collaborateur"]),
            "can_export":       role in ("admin", "direction", "chef"),
            "can_refresh":      True,
            "refresh_interval": 300,
        })

    @action(detail=False, methods=["get"])
    def export(self, request):
        if request.user.role not in ("admin", "direction", "chef"):
            return Response({"error": "Export non autorisé"}, status=403)
        period = request.query_params.get("period", "month")
        fmt    = request.query_params.get("format", "json")
        try:
            svc  = StatsService(request.user, request)
            data = svc.get_dashboard_stats(period)
            if fmt == "json":
                return Response(data)
            return Response({"message": f"Export {fmt.upper()} en cours de développement"}, status=501)
        except Exception as e:
            return Response({"error": str(e)}, status=500)