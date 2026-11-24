"""tools/smem_neg_probe.py without a GPU: encodings, translator expectations, kernel builder, and oracle lifecycle.

    python -I tests/test_smem_neg_probe.py
"""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "hw_oracle"))

import runner  # noqa: E402
import smem_neg_probe as p  # noqa: E402


class SmemNegProbeTest(unittest.TestCase):
    def test_seed_bounds(self):
        self.assertEqual(p.seed(-0x40), (p.SEED - 0x40) & 0xFFFFFFFF)
        self.assertEqual(p.seed(0), p.SEED)
        self.assertEqual(p.seed(0xBC), p.SEED + 0xBC)
        self.assertIsNone(p.seed(-0x44))
        self.assertIsNone(p.seed(0xC0))

    def test_sbuf_raw_encoding(self):
        lines = p.sbuf_raw(48, 12, 0x7D, -4)
        self.assertEqual(lines, [".long 0xf4200c06", ".long 0xfa1ffffc"])

    def test_translator_sbuf_bounds(self):
        self.assertEqual(p.translator_sbuf(0, 0), [0])
        self.assertEqual(p.translator_sbuf(0xFC, 0), [0xFC])
        self.assertEqual(p.translator_sbuf(0x100, 0), [None])
        # No 32-bit wrap (#1686; gfx1036 and gfx1030 read 0 here): 0xfffffffc + 8 is past NUM_RECORDS, not +4.
        self.assertEqual(p.translator_sbuf(0xFFFFFFFC, 8), [None])
        self.assertEqual(p.translator_sbuf(0xFFFFFFFC, 0), [None])
        self.assertEqual(p.translator_sbuf(0x80000000, 0), [None])
        self.assertEqual(p.translator_sbuf(0xF0, 0xC), [0xFC])
        self.assertEqual(p.translator_sbuf(0xF0, 0x10), [None])

    def test_expected_and_kernel_lines(self):
        want = p.expected()
        self.assertEqual(list(want.keys()), [r[0] for r in p.ROWS])
        self.assertEqual(want["sload_imm_m4"], [(p.SEED - 4) & 0xFFFFFFFF])
        self.assertEqual(want["sload_x2_soff4_m10"], [(p.SEED - 0xC) & 0xFFFFFFFF, (p.SEED - 8) & 0xFFFFFFFF])
        self.assertEqual(want["sbuf_soffm4_imm8"], [None])
        self.assertEqual(want["sbuf_soffm4"], [None])

        lines, order = p.kernel_lines()
        self.assertEqual(len(order), sum(len(r[2]) for r in p.ROWS))
        self.assertEqual(lines[-1], "s_endpgm")

    def test_unsupported_encodings_are_never_run(self):
        names = {r[0] for r in p.ROWS}
        lines, _order = p.kernel_lines()
        self.assertEqual(len(p.UNSUPPORTED), 2)
        for name, enc, why in p.UNSUPPORTED:
            with self.subTest(name=name):
                self.assertNotIn(name, names)
                self.assertNotIn(name, p.expected())
                w1 = int(enc[1].split()[1], 16)
                self.assertTrue(w1 & 0x100000, "an unsupported row is a bit-20 IMM encoding")
                for word in enc:
                    self.assertNotIn(word, lines)
                self.assertIn("gfx1030", why)
        self.assertFalse([ln for ln in lines if ln.startswith(".long")], "the safe kernel has no hand-encoded words")

    def test_translator_mode_prints_every_row(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = p.main(["--oracle", "translator"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        for name, *_ in p.ROWS:
            self.assertIn(name, out)
        for name, *_ in p.UNSUPPORTED:
            self.assertIn(f"{name:22} unsupported, not run", out)


class OracleLifecycleTest(unittest.TestCase):
    def _expected_flat(self):
        want = p.expected()
        flat = []
        for name, *_ in p.ROWS:
            flat.extend(0 if v is None else v for v in want[name])
        return flat

    def _run_hw(self, fake_oracle):
        buf = io.StringIO()
        with (
            mock.patch.object(runner, "open_oracle", return_value=fake_oracle) as open_mock,
            mock.patch.object(runner, "Oracle", side_effect=AssertionError("Oracle() called directly")),
            contextlib.redirect_stdout(buf),
        ):
            rc = p.main(["--oracle", "hw"])
        open_mock.assert_called_once_with()
        return rc, buf.getvalue()

    def test_hw_uses_open_oracle_and_closes_on_match(self):
        flat = self._expected_flat()

        class FakeOracle:
            device = "fake-gpu"
            arch = "gfx1036"
            closed = False

            def run(self, kernels):
                return [list(flat)]

            def close(self):
                self.closed = True

        fake = FakeOracle()
        rc, out = self._run_hw(fake)
        self.assertEqual(rc, 0)
        self.assertTrue(fake.closed)
        self.assertIn("device: fake-gpu (gfx1036)", out)
        self.assertNotIn("DIFFERS", out)
        self.assertIn(f"summary: {len(p.ROWS)} match, 0 differ, 0 not written, 2 unsupported (not run)", out)
        for name, *_ in p.UNSUPPORTED:
            self.assertIn(f"{name:22} unsupported, not run", out)

    def _fake(self, words):
        class FakeOracle:
            device = "fake-gpu"
            arch = "gfx1030"
            closed = False

            def run(self, kernels):
                return [list(words)]

            def close(self):
                self.closed = True
        return FakeOracle()

    def test_hw_unwritten_words_are_incomplete_not_a_result(self):
        flat = self._expected_flat()
        for label, words in (("all", [runner.SENTINEL] * len(flat)),
                             ("one", [runner.SENTINEL] + flat[1:]),
                             ("last", flat[:-1] + [runner.SENTINEL])):
            with self.subTest(case=label):
                fake = self._fake(words)
                rc, out = self._run_hw(fake)
                self.assertEqual(rc, 2)
                self.assertTrue(fake.closed)
                self.assertIn("NOT WRITTEN", out)
                self.assertIn("incomplete", out)
                self.assertNotIn(f"summary: {len(p.ROWS)} match", out)

    def test_hw_wrapped_sbuf_answer_is_a_mismatch(self):
        # The stale rule (32-bit wrap) predicted the dword at +4 for sOFF 0xfffffffc + IMM 8. Hardware reads 0, and
        # a GPU that returned the wrapped answer must now be reported as differing, not as a match.
        flat = self._expected_flat()
        at = sum(len(r[2]) for r in p.ROWS[:[r[0] for r in p.ROWS].index("sbuf_soffm4_imm8")])
        words = list(flat)
        words[at] = p.SEED + 4
        fake = self._fake(words)
        rc, out = self._run_hw(fake)
        self.assertEqual(rc, 1)
        self.assertIn("sbuf_soffm4_imm8", out)
        self.assertIn("DIFFERS", out)

    def test_hw_closes_on_mismatch(self):
        flat = self._expected_flat()

        class FakeOracle:
            device = "fake-gpu"
            arch = "gfx1036"
            closed = False

            def run(self, kernels):
                return [[0] * len(flat)]

            def close(self):
                self.closed = True

        fake = FakeOracle()
        rc, out = self._run_hw(fake)
        self.assertEqual(rc, 1)
        self.assertTrue(fake.closed)
        self.assertIn("DIFFERS", out)

    def test_hw_accepts_tuple_oracle_results(self):
        flat = self._expected_flat()

        class FakeOracle:
            device = "fake-gpu"
            arch = "gfx1036"
            closed = False

            def run(self, kernels):
                return (tuple(flat),)

            def close(self):
                self.closed = True

        fake = FakeOracle()
        rc, out = self._run_hw(fake)
        self.assertEqual(rc, 0)
        self.assertTrue(fake.closed)
        self.assertNotIn("DIFFERS", out)

    def test_hw_closes_on_malformed_oracle_results(self):
        flat = self._expected_flat()

        class FakeOracle:
            device = "fake-gpu"
            arch = "gfx1036"

            def __init__(self, responses):
                self.responses = responses
                self.closed = False

            def run(self, kernels):
                return self.responses[kernels[0].wave]

            def close(self):
                self.closed = True

        bad_cases = [
            ("empty_results", [], "expected 1"),
            ("none_results", None, "NoneType"),
            ("str_results", "bad", "str"),
            ("extra_results", [list(flat), list(flat)], "got 2"),
            ("none_kernel_result", [None], "NoneType"),
            ("int_kernel_result", [123], "int"),
            ("short_words", [[0] * 4], f"expected {len(flat)} words, got 4"),
            ("overlong_zeros", [[0] * (len(flat) + 1)], f"expected {len(flat)} words, got {len(flat) + 1}"),
            ("overlong_matching", [list(flat) + [0]], f"expected {len(flat)} words, got {len(flat) + 1}"),
            ("non_int_word", [[None] * len(flat)], "NoneType"),
            ("bool_word", [[True] * len(flat)], "bool"),
        ]
        for label, bad_ret, hint in bad_cases:
            for fail_wave in (32, 64):
                with self.subTest(case=label, wave=fail_wave):
                    responses = {32: [list(flat)], 64: [list(flat)]}
                    responses[fail_wave] = bad_ret
                    fake = FakeOracle(responses)
                    rc, out = self._run_hw(fake)
                    self.assertEqual(rc, 2)
                    self.assertTrue(fake.closed)
                    self.assertIn(f"wave{fail_wave}:", out)
                    self.assertIn(hint, out)
                    self.assertNotIn("device:", out)

    def test_hw_closes_on_kernel_rejection(self):
        class FakeOracle:
            device = "fake-gpu"
            arch = "gfx1036"
            closed = False

            def run(self, kernels):
                return ["assembler rejected"]

            def close(self):
                self.closed = True

        fake = FakeOracle()
        rc, out = self._run_hw(fake)
        self.assertEqual(rc, 2)
        self.assertTrue(fake.closed)
        self.assertIn("kernel rejected", out)

    def test_hw_unavailable_returns_77(self):
        buf = io.StringIO()
        with (
            mock.patch.object(runner, "open_oracle", side_effect=runner.Unavailable("no device")),
            mock.patch.object(runner, "Oracle", side_effect=AssertionError("Oracle() called directly")),
            contextlib.redirect_stdout(buf),
        ):
            rc = p.main(["--oracle", "hw"])
        self.assertEqual(rc, 77)
        self.assertIn("no device", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
