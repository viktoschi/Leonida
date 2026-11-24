# Source-only build prerequisites

Use this inventory to plan a clean checkout and identify which dependencies need to be available before going offline.
The Git revision of the checkout determines all repository-managed pins. Record it with `git rev-parse HEAD`.

## Start with the synthetic CPU checks

The Linux example below uses installed Python, Node, CMake, Ninja, and a C++20 compiler. It uses checked-in sources
and generated test inputs. The CMake commands select one portable target and disable the optional Vulkan header download.

```sh
git submodule status
python3 -IB make_game.py --help
python3 -IB tests/test_boot_trace.py
node --test tests/test_viewer_studio.cjs

build_dir="$(mktemp -d)/runtime"
cmake -S runtime -B "$build_dir" -G Ninja -DBUILD_TESTING=ON -DLEONIDA_VULKAN_HEADERS_FETCH=OFF
cmake --build "$build_dir" --target spirv_capability_test
ctest --test-dir "$build_dir" -N -R '^spirv_capability$'
ctest --test-dir "$build_dir" --output-on-failure -R '^spirv_capability$'
```

These commands were checked from a clean Linux checkout at `2ebde81ec07e530a3558bc3f7c4b79da6c37ab65` with Python
3.12.3, Node 24.22.3, CMake 3.28.3, Ninja 1.11.1, and GCC 13.3.0. They cover the CLI help, synthetic boot trace and
viewer studio tests, and one CTest. The CTest listing should show one test named `spirv_capability`. A leading `-` in `git submodule status` means the recorded submodule is uninitialized.
For a larger CTest run, inspect the registered target list and configure diagnostics first. Missing build
prerequisites can omit entire targets. [Testing guide](testing.md#what-you-need)

## Toolchain and package pins

| Area | Requirement and source of truth |
| --- | --- |
| Python and Node | CI selects Python `3.12` and Node `24`, with patch versions chosen by runner setup. The contributor guide documents Node 22+ for viewer tests. These checks use built-in modules with no npm install. [CI workflow](../.github/workflows/ci.yml) · [Contributor guide](../CONTRIBUTING.md) |
| Python packages | The separate pytest environment pins `pytest==9.2.0`, `numpy==2.5.5`, and `Pillow==13.0.0`. Record hashes, transitive resolutions, and the selected distributions separately for a reproducible package cache. [Requirements](../tests/requirements.txt) |
| C++ runtime | CMake 3.24+ and a C++20 compiler. The native Windows runtime requires an x64 build and Windows SDK 10.0.26100 or later with D3D12 root signature 1.2 declarations. CMake also offers portable tests on Linux and macOS. [Runtime build](../runtime/CMakeLists.txt) |
| .NET and NuGet | `global.json` requests SDK 8.0.100 with `latestMajor` roll-forward. CI selects `8.0.x`. The rpf9dump and diagnostics projects target `net8.0`. Their lockfiles record `BCnEncoder.Net` 2.3.0 and `CommunityToolkit.HighPerformance` 8.4.0 with NuGet content hashes. [SDK settings](../global.json) · [rpf9dump lockfile](../tools/rpf9dump/packages.lock.json) · [Diagnostics lockfile](../tests/Rpf9DumpDiagnostics/packages.lock.json) |
| rpf9-explorer | rpf9dump uses the Core project from the `breadbbbb/rpf9-explorer` submodule. Inspect the exact gitlink with `git ls-tree HEAD third_party/rpf9-explorer`. At the tested revision it is `e2939175c36a02d6ed25fa2c217b9d6ddcb8b516`. [Submodule origin](../.gitmodules) |
| LLVM and SPIRV-Tools | The Linux translator CI job checks for LLVM 21 with AMDGPU and installs distribution `spirv-tools`. The separate llvmpipe fixtures use LLVM 19. The Windows source helper defaults to the `llvmorg-21.1.8` tag. The macOS workflow selects Homebrew versions. Keep the executable versions with test results. [CI workflow](../.github/workflows/ci.yml) · [Runtime workflow](../.github/workflows/runtime.yml) · [Windows LLVM helper](../scripts/build_llvm_mc.ps1) |
| Rust | The BCPack calibration tool builds against vendored bcpack-rs in a locked, offline CI step. The optional XMA2 wrapper uses a separate Cargo lockfile and a Git dependency pinned to `27122f7dfcceb9a899555362ee0dde2d530e033c`. The Windows XMA2 workflow uses runner Rust and MSVC. [bcpack-rs](../third_party/bcpack-rs/Cargo.toml) · [XMA2 manifest](../runtime/xma_decoder/Cargo.toml) · [XMA2 workflow](../.github/workflows/xma2-decoder.yml) |

## Optional configure downloads

CMake's Vulkan-Headers and SDL3 downloads are opt-in. The checked-in archive digests below are SHA-256 values.

| Dependency | Pin and checksum | Offline alternatives |
| --- | --- | --- |
| Vulkan-Headers | SDK tag `vulkan-sdk-1.4.363.0`, commit `6802bb4733b63ed5efd3adb308a6c885ef180ea1`, archive `9044fbb356160e43201dc2094acb44c8a906722a63a35f48fc0f051579db9bb6` | Installed headers, `VULKAN_SDK`, or `FETCHCONTENT_SOURCE_DIR_VULKANHEADERS` |
| SDL3 for Windows GameInput | Release `3.4.20`, archive `f3bb06f55bed9557227a700af2ea62e49497ebdf58037732a731a5fb3ef8581f` | Installed static SDL3 3.2+ via `SDL3_DIR` or `CMAKE_PREFIX_PATH`, or `FETCHCONTENT_SOURCE_DIR_SDL3` |

CMake checks the digest on the pinned fetch path. If you supply an extracted directory override, verify the
source and integrity separately. The Windows runtime workflow also checks SHA-256
`82bf434e69b9bb4829de7e2b4bc2c5e7a7861e53d66cf75e5cc70f5f694a8d9b` for the glslang 16.6.0 release archive.
[Runtime build](../runtime/CMakeLists.txt) · [Runtime workflow](../.github/workflows/runtime.yml)

## Prepare an offline environment

- Bring an initialized checkout of the pinned submodule for rpf9dump. A source archive of the parent repository
  leaves out that checkout. Populate the local NuGet source or cache with packages from the lockfile beforehand.
- Provision the Python distributions for the target interpreter and platform before going offline if pytest is
  needed. The synthetic CPU example above uses the Python standard library.
- Make `spirv-as` and `spirv-val` available on PATH for the full semantic preflight. Linux CI sets
  `LEONIDA_REQUIRE_SPIRV_TOOLS=1`. Check that your assembler supports the capabilities exercised by the suite,
  since a distribution package can lag the fixtures. Use the AMDGPU-enabled `llvm-mc` described in the testing
  guide for GPU fixture assembly. [CI workflow](../.github/workflows/ci.yml) · [Testing guide](testing.md)
- CI builds `tools/bcpack_calibration/Cargo.toml` with `--locked --offline` and an empty Cargo cache. XMA2's pinned Git dependency
  needs to be available in the local Cargo cache or supplied through a verified offline source.
  [CI workflow](../.github/workflows/ci.yml) · [XMA2 lockfile](../runtime/xma_decoder/Cargo.lock)
- Treat package versions, Git revisions, and digests as provenance evidence. Preserve the existing vendor
  notices and verify the license of the pinned rpf9-explorer submodule separately before redistribution.
  [Redistribution review](redistribution-review.md)

The clean-checkout example covers Linux only. Windows SDK selection, macOS tool discovery, NuGet restore, optional
CMake downloads and Rust dependency provisioning were inventoried from repository sources. Validate those paths
on the relevant host before relying on them for a release or reporting coverage.
