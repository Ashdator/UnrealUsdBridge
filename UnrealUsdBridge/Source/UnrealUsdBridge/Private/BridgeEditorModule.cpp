#include "Modules/ModuleManager.h"
#include "BridgeEditorExport.h"
#include "ToolMenus.h"
#include "Interfaces/IPluginManager.h"
#include "ContentBrowserModule.h"
#include "IContentBrowserSingleton.h"
#include "Engine/StaticMesh.h"
#include "Editor.h"
#include "EngineUtils.h"
#include "Components/SceneComponent.h"
#include "FileHelpers.h"
#include "Misc/PackageName.h"
#include "Interfaces/IMainFrameModule.h"
#include "Windows/WindowsHWrapper.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformProcess.h"
#include "Misc/ScopedSlowTask.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "DesktopPlatformModule.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SComboBox.h"
#include "Widgets/Input/SNumericEntryBox.h"
#include "Widgets/Notifications/SProgressBar.h"
#include "Widgets/Text/STextBlock.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"

static const FName BridgeTab(TEXT("UnrealToIsaacUSD"));

class SBridgeExportPanel : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SBridgeExportPanel) {} SLATE_END_ARGS()
    void Construct(const FArguments&)
    {
        Output=FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir()/TEXT("IsaacUSD"));
        Isaac=TEXT("E:/Omniverse/Isaacsim-6.0.1");
        LoadSettings();
        Scopes={MakeShared<FString>(TEXT("Entire current map")),MakeShared<FString>(TEXT("Selected actors / mesh components")),MakeShared<FString>(TEXT("Selected Content Browser static mesh"))};
        Scope=Scopes[0];
        ChildSlot
        [ SNew(SScrollBox) +SScrollBox::Slot()
          [ SNew(SBox).Padding(12)
            [ SNew(SVerticalBox)
              +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,12)
                [SNew(STextBlock).Text(FText::FromString(TEXT("Unreal to Isaac USD 0.6.6 | Unreal 5.7 / Isaac Sim 6.0.1")))]
              +SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text(FText::FromString(TEXT("Export scope")))]
              +SVerticalBox::Slot().AutoHeight().Padding(0,3,0,10)
                [SNew(SComboBox<TSharedPtr<FString>>).OptionsSource(&Scopes).InitiallySelectedItem(Scope)
                 .OnGenerateWidget_Lambda([](TSharedPtr<FString> Item){return SNew(STextBlock).Text(FText::FromString(*Item));})
                 .OnSelectionChanged_Lambda([this](TSharedPtr<FString> Item,ESelectInfo::Type){Scope=Item;})
                 [SNew(STextBlock).Text_Lambda([this]{return FText::FromString(*Scope);})]]
              +SVerticalBox::Slot().AutoHeight()[PathRow(TEXT("Save folder"),Output)]
              +SVerticalBox::Slot().AutoHeight()[PathRow(TEXT("Isaac Sim installation (Python/USD libraries only)"),Isaac)]
              +SVerticalBox::Slot().AutoHeight().Padding(0,10,0,0)[Check(TEXT("Headless conversion (save, close Unreal, show command window)"),Headless)]
              +SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).AutoWrapText(true).Text(FText::FromString(TEXT("Headless mode exports the saved map or one mesh asset. The command window waits until this editor exits. Selected actors/components use editor mode.")))]
              +SVerticalBox::Slot().AutoHeight().Padding(0,10,0,0)[Check(TEXT("Include decals"),Decals)]
              +SVerticalBox::Slot().AutoHeight()[Check(TEXT("Exclude hidden objects (actors and components)"),ExcludeHidden)]
              +SVerticalBox::Slot().AutoHeight()[Check(TEXT("Export cameras"),Cameras)]
              +SVerticalBox::Slot().AutoHeight()[Check(TEXT("Export lights"),Lights)]
              +SVerticalBox::Slot().AutoHeight()[Check(TEXT("Export skeletal meshes as static reference pose"),Skeletal)]
              +SVerticalBox::Slot().AutoHeight().Padding(0,10,0,0)[Check(TEXT("Optimize heavy static meshes (export copies only)"),Optimize)]
              +SVerticalBox::Slot().AutoHeight()[IntegerRow(TEXT("Optimize above triangle count"),Threshold,100,100000000)]
              +SVerticalBox::Slot().AutoHeight()[IntegerRow(TEXT("Target triangles per unique mesh"),Target,4,100000000)]
              +SVerticalBox::Slot().AutoHeight()[IntegerRow(TEXT("Prefer existing source LOD (0 = simplify original)"),LOD,0,8)]
              +SVerticalBox::Slot().AutoHeight()
                [SNew(SHorizontalBox)+SHorizontalBox::Slot().FillWidth(1)[SNew(STextBlock).Text(FText::FromString(TEXT("Maximum simplification error (cm, before actor scale)")))]
                 +SHorizontalBox::Slot().MaxWidth(180)[SNew(SNumericEntryBox<float>).MinValue(.001f).MaxValue(1000.f)
                  .Value_Lambda([this]{return Error;}).OnValueChanged_Lambda([this](float V){Error=V;SaveSettings();})]]
              +SVerticalBox::Slot().AutoHeight().Padding(0,10)
                [SNew(STextBlock).AutoWrapText(true).Text(FText::FromString(TEXT("Original geometry is the default. Optimization prefers an existing source LOD; otherwise it simplifies a copy. Alpha/two-sided foliage is protected from automatic reduction. Repeated compatible meshes share PointInstancers. Asset builds run serially; source assets are never saved or rebuilt with new settings.")))]
              +SVerticalBox::Slot().AutoHeight()
                [SNew(SHorizontalBox)
                 +SHorizontalBox::Slot().AutoWidth().Padding(0,0,8,0)[SNew(SButton).Text(FText::FromString(TEXT("Convert to USD"))).IsEnabled_Lambda([this]{return !Busy;}).OnClicked(this,&SBridgeExportPanel::Start)]
                 +SHorizontalBox::Slot().AutoWidth().Padding(0,0,8,0)[SNew(SButton).Text(FText::FromString(TEXT("Cancel"))).IsEnabled_Lambda([this]{return Busy;}).OnClicked_Lambda([this]{FFileHelper::SaveStringToFile(TEXT("cancel"),*(Run/TEXT("cancel.request")));return FReply::Handled();})]
                 +SHorizontalBox::Slot().AutoWidth()[SNew(SButton).Text(FText::FromString(TEXT("Open output folder"))).OnClicked_Lambda([this]{FPlatformProcess::ExploreFolder(*(Run.IsEmpty()?Output:Run));return FReply::Handled();})]]
              +SVerticalBox::Slot().AutoHeight().Padding(0,10)[SNew(SProgressBar).Percent_Lambda([this]{return Percent;})]
              +SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).AutoWrapText(true).Text_Lambda([this]{return FText::FromString(Status);})]
            ]
          ]
        ];
    }
    ~SBridgeExportPanel()
    {
        if(Busy && !HandoffApproved && !Run.IsEmpty()) FFileHelper::SaveStringToFile(TEXT("cancel"),*(Run/TEXT("cancel.request")));
        if(Process.IsValid()) FPlatformProcess::CloseProc(Process);
    }
    virtual void Tick(const FGeometry& G,double Time,float Delta) override
    {
        SCompoundWidget::Tick(G,Time,Delta);
        if(!Busy || !Process.IsValid()) return;
        if(HeadlessStarting)
        {
            FString StateText;TSharedPtr<FJsonObject> State;
            if(FFileHelper::LoadFileToString(StateText,*(Run/TEXT("headless-status.json"))) &&
               FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(StateText),State) && State)
            {
                FString Phase;State->TryGetStringField(TEXT("state"),Phase);
                if(Phase==TEXT("failed") || Phase==TEXT("cancelled"))
                {
                    State->TryGetStringField(TEXT("message"),Status);Busy=false;HeadlessStarting=false;HandoffApproved=false;
                    FPlatformProcess::CloseProc(Process);Process.Reset();return;
                }
            }
            FString ReadyText;TSharedPtr<FJsonObject> Ready;
            if(!HandoffApproved && !FPaths::FileExists(Run/TEXT("cancel.request")) && FFileHelper::LoadFileToString(ReadyText,*(Run/TEXT("headless-ready.json"))) &&
                FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ReadyText),Ready) && Ready &&
                Ready->GetStringField(TEXT("job_id"))==JobId && Ready->GetStringField(TEXT("state"))==TEXT("ready") && FPlatformProcess::IsProcRunning(Process))
            {
                if(!FFileHelper::SaveStringToFile(JobId,*(Run/TEXT("headless-close-approved"))))
                {Status=TEXT("Could not approve headless handoff. Editor remains open.");return;}
                HandoffApproved=true;
                Status=TEXT("Headless worker is ready. Closing saved editor; progress continues in its command window.");
                IMainFrameModule::Get().RequestCloseEditor();
                return;
            }
            if(!FPlatformProcess::IsProcRunning(Process))
            {
                Busy=false;HeadlessStarting=false;HandoffApproved=false;
                FPlatformProcess::CloseProc(Process);Process.Reset();
                Status=TEXT("Headless startup stopped. Editor remains open; see ")+Run/TEXT("headless-console.log");
            }
            return;
        }
        FString Text; TSharedPtr<FJsonObject> J;
        if(FFileHelper::LoadFileToString(Text,*(Run/TEXT("editor-status.json"))) && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),J) && J)
        { Percent=J->GetNumberField(TEXT("fraction")); Status=J->GetStringField(TEXT("message")); }
        if(!FPlatformProcess::IsProcRunning(Process))
        {
            int32 Code=-1; FPlatformProcess::GetProcReturnCode(Process,&Code);
            Busy=false; FPlatformProcess::CloseProc(Process); Process.Reset();
            if(Code==0) { Percent=1; Status=TEXT("Complete: ")+Run/TEXT("Scene.usdc"); }
            else Status=TEXT("Conversion stopped: ")+Status+TEXT(" | Logs: ")+Run;
        }
    }
private:
    FString Output,Isaac,Run,Status=TEXT("Ready. Headless mode saves and closes Unreal before extraction; editor mode keeps the current scene open.");
    bool Decals=true,Cameras=true,Lights=true,Skeletal=false,Optimize=false,Busy=false,ExcludeHidden=false,Headless=false;
    bool HeadlessStarting=false,HandoffApproved=false;
    FString JobId;
    int32 Threshold=500000,Target=250000,LOD=1;
    float Error=1,Percent=0;
    FProcHandle Process;
    TArray<TSharedPtr<FString>> Scopes;
    TSharedPtr<FString> Scope;
    FString SettingsPath() const { return FPaths::ProjectSavedDir()/TEXT("UnrealUsdBridge/settings.json"); }
    void LoadSettings()
    {
        FString S; TSharedPtr<FJsonObject> J;
        if(FFileHelper::LoadFileToString(S,*SettingsPath()) && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(S),J) && J)
        {
            J->TryGetStringField(TEXT("output"),Output); J->TryGetStringField(TEXT("isaac"),Isaac);
            J->TryGetBoolField(TEXT("exclude_hidden"),ExcludeHidden); J->TryGetBoolField(TEXT("headless"),Headless);
            J->TryGetBoolField(TEXT("include_decals"),Decals); J->TryGetBoolField(TEXT("export_cameras"),Cameras);
            J->TryGetBoolField(TEXT("export_lights"),Lights); J->TryGetBoolField(TEXT("export_skeletal_meshes"),Skeletal);
            J->TryGetBoolField(TEXT("optimize"),Optimize); J->TryGetNumberField(TEXT("threshold"),Threshold);
            J->TryGetNumberField(TEXT("target"),Target); J->TryGetNumberField(TEXT("lod"),LOD);
            double SavedError=Error;if(J->TryGetNumberField(TEXT("max_error_cm"),SavedError) && FMath::IsFinite(SavedError)) Error=FMath::Clamp((float)SavedError,.001f,1000.f);
            Threshold=FMath::Clamp(Threshold,100,100000000);Target=FMath::Clamp(Target,4,100000000);LOD=FMath::Clamp(LOD,0,8);
        }
    }
    void SaveSettings()
    {
        auto J=MakeShared<FJsonObject>(); J->SetStringField(TEXT("output"),Output);J->SetStringField(TEXT("isaac"),Isaac);
        J->SetBoolField(TEXT("exclude_hidden"),ExcludeHidden);
        J->SetBoolField(TEXT("headless"),Headless);
        J->SetBoolField(TEXT("include_decals"),Decals);J->SetBoolField(TEXT("export_cameras"),Cameras);
        J->SetBoolField(TEXT("export_lights"),Lights);J->SetBoolField(TEXT("export_skeletal_meshes"),Skeletal);
        J->SetBoolField(TEXT("optimize"),Optimize);J->SetNumberField(TEXT("threshold"),Threshold);
        J->SetNumberField(TEXT("target"),Target);J->SetNumberField(TEXT("lod"),LOD);J->SetNumberField(TEXT("max_error_cm"),Error);
        FString S;FJsonSerializer::Serialize(J,TJsonWriterFactory<>::Create(&S));
        IFileManager::Get().MakeDirectory(*FPaths::GetPath(SettingsPath()),true);FFileHelper::SaveStringToFile(S,*SettingsPath());
    }
    TSharedRef<SWidget> PathRow(const TCHAR* Label,FString& Value)
    {
        return SNew(SVerticalBox)+SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text(FText::FromString(Label))]
        +SVerticalBox::Slot().AutoHeight().Padding(0,3,0,8)
        [SNew(SHorizontalBox)+SHorizontalBox::Slot().FillWidth(1)
         [SNew(SEditableTextBox).Text_Lambda([&Value]{return FText::FromString(Value);}).OnTextCommitted_Lambda([&Value](const FText& V,ETextCommit::Type){Value=V.ToString();})]
         +SHorizontalBox::Slot().AutoWidth()[SNew(SButton).Text(FText::FromString(TEXT("Browse"))).OnClicked_Lambda([&Value]
         { if(auto* D=FDesktopPlatformModule::Get()) {FString Chosen;if(D->OpenDirectoryDialog(FSlateApplication::Get().FindBestParentWindowHandleForDialogs(nullptr),TEXT("Choose folder"),Value,Chosen))Value=Chosen;} return FReply::Handled(); })]];
    }
    TSharedRef<SWidget> Check(const TCHAR* Label,bool& Value)
    {
        return SNew(SCheckBox).IsChecked_Lambda([&Value]{return Value?ECheckBoxState::Checked:ECheckBoxState::Unchecked;})
        .OnCheckStateChanged_Lambda([this,&Value](ECheckBoxState V){Value=V==ECheckBoxState::Checked;SaveSettings();})[SNew(STextBlock).Text(FText::FromString(Label))];
    }
    TSharedRef<SWidget> IntegerRow(const TCHAR* Label,int32& Value,int32 Min,int32 Max)
    {
        return SNew(SHorizontalBox)+SHorizontalBox::Slot().FillWidth(1)[SNew(STextBlock).Text(FText::FromString(Label))]
        +SHorizontalBox::Slot().MaxWidth(180)[SNew(SNumericEntryBox<int32>).MinValue(Min).MaxValue(Max)
        .Value_Lambda([&Value]{return Value;}).OnValueChanged_Lambda([this,&Value](int32 V){Value=V;SaveSettings();})];
    }
    static FString Quote(const FString& V) { return TEXT("\"")+V+TEXT("\""); }
    static FString Absolute(const FString& V)
    {FString P=FPaths::ConvertRelativePathToFull(V);FPaths::NormalizeFilename(P);return P;}
    FReply StartHeadless(const FString& Source)
    {
        if(Scope==Scopes[1]) {Status=TEXT("Headless mode reads the saved map. Choose Entire current map, or turn off Headless for selected actors/components.");return FReply::Handled();}
        const FString Project=Absolute(FPaths::GetProjectFilePath());
        const FString Engine=Absolute(FPaths::EngineDir()/TEXT("Binaries/Win64/UnrealEditor-Cmd.exe"));
        const FString Plugin=Absolute(IPluginManager::Get().FindPlugin(TEXT("UnrealUsdBridge"))->GetBaseDir());
        if(!FPaths::FileExists(Project) || !FPaths::FileExists(Engine) || !FPaths::FileExists(Plugin/TEXT("Resources/Python/run_headless.py")))
        {Status=TEXT("Headless project, Unreal executable or runner is missing. Editor remains open.");return FReply::Handled();}
        UWorld* World=GEditor->GetEditorWorldContext().World();
        if(Scope==Scopes[0] && (!World || !FPackageName::DoesPackageExist(World->GetOutermost()->GetName())))
            if(!World || !FEditorFileUtils::SaveCurrentLevel()) {Status=TEXT("Save the map before headless conversion. Editor remains open.");return FReply::Handled();}
        // Unreal's native dialog protects pending edits. A cancelled or partial
        // save never authorizes closing the editor or starting extraction.
        if(!FEditorFileUtils::SaveDirtyPackages(true,true,true,false,false,false))
        {Status=TEXT("Save cancelled or failed. Headless conversion was not started.");return FReply::Handled();}
        TArray<UPackage*> Dirty;FEditorFileUtils::GetDirtyWorldPackages(Dirty);FEditorFileUtils::GetDirtyContentPackages(Dirty);
        if(!Dirty.IsEmpty()) {Status=TEXT("Unsaved map/content packages remain. Save them before headless conversion; editor remains open.");return FReply::Handled();}
        World=GEditor->GetEditorWorldContext().World();
        if(!World && Scope==Scopes[0]) {Status=TEXT("No current saved world after saving. Editor remains open.");return FReply::Handled();}
        FString Package,SourceFile;const bool Asset=Scope==Scopes[2];
        if(Asset) FParse::Value(*Source,TEXT("BridgeAsset="),Package);
        else Package=World->GetOutermost()->GetName();
        if(!FPackageName::DoesPackageExist(Package,&SourceFile)) {Status=TEXT("The saved export package could not be found.");return FReply::Handled();}
        Run=Absolute(Output)/(FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"))+TEXT("_")+FGuid::NewGuid().ToString(EGuidFormats::Digits).Left(8));
        if(!IFileManager::Get().MakeDirectory(*Run,true)) {Status=TEXT("Cannot create headless output folder.");return FReply::Handled();}
        auto Job=MakeShared<FJsonObject>();JobId=FGuid::NewGuid().ToString(EGuidFormats::Digits);
        Job->SetNumberField(TEXT("schema_version"),1);Job->SetStringField(TEXT("job_id"),JobId);
        Job->SetStringField(TEXT("project"),Project);Job->SetStringField(TEXT("engine"),Engine);
        Job->SetStringField(TEXT("plugin"),Plugin/TEXT("UnrealUsdBridge.uplugin"));Job->SetStringField(TEXT("isaac"),Absolute(Isaac));
        Job->SetStringField(TEXT("run"),Run);Job->SetStringField(TEXT("package"),Package);
        Job->SetStringField(TEXT("source_file"),Absolute(SourceFile));Job->SetStringField(TEXT("kind"),Asset?TEXT("asset"):TEXT("map"));
        Job->SetNumberField(TEXT("editor_pid"),FPlatformProcess::GetCurrentProcessId());
        auto Options=MakeShared<FJsonObject>();Options->SetBoolField(TEXT("include_decals"),Decals);Options->SetBoolField(TEXT("export_cameras"),Cameras);
        Options->SetBoolField(TEXT("export_lights"),Lights);Options->SetBoolField(TEXT("export_skeletal_meshes"),Skeletal);
        Options->SetBoolField(TEXT("exclude_hidden"),ExcludeHidden);Options->SetBoolField(TEXT("optimize"),Optimize);
        Options->SetNumberField(TEXT("threshold"),Threshold);Options->SetNumberField(TEXT("target"),Target);
        Options->SetNumberField(TEXT("lod"),LOD);Options->SetNumberField(TEXT("max_error_cm"),Error);Job->SetObjectField(TEXT("options"),Options);
        // Session-only editor hiding is not necessarily saved in the map.
        // Preserve identities for loaded hidden actors/components in the job.
        auto Visibility=MakeShared<FJsonObject>();TArray<TSharedPtr<FJsonValue>> Actors,Components;
        if(ExcludeHidden && World)
            for(TActorIterator<AActor> It(World);It;++It)
            {
                const FString Guid=It->GetActorGuid().ToString(EGuidFormats::Digits);
                if(It->IsHidden() || It->IsHiddenEd())
                {auto A=MakeShared<FJsonObject>();A->SetStringField(TEXT("guid"),Guid);A->SetStringField(TEXT("path"),It->GetPathName());Actors.Add(MakeShared<FJsonValueObject>(A));}
                TInlineComponentArray<USceneComponent*> SceneComponents(*It);
                for(USceneComponent* C:SceneComponents) if(!C->IsVisible() || C->bHiddenInGame)
                {auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("actor_guid"),Guid);O->SetStringField(TEXT("name"),C->GetName());O->SetStringField(TEXT("path"),C->GetPathName());Components.Add(MakeShared<FJsonValueObject>(O));}
            }
        Visibility->SetArrayField(TEXT("actors"),Actors);Visibility->SetArrayField(TEXT("components"),Components);Job->SetObjectField(TEXT("visibility_snapshot"),Visibility);
        FString Text;FJsonSerializer::Serialize(Job,TJsonWriterFactory<>::Create(&Text));const FString JobPath=Run/TEXT("headless-job.json");
        if(!FFileHelper::SaveStringToFile(Text,*JobPath,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM)) {Status=TEXT("Could not save headless job. Editor remains open.");return FReply::Handled();}
        SaveSettings();
        const FString Python=Absolute(Isaac/TEXT("kit/python/python.exe"));
        FString Command=Quote(Python)+TEXT(" -B -u ")+Quote(Plugin/TEXT("Resources/Python/run_headless.py"))+TEXT(" --job ")+Quote(JobPath)+TEXT(" --keep-open");
        STARTUPINFOW Startup={};Startup.cb=sizeof(Startup);PROCESS_INFORMATION Info={};
        // Explicitly requested visible command window; no cmd.exe shell parses
        // project paths, so spaces, Unicode and shell metacharacters stay data.
        if(!::CreateProcessW(*Python,Command.GetCharArray().GetData(),nullptr,nullptr,false,CREATE_NEW_CONSOLE,nullptr,*FPaths::GetPath(Python),&Startup,&Info))
        {Status=FString::Printf(TEXT("Could not launch headless command window (Windows error %u). Editor remains open."),::GetLastError());return FReply::Handled();}
        Process=FPlatformProcess::OpenProcess(Info.dwProcessId);::CloseHandle(Info.hThread);::CloseHandle(Info.hProcess);
        if(!Process.IsValid()) {FFileHelper::SaveStringToFile(TEXT("cancel"),*(Run/TEXT("cancel.request")));Status=TEXT("Could not monitor headless startup. Editor remains open.");return FReply::Handled();}
        Busy=true;HeadlessStarting=true;HandoffApproved=false;Percent=.02f;
        Status=TEXT("Validating headless job in the command window. Unreal closes only after the runner reports ready.");
        return FReply::Handled();
    }
    FReply Start()
    {
        if(GEditor->PlayWorld) {Status=TEXT("Stop Play in Editor before exporting.");return FReply::Handled();}
        if(Output.Contains(TEXT("\"")) || Isaac.Contains(TEXT("\"")) || Output.Contains(TEXT("\n")) || Isaac.Contains(TEXT("\n")))
        {Status=TEXT("Folder paths cannot contain quotes or line breaks.");return FReply::Handled();}
        const FString Python=Isaac/TEXT("kit/python/python.exe");
        if(!FPaths::FileExists(Python)) {Status=TEXT("Choose a valid Isaac Sim installation folder.");return FReply::Handled();}
        if(Target>Threshold) {Status=TEXT("Target triangles must not exceed the optimization threshold.");return FReply::Handled();}
        FString Source=TEXT("-BridgeCurrentWorld");
        if(Scope==Scopes[1]) Source+=TEXT(" -BridgeSelected");
        if(Scope==Scopes[2])
        {
            TArray<FAssetData> Assets;
            FModuleManager::LoadModuleChecked<FContentBrowserModule>(TEXT("ContentBrowser")).Get().GetSelectedAssets(Assets);
            if(Assets.Num()!=1 || !Assets[0].IsInstanceOf(UStaticMesh::StaticClass()))
            {Status=TEXT("Select one Static Mesh asset in the Content Browser, or use selected actors for multiple meshes.");return FReply::Handled();}
            Source=TEXT("-BridgeAsset=")+Quote(Assets[0].PackageName.ToString());
        }
        if(Headless) return StartHeadless(Source);
        Run=FPaths::ConvertRelativePathToFull(Output)/(FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"))+TEXT("_")+FGuid::NewGuid().ToString(EGuidFormats::Digits).Left(8));
        if(!IFileManager::Get().MakeDirectory(*Run,true)) {Status=TEXT("Cannot create output folder: ")+Run;return FReply::Handled();}
        SaveSettings(); Busy=true; Percent=.02f; Status=TEXT("Reading current Unreal scene");
        FString Params=Source+TEXT(" -BridgeOut=")+Quote(Run);
        if(ExcludeHidden) Params+=TEXT(" -BridgeExcludeHidden");
        if(Decals==false) Params+=TEXT(" -BridgeNoDecals");
        if(!Cameras) Params+=TEXT(" -BridgeNoCameras");if(!Lights) Params+=TEXT(" -BridgeNoLights");
        if(Skeletal) Params+=TEXT(" -BridgeExportSkeletalMeshes");
        if(Optimize) Params+=TEXT(" -BridgeOptimize");
        Params+=FString::Printf(TEXT(" -BridgeThreshold=%d -BridgeTarget=%d -BridgeLOD=%d -BridgeMaxError=%f"),Threshold,Target,LOD,Error);
        FScopedSlowTask Task(100,FText::FromString(Status)); Task.MakeDialog(true);
        float Last=0;
        const int32 Code=BridgeEditor::Extract(Params,[&](float V,const FString& Actor)
        {Task.EnterProgressFrame(FMath::Max(0.f,V*100-Last),FText::FromString(TEXT("Extracting: ")+Actor));Last=V*100;Percent=V;return !Task.ShouldCancel();});
        if(Code) {Busy=false;Status=FString::Printf(TEXT("Extraction stopped (code %d). See Unreal Output Log. Folder: %s"),Code,*Run);return FReply::Handled();}
        const FString Plugin=IPluginManager::Get().FindPlugin(TEXT("UnrealUsdBridge"))->GetBaseDir();
        const FString Args=TEXT("-B -u ")+Quote(Plugin/TEXT("Resources/Python/run_conversion.py"))+TEXT(" --manifest ")+Quote(Run/TEXT("manifest.json"))+TEXT(" --isaac ")+Quote(Isaac)+
            FString::Printf(TEXT(" --decals %d --cameras %d --lights %d"),Decals,Cameras,Lights);
        Process=FPlatformProcess::CreateProc(*Python,*Args,false,true,true,nullptr,0,nullptr,nullptr);
        if(!Process.IsValid()) {Busy=false;Status=TEXT("Failed to launch standalone USD conversion worker.");}
        else {Percent=.35;Status=TEXT("Building USD; you can follow progress here. Scene opening is manual.");}
        return FReply::Handled();
    }
};

class FUnrealUsdBridgeModule : public IModuleInterface
{
    int32 PreviousConcurrency=-1;
public:
    virtual void StartupModule() override
    {
        // Apply before the editor's startup map is loaded. Commandlets also
        // accept -AsyncStaticMeshCompilationMaxConcurrency=1 at launch.
        if(auto* C=IConsoleManager::Get().FindConsoleVariable(TEXT("Editor.AsyncStaticMeshCompilationMaxConcurrency")))
        { PreviousConcurrency=C->GetInt();C->Set(1,ECVF_SetByCode); }
        if(IsRunningCommandlet()) return;
        FGlobalTabmanager::Get()->RegisterNomadTabSpawner(BridgeTab,FOnSpawnTab::CreateLambda([](const FSpawnTabArgs&)
        {return SNew(SDockTab).TabRole(ETabRole::NomadTab)[SNew(SBridgeExportPanel)];})).SetDisplayName(FText::FromString(TEXT("Unreal to Isaac USD")));
        UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateRaw(this,&FUnrealUsdBridgeModule::Menus));
    }
    void Menus()
    {
        FToolMenuOwnerScoped Owner(this);
        UToolMenu* Menu=UToolMenus::Get()->ExtendMenu(TEXT("LevelEditor.MainMenu.Tools"));
        Menu->AddSection(TEXT("IsaacUSD"),FText::FromString(TEXT("Isaac Sim"))).AddMenuEntry(TEXT("ExportIsaacUSD"),FText::FromString(TEXT("Unreal to Isaac USD")),
            FText::FromString(TEXT("Export a map or selected meshes")),FSlateIcon(),FUIAction(FExecuteAction::CreateLambda([]{FGlobalTabmanager::Get()->TryInvokeTab(BridgeTab);}))); 
    }
    virtual void ShutdownModule() override
    {
        if(auto* C=IConsoleManager::Get().FindConsoleVariable(TEXT("Editor.AsyncStaticMeshCompilationMaxConcurrency")))
            if(C->GetInt()==1) C->Set(PreviousConcurrency,ECVF_SetByCode);
        if(IsRunningCommandlet()) return;
        if(UToolMenus::IsToolMenuUIEnabled()) { UToolMenus::UnRegisterStartupCallback(this);UToolMenus::UnregisterOwner(this); }
        FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(BridgeTab);
    }
};
IMPLEMENT_MODULE(FUnrealUsdBridgeModule,UnrealUsdBridge)
