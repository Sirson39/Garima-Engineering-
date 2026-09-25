from django.urls import path

from .views import (
    ValuationBankCreateView,
    ValuationBankListView,
    ValuationDashboardView,
    ValuationRequestCreateView,
    ValuationRequestDetailView,
    ValuationRequestListView,
    transition_valuation_request,
)


urlpatterns = [
    path("", ValuationDashboardView.as_view(), name="valuation-dashboard"),
    path("requests/", ValuationRequestListView.as_view(), name="valuation-request-list"),
    path("requests/new/", ValuationRequestCreateView.as_view(), name="valuation-request-create"),
    path("requests/<int:pk>/", ValuationRequestDetailView.as_view(), name="valuation-request-detail"),
    path("requests/<int:pk>/transition/", transition_valuation_request, name="valuation-request-transition"),
    path("banks/", ValuationBankListView.as_view(), name="valuation-banks"),
    path("banks/new/", ValuationBankCreateView.as_view(), name="valuation-bank-create"),
]
