# Build and package the plugin

## Prerequisites

Use Windows x64, Unreal Engine 5.7.4 and Visual Studio 2022 with the C++ compiler and Windows SDK required by your Unreal installation. Install Isaac Sim 6.0.1 for conversion and Python/USD testing. Engine and Isaac runtime binaries are not vendored in this repository.

## Standalone package

From the repository root in PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "./scripts/build-plugin.ps1" -EngineRoot "C:/Program Files/Epic Games/UE_5.7"
```

`EngineRoot` is the folder **containing Engine**, not the Engine folder itself. Adjust the example to your installation. The execution-policy option applies to that PowerShell process only.

The helper calls Unreal's `RunUAT.bat BuildPlugin` with the source descriptor and Win64 target. The default destination is a new timestamped folder under ignored `build/`. You may pass `-PackageDirectory "D:/Builds/UnrealUsdBridge-0.6.6"`; it must not exist. The helper refuses existing destinations because Unreal's packaging command clears its output directory.

This wrapper is provided for repository portability. It has been syntax/path checked; the original 0.6.6 DLL was built using the workstation's UnrealBuildTool host-project workflow, not this new UAT wrapper. A new machine must perform its own successful build.

Copy the packaged plugin contents into `YourProject/Plugins/UnrealUsdBridge/`, preserving `Source`, `Resources`, `Binaries` and the descriptor. Do not omit `Resources/Python`: the Unreal panel launches these files for conversion.

## Build inside a project

Alternatively, copy the repository's `UnrealUsdBridge` folder into your project's `Plugins` folder, enable the plugin and build the project's Editor target using your Unreal/Visual Studio toolchain. A source build may require generating project files. A matching compiled Editor DLL must exist before a headless conversion can run.

## Checks

Syntax/descriptor check (no USD imports):

```powershell
python -B scripts/check-source.py
```

Runtime regression tests and native material fixtures are documented in [VALIDATION.md](VALIDATION.md). The Python suite uses Isaac's bundled Python and USD libraries. No pip dependency installation is required for the supplied suite.

Build output, engine caches, virtual environments and converted scenes are ignored by Git. Precompiled packages should be published as versioned release assets rather than mixed into source commits.
