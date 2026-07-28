"""Declarative model base shared by all compatibility mappings."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
