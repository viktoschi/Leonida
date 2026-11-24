# Contributing

Thanks for helping. A few rules keep the project safe to host:

- **No game data, ever.** That covers archives, the executable, carved files, shaders (DXBC, FSSM, disassembly,
  SPIR-V), textures, models, audio, videos, and reports or logs that quote them. `.gitignore` blocks the common
  types; check `git status` before you commit anyway.
- **No keys, decryption or protection workarounds**, and no links to where to get them. The tools only read files
  that are already plain on disk.
- Short excerpts needed to explain a format (a few header bytes, one instruction sequence) are fine in docs and
  comments.

## Before you start

Search the [current issues][issues] and [pull requests][pulls] to avoid duplicate work. For substantial changes,
describe the scope and intended tests in a relevant issue before implementing. Use a draft PR to share early work.
Link related issues and dependencies in the PR. Numbers from the original repository are historical; qualify
them with that repository's name or URL rather than treating them as IDs in this repository.

Keep changes focused and report reproducible commands, results, skipped checks, and relevant versions. For GPU
reports, include the exact commit, operating system, GPU, driver, and synthetic test output with local paths and
game information removed. A successful API call, valid SPIR-V, and bit-exact output are different results.
Separate new measurements from historical reports. See [GOVERNANCE.md](GOVERNANCE.md) for review and merge
policy, and [SECURITY.md](SECURITY.md) for private reporting instructions.
Please follow the [code of conduct](CODE_OF_CONDUCT.md). Contributions do not require joining the organization;
start with a fork and a pull request. See the [contributor access policy](GOVERNANCE.md#contributor-access) for
the responsibilities of each team.

Only contribute material you are authorized to redistribute. Preserve authorship, copyright and license notices;
for new third-party material document its source, version and applicable terms in the PR.

[issues]: https://github.com/LeonidaReforge/Leonida/issues
[pulls]: https://github.com/LeonidaReforge/Leonida/pulls

## Working on the code

- Python tools run with `python -I` and use only the standard library unless a file says otherwise.
- A text file a tool writes (JSON, CSV, a manifest, an assembly listing) names its line ending: `open(path, "w",
  encoding="utf-8", newline="\n")` (the same for `Path.open`, `Path.write_text` and a text-mode
  `tempfile.NamedTemporaryFile`), so the output is LF on Windows too and the same input gives the same bytes on every
  platform. `tests/test_text_write_line_endings.py` fails for a writer that forgets it.
- A report writer refuses an output that names one of its inputs or another output, and asks
  `tools/report_paths.same_report_path(a, b)` rather than deriving the answer again: it resolves both paths,
  applies the volume's case rules and falls back to `os.path.samefile`, so a new tool reuses one answer
  instead of a private copy. `tests/test_report_paths.py` covers it.
- A test that decodes the output of a child process names a replacement policy: `encoding="utf-8",
  errors="replace"`. On a Windows host whose UI language is not English the child writes the localized Win32 text
  in the ANSI code page, and a strict decode kills the reader thread, so `stdout` and `stderr` come back as `None`
  and replace the real failure with a `TypeError`. Where the bytes are the subject, capture without `encoding=`
  and compare `bytes`. `tests/test_child_output_decoding.py` fails for a capture that forgets the policy.
- `tools/rpf9dump` needs the submodule: `git submodule update --init`.
- A new shader-translator rule goes into the contract table in `docs/design.md`, with how it was confirmed: a GPU
  test, a Mesa/LLVM reference, or a count over the corpus.
- `python -I tests/test_<name>.py` runs one of the unit tests (standard library only; CI runs them all). The test
  files with no `__main__` block or an `import pytest` (they need the packages in `tests/requirements.txt`) run with
  `python -m pytest tests/test_<name>.py` instead, as [AGENTS.md](AGENTS.md) describes; under `python -I` they fail
  to import or run nothing.
- Runtime tests: `cmake -S runtime -B runtime/build`, `cmake --build runtime/build --config RelWithDebInfo`, then
  `ctest --test-dir runtime/build -C RelWithDebInfo --output-on-failure`. The CPU tests that need no game data are configured
  on Windows; Linux and macOS configure the portable subset (`gta6rt` and the shims are Windows-only). Tests that need the retail package read `LEONIDA_GAME_DIR` (and `LEONIDA_MOVIE` for the Bink
  decode test) in place and print `SKIP` when the variable is unset; never copy or commit those files.
- Viewer streaming tests: `node --test tests/test_viewer_streaming.cjs` (Node.js 22+, CI tests 24 LTS; no packages,
  browser, network or game data). These execute the viewer streaming code with a synthetic loader and clock.
- `loader_test` writes small PE images to a `leonida_loader_test` folder in `%TEMP%`. Antivirus that blocks newly
  written executables makes it stop with that reason; exclude the folder or set `LEONIDA_TEST_DIR` to one it skips.
- Tool checks: `python -m compileall -q make_game.py tools tests`. The optional
  `vk_pipeline_check <spirv dir> [cache.bin] [--jobs N]` creates a module (and, for compute shaders, a
  pipeline) for every translated shader and reports failures plus the saved cache path.
- GPU tests are small hand-written RDNA2 programs in `runtime/test/shaders`. `build.py` turns them into SPIR-V
  using `llvm-mc` with the AMDGPU target (LLVM 21+). `check.py` runs them on your GPU and compares the results.
  A new test gets its expected values in the comment at its top and a check in `check.py`.
  [docs/testing.md](docs/testing.md) covers setup per OS, including native Windows options, and known problems.
- Say what you tested and on which GPU in the pull request.
- Run the translator tests with `python -I scripts/run_semantic_tests.py tests/semantic` (see `tests/semantic/README.md`). A new
  translator rule should come with a small hand-written `.asm` fixture and its expected output words.
