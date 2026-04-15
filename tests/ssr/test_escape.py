"""Tests for pyxle.ssr._escape — inline-JSON escaping utilities."""

import json

import pytest

from pyxle.ssr._escape import escape_inline_json


class TestEscapeInlineJson:
    """Verify that all known dangerous sequences are neutralised."""

    def test_closes_script_tag(self):
        assert "</script>" not in escape_inline_json('{"x":"</script>"}')
        assert "<\\/script>" in escape_inline_json('{"x":"</script>"}')

    def test_closes_style_tag(self):
        assert "</style>" not in escape_inline_json("body{} </style>")

    def test_html_comment_open(self):
        result = escape_inline_json("<!-- comment -->")
        assert "<!--" not in result
        assert "\\u003c!--" in result

    def test_html_comment_close(self):
        result = escape_inline_json("<!-- comment -->")
        assert "-->" not in result
        assert "--\\u003e" in result

    def test_unicode_line_separator(self):
        result = escape_inline_json('{"x":"\u2028"}')
        assert "\u2028" not in result
        assert "\\u2028" in result

    def test_unicode_paragraph_separator(self):
        result = escape_inline_json('{"x":"\u2029"}')
        assert "\u2029" not in result
        assert "\\u2029" in result

    def test_safe_content_unchanged(self):
        safe = '{"name":"Pyxle","version":"1.0"}'
        assert escape_inline_json(safe) == safe

    def test_empty_string(self):
        assert escape_inline_json("") == ""

    def test_multiple_dangerous_sequences(self):
        raw = '</script><!-- -->\u2028\u2029'
        result = escape_inline_json(raw)
        assert "</script>" not in result
        assert "<!--" not in result
        assert "-->" not in result
        assert "\u2028" not in result
        assert "\u2029" not in result

    @pytest.mark.parametrize(
        "input_val,expected_fragment",
        [
            ("</", "<\\/"),
            ("<!--", "\\u003c!--"),
            ("-->", "--\\u003e"),
            ("\u2028", "\\u2028"),
            ("\u2029", "\\u2029"),
        ],
    )
    def test_individual_replacements(self, input_val, expected_fragment):
        assert expected_fragment in escape_inline_json(input_val)

    @pytest.mark.parametrize(
        "payload",
        [
            {"raw": "--> shell prompt"},
            {"raw": "<!-- html comment -->"},
            {"raw": "</script><script>alert(1)</script>"},
            {"raw": "line1\u2028line2"},
            {"nested": {"list": ["-->", "<!--", "</script>"]}},
            {"combo": "foo --> bar <!-- baz --> qux </script>"},
        ],
    )
    def test_output_is_valid_json_after_escape(self, payload):
        """Regression: the escaped output MUST still be parseable with
        JSON.parse / json.loads, and it must round-trip to the original data.

        Earlier versions replaced ``<!--`` with ``<\\!--`` and ``-->`` with
        ``--\\>``, both of which are invalid JSON escape sequences — this
        broke every docs page whose rendered content contained a literal
        ``-->`` (e.g. shell output examples)."""
        raw = json.dumps(payload, ensure_ascii=False)
        escaped = escape_inline_json(raw)
        # Must still parse, and must round-trip to the original data.
        assert json.loads(escaped) == payload
        # And none of the dangerous literal sequences survived.
        assert "</" not in escaped or "<\\/" in escaped
        assert "<!--" not in escaped
        assert "-->" not in escaped
