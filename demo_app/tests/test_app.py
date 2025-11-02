import pytest

from demo_app.app import add


@pytest.mark.parametrize("a,b,expected", [(2, 3, 5), (-1, 1, 0), (0, 0, 0)])
def test_add(a: int, b: int, expected: int) -> None:
    """Проверяет корректную сумму a + b."""
    assert add(a, b) == expected
