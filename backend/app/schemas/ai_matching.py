"""Strict contracts for privacy-minimized AI child-name reconciliation."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NameCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)


class ExcludedNameMatchPair(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    source_child_id: str = Field(min_length=1, max_length=200, alias="sourceChildId")
    portal_child_id: str = Field(min_length=1, max_length=200, alias="portalChildId")


class NameMatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    source_children: list[NameCandidate] = Field(
        min_length=1, max_length=500, alias="sourceChildren"
    )
    portal_children: list[NameCandidate] = Field(
        min_length=1, max_length=250, alias="portalChildren"
    )
    excluded_pairs: list[ExcludedNameMatchPair] = Field(
        default_factory=list,
        max_length=2_000,
        alias="excludedPairs",
    )

    @model_validator(mode="after")
    def unique_ids(self) -> "NameMatchRequest":
        for label, values in (
            ("source children", self.source_children),
            ("portal children", self.portal_children),
        ):
            ids = [value.id for value in values]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} must use unique IDs")
        source_ids = {value.id for value in self.source_children}
        portal_ids = {value.id for value in self.portal_children}
        excluded_pairs = [
            (pair.source_child_id, pair.portal_child_id) for pair in self.excluded_pairs
        ]
        if len(excluded_pairs) != len(set(excluded_pairs)):
            raise ValueError("excludedPairs must use unique source/portal pairs")
        if any(
            source_id not in source_ids or portal_id not in portal_ids
            for source_id, portal_id in excluded_pairs
        ):
            raise ValueError(
                "excludedPairs must reference IDs present in sourceChildren and portalChildren"
            )
        return self


class NameMatchResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_child_id: str = Field(alias="sourceChildId")
    portal_child_id: str = Field(alias="portalChildId")
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(max_length=300)
    accepted: bool


class NameMatchResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    model: str
    threshold: float
    chunk_count: int = Field(default=1, alias="chunkCount", ge=1)
    collision_count: int = Field(default=0, alias="collisionCount", ge=0)
    discarded_count: int = Field(default=0, alias="discardedCount", ge=0)
    matches: list[NameMatchResult]
    accepted_count: int = Field(alias="acceptedCount", ge=0)
    unresolved_source_child_ids: list[str] = Field(alias="unresolvedSourceChildIds")
    unresolved_portal_child_ids: list[str] = Field(alias="unresolvedPortalChildIds")
