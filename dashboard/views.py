# dashboard/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q, Avg, F, ExpressionWrapper, DurationField
from django.utils import timezone
from datetime import timedelta, datetime
import logging
from courriers.models import Courrier, Imputation
from core.models import Service

logger = logging.getLogger(__name__)

class DashboardViewSet(viewsets.ViewSet):
    """
    ViewSet pour le dashboard avec statistiques
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Statistiques générales du dashboard
        """
        try:
            # Récupérer les filtres
            period = request.query_params.get('period', 'today')
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            service_filter = request.query_params.get('service', 'all')
            
            # Calculer les dates selon la période
            today = timezone.now().date()
            date_filters = self._get_date_filters(period, start_date, end_date)
            
            # Base queryset
            queryset = Courrier.objects.filter(**date_filters, archived=False)
            
            # Filtrer par service si spécifié
            if service_filter != 'all':
                service = Service.objects.filter(nom=service_filter).first()
                if service:
                    queryset = queryset.filter(service_impute=service)
            
            # Calculer les statistiques
            total = queryset.count()
            entrants = queryset.filter(type='entrant').count()
            sortants = queryset.filter(type='sortant').count()
            internes = queryset.filter(type='interne').count()
            
            received = queryset.count()
            in_progress = queryset.filter(statut__in=['recu', 'impute', 'traitement']).count()
            late = queryset.filter(
                date_echeance__lt=today,
                statut__in=['recu', 'impute', 'traitement']
            ).count()
            archived = Courrier.objects.filter(
                **date_filters, 
                archived=True
            ).count()
            
            # Courriers urgents
            urgent = queryset.filter(priorite='urgente').count()
            
            # Délai moyen de traitement
            processed_courriers = Courrier.objects.filter(
                **date_filters,
                statut='repondu',
                date_reception__isnull=False,
                date_cloture__isnull=False
            )
            
            average_processing_time = 0
            if processed_courriers.exists():
                total_days = sum([
                    (c.date_cloture - c.date_reception).days 
                    for c in processed_courriers
                ])
                average_processing_time = round(total_days / processed_courriers.count(), 1)
            
            stats_data = {
                'received': received,
                'in_progress': in_progress,
                'late': late,
                'archived': archived,
                'urgent': urgent,
                'total': total,
                'entrants': entrants,
                'sortants': sortants,
                'internes': internes,
                'average_processing_time': average_processing_time,
                'period': period,
                'start_date': start_date,
                'end_date': end_date,
                'service': service_filter
            }
            
            return Response(stats_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Erreur stats dashboard: {e}", exc_info=True)
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def trends(self, request):
        """
        Tendances des courriers
        """
        try:
            period = request.query_params.get('period', 'today')
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            date_filters = self._get_date_filters(period, start_date, end_date)
            
            # Courriers cette période
            current_period = Courrier.objects.filter(**date_filters, archived=False).count()
            
            # Courriers période précédente
            previous_filters = self._get_previous_period_filters(period, start_date, end_date)
            previous_period = Courrier.objects.filter(**previous_filters, archived=False).count()
            
            # Calculer la tendance
            received_trend = 0
            if previous_period > 0:
                received_trend = round(((current_period - previous_period) / previous_period) * 100, 1)
            
            # Tendances par type
            trends_data = {
                'receivedTrend': received_trend,
                'currentPeriod': current_period,
                'previousPeriod': previous_period,
                'dailyData': self._get_daily_trends(period),
                'typeDistribution': {
                    'entrants': Courrier.objects.filter(**date_filters, type='entrant', archived=False).count(),
                    'sortants': Courrier.objects.filter(**date_filters, type='sortant', archived=False).count(),
                    'internes': Courrier.objects.filter(**date_filters, type='interne', archived=False).count(),
                }
            }
            
            return Response(trends_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Erreur trends dashboard: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def performance(self, request):
        """
        Performance par service
        """
        try:
            period = request.query_params.get('period', 'today')
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            date_filters = self._get_date_filters(period, start_date, end_date)
            
            performance_data = []
            services = Service.objects.all()
            
            for service in services:
                # Courriers imputés à ce service
                courriers_service = Courrier.objects.filter(
                    **date_filters,
                    service_impute=service,
                    archived=False
                )
                
                total = courriers_service.count()
                processed = courriers_service.filter(statut='repondu').count()
                late = courriers_service.filter(
                    date_echeance__lt=timezone.now().date(),
                    statut__in=['recu', 'impute', 'traitement']
                ).count()
                
                # Taux de complétion
                completion_rate = 0
                if total > 0:
                    completion_rate = round((processed / total) * 100, 1)
                
                # Délai moyen de traitement pour ce service
                processed_by_service = courriers_service.filter(
                    statut='repondu',
                    date_reception__isnull=False,
                    date_cloture__isnull=False
                )
                
                average_time = 0
                if processed_by_service.exists():
                    total_days = sum([
                        (c.date_cloture - c.date_reception).days 
                        for c in processed_by_service
                    ])
                    average_time = round(total_days / processed_by_service.count(), 1)
                
                performance_data.append({
                    'service': service.nom,
                    'service_id': service.id,
                    'processed': processed,
                    'total': total,
                    'late': late,
                    'completionRate': completion_rate,
                    'averageTime': average_time
                })
            
            return Response(performance_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Erreur performance dashboard: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_date_filters(self, period, start_date_str, end_date_str):
        """
        Retourne les filtres de date selon la période
        """
        today = timezone.now().date()
        
        if period == 'today':
            return {'date_reception': today}
        elif period == 'week':
            start_of_week = today - timedelta(days=today.weekday())
            return {'date_reception__gte': start_of_week, 'date_reception__lte': today}
        elif period == 'month':
            start_of_month = today.replace(day=1)
            return {'date_reception__gte': start_of_month, 'date_reception__lte': today}
        elif period == 'quarter':
            current_quarter = (today.month - 1) // 3 + 1
            start_of_quarter = datetime(today.year, 3 * current_quarter - 2, 1).date()
            return {'date_reception__gte': start_of_quarter, 'date_reception__lte': today}
        elif period == 'custom' and start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            return {'date_reception__gte': start_date, 'date_reception__lte': end_date}
        else:
            # Par défaut, ce mois
            start_of_month = today.replace(day=1)
            return {'date_reception__gte': start_of_month, 'date_reception__lte': today}
    
    def _get_previous_period_filters(self, period, start_date_str, end_date_str):
        """
        Retourne les filtres pour la période précédente
        """
        today = timezone.now().date()
        
        if period == 'today':
            yesterday = today - timedelta(days=1)
            return {'date_reception': yesterday}
        elif period == 'week':
            start_of_week = today - timedelta(days=today.weekday())
            start_of_previous_week = start_of_week - timedelta(days=7)
            end_of_previous_week = start_of_week - timedelta(days=1)
            return {'date_reception__gte': start_of_previous_week, 'date_reception__lte': end_of_previous_week}
        elif period == 'month':
            start_of_month = today.replace(day=1)
            end_of_previous_month = start_of_month - timedelta(days=1)
            start_of_previous_month = end_of_previous_month.replace(day=1)
            return {'date_reception__gte': start_of_previous_month, 'date_reception__lte': end_of_previous_month}
        elif period == 'quarter':
            current_quarter = (today.month - 1) // 3 + 1
            start_of_quarter = datetime(today.year, 3 * current_quarter - 2, 1).date()
            if current_quarter == 1:
                # Trimestre précédent = Q4 de l'année précédente
                start_of_previous_quarter = datetime(today.year - 1, 10, 1).date()
                end_of_previous_quarter = datetime(today.year - 1, 12, 31).date()
            else:
                start_of_previous_quarter = datetime(today.year, 3 * (current_quarter - 1) - 2, 1).date()
                end_of_previous_quarter = start_of_quarter - timedelta(days=1)
            return {'date_reception__gte': start_of_previous_quarter, 'date_reception__lte': end_of_previous_quarter}
        else:
            # Par défaut, mois précédent
            start_of_month = today.replace(day=1)
            end_of_previous_month = start_of_month - timedelta(days=1)
            start_of_previous_month = end_of_previous_month.replace(day=1)
            return {'date_reception__gte': start_of_previous_month, 'date_reception__lte': end_of_previous_month}
    
    def _get_daily_trends(self, period):
        """
        Génère des données quotidiennes pour les graphiques
        """
        today = timezone.now().date()
        daily_data = []
        
        if period == 'week':
            for i in range(7):
                day = today - timedelta(days=6 - i)
                count = Courrier.objects.filter(
                    date_reception=day,
                    archived=False
                ).count()
                daily_data.append({
                    'date': day.strftime('%d/%m'),
                    'count': count
                })
        elif period == 'month':
            for i in range(4):
                week_start = today - timedelta(days=28 - i*7)
                week_end = week_start + timedelta(days=6)
                count = Courrier.objects.filter(
                    date_reception__gte=week_start,
                    date_reception__lte=week_end,
                    archived=False
                ).count()
                daily_data.append({
                    'date': f'Sem {i+1}',
                    'count': count
                })
        
        return daily_data