"""Public-behavior checks added during review of the generated verifier suite."""
from enum import Enum, IntEnum

import pytest

import click
from click.core import ParameterSource
from click.shell_completion import CompletionItem
from click.testing import CliRunner


class Mode(Enum):
    FAST = "fast-value"
    SAFE = "safe-value"


class EmptyMode(str, Enum):
    EMPTY = ""
    SAFE = "safe-value"


class NumberMode(IntEnum):
    ZERO = 0
    ONE = 1


def completions(choice, prefix, ctx=None):
    param = click.Option(["--value"], type=choice)
    if ctx is None:
        ctx = click.Context(click.Command("cli", params=[param]))
    items = choice.shell_complete(ctx, param, prefix)
    assert all(isinstance(item, CompletionItem) for item in items)
    return [item.value for item in items]


def test_empty_string_enum_default_uses_member_name():
    """R2 and R6: an enum's underlying empty value must not replace its name."""
    @click.command()
    @click.option("--mode", type=click.Choice(EmptyMode),
                  default=EmptyMode.EMPTY, show_default=True)
    def cli(mode):
        return mode

    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "default: EMPTY" in result.output
    value = runner.invoke(cli, [], standalone_mode=False)
    assert value.exit_code == 0
    assert value.return_value is EmptyMode.EMPTY


def test_iterable_consumed_once_at_construction_and_original_identity_retained():
    objects = [["a"], {"b": 2}]

    class Once:
        count = 0

        def __iter__(self):
            self.count += 1
            if self.count > 1:
                raise AssertionError("iterable consumed twice")
            return iter(objects)

    source = Once()
    choice = click.Choice(source)
    assert source.count == 1
    first, second = objects
    objects.clear()
    assert choice.convert("['a']", None, None) is first
    assert choice.convert("{'b': 2}", None, None) is second
    assert completions(choice, "") == ["['a']", "{'b': 2}"]
    assert source.count == 1


def test_explicit_enum_aliases_remain_in_snapshot_but_completion_deduplicates():
    class Aliased(Enum):
        FIRST = 1
        ALIAS = 1
        SECOND = 2

    choice = click.Choice([Aliased.FIRST, Aliased.ALIAS, Aliased.SECOND])
    assert list(choice.choices) == [Aliased.FIRST, Aliased.FIRST, Aliased.SECOND]
    assert completions(choice, "") == ["FIRST", "SECOND"]


def test_normalizer_sees_strings_and_runs_before_casefold():
    observed = []

    def normalize(token):
        assert isinstance(token, str)
        observed.append(token)
        return token.replace("FAST", "READY")

    choice = click.Choice(Mode, case_sensitive=False)
    ctx = click.Context(click.Command("cli"), token_normalize_func=normalize)
    assert choice.normalize_choice(Mode.FAST, ctx) == "ready"
    assert observed == ["FAST"]
    assert choice.convert("READY", None, ctx) is Mode.FAST


def test_override_controls_conversion_and_completion_input_and_candidates():
    class Custom(click.Choice):
        def normalize_choice(self, choice, ctx):
            return super().normalize_choice(choice, ctx).replace("_", "").casefold()

    choice = Custom(["Read_Only", "Write_Only"])
    assert choice.convert("read_only", None, None) == "Read_Only"
    assert completions(choice, "r_e_a_d") == ["Read_Only"]


def test_completion_normalizes_empty_input_and_does_not_short_circuit():
    def normalize(token):
        return "b" if token == "" else token

    choice = click.Choice(["alpha", "beta"])
    ctx = click.Context(click.Command("cli"), token_normalize_func=normalize)
    assert completions(choice, "", ctx) == ["beta"]


def test_identical_canonical_tokens_are_deduplicated_and_first_value_wins():
    choice = click.Choice([10, "10", 20, "20"])
    assert choice.convert("10", None, None) == 10
    assert type(choice.convert("10", None, None)) is int
    assert completions(choice, "") == ["10", "20"]


def test_first_match_is_original_object_even_for_later_equal_object():
    first, later = [1], [1]
    assert first is not later
    choice = click.Choice([first, later])
    assert choice.convert(later, None, None) is first


def test_reuse_does_not_cache_context_in_conversion_or_completion():
    choice = click.Choice(["Read_Only", "Write_Only"])
    a = click.Context(click.Command("a"), token_normalize_func=lambda s: s.lower())
    b = click.Context(click.Command("b"), token_normalize_func=lambda s: s.replace("-", "_"))
    assert choice.convert("read_only", None, a) == "Read_Only"
    assert completions(choice, "read", a) == ["Read_Only"]
    assert choice.convert("Read-Only", None, b) == "Read_Only"
    assert completions(choice, "Read-", b) == ["Read_Only"]
    with pytest.raises(click.BadParameter):
        choice.convert("read_only", None, b)
    with pytest.raises(click.BadParameter):
        choice.convert("Read-Only", None, None)
    assert completions(choice, "read", b) == []
    assert completions(choice, "Read-", click.Context(click.Command("c"))) == []


@pytest.mark.parametrize("source", ["commandline", "environment", "default_map", "default", "callable"])
@pytest.mark.parametrize("shape", ["scalar", "multiple", "pair", "repeated_pair"])
def test_sources_precedence_callbacks_and_tuple_shapes(source, shape):
    """R4 checks all sources through parsing, not by directly calling convert."""
    expected = {
        "scalar": Mode.SAFE,
        "multiple": (Mode.SAFE, Mode.FAST),
        "pair": (Mode.SAFE, Mode.FAST),
        "repeated_pair": ((Mode.SAFE, Mode.FAST), (Mode.FAST, Mode.SAFE)),
    }[shape]
    fallback = {
        "scalar": Mode.FAST,
        "multiple": (Mode.FAST,),
        "pair": (Mode.FAST, Mode.FAST),
        "repeated_pair": ((Mode.FAST, Mode.FAST),),
    }[shape]
    arguments = {
        "scalar": ["--value", "SAFE"],
        "multiple": ["--value", "SAFE", "--value", "FAST"],
        "pair": ["--value", "SAFE", "FAST"],
        "repeated_pair": ["--value", "SAFE", "FAST", "--value", "FAST", "SAFE"],
    }[shape]
    env_text = {"scalar": "SAFE", "multiple": "SAFE FAST", "pair": "SAFE FAST",
                "repeated_pair": "SAFE FAST FAST SAFE"}[shape]
    callbacks, default_calls = [], []

    def default_factory():
        default_calls.append(True)
        return expected if source == "callable" else fallback

    def callback(ctx, param, value):
        callbacks.append((value, ctx.get_parameter_source(param.name)))
        return value

    kwargs = dict(type=click.Choice(Mode), envvar="DA_TYPED_VALUE", callback=callback)
    if shape in ("multiple", "repeated_pair"):
        kwargs["multiple"] = True
    if shape in ("pair", "repeated_pair"):
        kwargs["nargs"] = 2
    kwargs["default"] = expected if source == "default" else default_factory

    @click.command()
    @click.option("--value", **kwargs)
    @click.pass_context
    def cli(ctx, value):
        return value, ctx.get_parameter_source("value")

    env = {"DA_TYPED_VALUE": None}
    extras = {}
    args = []
    if source in ("commandline", "environment"):
        env["DA_TYPED_VALUE"] = env_text
        extras["default_map"] = {"value": fallback}
    if source == "commandline":
        args = arguments
        env["DA_TYPED_VALUE"] = "FAST" if shape in ("scalar", "multiple") else "FAST FAST"
    if source == "default_map":
        extras["default_map"] = {"value": expected}
    result = CliRunner().invoke(cli, args, env=env, standalone_mode=False, **extras)
    assert result.exit_code == 0, result.exception
    expected_source = {
        "commandline": ParameterSource.COMMANDLINE,
        "environment": ParameterSource.ENVIRONMENT,
        "default_map": ParameterSource.DEFAULT_MAP,
        "default": ParameterSource.DEFAULT,
        "callable": ParameterSource.DEFAULT,
    }[source]
    assert result.return_value == (expected, expected_source)
    assert callbacks == [(expected, expected_source)]
    assert len(default_calls) == (1 if source == "callable" else 0)


def test_optional_missing_value_remains_none():
    @click.command()
    @click.option("--mode", type=click.Choice(Mode))
    def cli(mode):
        return mode

    result = CliRunner().invoke(cli, [], standalone_mode=False)
    assert result.exit_code == 0
    assert result.return_value is None


@pytest.mark.parametrize("required, expected", [(True, "{FAST|SAFE}"), (False, "[FAST|SAFE]")])
def test_argument_metavar_brackets(required, expected):
    choice = click.Choice(Mode)
    param = click.Argument(["mode"], type=choice, required=required)
    assert choice.get_metavar(param) == expected


def test_display_tokens_are_not_context_normalized_or_casefolded():
    choice = click.Choice(Mode, case_sensitive=False)
    ctx = click.Context(click.Command("cli"), token_normalize_func=str.lower)
    param = click.Option(["--mode"], type=choice)
    assert choice.get_metavar(param) == "[FAST|SAFE]"
    assert choice.get_missing_message(param) == "Choose from:\n\tFAST,\n\tSAFE"
    with pytest.raises(click.BadParameter) as error:
        choice.convert("bad", param, ctx)
    assert str(error.value) == "'bad' is not one of 'FAST', 'SAFE'."
    assert completions(choice, "f", ctx) == ["FAST"]


@pytest.mark.parametrize("defaults", [(Mode.FAST, Mode.SAFE), [Mode.FAST, Mode.SAFE]])
def test_repeated_defaults_keep_join_format_for_lists_and_tuples(defaults):
    @click.command(context_settings={"show_default": True})
    @click.option("--mode", multiple=True, type=click.Choice(Mode), default=defaults)
    def cli(mode):
        pass

    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "default: FAST, SAFE" in result.output


def test_context_enables_single_enum_default_display():
    @click.command(context_settings={"show_default": True})
    @click.option("--mode", type=click.Choice(NumberMode), default=NumberMode.ZERO)
    def cli(mode):
        pass

    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "default: ZERO" in result.output


def test_non_choice_and_empty_string_choice_default_display_unchanged():
    @click.command()
    @click.option("--name", default="", show_default=True)
    @click.option("--choice", type=click.Choice(["", "other"]), default="", show_default=True)
    @click.option("--number", type=int, default=3, show_default=True)
    def cli(name, choice, number):
        pass

    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert result.output.count('default: ""') == 2
    assert "default: 3" in result.output
