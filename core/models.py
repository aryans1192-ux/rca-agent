from typing import Optional
from pydantic import BaseModel, field_validator, model_validator


class OrderRow(BaseModel):
    charge_date: str

    @field_validator("charge_date", mode="before")
    @classmethod
    def coerce_date(cls, v):
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    @model_validator(mode="before")
    @classmethod
    def replace_none_with_zero(cls, values):
        if isinstance(values, dict):
            return {k: (0 if v is None else v) for k, v in values.items()}
        return values

    store: str
    city: str
    hour: int
    total_orders: float = 0
    breached_count: float = 0
    breached_rate: float = 0
    is_problem_hour: int = 0
    pileup_count: float = 0
    pileup_flag: int = 0
    avg_or2a: float = 0
    order_projection: float = 0
    current_size: float = 0
    booked_size: float = 0
    noshow_count: float = 0
    man_hour: float = 0
    rider_hours_per_hour: float = 0
    booked_hours_per_hour: float = 0

    class Config:
        extra = "allow"


class DemandSpikeResult(BaseModel):
    triggered: bool
    reason: Optional[str] = None


class PileupResult(BaseModel):
    triggered: bool
    sustained: bool = False
    reason: Optional[str] = None


class SupplyResult(BaseModel):
    triggered: bool
    level: Optional[str] = None
    reason: Optional[str] = None


class RCAResult(BaseModel):
    store: str
    city: str
    hour: int
    avg_or2a: float
    breached_rate_pct: float
    total_orders: int
    order_projection: int
    booked_size: int
    current_size: int
    man_hour: float
    noshow_count: int
    root_causes: list[str]
    demand_spike: DemandSpikeResult
    pileup: PileupResult
    supply: SupplyResult


class StoreSummary(BaseModel):
    store: str
    city: str
    problem_hours: int
    total_orders: int


class CitySummary(BaseModel):
    city: str
    date: str
    total_orders: int
    weighted_breach_rate_pct: float
    weighted_avg_or2a: float
    problem_hours: int
    total_store_hours: int
