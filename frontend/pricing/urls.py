from __future__ import annotations

from django.urls import path

from pricing import views

app_name = "pricing"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/health/", views.HealthView.as_view(), name="api-health"),
    path("api/prices/latest/", views.LatestPricesView.as_view(), name="api-latest-prices"),
    path("api/forecast/system-prices/", views.ForecastSystemPricesView.as_view(), name="api-forecast-prices"),
    path(
        "api/forecast/fuel-generation/",
        views.ForecastFuelGenerationView.as_view(),
        name="api-forecast-generation",
    ),
    path("api/settle/", views.SettleView.as_view(), name="api-settle"),
    path("api/quote/", views.QuoteView.as_view(), name="api-quote"),
]
