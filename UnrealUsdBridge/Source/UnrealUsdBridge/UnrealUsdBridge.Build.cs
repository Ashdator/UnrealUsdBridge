using UnrealBuildTool;
public class UnrealUsdBridge : ModuleRules
{
    public UnrealUsdBridge(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.AddRange(new[] {
            "UnrealEd", "Json", "ImageCore", "Landscape", "Foliage", "MeshDescription",
            "StaticMeshDescription", "MeshUtilitiesCommon", "RenderCore", "RHI", "AssetRegistry", "Slate", "SlateCore", "InputCore", "ToolMenus", "LevelEditor", "MainFrame", "DesktopPlatform", "Projects", "ContentBrowser", "MeshReductionInterface"
        });
    }
}
