"""Demo-account profile from config/account.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from atlas.domain import AssetClass
from atlas.learning import LearningConfig
from atlas.paper import CostModel


class AccountConfig(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    starting_equity: float = Field(gt=0)
    equity_currency: str = Field(min_length=3, max_length=3)
    fx_to_base: float = Field(gt=0, description="Account currency -> base currency (USD)")
    target_demo_trades: int = Field(default=1000, ge=1)
    venues: list[str]
    costs: dict[AssetClass, CostModel]
    learning: LearningConfig = Field(default_factory=LearningConfig)

    @property
    def starting_equity_base(self) -> float:
        return self.starting_equity * self.fx_to_base

    def cost_model(self, asset_class: AssetClass) -> CostModel:
        return self.costs.get(asset_class, CostModel())

    @classmethod
    def from_yaml(cls, path: str | Path) -> AccountConfig:
        with open(path, encoding="utf-8") as f:
            return cls.model_validate(yaml.safe_load(f))
