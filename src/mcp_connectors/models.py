"""Public MCP contracts. Missing source values remain null."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Source = Literal["cvbankas", "cvmarket", "cvonline", "autoplius", "autogidas"]
JobSource = Literal["cvbankas", "cvmarket", "cvonline"]
CarSource = Literal["autoplius", "autogidas"]
Status = Literal["ok", "empty", "partial", "blocked", "network_error", "layout_changed",
                 "invalid_url", "not_found", "unsupported_filter"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Salary(Model):
    minimum: float | None = None
    maximum: float | None = None
    currency: str | None = None
    period: str | None = None
    raw: str | None = None


class JobListing(Model):
    kind: Literal["job"] = "job"
    source: Source
    url: str
    title: str
    company: str | None = None
    location: str | None = None
    salary: Salary | None = None
    description: str | None = None
    requirements: list[str] | None = None
    date_posted: str | None = None


class CarListing(Model):
    kind: Literal["car"] = "car"
    source: Source
    url: str
    title: str
    make: str | None = None
    model: str | None = None
    year: int | None = None
    price: float | None = None
    currency: str | None = None
    price_raw: str | None = None
    mileage_km: int | None = None
    fuel: str | None = None
    transmission: str | None = None
    engine: str | None = None
    location: str | None = None
    description: str | None = None
    date_posted: str | None = None


Listing = JobListing | CarListing


class SearchOptions(Model):
    query: str = Field(default="", max_length=200)
    limit: int = Field(default=10, ge=1, le=50, strict=True)
    page: int = Field(default=1, ge=1, le=100, strict=True)
    max_pages: int = Field(default=1, ge=1, le=3, strict=True)


class JobSearch(SearchOptions):
    city: Literal["Vilnius", "Kaunas", "Klaipėda", "Šiauliai", "Panevėžys"] | None = None


class CarSearch(SearchOptions):
    price_from: int | None = Field(default=None, ge=0, le=10000000, strict=True)
    price_to: int | None = Field(default=None, ge=0, le=10000000, strict=True)
    year_from: int | None = Field(default=None, ge=1900, le=2100, strict=True)
    year_to: int | None = Field(default=None, ge=1900, le=2100, strict=True)

    @model_validator(mode="after")
    def ordered_ranges(self):
        for low, high in ((self.price_from, self.price_to), (self.year_from, self.year_to)):
            if low is not None and high is not None and low > high:
                raise ValueError("Range minimum must not exceed maximum")
        return self


class SourceError(Model):
    code: Status
    message: str
    url: str | None = None
    http_status: int | None = None


class SearchResult(Model):
    source: Source
    status: Status
    items: list[Listing] = Field(default_factory=list)
    pages_fetched: int = 0
    has_more: bool = False
    next_page: int | None = None
    truncated: bool = False
    errors: list[SourceError] = Field(default_factory=list)


class SearchResponse(Model):
    results: list[SearchResult]


class ListingResult(Model):
    source: Source
    status: Status
    item: Listing | None = None
    error: SourceError | None = None
