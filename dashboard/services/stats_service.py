# dashboard/services/stats_service.py
#
# Corrections :
#   1. Les stats sont calculées sur le même périmètre que get_queryset()
#      (même filtrage par rôle/service/user)
#   2. Les courriers sortants utilisent date_envoi (pas date_reception)
#   3. Le filtre de période s'adapte au type de courrier

import logging
from datetime import timedelta, datetime, date
from django.utils import timezone
from django.db.models import Count, Q

from courriers.models import Courrier
from core.models import Service
from users.models import User

logger = logging.getLogger(__name__)


class StatsService:
    """
    Calcule les statistiques du dashboard en respectant exactement
    le même périmètre de visibilité que CourrierViewSet.get_queryset().
    """

    def __init__(self, user, request=None):
        self.user    = user
        self.request = request
        self.today   = timezone.now().date()

    # ─────────────────────────────────────────────────────────────
    # QUERYSET DE BASE — même logique que CourrierViewSet
    # ─────────────────────────────────────────────────────────────

    def _base_queryset(self):
        """
        Retourne le queryset filtré selon le rôle,
        SANS filtre de période (on l'applique après).
        Reproduit exactement get_queryset() de CourrierViewSet.
        """
        user = self.user
        qs   = Courrier.objects.all()

        if user.is_superuser or user.role == 'admin':
            pass  # tout visible

        elif user.role == 'direction':
            qs = qs.filter(confidentialite__in=['normale', 'restreinte'])

        elif user.role == 'chef':
            if user.service:
                qs = qs.filter(
                    Q(service_impute=user.service) |
                    Q(service_actuel=user.service) |
                    Q(responsable_actuel=user) |
                    Q(created_by=user)
                )
            else:
                qs = qs.none()

        elif user.role == 'agent_service':
            if user.service:
                qs = qs.filter(
                    Q(service_actuel=user.service) &
                    Q(responsable_actuel=user)
                )
            else:
                qs = qs.none()

        elif user.role == 'agent_courrier':
            if user.service:
                qs = qs.filter(
                    Q(responsable_actuel=user) |
                    Q(created_by=user)
                )
            else:
                qs = qs.filter(created_by=user)

        elif user.role == 'collaborateur':
            if user.service:
                qs = qs.filter(service_actuel=user.service)

        elif user.role == 'archiviste':
            qs = qs.filter(archived=True)

        return qs.distinct()

    # ─────────────────────────────────────────────────────────────
    # FILTRE DE PÉRIODE — adapté au type de courrier
    # Les sortants utilisent date_envoi, les entrants/internes date_reception
    # ─────────────────────────────────────────────────────────────

    def _apply_period(self, qs, period, start_date=None, end_date=None):
        """
        Applique le filtre de période en tenant compte du type de courrier :
        - entrants/internes → date_reception
        - sortants          → date_envoi OU date_reception
        On filtre sur (date_reception OU date_envoi) dans la période.
        """
        start, end = self._period_range(period, start_date, end_date)
        if start is None:
            return qs  # pas de filtre de période

        return qs.filter(
            Q(date_reception__gte=start, date_reception__lte=end) |
            Q(date_envoi__gte=start,     date_envoi__lte=end)
        )

    def _apply_period_strict(self, qs, period, type_courrier=None,
                              start_date=None, end_date=None):
        """
        Filtre strict selon le type :
        - sortant  → date_envoi
        - entrant/interne → date_reception
        - None     → les deux (OR)
        """
        start, end = self._period_range(period, start_date, end_date)
        if start is None:
            return qs

        if type_courrier == 'sortant':
            return qs.filter(
                Q(date_envoi__gte=start, date_envoi__lte=end) |
                Q(date_reception__gte=start, date_reception__lte=end)
            )
        elif type_courrier in ('entrant', 'interne'):
            return qs.filter(
                date_reception__gte=start, date_reception__lte=end
            )
        else:
            return qs.filter(
                Q(date_reception__gte=start, date_reception__lte=end) |
                Q(date_envoi__gte=start,     date_envoi__lte=end)
            )

    # ─────────────────────────────────────────────────────────────
    # STATS  →  /dashboard/stats/
    # ─────────────────────────────────────────────────────────────

    def get_stats(self, period="month", start_date=None, end_date=None):
        qs_all    = self._base_queryset()
        qs_period = self._apply_period(qs_all, period, start_date, end_date)

        # Ne pas filtrer les archivés sauf pour l'archiviste
        if self.user.role != 'archiviste':
            qs_period = qs_period.filter(archived=False)

        today = self.today
        return self._build_kpis(qs_period)

    def _build_kpis(self, qs):
        today = self.today

        # Courriers sortants dans le queryset
        qs_sortants = qs.filter(type='sortant')
        qs_entrants = qs.filter(type='entrant')
        qs_internes = qs.filter(type='interne')

        # Délai moyen : date_reception → date_cloture
        processed_qs = qs.filter(
            statut='repondu',
            date_reception__isnull=False,
            date_cloture__isnull=False,
        )

        return {
            "received":                qs.count(),
            "total":                   qs.count(),
            "entrants":                qs_entrants.count(),
            "sortants":                qs_sortants.count(),
            "internes":                qs_internes.count(),
            "in_progress":             qs.filter(
                                           statut__in=['recu', 'impute', 'traitement']
                                       ).count(),
            "late":                    qs.filter(
                                           date_echeance__lt=today,
                                           statut__in=['recu', 'impute', 'traitement']
                                       ).count(),
            "urgent":                  qs.filter(priorite='urgente').count(),
            "archived":                qs.filter(statut='repondu').count(),
            "repondus":                qs.filter(statut='repondu').count(),
            "average_processing_time": self._delai_moyen(processed_qs),
            # Détail par statut
            "par_statut": {
                s: qs.filter(statut=s).count()
                for s in ['recu', 'impute', 'traitement', 'repondu', 'archive']
            },
            # Données supplémentaires courriers sortants
            "sortants_detail": {
                "envoyes":   qs_sortants.filter(statut='repondu').count(),
                "en_cours":  qs_sortants.filter(
                                 statut__in=['recu', 'impute', 'traitement']
                             ).count(),
                "brouillon": qs_sortants.filter(statut='recu').count(),
            },
        }

    # ─────────────────────────────────────────────────────────────
    # TRENDS  →  /dashboard/trends/
    # ─────────────────────────────────────────────────────────────

    def get_trends(self, period="month", start_date=None, end_date=None):
        qs_base = self._base_queryset()
        if self.user.role != 'archiviste':
            qs_base = qs_base.filter(archived=False)

        qs_curr = self._apply_period(qs_base, period, start_date, end_date)
        qs_prev = self._apply_period_prev(qs_base, period, start_date, end_date)

        current  = qs_curr.count()
        previous = qs_prev.count()

        return {
            "receivedTrend":    round((current - previous) / previous * 100, 1) if previous else 0,
            "currentPeriod":    current,
            "previousPeriod":   previous,
            "dailyData":        self._daily_data(period),
            "typeDistribution": {
                "entrants": qs_curr.filter(type='entrant').count(),
                "sortants": qs_curr.filter(type='sortant').count(),
                "internes": qs_curr.filter(type='interne').count(),
            },
        }

    # ─────────────────────────────────────────────────────────────
    # PERFORMANCE  →  /dashboard/performance/
    # ─────────────────────────────────────────────────────────────

    def get_performance(self, period="month", start_date=None, end_date=None):
        today   = self.today
        role    = self.user.role

        if role == 'chef' and self.user.service:
            membres = User.objects.filter(service=self.user.service, actif=True)
            result  = []
            for agent in membres:
                qs_agent = self._base_queryset().filter(
                    Q(responsable_actuel=agent) | Q(agent_traitant=agent)
                )
                qs_agent = self._apply_period(qs_agent, period, start_date, end_date)
                total    = qs_agent.count()
                if total == 0:
                    continue
                proc = qs_agent.filter(statut='repondu').count()
                late = qs_agent.filter(
                    date_echeance__lt=today,
                    statut__in=['recu', 'impute', 'traitement']
                ).count()
                result.append({
                    "service":        f"{agent.prenom} {agent.nom}",
                    "service_id":     agent.id,
                    "total":          total,
                    "processed":      proc,
                    "late":           late,
                    "completionRate": round(proc / total * 100, 1),
                    "averageTime":    self._delai_moyen(qs_agent),
                })
            return sorted(result, key=lambda x: x["completionRate"], reverse=True)

        # Admin / direction → par service
        result = []
        for svc in Service.objects.all():
            qs_svc = Courrier.objects.filter(
                Q(service_impute=svc) | Q(service_actuel=svc),
                archived=False
            )
            qs_svc = self._apply_period(qs_svc, period, start_date, end_date)
            total  = qs_svc.count()
            if total == 0:
                continue
            proc = qs_svc.filter(statut='repondu').count()
            late = qs_svc.filter(
                date_echeance__lt=today,
                statut__in=['recu', 'impute', 'traitement']
            ).count()
            result.append({
                "service":        svc.nom,
                "service_id":     svc.id,
                "total":          total,
                "processed":      proc,
                "late":           late,
                "completionRate": round(proc / total * 100, 1),
                "averageTime":    self._delai_moyen(qs_svc),
            })
        return sorted(result, key=lambda x: x["completionRate"], reverse=True)

    # ─────────────────────────────────────────────────────────────
    # ROLE DASHBOARD  →  /dashboard/role-dashboard/
    # ─────────────────────────────────────────────────────────────

    def get_dashboard_stats(self, period="month", start_date=None, end_date=None):
        role        = self.user.role
        stats       = self.get_stats(period, start_date, end_date)
        trends      = self.get_trends(period, start_date, end_date)
        performance = self.get_performance(period, start_date, end_date)
        extra       = {}

        if role in ('admin', 'direction'):
            extra['evolution_mensuelle'] = self._evolution_12_mois()
            extra['top_agents']          = self._top_agents()
            extra['courriers_urgents']   = self._courriers_urgents()

        elif role == 'chef' and self.user.service:
            extra['service']               = {'id': self.user.service.id, 'nom': self.user.service.nom}
            extra['courriers_urgents']     = self._courriers_urgents(service=self.user.service)
            extra['a_traiter_aujourd_hui'] = self._a_traiter_aujourd_hui(service=self.user.service)
            extra['charge_travail']        = self._charge_travail(self.user.service)

        elif role in ('collaborateur', 'agent_service'):
            extra['prochaines_echeances']  = self._prochaines_echeances()
            extra['performance_mensuelle'] = self._performance_mensuelle()

        elif role == 'agent_courrier':
            qs_base = self._base_queryset().filter(archived=False)
            extra['derniers_courriers']     = self._derniers_courriers()
            extra['imputations_en_attente'] = self._imputations_en_attente()
            extra['repartition_canaux']     = list(
                qs_base.values('canal').annotate(count=Count('id')).order_by('-count')
            )

        elif role == 'archiviste':
            extra['archives_par_mois']    = self._archives_par_mois()
            extra['documents_a_archiver'] = self._documents_a_archiver()

        return {
            'role':        role,
            'stats':       stats,
            'trends':      trends,
            'performance': performance,
            **extra,
        }

    # ─────────────────────────────────────────────────────────────
    # Données spécialisées
    # ─────────────────────────────────────────────────────────────

    def _courriers_urgents(self, service=None, limit=10):
        qs = self._base_queryset().filter(
            priorite='urgente', archived=False,
            statut__in=['recu', 'impute', 'traitement']
        )
        if service:
            qs = qs.filter(Q(service_impute=service) | Q(service_actuel=service))
        return list(qs.order_by('date_echeance')[:limit].values(
            'id', 'reference', 'objet', 'statut', 'priorite',
            'date_echeance', 'expediteur_nom', 'service_impute__nom', 'type'
        ))

    def _a_traiter_aujourd_hui(self, service=None):
        qs = self._base_queryset().filter(
            archived=False, statut__in=['recu', 'impute', 'traitement'],
            date_echeance=self.today
        )
        if service:
            qs = qs.filter(Q(service_impute=service) | Q(service_actuel=service))
        return {
            'count':     qs.count(),
            'courriers': list(qs[:10].values('id', 'reference', 'objet', 'priorite', 'statut')),
        }

    def _prochaines_echeances(self, days=7):
        limit = self.today + timedelta(days=days)
        qs    = self._base_queryset().filter(
            archived=False, statut__in=['recu', 'impute', 'traitement'],
            date_echeance__gte=self.today, date_echeance__lte=limit
        ).order_by('date_echeance')
        return list(qs[:10].values('id', 'reference', 'objet', 'priorite', 'date_echeance', 'statut'))

    def _charge_travail(self, service):
        membres = User.objects.filter(service=service, actif=True)
        return sorted([
            {
                'agent':    f"{a.prenom} {a.nom}",
                'agent_id': a.id,
                'en_cours': Courrier.objects.filter(
                    Q(responsable_actuel=a) | Q(agent_traitant=a),
                    archived=False, statut__in=['recu', 'impute', 'traitement']
                ).count(),
            }
            for a in membres
        ], key=lambda x: x['en_cours'], reverse=True)

    def _derniers_courriers(self, limit=10):
        return list(
            self._base_queryset().filter(archived=False)
            .order_by('-created_at')[:limit]
            .values('id', 'reference', 'objet', 'type', 'statut', 'priorite',
                    'date_reception', 'expediteur_nom', 'service_impute__nom')
        )

    def _imputations_en_attente(self):
        return list(
            self._base_queryset().filter(statut='recu', archived=False)
            .order_by('date_reception')[:20]
            .values('id', 'reference', 'objet', 'type', 'priorite',
                    'date_reception', 'expediteur_nom')
        )

    def _documents_a_archiver(self, limit=20):
        return list(
            Courrier.objects.filter(statut='repondu', archived=False)
            .order_by('date_cloture')[:limit]
            .values('id', 'reference', 'objet', 'type', 'date_cloture', 'service_impute__nom')
        )

    def _archives_par_mois(self, months=6):
        today  = self.today
        result = []
        for i in range(months - 1, -1, -1):
            deb, fin = self._month_range(today, i)
            count    = Courrier.objects.filter(
                archived=True,
                date_archivage__gte=deb, date_archivage__lte=fin
            ).count()
            result.append({'date': deb.strftime('%b %Y'), 'count': count})
        return result

    def _evolution_12_mois(self):
        today  = self.today
        result = []
        for i in range(11, -1, -1):
            deb, fin = self._month_range(today, i)
            qs       = Courrier.objects.filter(archived=False).filter(
                Q(date_reception__gte=deb, date_reception__lte=fin) |
                Q(date_envoi__gte=deb,     date_envoi__lte=fin)
            )
            result.append({
                'mois':     deb.strftime('%b %Y'),
                'total':    qs.count(),
                'entrants': qs.filter(type='entrant').count(),
                'sortants': qs.filter(type='sortant').count(),
                'internes': qs.filter(type='interne').count(),
            })
        return result

    def _performance_mensuelle(self, months=6):
        today  = self.today
        result = []
        for i in range(months - 1, -1, -1):
            deb, fin = self._month_range(today, i)
            qs       = self._base_queryset().filter(
                Q(date_reception__gte=deb, date_reception__lte=fin) |
                Q(date_envoi__gte=deb,     date_envoi__lte=fin)
            )
            result.append({
                'mois':     deb.strftime('%b %Y'),
                'total':    qs.count(),
                'termines': qs.filter(statut='repondu').count(),
            })
        return result

    def _top_agents(self, limit=5):
        return list(
            Courrier.objects.filter(archived=False, statut='repondu')
            .values('agent_traitant__prenom', 'agent_traitant__nom', 'agent_traitant__id')
            .annotate(total=Count('id'))
            .order_by('-total')[:limit]
        )

    # ─────────────────────────────────────────────────────────────
    # Daily data pour trends?.dailyData
    # ─────────────────────────────────────────────────────────────

    def _daily_data(self, period):
        today = self.today
        data  = []
        role  = self.user.role

        def count_for(day_start, day_end=None):
            qs = self._base_queryset()
            if role != 'archiviste':
                qs = qs.filter(archived=False)
            if day_end is None:
                return qs.filter(
                    Q(date_reception=day_start) | Q(date_envoi=day_start)
                ).count()
            else:
                return qs.filter(
                    Q(date_reception__gte=day_start, date_reception__lte=day_end) |
                    Q(date_envoi__gte=day_start,     date_envoi__lte=day_end)
                ).count()

        if period in ('today', 'week'):
            for i in range(6, -1, -1):
                day = today - timedelta(days=i)
                data.append({'date': day.strftime('%d/%m'), 'count': count_for(day)})

        elif period == 'month':
            for i in range(4):
                ws = today - timedelta(days=27 - i * 7)
                we = ws + timedelta(days=6)
                data.append({'date': f'Sem {i+1}', 'count': count_for(ws, we)})

        elif period in ('quarter', 'year'):
            months = 12 if period == 'year' else 3
            for i in range(months - 1, -1, -1):
                deb, fin = self._month_range(today, i)
                data.append({'date': deb.strftime('%b'), 'count': count_for(deb, fin)})

        return data

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _delai_moyen(self, qs):
        try:
            items = qs.filter(date_reception__isnull=False, date_cloture__isnull=False)
            if not items.exists():
                return 0
            return round(
                sum((c.date_cloture - c.date_reception).days for c in items) / items.count(), 1
            )
        except Exception:
            return 0

    def _month_range(self, ref_date, months_ago):
        mo  = ref_date.month - months_ago
        yr  = ref_date.year + (mo - 1) // 12
        mo  = ((mo - 1) % 12) + 1
        deb = ref_date.replace(year=yr, month=mo, day=1)
        if mo == 12:
            fin = deb.replace(year=yr + 1, month=1, day=1) - timedelta(days=1)
        else:
            fin = deb.replace(month=mo + 1, day=1) - timedelta(days=1)
        return deb, fin

    def _period_range(self, period, start_date_str=None, end_date_str=None):
        """Retourne (start, end) ou (None, None) si pas de filtre."""
        today = self.today
        if period == 'today':
            return today, today
        elif period == 'week':
            return today - timedelta(days=today.weekday()), today
        elif period == 'month':
            return today.replace(day=1), today
        elif period == 'quarter':
            q   = (today.month - 1) // 3 + 1
            deb = datetime(today.year, 3 * q - 2, 1).date()
            return deb, today
        elif period == 'year':
            return today.replace(month=1, day=1), today
        elif period == 'custom' and start_date_str and end_date_str:
            return (
                datetime.strptime(start_date_str, '%Y-%m-%d').date(),
                datetime.strptime(end_date_str,   '%Y-%m-%d').date(),
            )
        elif period == 'all':
            return None, None
        else:
            # Par défaut : mois courant
            return today.replace(day=1), today

    def _apply_period_prev(self, qs, period, start_date=None, end_date=None):
        """Applique le filtre période précédente."""
        today = self.today
        if period == 'today':
            y = today - timedelta(days=1)
            return qs.filter(Q(date_reception=y) | Q(date_envoi=y))
        elif period == 'week':
            s = today - timedelta(days=today.weekday())
            ps, pe = s - timedelta(days=7), s - timedelta(days=1)
        elif period == 'month':
            s  = today.replace(day=1)
            pe = s - timedelta(days=1)
            ps = pe.replace(day=1)
        elif period == 'quarter':
            q   = (today.month - 1) // 3 + 1
            s   = datetime(today.year, 3 * q - 2, 1).date()
            if q == 1:
                ps, pe = datetime(today.year - 1, 10, 1).date(), datetime(today.year - 1, 12, 31).date()
            else:
                ps = datetime(today.year, 3 * (q - 1) - 2, 1).date()
                pe = s - timedelta(days=1)
        else:
            s  = today.replace(day=1)
            pe = s - timedelta(days=1)
            ps = pe.replace(day=1)

        return qs.filter(
            Q(date_reception__gte=ps, date_reception__lte=pe) |
            Q(date_envoi__gte=ps,     date_envoi__lte=pe)
        )