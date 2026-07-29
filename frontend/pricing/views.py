"""Views.

Two flavours living side by side, both calling `pricing.services`
directly rather than each other:

- DRF `APIView` subclasses -- the REST interface (`/api/...`), JSON in
  and out. This is the "Django + DRF" piece.
- `dashboard`, a plain Django view -- renders the actual HTML page a
  human looks at, using Django's own template engine, no DRF involved.

Django doesn't force you to choose one or the other the way you might
expect coming from a JS-frontend-plus-API-backend world -- one project,
one deployable, both jobs. That's *why* Django ended up being a good
fit for reworking this: FastAPI (in api/) is deliberately API-only, so
frontend/ was always going to need something else on top of it (a
separate React app was the original plan) -- Django can just do both
itself.
"""

from __future__ import annotations

from datetime import date as date_cls

from django.shortcuts import render
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from pricing import services
from pricing.serializers import (
    ForecastFuelGenerationQuerySerializer,
    ForecastSystemPricesQuerySerializer,
    LatestPricesQuerySerializer,
    QuoteQuerySerializer,
    SettleRequestSerializer,
)


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


class LatestPricesView(APIView):
    def get(self, request):
        query = LatestPricesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            prices = services.get_latest_prices(**query.validated_data)
        except FileNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(prices)


class ForecastSystemPricesView(APIView):
    def get(self, request):
        query = ForecastSystemPricesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            points = services.get_forecast_system_prices(query.validated_data["date"])
        except FileNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except services.InsufficientHistoryError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(points)


class ForecastFuelGenerationView(APIView):
    def get(self, request):
        query = ForecastFuelGenerationQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            points = services.get_forecast_fuel_generation(
                query.validated_data["date"], query.validated_data["fuel_type"]
            )
        except FileNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except services.InsufficientHistoryError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(points)


class SettleView(APIView):
    def post(self, request):
        body = SettleRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            result = services.settle(
                generators=data["generators"],
                consumers=data["consumers"],
                **(data.get("tariff") or {}),
            )
        except services.SettlementInputError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(result)


class QuoteView(APIView):
    def get(self, request):
        query = QuoteQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        try:
            result = services.get_quote(
                business_type=data["business_type"],
                renewable_share=data["renewable_share"],
                target_date=data["date"],
                settlement_period=data.get("settlement_period"),
            )
        except services.SettlementInputError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(result)


def dashboard(request):
    """The actual UI: a form (business type, renewable share, date),
    submitted as a GET (not POST) so a result is a shareable,
    bookmarkable URL and there's no CSRF token to wire up for a v1 that
    doesn't change any state -- see README.md.

    Calls pricing.services.get_quote directly, in-process -- not this
    same project's own /api/quote/ over HTTP. See services.py's module
    docstring for why that self-call would be pointless.
    """
    context = {
        "business_types": services.BUSINESS_TYPE_CHOICES,
        "form_values": {
            "business_type": request.GET.get("business_type", "office"),
            "renewable_share": request.GET.get("renewable_share", "0.5"),
            "date": request.GET.get("date", ""),
            "settlement_period": request.GET.get("settlement_period", ""),
        },
        "quote": None,
        "error": None,
    }

    if request.GET.get("date"):
        try:
            target_date = date_cls.fromisoformat(request.GET["date"])
            renewable_share = float(request.GET.get("renewable_share", 0.5))
            business_type = request.GET.get("business_type", "office")
            settlement_period = (
                int(request.GET["settlement_period"]) if request.GET.get("settlement_period") else None
            )
            context["quote"] = services.get_quote(
                business_type, renewable_share, target_date, settlement_period=settlement_period
            )
        except (ValueError, services.SettlementInputError) as exc:
            context["error"] = str(exc)

    return render(request, "pricing/dashboard.html", context)
