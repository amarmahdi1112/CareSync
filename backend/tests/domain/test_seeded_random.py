import pytest

from app.domain.random import SeededRandom


@pytest.mark.parametrize(
    ("seed", "expected"),
    [
        (
            "2024-01",
            [
                0.8900006350595504,
                0.28863415331579745,
                0.8903226612601429,
                0.7782411342486739,
                0.7449027239345014,
            ],
        ),
        (
            "",
            [
                0.7181076975539327,
                0.026964828837662935,
                0.02563006174750626,
                0.3498557007405907,
                0.9996825011912733,
            ],
        ),
        (
            12345,
            [
                0.9797282677609473,
                0.3067522644996643,
                0.484205421525985,
                0.817934412509203,
                0.5094283693470061,
            ],
        ),
    ],
)
def test_sequence_is_identical_to_legacy_mulberry32(seed: str | int, expected: list[float]) -> None:
    random = SeededRandom(seed)
    assert [random.next() for _ in range(5)] == expected
    assert random.call_count == 5


def test_range_choice_shuffle_and_fork_are_deterministic() -> None:
    first = SeededRandom("shuffle-test")
    second = SeededRandom("shuffle-test")
    original = [1, 2, 3, 4, 5]
    assert first.shuffle(original) == second.shuffle(original)
    assert original == [1, 2, 3, 4, 5]
    assert SeededRandom("same").next_int(5, 5) == 5
    assert SeededRandom("fork").fork("child").next() == SeededRandom("fork").fork("child").next()


def test_sampling_helpers_and_validation() -> None:
    random = SeededRandom("helpers")
    assert 10 <= random.next_float(10, 20) < 20
    assert isinstance(random.next_boolean(), bool)
    assert random.pick(["a", "b", "c"]) in {"a", "b", "c"}
    assert random.weighted_pick(["only"], [1]) == "only"
    assert isinstance(random.next_gaussian(), float)
    with pytest.raises(ValueError, match="empty"):
        random.pick([])
    with pytest.raises(ValueError, match="same length"):
        random.weighted_pick(["a"], [1, 2])
