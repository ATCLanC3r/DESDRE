from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.urls import reverse, path
from django.utils.html import format_html
from django.shortcuts import redirect
from django.http import HttpResponse, JsonResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.db.models import Sum
from django.core.exceptions import ValidationError
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from decimal import Decimal
import csv
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from .models import PaymentSettlement, SettlementOrder
from orders.models import OrderProducer
from mainApp.models import ProducerProfile
from .tasks import complete_old_settlements
from mainApp.admin_enforcer import AdminEnforcer

'''
Redesign with cleaner activity flow.
'''

class DateRangeFilter(SimpleListFilter):
    title = 'date range'
    parameter_name = 'date_range'

    def lookups(self, request, model_admin):
        return (
            ('week', 'This Week'),
            ('month', 'This Month'),
            ('quarter', 'This Quarter'),
            ('year', 'This Year'),
            ('custom', 'Custom Range'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'today':
            return queryset.filter(week_start=timezone.now().date())
        elif self.value() == 'week':
            today = timezone.now().date()
            start_of_week = today - timezone.timedelta(days=today.weekday())
            return queryset.filter(week_start=start_of_week)
        elif self.value() == 'month':
            return queryset.filter(
                week_start__year=timezone.now().year,
                week_start__month=timezone.now().month
            )
        elif self.value() == 'quarter':
            current_quarter = (timezone.now().month - 1) // 3 + 1
            return queryset.filter(week_start__quarter=current_quarter)
        elif self.value() == 'year':
            return queryset.filter(week_start__year=timezone.now().year)
        return queryset


class PaymentSettlementAdmin(AdminEnforcer, admin.ModelAdmin):
    """Main admin class for Payment Settlements with financial reporting (TC-025)"""

    change_list_template = 'admin/payments_paymentsettlement_change_list.html'

    list_display = ['id', 'producer', 'week_start', 'week_end', 'total_orders',
               'total_commission', 'total_payout', 'settlement_status']
    list_filter = ['settlement_status', 'week_start', 'week_end', 'producer', DateRangeFilter]
    search_fields = ['producer__business_name', 'payment_reference']
    readonly_fields = ['total_orders', 'total_subtotal', 'total_commission', 'total_payout']

    actions = ['complete_14_day_settlements']

    def get_actions(self, request):
        '''removes delete selected'''
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def changelist_view(self, request, extra_context=None):
        """Add financial report button to changelist page header"""
        extra_context = extra_context or {}
        extra_context['financial_report_url'] = reverse('admin:payments_paymentsettlement_financial_report')
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        """Custom URLs"""
        urls = super().get_urls()
        custom_urls = [
            path('financial-report/', self.admin_site.admin_view(self.financial_report_view), name='payments_paymentsettlement_financial_report'),
            path('export-csv/', self.admin_site.admin_view(self.export_csv), name='payments_paymentsettlement_export_csv'),
            path('export-pdf/', self.admin_site.admin_view(self.export_pdf), name='payments_paymentsettlement_export_pdf'),
            path('order-audit/<int:order_producer_id>/', self.admin_site.admin_view(self.order_audit_view), name='payments_paymentsettlement_order_audit'),
            path('<path:object_id>/orders/', self.admin_site.admin_view(self.settlement_orders_view), name='payments_paymentsettlement_orders'),
        ]
        return custom_urls + urls

    def settlement_orders_view(self, request, object_id):
        """View all orders associated with a specific settlement"""
        try:
            settlement = PaymentSettlement.objects.get(id=object_id)

            settlement_orders = SettlementOrder.objects.filter(
                settlement=settlement
            ).select_related(
                'order_producer__payment__user',
                'order_producer__producer'
            )

            orders_data = []
            total_subtotal = Decimal('0.00')
            total_commission = Decimal('0.00')
            total_payout = Decimal('0.00')

            for settlement_order in settlement_orders:
                customer_name = 'N/A'
                if settlement_order.order_producer and settlement_order.order_producer.payment:
                    if settlement_order.order_producer.payment.user:
                        customer_name = settlement_order.order_producer.payment.user.get_full_name() or settlement_order.order_producer.payment.user.username

                expected_commission = (settlement_order.order_subtotal * Decimal('0.05')).quantize(Decimal('0.01'))
                commission_matches = expected_commission == settlement_order.order_commission

                orders_data.append({
                    'order_producer_id': settlement_order.order_producer.id,
                    'order_id': settlement_order.order_id,
                    'product_names': settlement_order.get_product_names,
                    'customer_name': customer_name,
                    'completed_date': settlement_order.order_completed_at,
                    'subtotal': settlement_order.order_subtotal,
                    'commission': settlement_order.order_commission,
                    'payout': settlement_order.order_payout,
                    'expected_commission': expected_commission,
                    'commission_matches': commission_matches,
                    'status': settlement_order.order_producer.order_status if settlement_order.order_producer else 'Unknown',
                })

                total_subtotal += settlement_order.order_subtotal
                total_commission += settlement_order.order_commission
                total_payout += settlement_order.order_payout

            verification_summary = {
                'total_orders': len(orders_data),
                'subtotal_matches': total_subtotal == settlement.total_subtotal,
                'commission_matches': total_commission == settlement.total_commission,
                'payout_matches': total_payout == settlement.total_payout,
                'subtotal_difference': total_subtotal - settlement.total_subtotal,
                'commission_difference': total_commission - settlement.total_commission,
                'payout_difference': total_payout - settlement.total_payout,
            }

            context = {
                'title': f'Orders for Settlement #{settlement.id}',
                'settlement': settlement,
                'orders': orders_data,
                'summary': {
                    'total_orders': len(orders_data),
                    'total_subtotal': total_subtotal,
                    'total_commission': total_commission,
                    'total_payout': total_payout,
                },
                'verification_summary': verification_summary,
                'opts': self.model._meta,
                'current_filters': request.GET.urlencode(),
            }

            return TemplateResponse(request, 'admin/financial/settlement_orders.html', context)

        except PaymentSettlement.DoesNotExist:
            self.message_user(request, f'Settlement #{object_id} not found.', level='ERROR')
            return redirect('admin:payments_paymentsettlement_changelist')

    def financial_report_view(self, request):
        """Main financial report view with date filters and summaries"""
        format_type = request.GET.get('format')
        if format_type == 'csv':
            return self.export_csv(request)
        elif format_type == 'pdf':
            return self.export_pdf(request)

        # Use consolidated filter function
        settlements = self._get_filtered_settlements(request)

        # Get filter values for template context
        date_range = request.GET.get('date_range', '')
        date_from = request.GET.get('date_from', '')
        date_to = request.GET.get('date_to', '')
        producer_id = request.GET.get('producer', '')

        summary = settlements.aggregate(
            total_orders=Sum('total_orders'),
            total_subtotal=Sum('total_subtotal'),
            total_commission=Sum('total_commission'),
            total_payout=Sum('total_payout'),
        )

        running_totals = self._calculate_running_totals(settlements)
        period_summaries = self._calculate_period_summaries(settlements)
        verification = self._verify_commission_calculations(settlements)

        context = {
            'title': 'Financial Report',
            'settlements': settlements,
            'summary': summary,
            'running_totals': running_totals,
            'period_summaries': period_summaries,
            'verification': verification,
            'producers': ProducerProfile.objects.all(),
            'date_from': date_from,
            'date_to': date_to,
            'selected_producer': producer_id,
            'opts': self.model._meta,
            'current_filters': request.GET.urlencode(),
            'selected_date_range': date_range,
        }

        return TemplateResponse(request, 'admin/financial/financial_report.html', context)
    
    # =================
    # private functions
    # =================
    def _calculate_running_totals(self, settlements):
        """Calculate running totals across settlements"""
        running_total = Decimal('0.00')
        running_totals = []

        for settlement in settlements.order_by('week_start'):
            running_total += settlement.total_payout
            running_totals.append({
                'period': f"{settlement.week_start} - {settlement.week_end}",
                'producer': settlement.producer.business_name,
                'payout': settlement.total_payout,
                'running_total': running_total
            })

        return running_totals

    def _calculate_period_summaries(self, settlements):
        """Calculate summaries by period (weekly/monthly)"""
        summaries = {
            'weekly': {},
            'monthly': {}
        }

        for settlement in settlements:
            week_key = f"{settlement.week_start.year}-W{settlement.week_start.isocalendar()[1]}"
            if week_key not in summaries['weekly']:
                summaries['weekly'][week_key] = {
                    'total_orders': 0,
                    'total_commission': Decimal('0.00'),
                    'total_payout': Decimal('0.00')
                }
            summaries['weekly'][week_key]['total_orders'] += settlement.total_orders
            summaries['weekly'][week_key]['total_commission'] += settlement.total_commission
            summaries['weekly'][week_key]['total_payout'] += settlement.total_payout

            month_key = settlement.week_start.strftime('%Y-%m')
            if month_key not in summaries['monthly']:
                summaries['monthly'][month_key] = {
                    'total_orders': 0,
                    'total_commission': Decimal('0.00'),
                    'total_payout': Decimal('0.00')
                }
            summaries['monthly'][month_key]['total_orders'] += settlement.total_orders
            summaries['monthly'][month_key]['total_commission'] += settlement.total_commission
            summaries['monthly'][month_key]['total_payout'] += settlement.total_payout

        return summaries

    def _verify_commission_calculations(self, settlements):
        """Verify that commission calculations are accurate"""
        verification_results = []

        for settlement in settlements:
            try:
                settlement_orders = settlement.orders.select_related('order_producer').all()
                manual_commission_total = Decimal('0.00')
                manual_payout_total = Decimal('0.00')

                for settlement_order in settlement_orders:
                    expected_commission = (settlement_order.order_subtotal * Decimal('0.05')).quantize(Decimal('0.01'))
                    actual_commission = settlement_order.order_commission

                    if expected_commission != actual_commission:
                        verification_results.append({
                            'settlement_id': settlement.id,
                            'order_producer_id': settlement_order.order_producer.id,
                            'order_id': settlement_order.order_id,
                            'expected_commission': float(expected_commission),
                            'actual_commission': float(actual_commission),
                            'difference': float(expected_commission - actual_commission),
                            'status': 'MISMATCH'
                        })

                    manual_commission_total += actual_commission
                    manual_payout_total += settlement_order.order_payout

                commission_diff = abs(manual_commission_total - settlement.total_commission)
                if commission_diff > Decimal('0.01'):
                    verification_results.append({
                        'settlement_id': settlement.id,
                        'type': 'SETTLEMENT_TOTAL_MISMATCH',
                        'expected_commission': float(manual_commission_total),
                        'actual_commission': float(settlement.total_commission),
                        'difference': float(manual_commission_total - settlement.total_commission)
                    })

            except Exception as e:
                verification_results.append({
                    'settlement_id': settlement.id,
                    'type': 'ERROR',
                    'error_message': str(e)
                })

        return verification_results

    def export_csv(self, request):
        """Export financial report to CSV (range sensitive)"""
        settlements = self._get_filtered_settlements(request)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="financial_report.csv"'

        writer = csv.writer(response)

        writer.writerow(['FINANCIAL REPORT SUMMARY'])
        writer.writerow(['Generated:', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])

        writer.writerow([
            'Settlement ID', 'Producer', 'Week Start', 'Week End',
            'Total Orders', 'Subtotal', 'Commission (5%)', 'Producer Payout (95%)',
            'Status', 'Paid At'
        ])

        for settlement in settlements:
            writer.writerow([
                settlement.id,
                settlement.producer.business_name,
                settlement.week_start,
                settlement.week_end,
                settlement.total_orders,
                f"{settlement.total_subtotal:.2f}",
                f"{settlement.total_commission:.2f}",
                f"{settlement.total_payout:.2f}",
                settlement.settlement_status,
                settlement.paid_at.strftime('%Y-%m-%d') if settlement.paid_at else ''
            ])

        totals = settlements.aggregate(
            total_orders=Sum('total_orders'),
            total_commission=Sum('total_commission'),
            total_payout=Sum('total_payout')
        )

        writer.writerow([])
        writer.writerow(['TOTALS', '', '', '',
                        totals['total_orders'] if totals['total_orders'] else 0,
                        '',
                        f"{totals['total_commission']:.2f}" if totals['total_commission'] else "0.00",
                        f"{totals['total_payout']:.2f}" if totals['total_payout'] else "0.00"])

        writer.writerow([])
        writer.writerow(['ORDER DETAILS'])
        writer.writerow([
            'Order ID', 'Settlement ID', 'Producer', 'Customer',
            'Completed Date', 'Subtotal', 'Commission (5%)', 'Payout (95%)'
        ])

        for settlement in settlements:
            for settlement_order in settlement.orders.select_related('order_producer').all():
                customer_name = ''
                if settlement_order.order_producer and settlement_order.order_producer.payment:
                    if settlement_order.order_producer.payment.user:
                        customer_name = settlement_order.order_producer.payment.user.get_full_name() or settlement_order.order_producer.payment.user.username

                writer.writerow([
                    settlement_order.order_id,
                    settlement.id,
                    settlement.producer.business_name,
                    customer_name,
                    settlement_order.order_completed_at.strftime('%Y-%m-%d') if settlement_order.order_completed_at else '',
                    f"{settlement_order.order_subtotal:.2f}",
                    f"{settlement_order.order_commission:.2f}",
                    f"{settlement_order.order_payout:.2f}"
                ])

        return response

    def export_pdf(self, request):
        """Export financial report to PDF (range sensitive)"""
        settlements = self._get_filtered_settlements(request)

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="financial_report.pdf"'

        doc = SimpleDocTemplate(response, pagesize=landscape(letter))
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#366092'),
            spaceAfter=30
        )
        elements.append(Paragraph("Financial Report", title_style))
        elements.append(Paragraph(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        elements.append(Spacer(1, 20))

        summary_data = [['Settlement ID', 'Producer', 'Period', 'Orders', 'Commission', 'Payout']]

        for settlement in settlements[:50]:
            summary_data.append([
                str(settlement.id),
                settlement.producer.business_name[:30],
                f"{settlement.week_start} - {settlement.week_end}",
                str(settlement.total_orders),
                f"£{settlement.total_commission:.2f}",
                f"£{settlement.total_payout:.2f}"
            ])

        totals = settlements.aggregate(
            total_orders=Sum('total_orders'),
            total_commission=Sum('total_commission'),
            total_payout=Sum('total_payout')
        )

        summary_data.append([
            'TOTALS', '', '',
            str(totals['total_orders']) if totals['total_orders'] else '0',
            f"£{totals['total_commission']:.2f}" if totals['total_commission'] else "£0.00",
            f"£{totals['total_payout']:.2f}" if totals['total_payout'] else "£0.00"
        ])

        table = Table(summary_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))

        elements.append(table)
        doc.build(elements)

        return response

    def order_audit_view(self, request, order_producer_id):
        """HTML view for auditing individual orders - shows full order details with items grouped by producer"""
        try:
            # 1. Get the OrderProducer that was clicked (identifies the settlement)
            order_producer = OrderProducer.objects.select_related(
                'payment__user', 'producer', 'payment'
            ).get(id=order_producer_id)

            # 2. Find the settlement this belongs to (via SettlementOrder)
            settlement_order = SettlementOrder.objects.select_related(
                'settlement'
            ).filter(order_producer=order_producer).first()

            # 3. Get ALL OrderProducers for this order (multi-producer support)
            payment = order_producer.payment
            all_order_producers = OrderProducer.objects.filter(
                payment=payment
            ).select_related('producer').prefetch_related('order_items')

            # 4. Build structured data: items grouped by producer
            producers_data = []
            highlighted_producer_ids = set()

            if settlement_order:
                # Get all OrderProducers in this settlement
                settlement_order_producers = SettlementOrder.objects.filter(
                    settlement=settlement_order.settlement
                ).values_list('order_producer_id', flat=True)
                highlighted_producer_ids = set(settlement_order_producers)

            for op in all_order_producers:
                items = op.order_items.all()  # OrderItem with snapshot data
                producer_items = []
                for item in items:
                    producer_items.append({
                        'product_name': item.product_name,
                        'quantity': item.quantity,
                        'unit': item.unit,
                        'product_price': item.product_price,
                        'line_total': item.line_total,
                        'is_highlighted': op.id in highlighted_producer_ids
                    })

                producers_data.append({
                    'producer_name': op.producer.business_name if op.producer else 'Unknown',
                    'producer_id': op.id,
                    'is_highlighted': op.id in highlighted_producer_ids,
                    'subtotal': op.producer_subtotal,
                    'commission': op.commission,
                    'payout': op.producer_payout,
                    'items': producer_items
                })

            # 5. Customer info
            customer_name = 'Unknown'
            customer_email = ''
            if payment and payment.user:
                customer_name = payment.user.get_full_name() or payment.user.username
                customer_email = payment.user.email

            # 6. Verification for THIS producer (the one clicked)
            expected_commission = (order_producer.producer_subtotal * Decimal('0.05')).quantize(Decimal('0.01'))
            commission_matches = expected_commission == order_producer.commission

            # 7. Context for template
            context = {
                'title': f'Order Audit - Order #{payment.id if payment else order_producer_id}',
                'order_producer': order_producer,
                'payment': payment,
                'customer_name': customer_name,
                'customer_email': customer_email,
                'producers_data': producers_data,
                'expected_commission': float(expected_commission),
                'commission_matches': commission_matches,
                'settlement_order': settlement_order,
                'settlement': settlement_order.settlement if settlement_order else None,
                'opts': self.model._meta,
            }

            return TemplateResponse(request, 'admin/financial/order_audit.html', context)

        except OrderProducer.DoesNotExist:
            self.message_user(request, f'Order Producer {order_producer_id} not found.', level='ERROR')
            return redirect('admin:payments_paymentsettlement_financial_report')
        except Exception as e:
            self.message_user(request, f'Error: {str(e)}', level='ERROR')
            return redirect('admin:payments_paymentsettlement_financial_report')

    def _get_filtered_settlements(self, request):
        """Get filtered settlements based on request parameters (date_range, date_from, date_to, producer, settlement_ids)"""
        settlements = PaymentSettlement.objects.all()

        date_range = request.GET.get('date_range', '')
        date_from = request.GET.get('date_from', '')
        date_to = request.GET.get('date_to', '')
        producer_id = request.GET.get('producer', '')
        settlement_ids = request.GET.get('settlement_ids', '')

        # Handle date_range presets (week, month, quarter, year)
        if date_range and date_range != 'custom':
            today = timezone.now().date()
            if date_range == 'week':
                start_of_week = today - timezone.timedelta(days=today.weekday())
                settlements = settlements.filter(week_start=start_of_week)
            elif date_range == 'month':
                settlements = settlements.filter(
                    week_start__year=today.year,
                    week_start__month=today.month
                )
            elif date_range == 'quarter':
                current_quarter = (today.month - 1) // 3 + 1
                quarter_months = {
                    1: [1, 2, 3],
                    2: [4, 5, 6],
                    3: [7, 8, 9],
                    4: [10, 11, 12]
                }
                settlements = settlements.filter(
                    week_start__year=today.year,
                    week_start__month__in=quarter_months[current_quarter]
                )
            elif date_range == 'year':
                settlements = settlements.filter(week_start__year=today.year)

        # Handle custom date range
        if date_from:
            settlements = settlements.filter(week_start__gte=date_from)
        if date_to:
            settlements = settlements.filter(week_end__lte=date_to)

        # Handle producer filter
        if producer_id:
            settlements = settlements.filter(producer_id=producer_id)

        # Handle specific settlement IDs
        if settlement_ids:
            ids = [int(x) for x in settlement_ids.split(',') if x]
            settlements = settlements.filter(id__in=ids)

        return settlements.order_by('-week_start', 'id')
    
    # =================
    # action for completing last 14 day settlements
    # =================
    def complete_14_day_settlements(self, request, queryset):
        """Admin action to complete settlements that ended 14+ days ago"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("COMPLETE_14_DAY action called")

        completed_count = complete_old_settlements()
        logger.info(f"COMPLETE_14_DAY: completed_count = {completed_count}")

        if completed_count > 0:
            self.message_user(
                request,
                f'Successfully completed {completed_count} settlement(s) that ended 14+ days ago.'
            )
        else:
            self.message_user(
                request,
                'No settlements found that qualify for completion (period must have ended 14+ days ago).',
                level='INFO'
            )

    complete_14_day_settlements.short_description = "Complete settlements from 14+ days ago"


admin.site.register(PaymentSettlement, PaymentSettlementAdmin)
