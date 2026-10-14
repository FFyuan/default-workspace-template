import pytest

from workspace_themes.errors import InvalidThemeValueError
from workspace_themes.primitives import ThemeAuthor, ThemeDescription, ThemeName


@pytest.mark.parametrize("text_type", [ThemeName, ThemeDescription, ThemeAuthor])
@pytest.mark.parametrize("value", ["A\x7fB", "A\x1b[31mB", "A\nB", "A\tB"])
def test_theme_text_refuses_control_characters(
    text_type: type[ThemeName], value: str
) -> None:
    with pytest.raises(InvalidThemeValueError, match="control characters"):
        text_type(value)


def test_theme_text_is_trimmed() -> None:
    assert ThemeName("  Sepia \U0001d11e  ") == "Sepia \U0001d11e"
