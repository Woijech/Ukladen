from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PriceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    input_per_million: Decimal = Field(ge=0, le=1000000, allow_inf_nan=False)
    output_per_million: Decimal = Field(ge=0, le=1000000, allow_inf_nan=False)

    def estimate(self, input_tokens: int | None, output_tokens: int | None) -> Decimal | None:
        if input_tokens is None or output_tokens is None:
            return None
        return (
            input_tokens * self.input_per_million + output_tokens * self.output_per_million
        ) / 1000000
