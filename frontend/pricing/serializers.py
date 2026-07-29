"""DRF serializers: input validation for the REST endpoints.

DRF's `Serializer` is doing the same job here that pydantic's `BaseModel`
does in api/glasshouse_api/models.py -- declare the fields you expect,
DRF validates incoming data against them and raises a proper 400 with a
field-by-field error report if it doesn't match. `serializer.is_valid(
raise_exception=True)` is the DRF idiom for "validate or bail with a
DRF-formatted error response" -- there's no need to hand-write the
try/except-and-format-an-error-response boilerplate pydantic would also
save you from, DRF just expresses it as a different method call.

Used for both request *bodies* (SettleRequestSerializer, a POST) and
query *parameters* (everything else, GET) -- DRF serializers validate
either the same way; `request.query_params` is just a QueryDict passed
in as `data=`.
"""

from __future__ import annotations

from rest_framework import serializers

from pricing.services import BUSINESS_TYPE_CHOICES


class GeneratorSerializer(serializers.Serializer):
    id = serializers.CharField()
    available_mwh = serializers.FloatField(min_value=0)
    cost_gbp_per_mwh = serializers.FloatField(min_value=0)


class ConsumerSerializer(serializers.Serializer):
    id = serializers.CharField()
    demand_mwh = serializers.FloatField(min_value=0)


class TariffSerializer(serializers.Serializer):
    network_charge_gbp_per_mwh = serializers.FloatField(default=20.0)
    policy_cost_gbp_per_mwh = serializers.FloatField(default=15.0)
    platform_margin_fraction = serializers.FloatField(default=0.05)


class SettleRequestSerializer(serializers.Serializer):
    generators = GeneratorSerializer(many=True)
    consumers = ConsumerSerializer(many=True)
    tariff = TariffSerializer(required=False)

    def validate_generators(self, value: list[dict]) -> list[dict]:
        if not value:
            raise serializers.ValidationError("at least one generator is required")
        return value


class QuoteQuerySerializer(serializers.Serializer):
    date = serializers.DateField()
    business_type = serializers.ChoiceField(choices=BUSINESS_TYPE_CHOICES)
    renewable_share = serializers.FloatField(min_value=0.0, max_value=1.0, default=0.5)
    settlement_period = serializers.IntegerField(min_value=1, max_value=48, required=False, allow_null=True)


class ForecastSystemPricesQuerySerializer(serializers.Serializer):
    date = serializers.DateField()


class ForecastFuelGenerationQuerySerializer(serializers.Serializer):
    date = serializers.DateField()
    fuel_type = serializers.CharField()


class LatestPricesQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=336, default=48)
