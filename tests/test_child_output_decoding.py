"""A captured child process is decoded with a replacement policy, never with strict UTF-8.

On a Windows host whose UI language is not English, a test's child process writes the localized Win32
error text in the ANSI code page (cp1252 for German: "0xfc" is the u-umlaut). A
`subprocess.run(..., encoding="utf-8")` without `errors=` then kills the reader thread; `stdout` and
`stderr` come back as None, and the real failure is replaced by a `UnicodeDecodeError` or a
`TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'` far away from its cause. The
hosted runners are en-US, so nothing there notices.

The bytes stay authoritative where a test compares them: capture without `encoding=` and compare
`bytes`, as `test_redirected_cli_preserves_unicode_paths_and_guest_diagnostic` does.
"""
import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TESTS = Path(__file__).resolve().parent
# Callables whose keyword arguments decide how the child's output is decoded.
CAPTURING_CALLS = {"run", "check_output", "call", "check_call", "Popen"}


def decoded_captures(path):
    """Return the (line, function) of every captured call in `path` that names a codec but no policy."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None)
        if name not in CAPTURING_CALLS:
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
        if "encoding" not in keywords or "errors" in keywords:
            continue
        yield node.lineno, name


class ChildOutputDecodingTest(unittest.TestCase):
    def test_every_decoded_capture_names_a_replacement_policy(self):
        offenders = []
        for path in sorted(TESTS.rglob("test_*.py")):
            for line, name in decoded_captures(path):
                offenders.append(f"{path.relative_to(TESTS).as_posix()}:{line} ({name})")
        self.assertEqual(offenders, [])

    def test_the_check_finds_a_missing_policy(self):
        # The guard has to bite on the shape it forbids, or it would pass over a re-introduced bug.
        with tempfile.TemporaryDirectory() as temp:
            sample = Path(temp) / "test_sample.py"
            sample.write_text(
                "import subprocess\n"
                "subprocess.run(['cmd'], capture_output=True, encoding='utf-8')\n"
                "subprocess.run(['cmd'], capture_output=True, encoding='utf-8', errors='replace')\n",
                encoding="utf-8",
            )
            found = list(decoded_captures(sample))
        self.assertEqual(found, [(2, "run")])

    def test_a_child_writing_ansi_bytes_keeps_its_text_with_the_policy(self):
        # The rule is not style: the same call without a policy loses both streams before it returns.
        with tempfile.TemporaryDirectory() as temp:
            child = Path(temp) / "child.py"
            child.write_text(
                "import sys\n"
                "for stream in (sys.stdout, sys.stderr):\n"
                "    stream.buffer.write(b'error 0xfc \\xfc\\n')\n"
                "    stream.buffer.flush()\n"
                "sys.exit(1)\n",
                encoding="ascii",
            )
            raw = subprocess.run([sys.executable, "-I", str(child)], capture_output=True)
            decoded = subprocess.run(
                [sys.executable, "-I", str(child)],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(raw.returncode, 1)
        self.assertEqual(raw.stdout, b"error 0xfc \xfc\n")
        self.assertEqual(decoded.returncode, 1)
        self.assertEqual(decoded.stdout, "error 0xfc \ufffd\n")
        self.assertEqual(decoded.stderr, "error 0xfc \ufffd\n")


if __name__ == "__main__":
    unittest.main()
