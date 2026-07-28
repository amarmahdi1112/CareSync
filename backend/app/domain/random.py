"""Deterministic randomness shared by scheduling and claim generation."""

import math
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")
UINT32_MASK = 0xFFFFFFFF


def _uint32(value: int) -> int:
    return value & UINT32_MASK


def _imul(left: int, right: int) -> int:
    """Match JavaScript Math.imul's low 32-bit result."""
    return _uint32(left * right)


class SeededRandom:
    """Mulberry32 generator with byte-for-byte JavaScript number semantics."""

    def __init__(self, seed: str | int) -> None:
        self.state = self.hash_string(seed) if isinstance(seed, str) else _uint32(seed)
        self.call_count = 0

    def next(self) -> float:
        self.call_count += 1
        self.state = _uint32(self.state + 0x6D2B79F5)
        value = self.state
        value = _imul(value ^ (value >> 15), value | 1)
        value ^= _uint32(value + _imul(value ^ (value >> 7), value | 61))
        return _uint32(value ^ (value >> 14)) / 4294967296

    def next_int(self, minimum: int, maximum: int) -> int:
        return math.floor(self.next() * (maximum - minimum + 1)) + minimum

    def next_float(self, minimum: float, maximum: float) -> float:
        return self.next() * (maximum - minimum) + minimum

    def next_boolean(self, probability: float = 0.5) -> bool:
        return self.next() < probability

    def pick(self, items: Sequence[T]) -> T:
        if not items:
            raise ValueError("Cannot pick from empty sequence")
        return items[math.floor(self.next() * len(items))]

    choice = pick

    def shuffle(self, items: Sequence[T]) -> list[T]:
        result = list(items)
        for index in range(len(result) - 1, 0, -1):
            swap_index = math.floor(self.next() * (index + 1))
            result[index], result[swap_index] = result[swap_index], result[index]
        return result

    def weighted_pick(self, items: Sequence[T], weights: Sequence[float]) -> T:
        if not items:
            raise ValueError("Cannot pick from empty sequence")
        if len(items) != len(weights):
            raise ValueError("Items and weights must have the same length")
        random_value = self.next() * sum(weights)
        for item, weight in zip(items, weights, strict=True):
            random_value -= weight
            if random_value <= 0:
                return item
        return items[-1]

    def next_gaussian(self, mean: float = 0, standard_deviation: float = 1) -> float:
        first = self.next()
        second = self.next()
        standard_value = math.sqrt(-2 * math.log(first)) * math.cos(2 * math.pi * second)
        return mean + standard_value * standard_deviation

    def fork(self, modifier: str) -> "SeededRandom":
        return SeededRandom(_uint32(self.state + self.hash_string(modifier)))

    @staticmethod
    def hash_string(value: str) -> int:
        result = 5381
        for character in value:
            result = _uint32(result * 33) ^ ord(character)
        return _uint32(result)
