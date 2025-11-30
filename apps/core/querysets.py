"""
Query optimization utilities for LabControl platform.

These utilities help write efficient database queries, especially for:
- Subquery aggregations (avoiding N+1 queries)
- Complex annotations
- Performance optimization
"""

from django.db.models import PositiveIntegerField, Subquery


class SubqueryCount(Subquery):
    """
    Efficient COUNT in a subquery without GROUP BY.

    Usage:
        from apps.core.querysets import SubqueryCount
        from django.db.models import OuterRef

        studies = Study.objects.annotate(
            appointment_count=SubqueryCount(
                Appointment.objects.filter(study=OuterRef('pk'))
            )
        )

    This avoids N+1 queries and is more efficient than:
        - Prefetch with count
        - Annotate with Count (which requires GROUP BY)

    Reference: https://stackoverflow.com/a/47371514/1164966
    """

    template = "(SELECT count(*) FROM (%(subquery)s) _count)"
    output_field = PositiveIntegerField()


class SubqueryAggregate(Subquery):
    """
    Base class for subquery aggregations.

    Allows efficient aggregation operations (SUM, AVG, MAX, MIN) in subqueries.

    Reference: https://code.djangoproject.com/ticket/10060
    """

    template = '(SELECT %(function)s(_agg."%(column)s") FROM (%(subquery)s) _agg)'

    def __init__(self, queryset, column, output_field=None, **extra):
        """
        Initialize subquery aggregate.

        Args:
            queryset: The queryset to aggregate
            column: The column name to aggregate
            output_field: Output field type (auto-detected if not provided)
            **extra: Additional template context
        """
        if not output_field:
            # Infer output_field from the field type
            output_field = queryset.model._meta.get_field(column)
        super().__init__(
            queryset, output_field, column=column, function=self.function, **extra
        )


class SubquerySum(SubqueryAggregate):
    """
    Efficient SUM in a subquery.

    Usage:
        from apps.core.querysets import SubquerySum
        from django.db.models import OuterRef

        invoices = Invoice.objects.annotate(
            total_paid=SubquerySum(
                Payment.objects.filter(invoice=OuterRef('pk')),
                'amount'
            )
        )
    """

    function = "SUM"


class SubqueryMax(SubqueryAggregate):
    """
    Efficient MAX in a subquery.

    Usage:
        studies = Study.objects.annotate(
            latest_result_date=SubqueryMax(
                Result.objects.filter(study=OuterRef('pk')),
                'created_at'
            )
        )
    """

    function = "MAX"


class SubqueryMin(SubqueryAggregate):
    """
    Efficient MIN in a subquery.
    """

    function = "MIN"


class SubqueryAvg(SubqueryAggregate):
    """
    Efficient AVG in a subquery.
    """

    function = "AVG"
