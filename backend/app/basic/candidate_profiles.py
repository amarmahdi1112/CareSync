"""Server-authoritative candidate personal-profile completion policy."""

from __future__ import annotations

from app.basic.models import MarketplaceProfile, User

REQUIRED_PROFILE_FIELDS = ("first_name", "last_name", "email", "date_of_birth", "phone")


def missing_profile_fields(user: User, profile: MarketplaceProfile | None) -> list[str]:
    values = {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "date_of_birth": profile.date_of_birth if profile else None,
        "phone": profile.phone if profile else None,
    }
    return [name for name in REQUIRED_PROFILE_FIELDS if not values[name]]
