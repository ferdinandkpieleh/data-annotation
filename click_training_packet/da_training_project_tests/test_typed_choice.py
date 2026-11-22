"""Tests for the extended Choice type that supports typed choices (enums, integers, etc.)."""
import enum

import click
from click import Choice, Context, Command, Option, Argument
from click.shell_completion import ShellComplete, CompletionItem
from click.testing import CliRunner


# ---- Helpers ----

def _get_completions(cli, args, incomplete):
    comp = ShellComplete(cli, {}, cli.name, "_CLICK_COMPLETE")
    return comp.get_completions(args, incomplete)


def _get_words(cli, args, incomplete):
    return [c.value for c in _get_completions(cli, args, incomplete)]


class Color(enum.Enum):
    RED = "red-value"
    GREEN = "green-value"
    BLUE = "blue-value"


class Mode(enum.Enum):
    FAST = "fast-value"
    SAFE = "safe-value"


class StrEnum(str, enum.Enum):
    ALPHA = "alpha-val"
    BETA = "beta-val"


class IntEnum(int, enum.Enum):
    ONE = 1
    TWO = 2


class Priority(enum.Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = HIGH


# ---- Requirement 1: Construction from various iterables ----

class TestChoiceConstruction:
    def test_accepts_enum_class(self):
        c = Choice(Color)
        assert len(list(c.choices)) == 3

    def test_accepts_generator(self):
        def gen():
            yield 10
            yield 20
            yield 30
        c = Choice(gen())
        assert len(list(c.choices)) == 3

    def test_snapshot_isolation_from_original_list(self):
        original = ["a", "b", "c"]
        c = Choice(original)
        original.append("d")
        original.remove("a")
        assert list(c.choices) == ["a", "b", "c"]

    def test_enum_aliases_not_duplicated(self):
        c = Choice(Priority)
        names = [m.name for m in c.choices]
        assert names == ["LOW", "MEDIUM", "HIGH"]

    def test_preserves_unhashable_objects(self):
        items = [{"x": 1}, {"x": 2}]
        c = Choice(items)
        assert c.convert("{'x': 1}", None, None) is items[0]

    def test_preserves_original_objects(self):
        c = Choice([10, 20, 30])
        result = c.convert("20", None, None)
        assert result == 20
        assert isinstance(result, int)

    def test_generator_consumed_once(self):
        consumed = []

        def gen():
            for i in [1, 2, 3]:
                consumed.append(i)
                yield i

        c = Choice(gen())
        _ = list(c.choices)
        _ = list(c.choices)
        assert consumed == [1, 2, 3]


# ---- Requirement 2: Canonical tokens and normalize_choice ----

class TestCanonicalTokens:
    def test_enum_member_uses_name(self):
        c = Choice(Mode)
        assert c.normalize_choice(Mode.FAST, None) == "FAST"

    def test_str_enum_uses_name_not_value(self):
        c = Choice(StrEnum)
        assert c.normalize_choice(StrEnum.ALPHA, None) == "ALPHA"

    def test_int_enum_uses_name_not_value(self):
        c = Choice(IntEnum)
        assert c.normalize_choice(IntEnum.ONE, None) == "ONE"

    def test_non_enum_uses_str(self):
        c = Choice([10, 20])
        assert c.normalize_choice(10, None) == "10"

    def test_normalize_applies_ctx_token_normalize_func(self):
        c = Choice(["read_only"])
        ctx = Context(Command("test"), token_normalize_func=lambda s: s.replace("-", "_"))
        assert c.normalize_choice("read-only", ctx) == "read_only"

    def test_normalize_applies_casefold_when_not_case_sensitive(self):
        c = Choice(["Hello"], case_sensitive=False)
        result = c.normalize_choice("HELLO", None)
        assert result == "hello"

    def test_normalize_order_ctx_then_casefold(self):
        c = Choice(["ABC"], case_sensitive=False)
        ctx = Context(Command("test"), token_normalize_func=lambda s: s.replace("-", "_"))
        result = c.normalize_choice("A-BC", ctx)
        assert result == "a_bc"

    def test_normalize_choice_with_none_ctx(self):
        c = Choice(Color)
        result = c.normalize_choice(Color.RED, None)
        assert result == "RED"

    def test_subclass_override_normalize_choice(self):
        class CustomChoice(Choice):
            def normalize_choice(self, choice, ctx):
                token = choice.name if isinstance(choice, enum.Enum) else str(choice)
                return token.upper()

        c = CustomChoice(Mode)
        assert c.normalize_choice(Mode.FAST, None) == "FAST"
        assert c.convert("fast", None, None) == Mode.FAST


# ---- Requirement 3: Conversion behavior ----

class TestConversion:
    def test_enum_convert_by_name(self):
        c = Choice(Mode)
        assert c.convert("FAST", None, None) is Mode.FAST

    def test_enum_convert_case_insensitive(self):
        c = Choice(Mode, case_sensitive=False)
        assert c.convert("fast", None, None) is Mode.FAST

    def test_int_choice_convert(self):
        c = Choice([10, 20])
        result = c.convert("20", None, None)
        assert result == 20
        assert isinstance(result, int)

    def test_returns_first_match_in_source_order(self):
        c = Choice(["Straße", "STRASSE"], case_sensitive=False)
        result = c.convert("strasse", None, None)
        assert result == "Straße"

    def test_first_match_wins_even_with_later_stored_object(self):
        c = Choice(["Straße", "STRASSE"], case_sensitive=False)
        result = c.convert("STRASSE", None, None)
        assert result == "Straße"

    def test_non_string_input_uses_canonical_token(self):
        c = Choice(Color)
        result = c.convert(Color.RED, None, None)
        assert result is Color.RED

    def test_bad_parameter_on_invalid_value(self):
        c = Choice(Mode)
        import pytest
        with pytest.raises(click.exceptions.BadParameter):
            c.convert("INVALID", None, None)

    def test_no_attribute_error_on_non_string_input(self):
        c = Choice([10, 20])
        import pytest
        with pytest.raises(click.exceptions.BadParameter):
            c.convert(99, None, None)

    def test_unhashable_choices_work(self):
        items = [["a", "b"], ["c", "d"]]
        c = Choice(items)
        result = c.convert("['a', 'b']", None, None)
        assert result is items[0]

    def test_convert_with_ctx_normalizer(self):
        c = Choice(["read_only"])
        ctx = Context(Command("test"), token_normalize_func=lambda s: s.replace("-", "_"))
        assert c.convert("read-only", None, ctx) == "read_only"

    def test_enum_idempotent_convert(self):
        c = Choice(Mode)
        assert c.convert(Mode.FAST, None, None) is Mode.FAST

    def test_string_choice_still_works(self):
        c = Choice(["foo", "bar", "baz"])
        assert c.convert("bar", None, None) == "bar"


# ---- Requirement 4: Integration with Click options/arguments ----

class TestIntegration:
    def test_enum_option(self):
        runner = CliRunner()

        @click.command()
        @click.option("--mode", type=Choice(Mode))
        def cli(mode):
            click.echo(f"{mode.name}:{mode.value}")

        result = runner.invoke(cli, ["--mode=FAST"])
        assert result.exit_code == 0
        assert result.output == "FAST:fast-value\n"

    def test_enum_argument(self):
        runner = CliRunner()

        @click.command()
        @click.argument("color", type=Choice(Color))
        def cli(color):
            click.echo(color.name)

        result = runner.invoke(cli, ["RED"])
        assert result.exit_code == 0
        assert result.output == "RED\n"

    def test_int_choice_option(self):
        runner = CliRunner()

        @click.command()
        @click.option("--count", type=Choice([1, 2, 3]))
        def cli(count):
            click.echo(f"{count}:{type(count).__name__}")

        result = runner.invoke(cli, ["--count=2"])
        assert result.exit_code == 0
        assert result.output == "2:int\n"

    def test_enum_via_envvar(self):
        runner = CliRunner()

        @click.command()
        @click.option("--mode", type=Choice(Mode), envvar="APP_MODE")
        def cli(mode):
            click.echo(mode.name)

        result = runner.invoke(cli, env={"APP_MODE": "SAFE"})
        assert result.exit_code == 0
        assert result.output == "SAFE\n"

    def test_enum_default(self):
        runner = CliRunner()

        @click.command()
        @click.option("--mode", type=Choice(Mode), default=Mode.FAST)
        def cli(mode):
            click.echo(mode.name)

        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert result.output == "FAST\n"

    def test_callable_default(self):
        runner = CliRunner()

        @click.command()
        @click.option("--mode", type=Choice(Mode), default=lambda: Mode.SAFE)
        def cli(mode):
            click.echo(mode.name)

        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert result.output == "SAFE\n"

    def test_multiple_option(self):
        runner = CliRunner()

        @click.command()
        @click.option("--color", type=Choice(Color), multiple=True)
        def cli(color):
            for c in color:
                click.echo(c.name)

        result = runner.invoke(cli, ["--color=RED", "--color=BLUE"])
        assert result.exit_code == 0
        assert result.output == "RED\nBLUE\n"

    def test_nargs_option(self):
        runner = CliRunner()

        @click.command()
        @click.option("--pair", type=Choice(Color), nargs=2)
        def cli(pair):
            for c in pair:
                click.echo(c.name)

        result = runner.invoke(cli, ["--pair", "RED", "GREEN"])
        assert result.exit_code == 0
        assert result.output == "RED\nGREEN\n"

    def test_default_map(self):
        runner = CliRunner()

        @click.command()
        @click.option("--mode", type=Choice(Mode))
        @click.pass_context
        def cli(ctx, mode):
            click.echo(mode.name)

        result = runner.invoke(
            cli, [],
            default_map={"mode": "SAFE"},
        )
        assert result.exit_code == 0
        assert result.output == "SAFE\n"

    def test_parameter_source_reporting(self):
        runner = CliRunner()

        @click.command()
        @click.option("--mode", type=Choice(Mode), default=Mode.FAST)
        @click.pass_context
        def cli(ctx, mode):
            source = ctx.get_parameter_source("mode")
            click.echo(source.name)

        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "DEFAULT" in result.output

        result = runner.invoke(cli, ["--mode=SAFE"])
        assert result.exit_code == 0
        assert "COMMANDLINE" in result.output

    def test_reusable_choice_across_contexts(self):
        choice_type = Choice(["read_only", "write"])

        @click.command("cmd1", context_settings=dict(
            token_normalize_func=lambda s: s.replace("-", "_")
        ))
        @click.option("--mode", type=choice_type)
        def cmd1(mode):
            click.echo(mode)

        @click.command("cmd2")
        @click.option("--mode", type=choice_type)
        def cmd2(mode):
            click.echo(mode)

        runner = CliRunner()

        result = runner.invoke(cmd1, ["--mode=read-only"])
        assert result.exit_code == 0
        assert result.output.strip() == "read_only"

        result = runner.invoke(cmd2, ["--mode=read_only"])
        assert result.exit_code == 0
        assert result.output.strip() == "read_only"

        result = runner.invoke(cmd2, ["--mode=read-only"])
        assert result.exit_code != 0


# ---- Requirement 5: Metavar, missing message, error messages ----

class TestDisplay:
    def test_enum_metavar_option(self):
        runner = CliRunner()

        @click.command()
        @click.option("--mode", type=Choice(Mode))
        def cli(mode):
            pass

        result = runner.invoke(cli, ["--help"])
        assert "[FAST|SAFE]" in result.output

    def test_enum_metavar_required_argument(self):
        runner = CliRunner()

        @click.command()
        @click.argument("mode", type=Choice(Mode))
        def cli(mode):
            pass

        result = runner.invoke(cli, ["--help"])
        assert "{FAST|SAFE}" in result.output

    def test_int_choice_metavar(self):
        runner = CliRunner()

        @click.command()
        @click.option("--n", type=Choice([10, 20, 30]))
        def cli(n):
            pass

        result = runner.invoke(cli, ["--help"])
        assert "[10|20|30]" in result.output

    def test_enum_missing_message(self):
        runner = CliRunner()

        @click.command()
        @click.option("--mode", type=Choice(Mode), required=True)
        def cli(mode):
            pass

        result = runner.invoke(cli, [])
        assert "FAST" in result.output
        assert "SAFE" in result.output

    def test_enum_error_message_uses_canonical_tokens(self):
        runner = CliRunner()

        @click.command()
        @click.option("--mode", type=Choice(Mode))
        def cli(mode):
            pass

        result = runner.invoke(cli, ["--mode=INVALID"])
        assert result.exit_code == 2
        assert "'INVALID'" in result.output
        assert "FAST" in result.output
        assert "SAFE" in result.output

    def test_enum_error_no_qualified_name(self):
        runner = CliRunner()

        @click.command()
        @click.option("--mode", type=Choice(Mode))
        def cli(mode):
            pass

        result = runner.invoke(cli, ["--mode=INVALID"])
        assert "Mode.FAST" not in result.output
        assert "fast-value" not in result.output

    def test_to_info_dict_original_objects(self):
        c = Choice(Color)
        info = c.to_info_dict()
        assert "choices" in info
        choices = info["choices"]
        assert all(isinstance(item, Color) for item in choices)
        assert isinstance(choices, list)
        assert choices == [Color.RED, Color.GREEN, Color.BLUE]

    def test_to_info_dict_case_sensitive_field(self):
        c = Choice(Color, case_sensitive=False)
        info = c.to_info_dict()
        assert info["case_sensitive"] is False


# ---- Requirement 6: show_default for enums ----

class TestShowDefault:
    def test_enum_default_shown_as_canonical_token(self):
        runner = CliRunner()

        @click.command()
        @click.option("--mode", type=Choice(Mode), default=Mode.FAST, show_default=True)
        def cli(mode):
            pass

        result = runner.invoke(cli, ["--help"])
        assert "default: FAST" in result.output
        assert "Mode.FAST" not in result.output
        assert "fast-value" not in result.output

    def test_multiple_enum_defaults_shown_as_tokens(self):
        runner = CliRunner()

        @click.command()
        @click.option(
            "--colors", type=Choice(Color), multiple=True,
            default=[Color.RED, Color.BLUE], show_default=True
        )
        def cli(colors):
            pass

        result = runner.invoke(cli, ["--help"])
        assert "RED, BLUE" in result.output

    def test_explicit_string_show_default_preserved(self):
        runner = CliRunner()

        @click.command()
        @click.option(
            "--mode", type=Choice(Mode), default=Mode.FAST,
            show_default="uses fast mode"
        )
        def cli(mode):
            pass

        result = runner.invoke(cli, ["--help"])
        assert "uses fast mode" in result.output

    def test_callable_default_shown_as_dynamic(self):
        runner = CliRunner()

        calls = []

        def default():
            calls.append(True)
            return Mode.SAFE

        @click.command()
        @click.option(
            "--mode", type=Choice(Mode), default=default,
            show_default=True
        )
        def cli(mode):
            pass

        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "default: (dynamic)" in result.output
        assert calls == []


# ---- Requirement 7: Shell completion ----

class TestShellCompletion:
    def test_enum_completion_basic(self):
        cli = Command("cli", params=[Option(["-m"], type=Choice(Mode))])
        words = _get_words(cli, ["-m"], "")
        assert words == ["FAST", "SAFE"]

    def test_enum_completion_prefix(self):
        cli = Command("cli", params=[Option(["-m"], type=Choice(Mode))])
        words = _get_words(cli, ["-m"], "F")
        assert words == ["FAST"]

    def test_int_choice_completion(self):
        cli = Command("cli", params=[Option(["-n"], type=Choice([10, 20, 30]))])
        words = _get_words(cli, ["-n"], "")
        assert words == ["10", "20", "30"]

    def test_int_choice_completion_prefix(self):
        cli = Command("cli", params=[Option(["-n"], type=Choice([10, 20, 30]))])
        words = _get_words(cli, ["-n"], "2")
        assert words == ["20"]

    def test_case_insensitive_completion_unicode(self):
        cli = Command(
            "cli",
            params=[Option(["-c"], type=Choice(["Straße", "STRASSE"], case_sensitive=False))]
        )
        words = _get_words(cli, ["-c"], "STRASS")
        assert "Straße" in words
        assert "STRASSE" in words

    def test_case_insensitive_completion_returns_both_distinct_tokens(self):
        cli = Command(
            "cli",
            params=[Option(["-c"], type=Choice(["Straße", "STRASSE"], case_sensitive=False))]
        )
        words = _get_words(cli, ["-c"], "strass")
        assert len(words) == 2

    def test_distinct_canonical_tokens_survive_normalization_collision(self):
        class Dup(enum.Enum):
            A = 1
            B = 2

        class DupChoice(Choice):
            def normalize_choice(self, choice, ctx):
                return "same"

        cli = Command("cli", params=[Option(["-x"], type=DupChoice(Dup))])
        words = _get_words(cli, ["-x"], "")
        assert words == ["A", "B"]

    def test_completion_with_ctx_normalizer(self):
        cli = Command(
            "cli",
            params=[Option(["-m"], type=Choice(["read_only", "write"]))],
            context_settings=dict(token_normalize_func=lambda s: s.replace("-", "_")),
        )
        words = _get_words(cli, ["-m"], "read-")
        assert "read_only" in words

    def test_completion_tokens_acceptable_to_conversion(self):
        c = Choice(Mode)
        cli = Command("cli", params=[Option(["-m"], type=c)])
        words = _get_words(cli, ["-m"], "")
        for w in words:
            result = c.convert(w, None, None)
            assert isinstance(result, Mode)

    def test_completion_source_order(self):
        c = Choice(Color)
        cli = Command("cli", params=[Option(["-c"], type=c)])
        words = _get_words(cli, ["-c"], "")
        assert words == ["RED", "GREEN", "BLUE"]

    def test_completion_normalized_prefix_match(self):
        cli = Command(
            "cli",
            params=[Option(["-c"], type=Choice(Color, case_sensitive=False))]
        )
        words = _get_words(cli, ["-c"], "re")
        assert words == ["RED"]

    def test_empty_input_normalized(self):
        cli = Command(
            "cli",
            params=[Option(["-c"], type=Choice(Color, case_sensitive=False))]
        )
        words = _get_words(cli, ["-c"], "")
        assert words == ["RED", "GREEN", "BLUE"]


# ---- Requirement 8: Backward compatibility ----

class TestBackwardCompat:
    def test_string_choice_option_still_works(self):
        runner = CliRunner()

        @click.command()
        @click.option("--method", type=Choice(["foo", "bar", "baz"]))
        def cli(method):
            click.echo(method)

        result = runner.invoke(cli, ["--method=foo"])
        assert result.exit_code == 0
        assert result.output == "foo\n"

    def test_string_choice_error_message(self):
        runner = CliRunner()

        @click.command()
        @click.option("--method", type=Choice(["foo", "bar", "baz"]))
        def cli(method):
            click.echo(method)

        result = runner.invoke(cli, ["--method=meh"])
        assert result.exit_code == 2
        assert "'meh' is not one of 'foo', 'bar', 'baz'" in result.output

    def test_string_choice_help(self):
        runner = CliRunner()

        @click.command()
        @click.option("--method", type=Choice(["foo", "bar", "baz"]))
        def cli(method):
            click.echo(method)

        result = runner.invoke(cli, ["--help"])
        assert "--method [foo|bar|baz]" in result.output

    def test_string_choice_case_insensitive(self):
        runner = CliRunner()

        @click.command()
        @click.option("--foo", type=Choice(["Orange", "Apple"], case_sensitive=False))
        def cli(foo):
            click.echo(foo)

        result = runner.invoke(cli, ["--foo", "apple"])
        assert result.exit_code == 0
        assert result.output == "Apple\n"

    def test_string_choice_completion(self):
        cli = Command("cli", params=[Option(["-c"], type=Choice(["a1", "a2", "b"]))])
        assert _get_words(cli, ["-c"], "") == ["a1", "a2", "b"]
        assert _get_words(cli, ["-c"], "a") == ["a1", "a2"]
