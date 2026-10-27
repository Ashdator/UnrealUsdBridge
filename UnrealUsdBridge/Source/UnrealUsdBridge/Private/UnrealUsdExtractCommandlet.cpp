#include "UnrealUsdExtractCommandlet.h"
#include "Editor.h"
#include "BridgeEditorExport.h"
#include "Engine/Selection.h"
#include "StaticMeshCompiler.h"
#include "IMeshReductionManagerModule.h"
#include "IMeshReductionInterfaces.h"
#include "MeshReductionSettings.h"
#include "WorldPartition/WorldPartitionHelpers.h"
#include "WorldPartition/WorldPartitionActorDescInstance.h"
#include "HAL/PlatformMemory.h"
#include "Misc/OutputDeviceFile.h"
#include "Misc/ScopeExit.h"
#include "FileHelpers.h"
#include "EngineUtils.h"
#include "AssetCompilingManager.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/BlockingVolume.h"
#include "GameFramework/CameraBlockingVolume.h"
#include "Engine/DecalActor.h"
#include "Engine/Texture2D.h"
#include "Engine/TextureCube.h"
#include "Engine/LevelStreaming.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "InstancedFoliageActor.h"
#include "InstancedFoliage.h"
#include "FoliageType_InstancedStaticMesh.h"
#include "FoliageInstancedStaticMeshComponent.h"
#include "Components/SplineMeshComponent.h"
#include "BridgeSplineMesh.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/DecalComponent.h"
#include "Materials/MaterialExpressionDecalColor.h"
#include "Materials/MaterialExpressionDecalLifetimeOpacity.h"
#include "Components/LightComponent.h"
#include "Camera/CameraComponent.h"
#include "StaticMeshResources.h"
#include "LandscapeProxy.h"
#include "Landscape.h"
#include "LandscapeComponent.h"
#include "LandscapeInfo.h"
#include "StaticMeshAttributes.h"
#include "StaticMeshOperations.h"
#include "OverlappingCorners.h"
#include "WorldPartition/WorldPartition.h"
#include "WorldPartition/WorldPartitionHandle.h"
#include "ImageUtils.h"
#include "ImageCore.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "Modules/ModuleManager.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstance.h"
#include "Materials/MaterialInstanceConstant.h"
#include "Materials/MaterialExpressionConstant.h"
#include "Materials/MaterialExpressionConstant2Vector.h"
#include "Materials/MaterialExpressionConstant3Vector.h"
#include "Materials/MaterialExpressionConstant4Vector.h"
#include "Materials/MaterialExpressionScalarParameter.h"
#include "Materials/MaterialExpressionVectorParameter.h"
#include "Materials/MaterialExpressionTextureSample.h"
#include "Materials/MaterialExpressionTextureSampleParameter.h"
#include "Materials/MaterialExpressionTextureCoordinate.h"
#include "Materials/MaterialExpressionAdd.h"
#include "Materials/MaterialExpressionMultiply.h"
#include "Materials/MaterialExpressionSubtract.h"
#include "Materials/MaterialExpressionDivide.h"
#include "Materials/MaterialExpressionOneMinus.h"
#include "Materials/MaterialExpressionComponentMask.h"
#include "Materials/MaterialExpressionStaticSwitchParameter.h"
#include "Materials/MaterialExpressionStaticSwitch.h"
#include "Materials/MaterialExpressionStaticBool.h"
#include "Materials/MaterialExpressionStaticBoolParameter.h"
#include "Materials/MaterialExpressionRayTracingQualitySwitch.h"
#include "Materials/MaterialExpressionCollectionParameter.h"
#include "Materials/MaterialParameterCollection.h"
#include "Materials/MaterialParameterCollectionInstance.h"
#include "Materials/MaterialExpressionFmod.h"
#include "Materials/MaterialExpressionReflectionVectorWS.h"
#include "Materials/MaterialExpressionCameraVectorWS.h"
#include "Materials/MaterialExpressionPixelNormalWS.h"
#include "Materials/MaterialExpressionVertexNormalWS.h"
#include "Materials/MaterialExpressionTwoSidedSign.h"
#include "Materials/MaterialExpressionLocalPosition.h"
#include "Materials/MaterialExpressionVertexInterpolator.h"
#include "Materials/MaterialExpressionCeil.h"
#include "Materials/MaterialExpressionFloor.h"
#include "Materials/MaterialExpressionNoise.h"
#include "Materials/MaterialExpressionCustom.h"
#include "Materials/MaterialExpressionTransform.h"
#include "UObject/UnrealType.h"
#include "Materials/MaterialExpressionReroute.h"
#include "Materials/MaterialExpressionMaterialFunctionCall.h"
#include "Materials/MaterialExpressionFunctionInput.h"
#include "Materials/MaterialExpressionFunctionOutput.h"
#include "Materials/MaterialExpressionLinearInterpolate.h"
#include "Materials/MaterialExpressionClamp.h"
#include "Materials/MaterialExpressionPower.h"
#include "Materials/MaterialExpressionSine.h"
#include "Materials/MaterialExpressionCosine.h"
#include "Materials/MaterialExpressionFresnel.h"
#include "Materials/MaterialExpressionLandscapeLayerCoords.h"
#include "Materials/MaterialExpressionNormalize.h"
#include "Materials/MaterialExpressionDesaturation.h"
#include "Materials/MaterialExpressionAppendVector.h"
#include "Materials/MaterialExpressionVertexColor.h"
#include "Materials/MaterialExpressionWorldPosition.h"
#include "Materials/MaterialExpressionConstantBiasScale.h"
#include "Materials/MaterialExpressionRotateAboutAxis.h"
#include "Materials/MaterialExpressionDotProduct.h"
#include "Materials/MaterialExpressionDistance.h"
#include "Materials/MaterialExpressionCrossProduct.h"
#include "Materials/MaterialExpressionAbs.h"
#include "Materials/MaterialExpressionSaturate.h"
#include "Materials/MaterialExpressionMakeMaterialAttributes.h"
#include "Materials/MaterialExpressionBlendMaterialAttributes.h"
#include "Materials/MaterialExpressionQualitySwitch.h"
#include "Materials/MaterialExpressionRuntimeVirtualTextureReplace.h"
#include "Materials/MaterialExpressionVirtualTextureFeatureSwitch.h"
#include "Materials/MaterialExpressionPerInstanceFadeAmount.h"
#include "Materials/MaterialExpressionGetMaterialAttributes.h"
#include "Materials/MaterialExpressionSetMaterialAttributes.h"
#include "Materials/MaterialExpressionBreakMaterialAttributes.h"
#include "Materials/MaterialAttributeDefinitionMap.h"
#include "Materials/MaterialExpressionTextureObject.h"
#include "Materials/MaterialExpressionTextureObjectParameter.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialExpressionLandscapeLayerBlend.h"
#include "Materials/MaterialExpressionLandscapeLayerSample.h"
#include "LandscapeLayerInfoObject.h"
#include "Materials/MaterialExpressionObjectPositionWS.h"
#include "Materials/MaterialExpressionFrac.h"
#include "StaticMeshComponentLODInfo.h"
#include "Materials/MaterialExpressionIf.h"
#include "Materials/MaterialExpressionPanner.h"
#include "Materials/MaterialExpressionTime.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/RectLightComponent.h"
#include "Materials/MaterialExpressionPerInstanceRandom.h"

namespace Bridge
{
bool IsBlockingVolumeClass(const UClass* Class)
{
    return Class && (Class->IsChildOf(ABlockingVolume::StaticClass()) || Class->IsChildOf(ACameraBlockingVolume::StaticClass()));
}
bool IsExportHiddenActor(const AActor* Actor)
{
    return Actor && (Actor->IsHidden() || Actor->IsHiddenEd());
}
bool IsExportHiddenComponent(const USceneComponent* Component)
{
    return Component && (!Component->IsVisible() || Component->bHiddenInGame || IsExportHiddenActor(Component->GetOwner()));
}
using Obj = TSharedPtr<FJsonObject>;
using Val = TSharedPtr<FJsonValue>;
using Arr = TArray<Val>;
Obj Object() { return MakeShared<FJsonObject>(); }
Val V(Obj O) { return MakeShared<FJsonValueObject>(O); }
Val N(double X) { return MakeShared<FJsonValueNumber>(X); }
Val S(const FString& X) { return MakeShared<FJsonValueString>(X); }
Val A(const Arr& X) { return MakeShared<FJsonValueArray>(X); }
Arr Vec(std::initializer_list<double> Values) { Arr R; for (double X : Values) R.Add(N(X)); return R; }
Obj Node(const FString& Op) { Obj R=Object(); R->SetStringField(TEXT("op"),Op); return R; }
Obj Constant(std::initializer_list<double> Values) { Obj R=Node(TEXT("constant")); R->SetArrayField(TEXT("value"),Vec(Values)); return R; }
Obj Bad(const FString& Why) { Obj R=Node(TEXT("unsupported")); R->SetStringField(TEXT("reason"),Why); return R; }
FString Id(const FString& Path) { return TEXT("a_")+FMD5::HashAnsiString(*Path); }
bool Save(Obj O, const FString& Path)
{
    if(O->HasField(TEXT("schema_version")) && O->HasField(TEXT("map")))
    {
        O->SetStringField(TEXT("extractor_version"),TEXT("0.6.6"));
        O->SetStringField(TEXT("extractor_patch"),TEXT("bounded-diagnostics-streamed-utf8-nonvirtual-static-fade"));
    }
    // Stream UTF-8 through Unreal's buffered file archive. FString-backed
    // JSON writers allocate a 32-bit memory archive and duplicate the complete
    // output in RAM before writing it. Do not increase that buffer's limit.
    const FString Temporary=Path+TEXT(".writing");
    TUniquePtr<FArchive> File(IFileManager::Get().CreateFileWriter(*Temporary));
    if(!File) return false;
    auto Writer=TJsonWriterFactory<UTF8CHAR,TCondensedJsonPrintPolicy<UTF8CHAR>>::Create(File.Get());
    const bool Serialized=FJsonSerializer::Serialize(O.ToSharedRef(),Writer);
    const bool Closed=File->Close();
    const bool Success=Serialized && Closed && !File->IsError();
    File.Reset();
    if(!Success) return false;
    return IFileManager::Get().Move(*Path,*Temporary,true,false,false,true);
}
Arr Matrix(const FTransform& T)
{
    Arr R; const FMatrix M=T.ToMatrixWithScale();
    // Coordinate reflection is applied in the USD writer, once, to meshes and transforms.
    for(int I=0;I<4;++I) for(int J=0;J<4;++J) R.Add(N(M.M[I][J]));
    return R;
}

struct FLandscapeVertex
{
    FVector3f Position,Normal;
    FVector2f UV;
    bool operator==(const FLandscapeVertex& Other) const { return Position==Other.Position && Normal==Other.Normal && UV==Other.UV; }
    friend uint32 GetTypeHash(const FLandscapeVertex& V) { return HashCombine(HashCombine(GetTypeHash(V.Position),GetTypeHash(V.Normal)),GetTypeHash(V.UV)); }
};

// Merge only exactly identical exported corners; retain UV and normal seams.
struct FSourceVertex
{
    FVector3f Position,Normal;
    FColor Color;
    TArray<FVector2f> UVs;
    bool operator==(const FSourceVertex& B) const { return Position==B.Position && Normal==B.Normal && Color==B.Color && UVs==B.UVs; }
    friend uint32 GetTypeHash(const FSourceVertex& V)
    {
        uint32 H=HashCombine(HashCombine(GetTypeHash(V.Position),GetTypeHash(V.Normal)),GetTypeHash(V.Color));
        for(const auto& UV:V.UVs) H=HashCombine(H,GetTypeHash(UV));
        return H;
    }
};

struct FExport
{
    FString Out;
    bool Optimize=false,ExcludeHidden=false;
    int32 HiddenActors=0,HiddenComponents=0;
    TSet<FString> SnapshotActorGuids,SnapshotActorPaths,SnapshotComponentKeys,SnapshotComponentPaths;
    int32 Threshold=500000, Target=250000, PreferredLOD=1;
    float MaxError=1.0f;
    Obj Materials=Object(), Textures=Object(), Meshes=Object();
    Arr Instances, Instancers, Issues, Notes, Lights, Cameras, Decals;
    TMap<FString,Obj> LandscapeWeights;
    TMap<FString,TArray<FVector3f>> SourcePositions,SourceNormals;
    TSet<ULandscapeInfo*> ExportedLandscapes;
    void Issue(const FString& Message) { Issues.Add(S(Message)); UE_LOG(LogTemp,Warning,TEXT("BRIDGE: %s"),*Message); }
    void Note(const FString& Message) { Notes.Add(S(Message)); }
    void LoadHiddenSnapshot(Obj Snapshot)
    {
        if(!Snapshot) return;
        const Arr* Actors=nullptr;
        if(Snapshot->TryGetArrayField(TEXT("actors"),Actors)) for(const Val& Value:*Actors)
        {
            const Obj A=Value->AsObject();if(!A) continue;
            FString Guid,Path;FGuid Id;
            A->TryGetStringField(TEXT("guid"),Guid);A->TryGetStringField(TEXT("path"),Path);
            if(FGuid::ParseExact(Guid,EGuidFormats::Digits,Id) && Id.IsValid()) SnapshotActorGuids.Add(Id.ToString(EGuidFormats::Digits));
            if(!Path.IsEmpty()) SnapshotActorPaths.Add(Path);
        }
        const Arr* Components=nullptr;
        if(Snapshot->TryGetArrayField(TEXT("components"),Components)) for(const Val& Value:*Components)
        {
            const Obj C=Value->AsObject();if(!C) continue;
            FString Guid,Name,Path;FGuid Id;
            C->TryGetStringField(TEXT("actor_guid"),Guid);C->TryGetStringField(TEXT("name"),Name);C->TryGetStringField(TEXT("path"),Path);
            if(FGuid::ParseExact(Guid,EGuidFormats::Digits,Id) && Id.IsValid() && !Name.IsEmpty()) SnapshotComponentKeys.Add(Id.ToString(EGuidFormats::Digits)+TEXT("|")+Name);
            if(!Path.IsEmpty()) SnapshotComponentPaths.Add(Path);
        }
    }
    bool HiddenActor(const AActor* Actor) const
    {
        return Actor && (IsExportHiddenActor(Actor) || SnapshotActorPaths.Contains(Actor->GetPathName()) ||
            (Actor->GetActorGuid().IsValid() && SnapshotActorGuids.Contains(Actor->GetActorGuid().ToString(EGuidFormats::Digits))));
    }
    bool HiddenComponent(const USceneComponent* Component) const
    {
        if(!Component) return false;
        const AActor* Owner=Component->GetOwner();
        return IsExportHiddenComponent(Component) || HiddenActor(Owner) || SnapshotComponentPaths.Contains(Component->GetPathName()) ||
            (Owner && Owner->GetActorGuid().IsValid() && SnapshotComponentKeys.Contains(Owner->GetActorGuid().ToString(EGuidFormats::Digits)+TEXT("|")+Component->GetName()));
    }
    void Policy(Obj Manifest)
    {
        Obj P=Object();P->SetBoolField(TEXT("enabled"),Optimize);
        P->SetNumberField(TEXT("threshold_triangles"),Threshold);P->SetNumberField(TEXT("target_triangles"),Target);
        P->SetNumberField(TEXT("preferred_lod"),PreferredLOD);P->SetNumberField(TEXT("max_error_cm_before_actor_scale"),MaxError);
        Manifest->SetObjectField(TEXT("mesh_optimization"),P);
        Obj Visibility=Object();Visibility->SetBoolField(TEXT("exclude_hidden"),ExcludeHidden);
        Visibility->SetNumberField(TEXT("skipped_actors"),HiddenActors);Visibility->SetNumberField(TEXT("skipped_components"),HiddenComponents);
        Visibility->SetNumberField(TEXT("session_hidden_actor_paths"),SnapshotActorPaths.Num());
        Visibility->SetNumberField(TEXT("session_hidden_component_paths"),SnapshotComponentPaths.Num());
        Manifest->SetObjectField(TEXT("visibility_filter"),Visibility);
    }

    FString Texture(UTexture* In)
    {
        if(!In) return FString();
        const FString Key=Id(In->GetPathName());
        if(Textures->HasField(Key)) return Key;
        UTexture2D* T=Cast<UTexture2D>(In);
        UTextureCube* Cube=Cast<UTextureCube>(In);
        if((!T && !Cube) || In->Source.GetNumBlocks()!=1 || In->Source.GetNumLayers()!=1)
        { Issue(In->GetPathName()+TEXT(": requires a source-backed single-block 2D texture; cubemap/UDIM sampling needs separate translation")); return FString(); }
        FImage Image;
        if(!(Cube?Cube->Source.GetMipImage(Image,0):FImageUtils::GetTexture2DSourceImage(T,Image)))
        { Issue(In->GetPathName()+TEXT(": source texture pixels are unavailable (cooked content is unsupported)")); return FString(); }
        if(Cube && (Image.NumSlices!=1 || !Cube->Source.IsLongLatCubemap()))
        { Issue(In->GetPathName()+TEXT(": cubemap source has six faces; this exporter currently requires its original longitude-latitude source image")); return FString(); }
        const bool FloatImage=Image.Format==ERawImageFormat::RGBA16F || Image.Format==ERawImageFormat::RGBA32F || Image.Format==ERawImageFormat::R16F || Image.Format==ERawImageFormat::R32F;
        const FString Relative=TEXT("textures/")+Key+(FloatImage?TEXT(".exr"):TEXT(".png"));
        if(!FImageUtils::SaveImageByExtension(*(Out/Relative),Image))
        { Issue(In->GetPathName()+TEXT(": failed to write source texture")); return FString(); }
        Obj J=Object(); J->SetStringField(TEXT("file"),Relative); J->SetStringField(TEXT("source"),In->GetPathName());
        J->SetBoolField(TEXT("srgb"),In->SRGB && !FloatImage); J->SetBoolField(TEXT("flip_green"),T?T->bFlipGreenChannel:false);
        if(Cube)
        {
            J->SetStringField(TEXT("texture_dimension"),TEXT("cube_longlat"));
            J->SetArrayField(TEXT("resolution"),Vec({double(Image.SizeX),double(Image.SizeY)}));
            Note(In->GetPathName()+TEXT(": original cubemap panorama exported with directional longlat sampling; receiving material was not baked"));
        }
        else if(T->VirtualTextureStreaming) Note(In->GetPathName()+TEXT(": source-backed virtual Texture2D pixels exported as a regular texture; virtual streaming is not reproduced"));
        Textures->SetObjectField(Key,J); return Key;
    }

    Obj LandscapeWeight(ULandscapeComponent* Component,FName Name)
    {
        ULandscapeInfo* Info=Component->GetLandscapeInfo();
        ALandscape* Actor=Info?Info->LandscapeActor.Get():nullptr;
        if(!Actor) return Bad(TEXT("Landscape layer export requires the main landscape actor to be loaded"));
        const FString Source=Actor->GetPathName()+TEXT("/LandscapeMask_")+Name.ToString();
        const FString Key=Id(Source);
        if(const Obj* Cached=LandscapeWeights.Find(Key)) return *Cached;
        auto Fail=[&](const FString& Why) { Obj R=Bad(Why); LandscapeWeights.Add(Key,R); return R; };
        ULandscapeLayerInfoObject* LayerInfo=nullptr;
        // Inspect the final allocations across all loaded components, not just
        // the component currently being exported. A layer can be zero locally.
        for(const auto& Pair:Info->XYtoComponentMap)
        {
            ULandscapeComponent* C=Pair.Value; if(!C) continue;
            bool HasFinal=false,HasPending=false;
            for(const auto& Allocation:C->GetWeightmapLayerAllocations())
                if(Allocation.LayerInfo && Allocation.LayerInfo->GetLayerName()==Name)
                {
                    const auto& Maps=C->GetWeightmapTextures();
                    if(!Maps.IsValidIndex(Allocation.WeightmapTextureIndex) || !Maps[Allocation.WeightmapTextureIndex])
                        return Fail(TEXT("Missing final landscape weightmap for ")+Name.ToString());
                    LayerInfo=Allocation.LayerInfo; HasFinal=true;
                }
            C->ForEachLayer([&](const FGuid&,FLandscapeLayerComponentData& Layer)
            {
                for(const auto& Allocation:Layer.WeightmapData.LayerAllocations)
                    if(Allocation.LayerInfo && Allocation.LayerInfo->GetLayerName()==Name) HasPending=true;
            });
            if(!HasFinal && HasPending)
                return Fail(TEXT("Landscape paint is present in edit layers but absent from final weightmaps; open and save the landscape in Unreal before conversion"));
        }
        if(!LayerInfo) { Obj R=Constant({0}); LandscapeWeights.Add(Key,R); return R; }
        FIntRect Extent;
        if(!Info->GetLandscapeExtent(Extent)) return Fail(TEXT("Landscape export extent unavailable"));
        const int64 Width=int64(Extent.Max.X)-Extent.Min.X+1,Height=int64(Extent.Max.Y)-Extent.Min.Y+1;
        if(Width<=0 || Height<=0 || Width>16384 || Height>16384)
            return Fail(TEXT("Full landscape mask exceeds 16384 pixels per axis; tiled mask export is not yet supported"));
        const FString Relative=TEXT("textures/")+Key+TEXT(".png");
        {
            // Exactly the Landscape Manage > Export path, with Export Selected
            // Edit Layer disabled. Never save or change the source map.
            FScopedSetLandscapeEditingLayer Scope(Actor,FGuid());
            FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("LandscapeEditor"));
            Info->ExportLayer(LayerInfo,Out/Relative,Extent);
        }
        if(IFileManager::Get().FileSize(*(Out/Relative))<=0) return Fail(TEXT("Unreal landscape layer PNG export failed: ")+Name.ToString());
        Obj TextureInfo=Object(); TextureInfo->SetStringField(TEXT("file"),Relative); TextureInfo->SetStringField(TEXT("source"),Source);
        TextureInfo->SetBoolField(TEXT("srgb"),false); TextureInfo->SetBoolField(TEXT("flip_green"),false);
        TextureInfo->SetStringField(TEXT("usage"),TEXT("landscape_weight")); TextureInfo->SetStringField(TEXT("layer_name"),Name.ToString());
        TextureInfo->SetStringField(TEXT("export_mode"),TEXT("combined_landscape_layers"));
        TextureInfo->SetArrayField(TEXT("resolution"),Vec({double(Width),double(Height)}));
        TextureInfo->SetArrayField(TEXT("landscape_extent"),Vec({double(Extent.Min.X),double(Extent.Min.Y),double(Extent.Max.X),double(Extent.Max.Y)}));
        Textures->SetObjectField(Key,TextureInfo);
        Obj TextureNode=Node(TEXT("texture")),UV=Node(TEXT("uv")); UV->SetNumberField(TEXT("channel"),1);
        TextureNode->SetStringField(TEXT("texture"),Key); TextureNode->SetObjectField(TEXT("uv"),UV);
        TextureNode->SetStringField(TEXT("color_space"),TEXT("raw")); TextureNode->SetStringField(TEXT("usage"),TEXT("landscape_weight"));
        TextureNode->SetStringField(TEXT("wrap_s"),TEXT("clamp")); TextureNode->SetStringField(TEXT("wrap_t"),TEXT("clamp"));
        Obj R=Node(TEXT("mask")); R->SetObjectField(TEXT("input"),TextureNode); R->SetArrayField(TEXT("channels"),Vec({0}));
        LandscapeWeights.Add(Key,R);
        Note(FString::Printf(TEXT("%s: exported combined landscape paint layer as %lld x %lld grayscale PNG using Unreal ExportLayer"),*Source,Width,Height));
        return R;
    }

    FString Material(UMaterialInterface* MI, ULandscapeComponent* Landscape=nullptr);
    FString Mesh(UStaticMesh* SM,USplineMeshComponent* Spline=nullptr)
    {
        if(!SM) return FString();
        const FString Key=Id(Spline?Spline->GetPathName():SM->GetPathName());
        if(Meshes->HasField(Key)) return Key;
        // Keep the original longitudinal subdivisions: reducing a straight
        // source first can straighten an otherwise correctly curved rope.
        const bool OptimizeMesh=Optimize && !Spline;
        // Finish only this unique asset, rather than retaining every map build.
        FStaticMeshCompilingManager::Get().FinishCompilation({SM});
        // Render LOD0 is the simplified fallback on Nanite meshes. Never use it
        // as geometry here. Clone editor source data, without changing the asset.
        bool HiRes=SM->IsHiResMeshDescriptionValid();
        const FMeshDescription* Original=HiRes?SM->GetHiResMeshDescription():SM->GetMeshDescription(0);
        if(!Original || Original->Triangles().Num()==0)
        {
            Issue(SM->GetPathName()+TEXT(": original mesh description unavailable; omitted instead of exporting reduced render geometry"));
            return FString();
        }
        const int32 OriginalTriangles=Original->Triangles().Num();
        FString Mode=HiRes?TEXT("original_hi_res"):TEXT("original_lod0");
        int32 SourceLOD=0;
        bool Protected=false;
        for(const FStaticMaterial& Slot:SM->GetStaticMaterials())
            if(Slot.MaterialInterface)
            {
                UMaterial* M=Slot.MaterialInterface->GetMaterial();
                if(M && (M->IsTwoSided() || M->GetBlendMode()!=BLEND_Opaque || M->GetShadingModels().HasShadingModel(MSM_TwoSidedFoliage))) Protected=true;
            }
        if(OptimizeMesh && OriginalTriangles>Threshold && !Protected)
        {
            FBox3f Box(ForceInit);
            const auto Positions=FStaticMeshConstAttributes(*Original).GetVertexPositions();
            for(FVertexID V:Original->Vertices().GetElementIDs()) Box+=Positions[V];
            const FVector3f Extent=Box.GetExtent();
            if(Extent.GetMax()>0 && Extent.GetMin()<Extent.GetMax()*.001f) Protected=true;
        }
        // Thin cards/alpha foliage retain original topology unless the user
        // supplies a source-backed LOD. Automatic reduction never removes leaves.
        const FMeshDescription* Chosen=Original;
        FMeshDescription ExistingLOD;
        FMeshBuildSettings Settings=HiRes?SM->GetHiResSourceModel().BuildSettings:SM->GetSourceModel(0).BuildSettings;
        float ReductionError=0;
        if(OptimizeMesh && OriginalTriangles>Threshold)
        {
            if(PreferredLOD>0 && PreferredLOD<SM->GetNumSourceModels())
                if(const FMeshDescription* LOD=SM->GetMeshDescription(PreferredLOD))
                    if(LOD->Triangles().Num()>0 && LOD->Triangles().Num()<OriginalTriangles)
                    {
                        Chosen=LOD; SourceLOD=PreferredLOD; HiRes=false;
                        Settings=SM->GetSourceModel(SourceLOD).BuildSettings;
                        Mode=FString::Printf(TEXT("existing_source_lod%d"),SourceLOD);
                    }
            // Auto-generated Unreal LODs have render data but no source mesh
            // description. The explicit preferred LOD may use that existing
            // geometry; never silently use the Nanite LOD0 fallback.
            if(Chosen==Original && PreferredLOD>0 && PreferredLOD<SM->GetNumLODs())
            {
                const auto& L=SM->GetLODForExport(PreferredLOD);
                const auto& VB=L.VertexBuffers;
                if(L.GetNumTriangles()>0 && L.GetNumTriangles()<OriginalTriangles)
                {
                    FStaticMeshAttributes EA(ExistingLOD); EA.Register();
                    auto P=EA.GetVertexPositions(); auto UV=EA.GetVertexInstanceUVs();
                    auto Nrm=EA.GetVertexInstanceNormals(); auto Tang=EA.GetVertexInstanceTangents();
                    auto Signs=EA.GetVertexInstanceBinormalSigns();auto Col=EA.GetVertexInstanceColors();
                    auto Slots=EA.GetPolygonGroupMaterialSlotNames();
                    const int32 NumUV=VB.StaticMeshVertexBuffer.GetNumTexCoords();UV.SetNumChannels(NumUV);
                    TArray<FVertexID> Verts;
                    for(uint32 I=0;I<VB.PositionVertexBuffer.GetNumVertices();++I)
                    {FVertexID V=ExistingLOD.CreateVertex();P[V]=VB.PositionVertexBuffer.VertexPosition(I);Verts.Add(V);}
                    bool Valid=true;
                    for(const FStaticMeshSection& Section:L.Sections)
                    {
                        if(!SM->GetStaticMaterials().IsValidIndex(Section.MaterialIndex)) {Valid=false;break;}
                        const FPolygonGroupID G=ExistingLOD.CreatePolygonGroup();
                        Slots[G]=SM->GetStaticMaterials()[Section.MaterialIndex].ImportedMaterialSlotName;
                        for(uint32 Face=0;Face<Section.NumTriangles;++Face)
                        {
                            TArray<FVertexInstanceID> Corners;
                            for(uint32 C=0;C<3;++C)
                            {
                                const uint32 I=L.IndexBuffer.GetIndex(Section.FirstIndex+Face*3+C);
                                FVertexInstanceID VI=ExistingLOD.CreateVertexInstance(Verts[I]);Corners.Add(VI);
                                const FVector3f T=VB.StaticMeshVertexBuffer.VertexTangentX(I),Y=VB.StaticMeshVertexBuffer.VertexTangentY(I),Z=VB.StaticMeshVertexBuffer.VertexTangentZ(I);
                                Nrm[VI]=Z;Tang[VI]=T;Signs[VI]=FVector3f::DotProduct(FVector3f::CrossProduct(Z,T),Y)<0?-1.f:1.f;
                                const FLinearColor Color=VB.ColorVertexBuffer.GetNumVertices()>I?FLinearColor::FromSRGBColor(VB.ColorVertexBuffer.VertexColor(I)):FLinearColor::White;
                                Col[VI]=FVector4f(Color.R,Color.G,Color.B,Color.A);
                                for(int32 U=0;U<NumUV;++U) UV.Set(VI,U,VB.StaticMeshVertexBuffer.GetVertexUV(I,U));
                            }
                            ExistingLOD.CreateTriangle(G,Corners);
                        }
                    }
                    if(Valid && ExistingLOD.Triangles().Num()>0)
                    {
                        Chosen=&ExistingLOD;SourceLOD=PreferredLOD;HiRes=false;
                        Settings.BuildScale3D=FVector::OneVector;Settings.bGenerateLightmapUVs=false;Settings.bRecomputeNormals=false;
                        Mode=FString::Printf(TEXT("existing_render_lod%d"),SourceLOD);
                    }
                }
            }
        }
        FMeshDescription D=*Chosen;
        const FVector3f Scale(Settings.BuildScale3D);
        if(FMath::IsNearlyZero(Scale.X) || FMath::IsNearlyZero(Scale.Y) || FMath::IsNearlyZero(Scale.Z))
        { Issue(SM->GetPathName()+TEXT(": source mesh has a zero build scale")); return FString(); }
        EComputeNTBsFlags Flags=EComputeNTBsFlags::None;
        if(Settings.bRecomputeNormals) Flags|=EComputeNTBsFlags::Normals;
        if(Settings.bUseMikkTSpace) Flags|=EComputeNTBsFlags::UseMikkTSpace;
        if(Settings.bComputeWeightedNormals) Flags|=EComputeNTBsFlags::WeightedNTBs;
        if(Settings.bRemoveDegenerates) Flags|=EComputeNTBsFlags::IgnoreDegenerateTriangles;
        FStaticMeshOperations::ComputeTriangleTangentsAndNormals(D);
        FStaticMeshOperations::ComputeTangentsAndNormals(D,Flags);
        // Materials can sample a UV channel Unreal generates during mesh build.
        // Reproduce that layout on the original topology rather than dropping it.
        if(Settings.bGenerateLightmapUVs && D.VertexInstances().Num()>0)
        {
            FStaticMeshAttributes Mutable(D);
            auto TexCoords=Mutable.GetVertexInstanceUVs();
            const int32 ExistingChannels=TexCoords.GetNumChannels();
            int32 Src=Settings.SrcLightmapIndex, Dst=Settings.DstLightmapIndex;
            if(Src>=ExistingChannels) Src=0;
            if(Dst>=ExistingChannels)
            {
                Dst=FMath::Min(Dst,MAX_MESH_TEXTURE_COORDS_MD-1);
                TexCoords.SetNumChannels(Dst+1); Dst=ExistingChannels;
            }
            FOverlappingCorners Overlaps;
            FStaticMeshOperations::FindOverlappingCorners(Overlaps,D,Settings.bRemoveDegenerates?THRESH_POINTS_ARE_SAME:0.0f);
            if(!FStaticMeshOperations::CreateLightMapUVLayout(D,Src,Dst,Settings.MinLightmapResolution,
                    static_cast<ELightmapUVVersion>(SM->GetLightmapUVVersion()),Overlaps))
                Issue(SM->GetPathName()+TEXT(": Unreal generated lightmap UV layout failed on original mesh"));
        }
        // Stable material-slot identity survives reducer group compaction. Do
        // not look up section overrides by the reducer's new group ordinal.
        TMap<FName,int32> ExportSlotByName;
        {
            auto Names=FStaticMeshAttributes(D).GetPolygonGroupMaterialSlotNames();
            int32 SectionIndex=0;
            for(FPolygonGroupID Group:D.PolygonGroups().GetElementIDs())
            {
                int32 Slot=SM->GetMaterialIndexFromImportedMaterialSlotName(Names[Group]);
                if(Slot==INDEX_NONE) Slot=Group.GetValue();
                if(!HiRes && SM->GetSectionInfoMap().IsValidSection(SourceLOD,SectionIndex))
                    Slot=SM->GetSectionInfoMap().Get(SourceLOD,SectionIndex).MaterialIndex;
                const FName StableName(*FString::Printf(TEXT("BridgeMaterialSlot_%d"),Slot));
                Names[Group]=StableName;ExportSlotByName.Add(StableName,Slot);++SectionIndex;
            }
        }
        if(OptimizeMesh && OriginalTriangles>Threshold && Chosen==Original && !Protected)
        {
            auto& Manager=FModuleManager::LoadModuleChecked<IMeshReductionManagerModule>(TEXT("MeshReductionInterface"));
            IMeshReduction* Reducer=Manager.GetStaticMeshReductionInterface();
            if(Reducer && Reducer->IsSupported())
            {
                FMeshReductionSettings R;
                R.PercentTriangles=FMath::Min(1.0f,float(Target)/float(D.Triangles().Num()));
                R.MaxNumOfTriangles=Target;
                R.TerminationCriterion=EStaticMeshReductionTerimationCriterion::Triangles;
                R.MaxDeviation=MaxError/FMath::Max3(FMath::Abs(Scale.X),FMath::Abs(Scale.Y),FMath::Abs(Scale.Z));
                R.SilhouetteImportance=EMeshFeatureImportance::Highest;
                R.TextureImportance=EMeshFeatureImportance::Highest;
                R.ShadingImportance=EMeshFeatureImportance::High;
                R.VertexColorImportance=EMeshFeatureImportance::Highest;
                R.bRecalculateNormals=false; R.WeldingThreshold=0;
                FOverlappingCorners Overlaps;
                FStaticMeshOperations::FindOverlappingCorners(Overlaps,D,0);
                FMeshDescription Reduced;
                FStaticMeshAttributes(Reduced).Register();
                Reducer->ReduceMeshDescription(Reduced,ReductionError,D,Overlaps,R);
                const float WorldError=ReductionError*FMath::Max3(FMath::Abs(Scale.X),FMath::Abs(Scale.Y),FMath::Abs(Scale.Z));
                bool Valid=Reduced.Triangles().Num()>0 && Reduced.Triangles().Num()<D.Triangles().Num() && FMath::IsFinite(WorldError) && WorldError<=MaxError+KINDA_SMALL_NUMBER;
                FStaticMeshConstAttributes RA(Reduced), DA(D);
                Valid=Valid && RA.GetVertexInstanceUVs().GetNumChannels()==DA.GetVertexInstanceUVs().GetNumChannels();
                TSet<FName> OriginalSlots,ReducedSlots;
                for(FPolygonGroupID G:D.PolygonGroups().GetElementIDs()) if(D.GetPolygonGroupTriangles(G).Num()) OriginalSlots.Add(DA.GetPolygonGroupMaterialSlotNames()[G]);
                for(FPolygonGroupID G:Reduced.PolygonGroups().GetElementIDs()) if(Reduced.GetPolygonGroupTriangles(G).Num()) ReducedSlots.Add(RA.GetPolygonGroupMaterialSlotNames()[G]);
                Valid=Valid && OriginalSlots.Num()==ReducedSlots.Num();
                for(FName Slot:OriginalSlots) Valid=Valid && ReducedSlots.Contains(Slot);
                if(Valid) { D=MoveTemp(Reduced); Mode=TEXT("simplified_export_copy"); }
                else Note(SM->GetPathName()+TEXT(": reduction failed quality/material/UV checks; kept original geometry"));
            }
            else Note(SM->GetPathName()+TEXT(": no supported mesh reducer; kept original geometry"));
        }
        else if(OptimizeMesh && OriginalTriangles>Threshold && Protected && Chosen==Original)
            Note(SM->GetPathName()+TEXT(": automatic reduction skipped for two-sided/opacity foliage or thin surfaces"));
        FStaticMeshConstAttributes Attr(D);
        const auto P=Attr.GetVertexPositions(); const auto Normals=Attr.GetVertexInstanceNormals();
        const auto Colors=Attr.GetVertexInstanceColors(); const auto UV=Attr.GetVertexInstanceUVs();
        const auto SlotNames=Attr.GetPolygonGroupMaterialSlotNames();
        const int32 Channels=UV.GetNumChannels();
        TArray<FSourceVertex> Vertices; TMap<FSourceVertex,int32> Lookup;
        TMap<FVertexInstanceID,int32> Corners;
        TArray<FVector3f> UnbentPositions,UnbentNormals;
        bool ValidSpline=true; bool ValidGeometry=true; int32 RepairedUVs=0;
        const bool ReverseSpline=Spline && BridgeSpline::ReverseWinding(Spline);
        auto Vertex=[&](FVertexInstanceID VI)
        {
            if(const int32* Found=Corners.Find(VI)) return *Found;
            FSourceVertex V; V.Position=P[D.GetVertexInstanceVertex(VI)]*Scale;
            V.Normal=(Normals[VI]/Scale).GetSafeNormal();
            if(V.Position.ContainsNaN() || V.Normal.ContainsNaN()) {ValidGeometry=false;V.Position=FVector3f::ZeroVector;V.Normal=FVector3f(0,0,1);}
            const FVector3f UnbentPosition=V.Position,UnbentNormal=V.Normal;
            if(Spline && !BridgeSpline::Deform(Spline,UnbentPosition,UnbentNormal,V.Position,V.Normal))
            {ValidSpline=false;V.Position=FVector3f::ZeroVector;V.Normal=FVector3f(0,0,1);}
            // Match Unreal's source-linear -> render-vertex colour conversion.
            V.Color=Colors.IsValid()?FLinearColor(Colors[VI]).ToFColor(true):FColor::White;
            for(int32 C=0;C<Channels;++C) {auto U=UV.Get(VI,C);if(!FMath::IsFinite(U.X)){U.X=0;++RepairedUVs;}if(!FMath::IsFinite(U.Y)){U.Y=0;++RepairedUVs;}V.UVs.Add(U);}
            int32 Index;
            const int32* Found=Lookup.Find(V);
            // A closed/folded spline may map distinct source vertices to the
            // same output point. Keep their source paint coordinates separate.
            if(Found && (!Spline || UnbentPositions[*Found]==UnbentPosition)) Index=*Found;
            else
            {
                Index=Vertices.Add(V);Lookup.Add(V,Index);
                if(Spline) {UnbentPositions.Add(UnbentPosition);UnbentNormals.Add(UnbentNormal);}
            }
            Corners.Add(VI,Index); return Index;
        };
        Arr Indices,Sections; int32 SectionIndex=0;
        for(FPolygonGroupID Group:D.PolygonGroups().GetElementIDs())
        {
            const int32* SavedSlot=ExportSlotByName.Find(SlotNames[Group]);
            if(!SavedSlot) { Issue(SM->GetPathName()+TEXT(": reducer lost a material-slot identity; mesh omitted")); return FString(); }
            const int32 Slot=*SavedSlot;
            const int32 First=Indices.Num()/3;
            for(FTriangleID Triangle:D.GetPolygonGroupTriangles(Group))
            {
                const auto VI=D.GetTriangleVertexInstances(Triangle);
                for(int32 C=0;C<3;++C) Indices.Add(N(Vertex(VI[ReverseSpline?2-C:C])));
            }
            const int32 Count=Indices.Num()/3-First;
            if(Count)
            {
                if(!SM->GetStaticMaterials().IsValidIndex(Slot))
                { Issue(SM->GetPathName()+TEXT(": cannot resolve original mesh material slot")); return FString(); }
                Obj Q=Object(); Q->SetNumberField(TEXT("slot"),Slot); Q->SetNumberField(TEXT("first_face"),First); Q->SetNumberField(TEXT("face_count"),Count); Sections.Add(V(Q));
            }
            ++SectionIndex;
        }
        if(!ValidGeometry) {Issue(SM->GetPathName()+TEXT(": non-finite positions/normals; mesh omitted"));return FString();}
        if(RepairedUVs) Note(FString::Printf(TEXT("%s: replaced %d non-finite UV coordinates with zero; inspect source UV channels"),*SM->GetPathName(),RepairedUVs));
        if(!ValidSpline) {Issue(Spline->GetPathName()+TEXT(": spline has non-finite or degenerate deformation; omitted"));return FString();}
        if(Spline)
        {
            Mode=TEXT("spline_deformed_original");
            Note(Spline->GetPathName()+TEXT(": spline deformation frozen as static geometry; original subdivisions retained, export reduction/LOD selection skipped"));
        }
        Arr Points,NormalData,ColorData,UVData; TArray<Arr> UVChannels; UVChannels.SetNum(Channels);
        TArray<FVector3f>& CachedPositions=SourcePositions.FindOrAdd(Key);
        TArray<FVector3f>& CachedNormals=SourceNormals.FindOrAdd(Key);
        for(const FSourceVertex& Vtx:Vertices)
        {
            const auto& X=Vtx.Position; const auto& Z=Vtx.Normal; const auto& C=Vtx.Color;
            Points.Add(A(Vec({X.X,X.Y,X.Z}))); NormalData.Add(A(Vec({Z.X,Z.Y,Z.Z})));
            ColorData.Add(A(Vec({C.R/255.0,C.G/255.0,C.B/255.0,C.A/255.0})));
            for(int32 CIndex=0;CIndex<Channels;++CIndex) UVChannels[CIndex].Add(A(Vec({Vtx.UVs[CIndex].X,Vtx.UVs[CIndex].Y})));
            const int32 PaintIndex=CachedPositions.Num();
            CachedPositions.Add(Spline?UnbentPositions[PaintIndex]:X);
            CachedNormals.Add(Spline?UnbentNormals[PaintIndex]:Z);
        }
        for(const Arr& Channel:UVChannels) UVData.Add(A(Channel));
        int32 RenderTriangles=0; const FStaticMeshRenderData* RD=SM->GetRenderData();
        if(RD && !RD->LODResources.IsEmpty()) RenderTriangles=RD->LODResources[0].IndexBuffer.GetNumIndices()/3;
        Obj J=Object(); J->SetStringField(TEXT("source"),SM->GetPathName()); J->SetArrayField(TEXT("points"),Points);
        J->SetArrayField(TEXT("normals"),NormalData); J->SetArrayField(TEXT("uvs"),UVData); J->SetArrayField(TEXT("colors"),ColorData);
        J->SetArrayField(TEXT("indices"),Indices); J->SetArrayField(TEXT("sections"),Sections); J->SetStringField(TEXT("geometry_source"),Mode);
        J->SetNumberField(TEXT("source_triangles"),OriginalTriangles); J->SetNumberField(TEXT("render_lod0_triangles"),RenderTriangles);
        if(Spline)
        {
            J->SetStringField(TEXT("spline_component"),Spline->GetPathName());
            J->SetStringField(TEXT("source_mesh"),SM->GetPathName());
            J->SetBoolField(TEXT("spline_reversed_winding"),ReverseSpline);
        }
        const FString Relative=TEXT("meshes/")+Key+TEXT(".json");
        if(!Save(J,Out/Relative)) { Issue(TEXT("Could not save ")+Relative); return FString(); }
        Obj Ref=Object(); Ref->SetStringField(TEXT("file"),Relative); Ref->SetStringField(TEXT("source"),SM->GetPathName());
        Ref->SetStringField(TEXT("geometry_source"),Mode); Ref->SetNumberField(TEXT("source_triangles"),OriginalTriangles);
        if(Spline) {Ref->SetStringField(TEXT("spline_component"),Spline->GetPathName());Ref->SetStringField(TEXT("source_mesh"),SM->GetPathName());}
        Ref->SetNumberField(TEXT("exported_triangles"),Indices.Num()/3); Ref->SetNumberField(TEXT("reduction_error_cm"),ReductionError*FMath::Max3(FMath::Abs(Scale.X),FMath::Abs(Scale.Y),FMath::Abs(Scale.Z))); Ref->SetNumberField(TEXT("render_lod0_triangles"),RenderTriangles);
        Meshes->SetObjectField(Key,Ref);
        if(Spline)
        { UE_LOG(LogTemp,Display,TEXT("BRIDGE SPLINE MESH: %s | source %s | %d triangles | reversed winding %d"),*Spline->GetPathName(),*SM->GetPathName(),Indices.Num()/3,ReverseSpline?1:0); }
        else
        { UE_LOG(LogTemp,Display,TEXT("BRIDGE ORIGINAL MESH: %s | %s | source/exported %d/%d triangles | render LOD0 %d"),*SM->GetPathName(),*Mode,OriginalTriangles,Indices.Num()/3,RenderTriangles); }
        return Key;
    }

    FString SkeletalMesh(USkeletalMesh* SK)
    {
        if(!SK) return FString();
        const FString Key=Id(SK->GetPathName());
        if(Meshes->HasField(Key)) return Key;
        const FMeshDescription* Original=SK->GetMeshDescription(0);
        if(!Original || Original->Triangles().Num()==0)
        { Issue(SK->GetPathName()+TEXT(": original skeletal LOD0 mesh description unavailable; omitted")); return FString(); }
        // Use the existing source-geometry serializer without building or saving
        // a new asset. Imported skeletal positions already represent reference pose.
        UStaticMesh* Proxy=NewObject<UStaticMesh>(GetTransientPackage());
        auto& Settings=Proxy->AddSourceModel().BuildSettings;
        Settings.bRecomputeNormals=false; Settings.bRecomputeTangents=false;
        Settings.bGenerateLightmapUVs=false; Settings.bRemoveDegenerates=false;
        Proxy->CreateMeshDescription(0,FMeshDescription(*Original));
        for(const FSkeletalMaterial& M:SK->GetMaterials())
            Proxy->GetStaticMaterials().Add(FStaticMaterial(M.MaterialInterface,M.MaterialSlotName,M.ImportedMaterialSlotName));
        FStaticMeshConstAttributes Attributes(*Original);
        const auto Slots=Attributes.GetPolygonGroupMaterialSlotNames();
        const FSkeletalMeshLODInfo* LOD=SK->GetLODInfo(0); int32 Section=0;
        for(FPolygonGroupID Group:Original->PolygonGroups().GetElementIDs())
        {
            int32 Slot=Proxy->GetMaterialIndexFromImportedMaterialSlotName(Slots[Group]);
            if(Slot==INDEX_NONE) Slot=Group.GetValue();
            if(LOD && LOD->LODMaterialMap.IsValidIndex(Section) && LOD->LODMaterialMap[Section]!=INDEX_NONE)
                Slot=LOD->LODMaterialMap[Section];
            FMeshSectionInfo Info;Info.MaterialIndex=Slot;Proxy->GetSectionInfoMap().Set(0,Section++,Info);
        }
        TGuardValue<bool> KeepSkeletalTopology(Optimize,false);
        const FString ProxyKey=Mesh(Proxy);if(ProxyKey.IsEmpty()) return FString();
        Obj Ref=Meshes->GetObjectField(ProxyKey);
        FString Text;FFileHelper::LoadFileToString(Text,*(Out/Ref->GetStringField(TEXT("file"))));
        Obj Geometry;auto Reader=TJsonReaderFactory<>::Create(Text);
        if(!FJsonSerializer::Deserialize(Reader,Geometry)) return FString();
        Geometry->SetStringField(TEXT("source"),SK->GetPathName());
        Geometry->SetStringField(TEXT("geometry_source"),TEXT("skeletal_reference_lod0"));
        const FString Relative=TEXT("meshes/")+Key+TEXT(".json");
        if(!Save(Geometry,Out/Relative)) return FString();
        IFileManager::Get().Delete(*(Out/Ref->GetStringField(TEXT("file"))));
        Ref->SetStringField(TEXT("file"),Relative);Ref->SetStringField(TEXT("source"),SK->GetPathName());
        Ref->SetStringField(TEXT("geometry_source"),TEXT("skeletal_reference_lod0"));
        Meshes->RemoveField(ProxyKey);Meshes->SetObjectField(Key,Ref);
        Note(SK->GetPathName()+TEXT(": skeletal LOD0 exported in reference pose as static geometry; no bones, animation, morph targets or cloth deformation"));
        return Key;
    }

    void PaintedColors(UStaticMeshComponent* Component,const FString& Key,Obj Instance)
    {
        if(Component->LODData.IsEmpty() || !Component->LODData[0].OverrideVertexColors) return;
        const auto* RD=Component->GetStaticMesh()->GetRenderData();
        if(!RD || RD->LODResources.IsEmpty() || !SourcePositions.Contains(Key)) return;
        const auto& L=RD->LODResources[0]; const auto* Buffer=Component->LODData[0].OverrideVertexColors;
        if(Buffer->GetNumVertices()!=L.VertexBuffers.PositionVertexBuffer.GetNumVertices())
        { Issue(Component->GetPathName()+TEXT(": invalid component paint buffer; original mesh vertex colours retained")); return; }
        TArray<FStaticMeshBuildVertex> NewVertices;
        const auto& Positions=SourcePositions[Key]; const auto& Normals=SourceNormals[Key];
        for(int32 I=0;I<Positions.Num();++I)
        { FStaticMeshBuildVertex V{}; V.Position=Positions[I]; V.TangentZ=Normals[I]; NewVertices.Add(V); }
        FPositionVertexBuffer NewP; NewP.Init(Positions);
        FStaticMeshVertexBuffer NewN; NewN.Init(NewVertices,1);
        TArray<FColor> Remapped;
        RemapPaintedVertexColors(Component->LODData[0].PaintedVertices,Buffer,L.VertexBuffers.PositionVertexBuffer,L.VertexBuffers.StaticMeshVertexBuffer,NewP,&NewN,Remapped);
        if(Remapped.Num()!=Positions.Num())
        { Issue(Component->GetPathName()+TEXT(": component paint remap failed; original mesh vertex colours retained")); return; }
        Arr Colors; for(const FColor C:Remapped) Colors.Add(A(Vec({C.R/255.0,C.G/255.0,C.B/255.0,C.A/255.0})));
        Instance->SetArrayField(TEXT("colors"),Colors);
        Note(Component->GetPathName()+TEXT(": component paint transferred to original mesh with Unreal nearest-position/normal remapping"));
    }

    Arr Slots(UPrimitiveComponent* C)
    {
        Arr R; for(int32 I=0;I<C->GetNumMaterials();++I) R.Add(S(Material(C->GetMaterial(I)))); return R;
    }
    void Landscape(ALandscapeProxy* Landscape);
};

struct FFunctionScope
{
    TMap<UMaterialExpressionFunctionInput*,FExpressionInput> Inputs;
    TSharedPtr<FFunctionScope> Parent;
    TMap<TPair<UMaterialExpressionFunctionInput*,EMaterialProperty>,Obj> Resolved;
};

struct FGraph
{
    FExport& Export;
    UMaterialInterface* Material;
    TSharedPtr<FFunctionScope> FunctionScope;
    ULandscapeComponent* Landscape=nullptr;
    EMaterialProperty Property=MP_BaseColor;
    Obj Default() { return Property==MP_Normal?Constant({0,0,1}):Property==MP_Roughness || Property==MP_Specular?Constant({0.5}):Property==MP_Opacity || Property==MP_OpacityMask || Property==MP_AmbientOcclusion?Constant({1}):Constant({0}); }
    Obj Bin(const FString& Op,Obj A,Obj B) { Obj R=Node(Op); R->SetObjectField(TEXT("a"),A); R->SetObjectField(TEXT("b"),B); return R; }
    Obj Weight(FName Name)
    {
        if(!Landscape) return Bad(TEXT("Landscape layer node used outside a landscape component"));
        return Export.LandscapeWeight(Landscape,Name);
    }
    Obj Input(const FExpressionInput& I, int Depth=0)
    {
        if(!I.Expression) return Bad(TEXT("Unconnected required expression"));
        Obj R=Expression(I.Expression,I.OutputIndex,Depth+1);
        if(I.Mask)
        {
            Arr Channels; if(I.MaskR) Channels.Add(N(0)); if(I.MaskG) Channels.Add(N(1)); if(I.MaskB) Channels.Add(N(2)); if(I.MaskA) Channels.Add(N(3));
            Obj M=Node(TEXT("mask")); M->SetObjectField(TEXT("input"),R); M->SetArrayField(TEXT("channels"),Channels); return M;
        }
        return R;
    }
    Obj Or(const FExpressionInput& I,float F,int D) { return I.Expression?Input(I,D):Constant({F}); }
    Obj Binary(const FString& Op,const FExpressionInput& A,float CA,const FExpressionInput& B,float CB,int D)
    { Obj R=Node(Op); R->SetObjectField(TEXT("a"),Or(A,CA,D)); R->SetObjectField(TEXT("b"),Or(B,CB,D)); return R; }
    Obj Expression(UMaterialExpression* E,int Output,int D)
    {
        if(!E || D>128) return Bad(TEXT("Missing expression or graph depth exceeded"));
        if(auto* X=Cast<UMaterialExpressionVirtualTextureFeatureSwitch>(E))
        {
            // USD/MDL cannot sample Unreal's runtime virtual texture pages.
            // Follow the ordinary surface path, including material bundles,
            // without evaluating/exporting resources from the virtual path.
            if(!X->No.GetTracedInput().Expression)
                return Bad(TEXT("VirtualTextureFeatureSwitch has no connected non-virtual No input at ")+X->GetPathName());
            Export.Note(Material->GetPathName()+TEXT(": VirtualTextureFeatureSwitch uses non-virtual No input; Unreal runtime virtual-texture blending is not reproduced"));
            return Input(X->No,D);
        }
        if(Cast<UMaterialExpressionPerInstanceFadeAmount>(E))
        {
            // Static export has no Unreal foliage cull-distance fade state.
            // Keep the surrounding opacity graph, especially its leaf mask.
            Export.Note(Material->GetPathName()+TEXT(": PerInstanceFadeAmount fixed at 1 for fully visible static foliage; texture opacity masks retained"));
            return Constant({1});
        }
        if(auto* X=Cast<UMaterialExpressionRuntimeVirtualTextureReplace>(E))
        {
            Export.Note(Material->GetPathName()+TEXT(": runtime virtual texture write pass omitted; retained normal visible-surface input"));
            return Input(X->Default,D);
        }
        if(auto* X=Cast<UMaterialExpressionQualitySwitch>(E))
        {
            auto* Quality=IConsoleManager::Get().FindConsoleVariable(TEXT("r.MaterialQualityLevel"));
            const int32 Level=Quality?Quality->GetInt():INDEX_NONE;
            const FExpressionInput& Selected=Level>=0 && Level<EMaterialQualityLevel::Num && X->Inputs[Level].GetTracedInput().Expression?X->Inputs[Level]:X->Default;
            Export.Note(Material->GetPathName()+FString::Printf(TEXT(": QualitySwitch uses quality %d with Unreal default-input fallback"),Level));
            return Input(Selected,D);
        }
        if(auto* X=Cast<UMaterialExpressionGetMaterialAttributes>(E))
        {
            if(Output==0) return X->MaterialAttributes.Expression?Input(X->MaterialAttributes,D):Default();
            if(!X->AttributeGetTypes.IsValidIndex(Output-1)) return Bad(TEXT("Invalid GetMaterialAttributes output"));
            const auto Selected=FMaterialAttributeDefinitionMap::GetProperty(X->AttributeGetTypes[Output-1]);
            if(Selected==MP_MAX) return Bad(TEXT("Unknown material attribute GUID"));
            TGuardValue<EMaterialProperty> SelectProperty(Property,Selected);
            return X->MaterialAttributes.Expression?Input(X->MaterialAttributes,D):Default();
        }
        if(auto* X=Cast<UMaterialExpressionSetMaterialAttributes>(E))
        {
            const int32 Pin=X->AttributeSetTypes.Find(FMaterialAttributeDefinitionMap::GetID(Property));
            if(Pin!=INDEX_NONE && X->Inputs.IsValidIndex(Pin+1) && X->Inputs[Pin+1].Expression) return Input(X->Inputs[Pin+1],D);
            return !X->Inputs.IsEmpty() && X->Inputs[0].Expression?Input(X->Inputs[0],D):Default();
        }
        if(auto* X=Cast<UMaterialExpressionBreakMaterialAttributes>(E))
        {
            static const EMaterialProperty Properties[]={MP_BaseColor,MP_Metallic,MP_Specular,MP_Roughness,MP_Anisotropy,MP_EmissiveColor,MP_Opacity,MP_OpacityMask,MP_Normal,MP_Tangent,MP_WorldPositionOffset,MP_SubsurfaceColor,MP_CustomData0,MP_CustomData1,MP_AmbientOcclusion,MP_Refraction,MP_CustomizedUVs0,MP_CustomizedUVs1,MP_CustomizedUVs2,MP_CustomizedUVs3,MP_CustomizedUVs4,MP_CustomizedUVs5,MP_CustomizedUVs6,MP_CustomizedUVs7,MP_PixelDepthOffset,MP_ShadingModel,MP_Displacement};
            if(Output<0 || Output>=UE_ARRAY_COUNT(Properties)) return Bad(TEXT("Invalid BreakMaterialAttributes output"));
            TGuardValue<EMaterialProperty> SelectProperty(Property,Properties[Output]);
            return X->MaterialAttributes.Expression?Input(X->MaterialAttributes,D):Default();
        }
        if(auto* X=Cast<UMaterialExpressionTextureObjectParameter>(E))
        {
            UTexture* Texture=X->Texture;Material->GetTextureParameterValue(FMaterialParameterInfo(X->ParameterName),Texture);
            if(!Texture) return Bad(TEXT("Missing texture object parameter"));
            Obj R=Node(TEXT("texture_object"));R->SetStringField(TEXT("source"),Texture->GetPathName());return R;
        }
        if(auto* X=Cast<UMaterialExpressionTextureObject>(E))
        {
            if(!X->Texture) return Bad(TEXT("Missing texture object"));
            Obj R=Node(TEXT("texture_object"));R->SetStringField(TEXT("source"),X->Texture->GetPathName());return R;
        }

        if(Cast<UMaterialExpressionTime>(E)) { Export.Note(Material->GetPathName()+TEXT(": time-dependent material sampled at time zero")); return Constant({0}); }
        if(auto* X=Cast<UMaterialExpressionIf>(E))
        {
            Obj R=Node(TEXT("if")); R->SetObjectField(TEXT("a"),Input(X->A,D)); R->SetObjectField(TEXT("b"),Or(X->B,X->ConstB,D));
            R->SetObjectField(TEXT("greater"),Input(X->AGreaterThanB,D)); R->SetObjectField(TEXT("less"),Input(X->ALessThanB,D));
            R->SetObjectField(TEXT("equal"),Input(X->AEqualsB.Expression?X->AEqualsB:X->AGreaterThanB,D)); R->SetNumberField(TEXT("threshold"),X->AEqualsB.Expression?X->EqualsThreshold:0); return R;
        }
        if(auto* X=Cast<UMaterialExpressionPanner>(E))
        {
            Obj UV=Node(TEXT("uv")); UV->SetNumberField(TEXT("channel"),X->ConstCoordinate);
            Obj Pan=Bin(TEXT("multiply"),X->Speed.Expression?Input(X->Speed,D):Constant({X->SpeedX,X->SpeedY}),Or(X->Time,0,D));
            if(X->bFractionalPart) { Obj Fraction=Node(TEXT("frac")); Fraction->SetObjectField(TEXT("input"),Pan); Pan=Fraction; }
            Export.Note(Material->GetPathName()+TEXT(": texture panning sampled at time zero"));
            return Bin(TEXT("add"),X->Coordinate.Expression?Input(X->Coordinate,D):UV,Pan);
        }
        if(auto* X=Cast<UMaterialExpressionMakeMaterialAttributes>(E))
        {
            FExpressionInput* I=nullptr;
            switch(Property) { case MP_BaseColor:I=&X->BaseColor;break; case MP_Normal:I=&X->Normal;break; case MP_Roughness:I=&X->Roughness;break; case MP_Metallic:I=&X->Metallic;break; case MP_Specular:I=&X->Specular;break; case MP_EmissiveColor:I=&X->EmissiveColor;break; case MP_Opacity:I=&X->Opacity;break; case MP_OpacityMask:I=&X->OpacityMask;break; case MP_AmbientOcclusion:I=&X->AmbientOcclusion;break; default:break; }
            return I && I->Expression?Input(*I,D):Default();
        }
        if(auto* X=Cast<UMaterialExpressionBlendMaterialAttributes>(E))
        {
            const auto Blend=FMaterialAttributeDefinitionMap::GetShaderFrequency(Property)==SF_Vertex?X->VertexAttributeBlendType:X->PixelAttributeBlendType;
            auto Attribute=[&](const FExpressionInput& I){return I.Expression?Input(I,D):Default();};
            if(Blend==EMaterialAttributeBlend::UseA) return Attribute(X->A);
            if(Blend==EMaterialAttributeBlend::UseB) return Attribute(X->B);
            Obj R=Node(TEXT("lerp"));R->SetObjectField(TEXT("a"),Attribute(X->A));R->SetObjectField(TEXT("b"),Attribute(X->B));R->SetObjectField(TEXT("alpha"),Or(X->Alpha,0,D));return R;
        }
        if(auto* X=Cast<UMaterialExpressionLandscapeLayerSample>(E)) return Weight(X->ParameterName);
        if(auto* X=Cast<UMaterialExpressionLandscapeLayerBlend>(E))
        {
            Obj Result=Constant({0}),Sum=Constant({0}); TArray<Obj> Weights; bool Normalize=false;
            for(const auto& Layer:X->Layers)
            {
                Obj W=Weight(Layer.LayerName);
                if(Layer.BlendType==LB_HeightBlend)
                {
                    Normalize=true; Obj C=Node(TEXT("clamp"));
                    C->SetObjectField(TEXT("input"),Bin(TEXT("add"),Bin(TEXT("subtract"),Bin(TEXT("multiply"),W,Constant({2})),Constant({1})),Or(Layer.HeightInput,Layer.ConstHeightInput,D)));
                    C->SetObjectField(TEXT("min"),Constant({0.0001})); C->SetObjectField(TEXT("max"),Constant({1})); W=C;
                }
                Weights.Add(W); if(Layer.BlendType!=LB_AlphaBlend) Sum=Bin(TEXT("add"),Sum,W);
            }
            for(int32 I=0;I<X->Layers.Num();++I)
            {
                const auto& Layer=X->Layers[I]; if(Layer.BlendType==LB_AlphaBlend) continue;
                Obj Value=Layer.LayerInput.Expression?Input(Layer.LayerInput,D):Constant({Layer.ConstLayerInput.X,Layer.ConstLayerInput.Y,Layer.ConstLayerInput.Z});
                Result=Bin(TEXT("add"),Result,Bin(TEXT("multiply"),Value,Normalize?Bin(TEXT("divide"),Weights[I],Sum):Weights[I]));
            }
            for(int32 I=0;I<X->Layers.Num();++I)
            {
                const auto& Layer=X->Layers[I]; if(Layer.BlendType!=LB_AlphaBlend) continue;
                Obj R=Node(TEXT("lerp")); R->SetObjectField(TEXT("a"),Result); R->SetObjectField(TEXT("b"),Layer.LayerInput.Expression?Input(Layer.LayerInput,D):Constant({Layer.ConstLayerInput.X,Layer.ConstLayerInput.Y,Layer.ConstLayerInput.Z})); R->SetObjectField(TEXT("alpha"),Weights[I]); Result=R;
            }
            return Result;
        }
        if(Cast<UMaterialExpressionVertexColor>(E)) return Node(TEXT("vertex_color"));
        if(Cast<UMaterialExpressionObjectPositionWS>(E)) return Node(TEXT("object_position"));
        if(Cast<UMaterialExpressionPerInstanceRandom>(E)) return Node(TEXT("per_instance_random"));
        if(Cast<UMaterialExpressionCameraVectorWS>(E)) return Node(TEXT("camera_vector"));
        if(Cast<UMaterialExpressionPixelNormalWS>(E)) return Node(TEXT("pixel_normal"));
        if(Cast<UMaterialExpressionVertexNormalWS>(E)) return Node(TEXT("vertex_normal"));
        if(Cast<UMaterialExpressionTwoSidedSign>(E)) return Node(TEXT("two_sided_sign"));
        if(auto* X=Cast<UMaterialExpressionVertexInterpolator>(E))
        {
            Obj R=Node(TEXT("vertex_interpolator"));R->SetObjectField(TEXT("input"),Input(X->Input,D));return R;
        }
        if(auto* X=Cast<UMaterialExpressionLocalPosition>(E))
        {
            Obj R=Node(TEXT("local_position"));
            R->SetStringField(TEXT("origin"),X->LocalOrigin==ELocalPositionOrigin::Primitive?TEXT("component"):X->LocalOrigin==ELocalPositionOrigin::InstancePreSkinning?TEXT("instance_pre_skinning"):TEXT("instance"));
            R->SetBoolField(TEXT("include_offsets"),X->IncludedOffsets==EPositionIncludedOffsets::IncludeOffsets);
            return R;
        }
        if(auto* X=Cast<UMaterialExpressionCeil>(E)) { Obj R=Node(TEXT("ceil"));R->SetObjectField(TEXT("input"),Input(X->Input,D));return R; }
        if(auto* X=Cast<UMaterialExpressionFloor>(E)) { Obj R=Node(TEXT("floor"));R->SetObjectField(TEXT("input"),Input(X->Input,D));return R; }
        if(auto* X=Cast<UMaterialExpressionNoise>(E))
        {
            // The MDL backend reproduces computational Voronoi with a
            // connected position. Other algorithms retain full diagnostics.
            const bool Supported=X->NoiseFunction==NOISEFUNCTION_VoronoiALU && X->Position.Expression;
            Obj R=Supported?Node(TEXT("unreal_noise")):Bad(TEXT("MaterialExpressionNoise at ")+X->GetPathName());
            Obj Settings=Object();Settings->SetNumberField(TEXT("function"),X->NoiseFunction);Settings->SetNumberField(TEXT("quality"),X->Quality);
            Settings->SetNumberField(TEXT("scale"),X->Scale);Settings->SetNumberField(TEXT("levels"),X->Levels);Settings->SetNumberField(TEXT("level_scale"),X->LevelScale);
            Settings->SetNumberField(TEXT("output_min"),X->OutputMin);Settings->SetNumberField(TEXT("output_max"),X->OutputMax);
            Settings->SetBoolField(TEXT("turbulence"),X->bTurbulence);Settings->SetBoolField(TEXT("tiling"),X->bTiling);Settings->SetNumberField(TEXT("repeat_size"),X->RepeatSize);
            Settings->SetNumberField(TEXT("position_origin"),static_cast<int32>(X->WorldPositionOriginType));R->SetObjectField(TEXT("noise_settings"),Settings);
            if(X->Position.Expression) R->SetObjectField(TEXT("position"),Input(X->Position,D));
            if(X->FilterWidth.Expression) R->SetObjectField(TEXT("filter_width"),Input(X->FilterWidth,D));
            return R;
        }
        if(auto* X=Cast<UMaterialExpressionReflectionVectorWS>(E))
        {
            Obj R=Node(TEXT("reflection_vector"));
            if(X->CustomWorldNormal.Expression) R->SetObjectField(TEXT("normal"),Input(X->CustomWorldNormal,D));
            R->SetBoolField(TEXT("normalize_custom"),X->bNormalizeCustomWorldNormal);return R;
        }
        if(auto* X=Cast<UMaterialExpressionTransform>(E))
        {
            auto Space=[](int32 Value)->FString { return Value==0?TEXT("tangent"):Value==1?TEXT("object"):Value==2?TEXT("world"):FString(); };
            const FString From=Space(X->TransformSourceType),To=Space(X->TransformType);
            if(From.IsEmpty() || To.IsEmpty()) return Bad(TEXT("Vector Transform requires tangent, local or world space at ")+X->GetPathName());
            Obj R=Node(TEXT("transform_vector"));R->SetObjectField(TEXT("input"),Input(X->Input,D));R->SetStringField(TEXT("from"),From);R->SetStringField(TEXT("to"),To);return R;
        }
        if(E->GetClass()->GetName()==TEXT("MaterialExpressionMaterialXRemap"))
        {
            // MaterialX's expression is private to an optional engine plugin.
            // Read its reflected input/default fields instead of depending on
            // that plugin's private headers or constructing guessed defaults.
            auto Pin=[&](FName PinName)->Obj
            {
                auto* Property=FindFProperty<FStructProperty>(E->GetClass(),PinName);
                if(!Property || Property->Struct->GetFName()!=TEXT("ExpressionInput") || Property->GetElementSize()!=sizeof(FExpressionInput)) return Bad(TEXT("Missing MaterialX Remap input: ")+PinName.ToString());
                const FExpressionInput& Value=*Property->ContainerPtrToValuePtr<FExpressionInput>(E);
                if(Value.Expression) return Input(Value,D);
                auto* Default=FindFProperty<FFloatProperty>(E->GetClass(),FName(*(PinName.ToString()+TEXT("Default"))));
                return Default?Constant({Default->GetPropertyValue_InContainer(E)}):Bad(TEXT("Unconnected MaterialX Remap input: ")+PinName.ToString());
            };
            Obj Low=Pin(TEXT("InputLow")),High=Pin(TEXT("InputHigh")),TargetLow=Pin(TEXT("TargetLow")),TargetHigh=Pin(TEXT("TargetHigh"));
            return Bin(TEXT("add"),TargetLow,Bin(TEXT("multiply"),Bin(TEXT("subtract"),Pin(TEXT("Input")),Low),Bin(TEXT("divide"),Bin(TEXT("subtract"),TargetHigh,TargetLow),Bin(TEXT("subtract"),High,Low))));
        }
        if(Cast<UMaterialExpressionDecalColor>(E)) return Node(TEXT("decal_color"));
        if(Cast<UMaterialExpressionDecalLifetimeOpacity>(E)) return Constant({1});
        if(auto* X=Cast<UMaterialExpressionFrac>(E)) { Obj R=Node(TEXT("frac")); R->SetObjectField(TEXT("input"),Input(X->Input,D)); return R; }
        if(Cast<UMaterialExpressionWorldPosition>(E)) return Node(TEXT("world_position"));
        if(auto* X=Cast<UMaterialExpressionNormalize>(E)) { Obj R=Node(TEXT("normalize")); R->SetObjectField(TEXT("input"),Input(X->VectorInput,D)); return R; }
        if(auto* X=Cast<UMaterialExpressionAbs>(E)) { Obj R=Node(TEXT("abs")); R->SetObjectField(TEXT("input"),Input(X->Input,D)); return R; }
        if(auto* X=Cast<UMaterialExpressionSaturate>(E)) { Obj R=Node(TEXT("clamp")); R->SetObjectField(TEXT("input"),Input(X->Input,D)); R->SetObjectField(TEXT("min"),Constant({0})); R->SetObjectField(TEXT("max"),Constant({1})); return R; }
        if(auto* X=Cast<UMaterialExpressionAppendVector>(E)) return Bin(TEXT("append"),Input(X->A,D),Input(X->B,D));
        if(auto* X=Cast<UMaterialExpressionDotProduct>(E)) return Bin(TEXT("dot"),Input(X->A,D),Input(X->B,D));
        if(auto* X=Cast<UMaterialExpressionDistance>(E)) return Bin(TEXT("distance"),Input(X->A,D),Input(X->B,D));
        if(auto* X=Cast<UMaterialExpressionCrossProduct>(E)) return Bin(TEXT("cross"),Input(X->A,D),Input(X->B,D));
        if(auto* X=Cast<UMaterialExpressionSine>(E))
        { Obj R=Node(TEXT("sin")); R->SetObjectField(TEXT("input"),Input(X->Input,D)); R->SetNumberField(TEXT("frequency"),X->Period>0?2.0*UE_PI/X->Period:1.0); return R; }
        if(auto* X=Cast<UMaterialExpressionCosine>(E))
        {
            if(X->Period<=0) return Bad(TEXT("Cosine requires a positive period"));
            Obj R=Node(TEXT("cos")); R->SetObjectField(TEXT("input"),Input(X->Input,D)); R->SetNumberField(TEXT("frequency"),2.0*UE_PI/X->Period); return R;
        }
        if(auto* X=Cast<UMaterialExpressionFresnel>(E))
        {
            if(X->Normal.Expression) return Bad(TEXT("Fresnel with an explicit world-space normal requires additional translation"));
            Obj R=Node(TEXT("fresnel"));
            R->SetObjectField(TEXT("exponent"),Or(X->ExponentIn,X->Exponent,D));
            R->SetObjectField(TEXT("base"),Or(X->BaseReflectFractionIn,X->BaseReflectFraction,D)); return R;
        }
        if(auto* X=Cast<UMaterialExpressionConstantBiasScale>(E)) return Bin(TEXT("multiply"),Bin(TEXT("add"),Input(X->Input,D),Constant({X->Bias})),Constant({X->Scale}));
        if(auto* X=Cast<UMaterialExpressionClamp>(E))
        {
            Obj R=Node(TEXT("clamp")); R->SetObjectField(TEXT("input"),Input(X->Input,D));
            R->SetObjectField(TEXT("min"),Or(X->Min,X->ClampMode==CMODE_ClampMax?-1.e20f:X->MinDefault,D));
            R->SetObjectField(TEXT("max"),Or(X->Max,X->ClampMode==CMODE_ClampMin?1.e20f:X->MaxDefault,D)); return R;
        }
        if(auto* X=Cast<UMaterialExpressionDesaturation>(E))
        {
            Obj R=Node(TEXT("desaturate")); R->SetObjectField(TEXT("input"),Input(X->Input,D)); R->SetObjectField(TEXT("fraction"),Or(X->Fraction,1,D));
            R->SetArrayField(TEXT("weights"),Vec({X->LuminanceFactors.R,X->LuminanceFactors.G,X->LuminanceFactors.B})); return R;
        }
        if(auto* X=Cast<UMaterialExpressionRotateAboutAxis>(E))
        {
            Obj R=Node(TEXT("rotate_about_axis")); R->SetObjectField(TEXT("axis"),Input(X->NormalizedRotationAxis,D)); R->SetObjectField(TEXT("angle"),Input(X->RotationAngle,D)); R->SetObjectField(TEXT("pivot"),Input(X->PivotPoint,D)); R->SetObjectField(TEXT("position"),Input(X->Position,D)); R->SetNumberField(TEXT("period"),X->Period); return R;
        }
        if(auto* X=Cast<UMaterialExpressionScalarParameter>(E)) { float F=X->DefaultValue; Material->GetScalarParameterValue(FMaterialParameterInfo(X->ParameterName),F); Obj R=Constant({F}); R->SetStringField(TEXT("parameter"),X->ParameterName.ToString()); return R; }
        if(auto* X=Cast<UMaterialExpressionVectorParameter>(E)) { FLinearColor C=X->DefaultValue; Material->GetVectorParameterValue(FMaterialParameterInfo(X->ParameterName),C); Obj R=Constant({C.R,C.G,C.B,C.A}); R->SetStringField(TEXT("parameter"),X->ParameterName.ToString()); return R; }
        if(auto* X=Cast<UMaterialExpressionConstant>(E)) return Constant({X->R});
        if(auto* X=Cast<UMaterialExpressionConstant2Vector>(E)) return Constant({X->R,X->G});
        if(auto* X=Cast<UMaterialExpressionConstant3Vector>(E)) return Constant({X->Constant.R,X->Constant.G,X->Constant.B});
        if(auto* X=Cast<UMaterialExpressionConstant4Vector>(E)) return Constant({X->Constant.R,X->Constant.G,X->Constant.B,X->Constant.A});
        if(auto* X=Cast<UMaterialExpressionStaticSwitchParameter>(E))
        { bool B=X->DefaultValue; FGuid Guid; Material->GetStaticSwitchParameterValue(FMaterialParameterInfo(X->ParameterName),B,Guid); return Input(B?X->A:X->B,D); }
        if(auto* X=Cast<UMaterialExpressionStaticBoolParameter>(E))
        { bool B=X->DefaultValue; FGuid Guid; Material->GetStaticSwitchParameterValue(FMaterialParameterInfo(X->ParameterName),B,Guid); return Constant({B?1.0:0.0}); }
        if(auto* X=Cast<UMaterialExpressionStaticBool>(E)) return Constant({X->Value?1.0:0.0});
        if(auto* X=Cast<UMaterialExpressionStaticSwitch>(E))
        {
            bool B=X->DefaultValue;
            if(X->Value.Expression)
            {
                Obj Value=Input(X->Value,D); const Arr* Values=nullptr;
                if(Value->GetStringField(TEXT("op"))==TEXT("mask"))
                {
                    const Arr& Channels=Value->GetArrayField(TEXT("channels"));
                    if(Channels.Num()==1 && Channels[0]->AsNumber()==0) Value=Value->GetObjectField(TEXT("input"));
                }
                if(Value->GetStringField(TEXT("op"))!=TEXT("constant") || !Value->TryGetArrayField(TEXT("value"),Values) || Values->Num()!=1)
                    return Bad(TEXT("StaticSwitch requires a resolved scalar static-bool input at ")+X->GetPathName());
                B=(*Values)[0]->AsNumber()!=0;
            }
            return Input(B?X->A:X->B,D);
        }
        if(auto* X=Cast<UMaterialExpressionRayTracingQualitySwitch>(E))
        {
            // UE uses the Normal input for the main visible surface. Its
            // RayTraced input is often a cheaper secondary-ray approximation.
            Export.Note(Material->GetPathName()+TEXT(": RayTracingQualitySwitch resolved to Normal for the visible Unreal surface; secondary-ray simplification is not reproduced"));
            return Input(X->Normal,D);
        }
        if(auto* X=Cast<UMaterialExpressionCollectionParameter>(E))
        {
            if(!X->Collection) return Bad(TEXT("Missing material parameter collection at ")+X->GetPathName());
            FName Parameter=X->ParameterName;
            if(Parameter.IsNone()) Parameter=X->Collection->GetParameterName(X->ParameterId);
            bool Found=false; float Scalar=X->Collection->GetScalarParameterDefaultValue(Parameter,Found);
            UWorld* World=GEditor?GEditor->GetEditorWorldContext().World():nullptr;
            auto* Instance=World?World->GetParameterCollectionInstance(X->Collection):nullptr;
            Obj R;
            if(Found)
            {
                if(Instance) Instance->GetScalarParameterValue(Parameter,Scalar);
                R=Constant({Scalar});
            }
            else
            {
                FLinearColor Vector=X->Collection->GetVectorParameterDefaultValue(Parameter,Found);
                if(!Found) return Bad(TEXT("Unknown material collection parameter: ")+Parameter.ToString());
                if(Instance) Instance->GetVectorParameterValue(Parameter,Vector);
                R=Constant({Vector.R,Vector.G,Vector.B,Vector.A});
            }
            R->SetStringField(TEXT("parameter"),X->Collection->GetPathName()+TEXT("::")+Parameter.ToString());
            R->SetStringField(TEXT("parameter_label"),X->Collection->GetName()+TEXT(".")+Parameter.ToString());
            Export.Note(Material->GetPathName()+TEXT(": material collection ")+X->Collection->GetName()+TEXT(".")+Parameter.ToString()+TEXT(" captured from editor world/defaults; runtime Blueprint changes are not exported"));
            return R;
        }
        if(auto* X=Cast<UMaterialExpressionReroute>(E)) return Input(X->Input,D);
        if(auto* X=Cast<UMaterialExpressionMaterialFunctionCall>(E))
        {
            if(!X->FunctionOutputs.IsValidIndex(Output) || !X->FunctionOutputs[Output].ExpressionOutput) return Bad(TEXT("Missing function output"));
            const auto Previous=FunctionScope;
            FunctionScope=MakeShared<FFunctionScope>();FunctionScope->Parent=Previous;
            for(const auto& I:X->FunctionInputs) if(I.ExpressionInput && I.Input.Expression) FunctionScope->Inputs.Add(I.ExpressionInput,I.Input);
            Obj R=Input(X->FunctionOutputs[Output].ExpressionOutput->A,D);
            FunctionScope=Previous; return R;
        }
        if(auto* X=Cast<UMaterialExpressionFunctionInput>(E))
        {
            for(auto Scope=FunctionScope;Scope;Scope=Scope->Parent)
                if(const FExpressionInput* Found=Scope->Inputs.Find(X))
                {
                    const TPair<UMaterialExpressionFunctionInput*,EMaterialProperty> Key(X,Property);
                    if(const Obj* Cached=Scope->Resolved.Find(Key)) return *Cached;
                    const auto Previous=FunctionScope;FunctionScope=Scope->Parent;
                    Obj R=Input(*Found,D);FunctionScope=Previous;Scope->Resolved.Add(Key,R);return R;
                }
            if(X->bUsePreviewValueAsDefault)
            {
                if(X->Preview.Expression) return Input(X->Preview,D);
                if(X->InputType==FunctionInput_Scalar) return Constant({X->PreviewValue.X});
                if(X->InputType==FunctionInput_Vector2) return Constant({X->PreviewValue.X,X->PreviewValue.Y});
                if(X->InputType==FunctionInput_Vector3) return Constant({X->PreviewValue.X,X->PreviewValue.Y,X->PreviewValue.Z});
                if(X->InputType==FunctionInput_Vector4) return Constant({X->PreviewValue.X,X->PreviewValue.Y,X->PreviewValue.Z,X->PreviewValue.W});
                if(X->InputType==FunctionInput_StaticBool) return Constant({X->PreviewValue.X!=0?1.0:0.0});
                if(X->InputType==FunctionInput_MaterialAttributes) return Property==MP_EmissiveColor?Constant({X->PreviewValue.X,X->PreviewValue.Y,X->PreviewValue.Z}):Default();
            }
            return Bad(TEXT("Unsupported or missing function input: ")+X->InputName.ToString());
        }
        if(auto* X=Cast<UMaterialExpressionTextureCoordinate>(E))
        {
            if(X->UnMirrorU || X->UnMirrorV) return Bad(TEXT("Unmirror UVs require a richer shader backend"));
            Obj R=Node(TEXT("uv")); R->SetNumberField(TEXT("channel"),X->CoordinateIndex); R->SetArrayField(TEXT("scale"),Vec({X->UTiling,X->VTiling})); return R;
        }
        if(auto* X=Cast<UMaterialExpressionLandscapeLayerCoords>(E))
        {
            if(X->CustomUVType!=LCCT_None || X->MappingRotation!=0 || (X->MappingType!=TCMT_Auto && X->MappingType!=TCMT_XY)) return Bad(TEXT("Landscape coordinates currently require XY mapping without rotation/custom UVs"));
            Obj UV=Node(TEXT("uv")); const float Scale=X->MappingScale==0?1:1/X->MappingScale; UV->SetArrayField(TEXT("scale"),Vec({Scale,Scale}));
            Obj R=Node(TEXT("add")); R->SetObjectField(TEXT("a"),UV); R->SetObjectField(TEXT("b"),Constant({X->MappingPanU,X->MappingPanV})); return R;
        }
        if(auto* X=Cast<UMaterialExpressionTextureSample>(E))
        {
            UTexture* Texture=X->Texture;
            if(auto* P=Cast<UMaterialExpressionTextureSampleParameter>(X)) Material->GetTextureParameterValue(FMaterialParameterInfo(P->ParameterName),Texture);
            if(X->TextureObject.Expression)
            {
                Obj Resource=Input(X->TextureObject,D);FString Source;
                if(Resource->GetStringField(TEXT("op"))!=TEXT("texture_object") || !Resource->TryGetStringField(TEXT("source"),Source)) return Bad(TEXT("TextureObject input could not resolve its source"));
                Texture=LoadObject<UTexture>(nullptr,*Source);
            }
            const FString Key=Export.Texture(Texture); if(Key.IsEmpty()) return Bad(TEXT("Texture source could not be exported"));
            const bool Normal=X->SamplerType==SAMPLERTYPE_Normal || X->SamplerType==SAMPLERTYPE_VirtualNormal;
            if(Cast<UTextureCube>(Texture))
            {
                if(X->MipValueMode!=TMVM_None) return Bad(TEXT("Explicit texture mip/derivative control is unsupported"));
                if(Normal) return Bad(TEXT("Cubemap normal decoding requires a world-space normal backend"));
                if(!X->Coordinates.Expression) return Bad(TEXT("Cubemap sample requires a connected UVW direction"));
                Obj R=Node(TEXT("texture"));R->SetStringField(TEXT("texture"),Key);
                R->SetStringField(TEXT("texture_dimension"),TEXT("cube_longlat"));
                R->SetObjectField(TEXT("direction"),Input(X->Coordinates,D));
                R->SetStringField(TEXT("color_space"),Export.Textures->GetObjectField(Key)->GetBoolField(TEXT("srgb"))?TEXT("sRGB"):TEXT("raw"));
                return R;
            }
            auto* T=CastChecked<UTexture2D>(Texture);
            Obj R=Node(TEXT("texture")); R->SetStringField(TEXT("texture"),Key);
            // Keep the actual map/instance override even when its renderer-only
            // mip selection cannot be translated. The basic surface fallback
            // uses automatic filtering and reports the omitted effect.
            if(X->MipValueMode!=TMVM_None) R->SetStringField(TEXT("sampling_issue"),TEXT("Explicit texture mip/derivative control is unsupported"));
            R->SetNumberField(TEXT("source_uv_channel"),X->ConstCoordinate);
            Obj UV=Node(TEXT("uv")); UV->SetNumberField(TEXT("channel"),X->ConstCoordinate);
            R->SetObjectField(TEXT("uv"),X->Coordinates.Expression?Input(X->Coordinates,D):UV);
            R->SetBoolField(TEXT("normal_map"),Normal); R->SetBoolField(TEXT("flip_green"),T->bFlipGreenChannel);
            R->SetStringField(TEXT("color_space"),Export.Textures->GetObjectField(Key)->GetBoolField(TEXT("srgb")) && !Normal?TEXT("sRGB"):TEXT("raw"));
            auto Wrap=[](TextureAddress W) { return W==TA_Clamp?TEXT("clamp"):W==TA_Mirror?TEXT("mirror"):TEXT("repeat"); };
            R->SetStringField(TEXT("wrap_s"),X->SamplerSource==SSM_Wrap_WorldGroupSettings?TEXT("repeat"):X->SamplerSource==SSM_Clamp_WorldGroupSettings?TEXT("clamp"):Wrap(T->AddressX));
            R->SetStringField(TEXT("wrap_t"),X->SamplerSource==SSM_Wrap_WorldGroupSettings?TEXT("repeat"):X->SamplerSource==SSM_Clamp_WorldGroupSettings?TEXT("clamp"):Wrap(T->AddressY));
            // Output masks on FExpressionInput select RGB/R/G/B/A. Keep RGBA here.
            return R;
        }
        if(auto* X=Cast<UMaterialExpressionMultiply>(E)) return Binary(TEXT("multiply"),X->A,X->ConstA,X->B,X->ConstB,D);
        if(auto* X=Cast<UMaterialExpressionAdd>(E)) return Binary(TEXT("add"),X->A,X->ConstA,X->B,X->ConstB,D);
        if(auto* X=Cast<UMaterialExpressionSubtract>(E)) return Binary(TEXT("subtract"),X->A,X->ConstA,X->B,X->ConstB,D);
        if(auto* X=Cast<UMaterialExpressionDivide>(E)) return Binary(TEXT("divide"),X->A,X->ConstA,X->B,X->ConstB,D);
        if(auto* X=Cast<UMaterialExpressionFmod>(E)) return Bin(TEXT("fmod"),Input(X->A,D),Input(X->B,D));
        if(auto* X=Cast<UMaterialExpressionOneMinus>(E)) { Obj R=Node(TEXT("one_minus")); R->SetObjectField(TEXT("input"),Input(X->Input,D)); return R; }
        if(auto* X=Cast<UMaterialExpressionComponentMask>(E))
        {
            Obj R=Node(TEXT("mask")); Arr C; if(X->R) C.Add(N(0)); if(X->G) C.Add(N(1)); if(X->B) C.Add(N(2)); if(X->A) C.Add(N(3));
            R->SetArrayField(TEXT("channels"),C); R->SetObjectField(TEXT("input"),Input(X->Input,D)); return R;
        }
        if(auto* X=Cast<UMaterialExpressionLinearInterpolate>(E))
        { Obj R=Binary(TEXT("lerp"),X->A,X->ConstA,X->B,X->ConstB,D); R->SetObjectField(TEXT("alpha"),Or(X->Alpha,X->ConstAlpha,D)); return R; }
        if(auto* X=Cast<UMaterialExpressionPower>(E)) return Binary(TEXT("power"),X->Base,0,X->Exponent,X->ConstExponent,D);
        Obj Unsupported=Bad(E->GetClass()->GetName()+TEXT(" at ")+E->GetPathName());
        // Unknown-node diagnostics must stay shallow. Recursively lowering
        // every hidden input can expand a shared graph exponentially, even
        // with a depth limit. Preserve pin identity, not another graph tree.
        Arr Pins;
        TSet<const FExpressionInput*> SeenPins;
        for(int32 PinIndex=0;PinIndex<32;++PinIndex)
        {
            const FExpressionInput* Pin=E->GetInput(PinIndex);if(!Pin) break;
            if(SeenPins.Contains(Pin)) break;
            SeenPins.Add(Pin);
            Obj Diagnostic=Object();Diagnostic->SetNumberField(TEXT("index"),PinIndex);
            Diagnostic->SetStringField(TEXT("name"),E->GetInputName(PinIndex).ToString());
            Diagnostic->SetBoolField(TEXT("connected"),Pin->Expression!=nullptr);
            if(Pin->Expression)
            {
                Diagnostic->SetStringField(TEXT("source_path"),Pin->Expression->GetPathName());
                Diagnostic->SetStringField(TEXT("source_class"),Pin->Expression->GetClass()->GetName());
                Diagnostic->SetNumberField(TEXT("output_index"),Pin->OutputIndex);
            }
            Pins.Add(MakeShared<FJsonValueObject>(Diagnostic));
        }
        if(!Pins.IsEmpty()) Unsupported->SetArrayField(TEXT("diagnostic_inputs"),Pins);
        return Unsupported;
    }
};

FString FExport::Material(UMaterialInterface* MI, ULandscapeComponent* Landscape)
{
    if(!MI) { Issue(TEXT("A material slot is empty")); return FString(); }
    FString Context;
    if(Landscape && Landscape->GetLandscapeInfo() && Landscape->GetLandscapeInfo()->LandscapeActor.IsValid())
        Context=Landscape->GetLandscapeInfo()->LandscapeActor->GetPathName();
    FString Key=Id(MI->GetPathName()+Context); if(Materials->HasField(Key)) return Key;
    Obj J=Object(), Inputs=Object(); Arr Problems;
    UMaterial* M=MI->GetMaterial(); FGraph Graph{*this,MI,{},Landscape};
    const bool IsDecal=M->MaterialDomain==MD_DeferredDecal;
    J->SetStringField(TEXT("domain"),IsDecal?TEXT("decal"):TEXT("surface"));
    J->SetNumberField(TEXT("decal_response"),M->GetMaterialDecalResponse());
    bool WaterSurface=!IsDecal && MI->GetShadingModels().HasShadingModel(MSM_SingleLayerWater);
    if(!IsDecal && MI->GetBlendMode()==BLEND_Translucent)
    {
        FString Tokens=MI->GetPathName();Tokens.ReplaceInline(TEXT("_"),TEXT("/"));Tokens.ReplaceInline(TEXT("."),TEXT("/"));
        TArray<FString> Parts;Tokens.ParseIntoArray(Parts,TEXT("/"),true);
        for(const FString& Part:Parts) if(Part.Equals(TEXT("water"),ESearchCase::IgnoreCase)) WaterSurface=true;
    }
    J->SetBoolField(TEXT("water_surface"),WaterSurface);
    if(WaterSurface)
    {
        J->SetStringField(TEXT("source"),MI->GetPathName());J->SetStringField(TEXT("name"),MI->GetName());
        J->SetBoolField(TEXT("two_sided"),MI->IsTwoSided());J->SetBoolField(TEXT("translucent"),true);
        J->SetObjectField(TEXT("inputs"),Inputs);J->SetArrayField(TEXT("issues"),{});
        Note(MI->GetPathName()+TEXT(": water material extraction excluded by user policy; geometry retained for manual material assignment"));
        Materials->SetObjectField(Key,J);return Key;
    }
    auto Problem=[&](const FString& P) { Problems.Add(S(P)); };
    const bool Foliage=MI->GetShadingModels().HasOnlyShadingModel(MSM_TwoSidedFoliage);
    const bool Unlit=MI->GetShadingModels().HasOnlyShadingModel(MSM_Unlit);
    if(!MI->GetShadingModels().HasOnlyShadingModel(MSM_DefaultLit) && !Foliage && !Unlit && !IsDecal) Problem(TEXT("Unsupported Unreal shading model"));
    if(M->MaterialDomain!=MD_Surface && !IsDecal) Problem(TEXT("Unsupported Unreal material domain"));
    if(Foliage) Note(MI->GetPathName()+TEXT(": foliage uses opaque PBR/cutout shading without subsurface or transmission"));
    J->SetBoolField(TEXT("foliage"),Foliage);
    J->SetBoolField(TEXT("unlit"),Unlit);
    J->SetStringField(TEXT("normal_space"),M->bTangentSpaceNormal?TEXT("tangent"):TEXT("world"));
    if(MI->GetBlendMode()!=BLEND_Opaque && MI->GetBlendMode()!=BLEND_Masked && MI->GetBlendMode()!=BLEND_Translucent) Problem(TEXT("Unsupported Unreal blend mode"));
    J->SetBoolField(TEXT("translucent"),MI->GetBlendMode()==BLEND_Translucent);
    auto Scalar=[&](const TCHAR* Name, EMaterialProperty Prop,float Fallback)
    {
        Graph.Property=Prop;
        if(M->bUseMaterialAttributes) { Inputs->SetObjectField(Name,Graph.Input(*M->GetExpressionInputForProperty(MP_MaterialAttributes))); return; }
        auto* I=static_cast<FScalarMaterialInput*>(M->GetExpressionInputForProperty(Prop));
        Inputs->SetObjectField(Name,I && I->Expression?Graph.Input(*I):Constant({I && I->UseConstant?I->Constant:Fallback}));
    };
    auto Color=[&](const TCHAR* Name, EMaterialProperty Prop)
    {
        Graph.Property=Prop;
        if(M->bUseMaterialAttributes) { Inputs->SetObjectField(Name,Graph.Input(*M->GetExpressionInputForProperty(MP_MaterialAttributes))); return; }
        auto* I=static_cast<FColorMaterialInput*>(M->GetExpressionInputForProperty(Prop));
        const FLinearColor C=I && I->UseConstant?I->Constant:FLinearColor::Black;
        Inputs->SetObjectField(Name,I && I->Expression?Graph.Input(*I):Constant({C.R,C.G,C.B}));
    };
    Color(TEXT("base_color"),MP_BaseColor);
    // Resolve instance overrides and Material Attributes using the same graph
    // traversal as base color. Preserve HDR values and source texture sampling.
    Color(TEXT("emissive"),MP_EmissiveColor);
    Scalar(TEXT("roughness"),MP_Roughness,0.5f); Scalar(TEXT("metallic"),MP_Metallic,0);
    // Specular is independent of Metallic in Unreal; do not infer it from
    // texture filenames or discard its material-instance overrides.
    if(!Unlit) Scalar(TEXT("specular"),MP_Specular,0.5f);
    if(MI->GetBlendMode()==BLEND_Masked) { Scalar(TEXT("opacity"),MP_OpacityMask,1); J->SetNumberField(TEXT("opacity_threshold"),MI->GetOpacityMaskClipValue()); }
    if(MI->GetBlendMode()==BLEND_Translucent) { Scalar(TEXT("opacity"),MP_Opacity,1); if(!IsDecal) Note(MI->GetPathName()+TEXT(": opacity is transferred as PBR cutout coverage; Unreal refraction/translucency is not reproduced")); }
    if(IsDecal)
    {
        Arr Channels;
        for(const auto& Pair:TArray<TPair<FString,EMaterialProperty>>{{TEXT("base_color"),MP_BaseColor},{TEXT("normal"),MP_Normal},{TEXT("roughness"),MP_Roughness},{TEXT("metallic"),MP_Metallic},{TEXT("specular"),MP_Specular},{TEXT("emissive"),MP_EmissiveColor}})
            if(M->bUseMaterialAttributes || (M->GetExpressionInputForProperty(Pair.Value) && M->GetExpressionInputForProperty(Pair.Value)->Expression)) Channels.Add(S(Pair.Key));
        J->SetArrayField(TEXT("decal_channels"),Channels);
        if(MI->GetBlendMode()!=BLEND_Translucent) Problem(TEXT("Only translucent/DBuffer alpha-blended decals are supported; additive, modulate and alpha-composite decals need separate blend handling"));
    }
    auto* Normal=M->GetExpressionInputForProperty(MP_Normal);
    Graph.Property=MP_Normal;
    if(M->bUseMaterialAttributes) Inputs->SetObjectField(TEXT("normal"),Graph.Input(*M->GetExpressionInputForProperty(MP_MaterialAttributes)));
    else if(Normal && Normal->Expression) Inputs->SetObjectField(TEXT("normal"),Graph.Input(*Normal));
    if(auto* I=M->GetExpressionInputForProperty(MP_WorldPositionOffset); I && I->Expression) Note(MI->GetPathName()+TEXT(": world-position offset / foliage wind is frozen at the undeformed rest pose"));
    if(auto* I=M->GetExpressionInputForProperty(MP_PixelDepthOffset); I && I->Expression)
    {
        Graph.Property=MP_PixelDepthOffset;
        J->SetObjectField(TEXT("pixel_depth_offset"),Graph.Input(*I));
        Problem(TEXT("Connected Pixel Depth Offset is unsupported unless the captured value is provably zero"));
    }
    for(EMaterialProperty Prop:{MP_CustomizedUVs0,MP_CustomizedUVs1,MP_CustomizedUVs2,MP_CustomizedUVs3,MP_CustomizedUVs4,MP_CustomizedUVs5,MP_CustomizedUVs6,MP_CustomizedUVs7})
        if(auto* I=M->GetExpressionInputForProperty(Prop); I && I->Expression) Problem(FString::Printf(TEXT("Connected vertex/displacement/custom-UV property %d is unsupported"),(int32)Prop));
    J->SetStringField(TEXT("source"),MI->GetPathName()); J->SetStringField(TEXT("name"),MI->GetName());
    J->SetBoolField(TEXT("two_sided"),MI->IsTwoSided()); J->SetObjectField(TEXT("inputs"),Inputs); J->SetArrayField(TEXT("issues"),Problems);
    Materials->SetObjectField(Key,J); return Key;
}

void FExport::Landscape(ALandscapeProxy* P)
{
    ULandscapeInfo* Info=P->GetLandscapeInfo(); FIntRect Extent;
    if(!Info || !Info->GetLandscapeExtent(Extent)) { Issue(P->GetPathName()+TEXT(": landscape extent unavailable")); return; }
    if(ExportedLandscapes.Contains(Info)) return;
    ExportedLandscapes.Add(Info);
    ALandscape* Actor=Info->LandscapeActor.Get();
    if(!Actor) { Issue(P->GetPathName()+TEXT(": main landscape actor must be loaded")); return; }
    TArray<ULandscapeComponent*> LandscapeComponents;
    for(const auto& Pair:Info->XYtoComponentMap)
        if(Pair.Value)
        {
            if(ExcludeHidden && HiddenComponent(Pair.Value)) {++HiddenComponents;continue;}
            LandscapeComponents.Add(Pair.Value);
        }
    LandscapeComponents.Sort([](const ULandscapeComponent& A,const ULandscapeComponent& B)
    { const auto X=A.GetSectionBase(),Y=B.GetSectionBase(); return X.Y==Y.Y?X.X<Y.X:X.Y<Y.Y; });
    if(LandscapeComponents.IsEmpty()) return;
    Arr Points,Normals,Indices,UVs,Sections,Sources; TArray<Arr> Channels; Channels.SetNum(2);
    TMap<FLandscapeVertex,int32> Vertices;
    UMaterialInterface* SharedMaterial=LandscapeComponents[0]->GetLandscapeMaterial(); bool DifferentMaterials=false;
    for(ULandscapeComponent* C:LandscapeComponents)
    {
        DifferentMaterials|=C->GetLandscapeMaterial()!=SharedMaterial;
        FMeshDescription D; FStaticMeshAttributes Attributes(D); Attributes.Register();
        ALandscapeProxy::FRawMeshExportParams Params;
        Params.ExportLOD=0;
        Params.UVConfiguration.ExportUVMappingTypes={ALandscapeProxy::FRawMeshExportParams::EUVMappingType::TerrainCoordMapping_XY,ALandscapeProxy::FRawMeshExportParams::EUVMappingType::WeightmapUV};
        TArray<ULandscapeComponent*> Components{C}; Params.ComponentsToExport=MakeArrayView(Components);
        if(!C->GetLandscapeProxy()->ExportToRawMesh(Params,D)) { Issue(C->GetPathName()+TEXT(": landscape geometry export failed; unified landscape omitted")); return; }
        const auto Pos=Attributes.GetVertexPositions(); const auto Norm=Attributes.GetVertexInstanceNormals(); const auto UV=Attributes.GetVertexInstanceUVs();
        Sources.Add(S(C->GetPathName()));
        for(auto T:D.Triangles().GetElementIDs())
        {
            for(auto VI:D.GetTriangleVertexInstances(T))
            {
                const auto X=Pos[D.GetVertexInstanceVertex(VI)]; const auto Z=Norm[VI];
                const auto Grid=UV.Get(VI,0); const FLandscapeVertex Vertex{X,Z,Grid};
                if(const int32* Existing=Vertices.Find(Vertex)) { Indices.Add(N(*Existing)); continue; }
                const int32 Index=Points.Num(); Vertices.Add(Vertex,Index); Indices.Add(N(Index));
                Points.Add(A(Vec({X.X,X.Y,X.Z}))); Normals.Add(A(Vec({Z.X,Z.Y,Z.Z})));
                Channels[0].Add(A(Vec({Grid.X,Grid.Y})));
                Channels[1].Add(A(Vec({(double(Grid.X)-Extent.Min.X+0.5)/(Extent.Width()+1),
                                      (double(Grid.Y)-Extent.Min.Y+0.5)/(Extent.Height()+1)})));
            }
        }
    }
    for(const Arr& Channel:Channels) UVs.Add(A(Channel));
    Obj Section=Object(); Section->SetNumberField(TEXT("slot"),0); Section->SetNumberField(TEXT("first_face"),0); Section->SetNumberField(TEXT("face_count"),Indices.Num()/3); Sections.Add(V(Section));
    Obj J=Object(); J->SetStringField(TEXT("source"),Actor->GetPathName()); J->SetBoolField(TEXT("unified_landscape"),true); J->SetArrayField(TEXT("landscape_components"),Sources);
    J->SetArrayField(TEXT("points"),Points); J->SetArrayField(TEXT("normals"),Normals); J->SetArrayField(TEXT("indices"),Indices); J->SetArrayField(TEXT("uvs"),UVs); J->SetArrayField(TEXT("sections"),Sections);
    const FString Key=Id(Actor->GetPathName()),Relative=TEXT("meshes/")+Key+TEXT(".json");
    if(!Save(J,Out/Relative)) { Issue(TEXT("Could not save unified landscape mesh")); return; }
    Obj Ref=Object(); Ref->SetStringField(TEXT("file"),Relative); Meshes->SetObjectField(Key,Ref);
    const FString MaterialKey=Material(SharedMaterial,LandscapeComponents[0]);
    if(DifferentMaterials && Materials->HasField(MaterialKey))
    {
        Obj M=Materials->GetObjectField(MaterialKey); Arr Problems=M->GetArrayField(TEXT("issues"));
        Problems.Add(S(TEXT("Landscape components use different material overrides; a single landscape material cannot preserve those overrides"))); M->SetArrayField(TEXT("issues"),Problems);
    }
    Obj I=Object(); I->SetStringField(TEXT("name"),Actor->GetActorLabel()); I->SetStringField(TEXT("source"),Actor->GetPathName()); I->SetStringField(TEXT("mesh"),Key); I->SetArrayField(TEXT("matrix"),Matrix(FTransform::Identity)); I->SetArrayField(TEXT("materials"),{S(MaterialKey)}); Instances.Add(V(I));
    Note(FString::Printf(TEXT("%s: merged %d landscape components into one mesh and one material, retaining %d triangles"),*Actor->GetPathName(),LandscapeComponents.Num(),Indices.Num()/3));
}
}

#include "BridgeSplineFixture.h"
#include "BridgeVisibilityFixture.h"

UUnrealUsdExtractCommandlet::UUnrealUsdExtractCommandlet()
{ IsClient=false; IsServer=false; IsEditor=true; LogToConsole=true; ShowErrorCount=true; }

int32 BridgeEditor::Extract(const FString& Params, TFunction<bool(float,const FString&)> Progress)
{
    using namespace Bridge;
    UE_LOG(LogTemp,Display,TEXT("BRIDGE_EXTRACTOR_VERSION: 0.6.6"));
    UE_LOG(LogTemp,Display,TEXT("BRIDGE_EXTRACTOR_PATCH: bounded-diagnostics-streamed-utf8"));
    FString Map,Out,Asset;
    const bool Current=FParse::Param(*Params,TEXT("BridgeCurrentWorld"));
    const bool Selected=FParse::Param(*Params,TEXT("BridgeSelected"));
    const bool IncludeDecals=!FParse::Param(*Params,TEXT("BridgeNoDecals"));
    UStaticMesh* FixtureSource=nullptr;
    int32 FixtureTriangles=0;
    bool FixtureDirty=false;
    Obj VisibilitySnapshot;
    FString VisibilitySnapshotPath;
    if(FParse::Value(*Params,TEXT("BridgeHiddenSnapshot="),VisibilitySnapshotPath))
    {
        FString Text;
        if(!FFileHelper::LoadFileToString(Text,*VisibilitySnapshotPath) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),VisibilitySnapshot) || !VisibilitySnapshot)
        {UE_LOG(LogTemp,Error,TEXT("Cannot read headless visibility snapshot %s"),*VisibilitySnapshotPath);return 1;}
    }
    auto Configure=[&](FExport& E)
    {
        E.Optimize=FParse::Param(*Params,TEXT("BridgeOptimize"));
        E.ExcludeHidden=FParse::Param(*Params,TEXT("BridgeExcludeHidden"));
        if(E.ExcludeHidden) E.LoadHiddenSnapshot(VisibilitySnapshot);
        FParse::Value(*Params,TEXT("BridgeThreshold="),E.Threshold);
        FParse::Value(*Params,TEXT("BridgeTarget="),E.Target);
        FParse::Value(*Params,TEXT("BridgeLOD="),E.PreferredLOD);
        FParse::Value(*Params,TEXT("BridgeMaxError="),E.MaxError);
        E.Threshold=FMath::Max(100,E.Threshold); E.Target=FMath::Clamp(E.Target,4,E.Threshold);
        E.PreferredLOD=FMath::Max(0,E.PreferredLOD);
        if(!FMath::IsFinite(E.MaxError) || E.MaxError<=0) E.MaxError=1.0f;
    };
    const bool Fixture=FParse::Param(*Params,TEXT("BridgeTestLandscape"));
    const bool FoliageFixture=FParse::Param(*Params,TEXT("BridgeTestFoliage"));
    const bool DecalFixture=FParse::Param(*Params,TEXT("BridgeTestDecals"));
    const bool SkeletalFixture=FParse::Param(*Params,TEXT("BridgeTestSkeletal"));
    const bool MaterialFixture=FParse::Param(*Params,TEXT("BridgeTestMaterials"));
    const bool EditorFixture=FParse::Param(*Params,TEXT("BridgeTestEditor"));
    const bool SplineFixture=FParse::Param(*Params,TEXT("BridgeTestSplines"));
    const bool VisibilityFixture=FParse::Param(*Params,TEXT("BridgeTestVisibility"));
    const bool ExportSkeletalMeshes=FParse::Param(*Params,TEXT("BridgeExportSkeletalMeshes"));
    const bool FoliageOnly=FParse::Param(*Params,TEXT("BridgeFoliageOnly"));
    const bool LandscapeOnly=FParse::Param(*Params,TEXT("BridgeLandscapeOnly"));
    FParse::Value(*Params,TEXT("BridgeMap="),Map); FParse::Value(*Params,TEXT("BridgeAsset="),Asset);
    if((Map.IsEmpty() && Asset.IsEmpty() && !Current && !Fixture && !FoliageFixture && !DecalFixture && !SkeletalFixture && !MaterialFixture && !EditorFixture && !SplineFixture && !VisibilityFixture) || !FParse::Value(*Params,TEXT("BridgeOut="),Out))
    { UE_LOG(LogTemp,Error,TEXT("BridgeMap or BridgeAsset, and BridgeOut are required")); return 1; }
    IFileManager::Get().MakeDirectory(*(Out/TEXT("textures")),true); IFileManager::Get().MakeDirectory(*(Out/TEXT("meshes")),true);
    FOutputDeviceFile ExtractionLog(*(Out/TEXT("unreal-extraction.log")),true,false);
    GLog->AddOutputDevice(&ExtractionLog);
    ON_SCOPE_EXIT { GLog->RemoveOutputDevice(&ExtractionLog); };
    if(MaterialFixture)
    {
        UWorld* TestWorld=GEditor->NewMap(); FExport E; E.Out=Out;
        auto Scalar=[](UMaterial* M,float V) { auto* X=NewObject<UMaterialExpressionConstant>(M);X->R=V;M->GetExpressionCollection().AddExpression(X);return X; };
        auto Emit=[&](UMaterial* M,UMaterialExpression* X) { M->GetExpressionCollection().AddExpression(X);M->GetExpressionInputForProperty(MP_Roughness)->Connect(0,X);E.Material(M); };
        UMaterial* Mod=NewObject<UMaterial>(GetTransientPackage(),TEXT("SignedRemainder"));
        auto* ModNode=NewObject<UMaterialExpressionFmod>(Mod);ModNode->A.Connect(0,Scalar(Mod,-3.25));ModNode->B.Connect(0,Scalar(Mod,-2));Emit(Mod,ModNode);
        auto* CeilMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("SignedCeiling"));
        auto* Ceil=NewObject<UMaterialExpressionCeil>(CeilMaterial);Ceil->Input.Connect(0,Scalar(CeilMaterial,-2.5));Emit(CeilMaterial,Ceil);
        auto* FloorMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("SignedFloor"));
        auto* Floor=NewObject<UMaterialExpressionFloor>(FloorMaterial);Floor->Input.Connect(0,Scalar(FloorMaterial,-2.5));Emit(FloorMaterial,Floor);
        UMaterial* Default=NewObject<UMaterial>(GetTransientPackage(),TEXT("DefaultSwitch"));
        auto* DefaultSwitch=NewObject<UMaterialExpressionStaticSwitch>(Default);DefaultSwitch->DefaultValue=false;DefaultSwitch->B.Connect(0,Scalar(Default,0.3));Emit(Default,DefaultSwitch);
        UMaterial* Bool=NewObject<UMaterial>(GetTransientPackage(),TEXT("ConnectedSwitch"));
        auto* BoolNode=NewObject<UMaterialExpressionStaticBool>(Bool);BoolNode->Value=true;Bool->GetExpressionCollection().AddExpression(BoolNode);
        auto* BoolSwitch=NewObject<UMaterialExpressionStaticSwitch>(Bool);BoolSwitch->Value.Connect(0,BoolNode);BoolSwitch->A.Connect(0,Scalar(Bool,0.7));Emit(Bool,BoolSwitch);
        UMaterial* Preview=NewObject<UMaterial>(GetTransientPackage(),TEXT("FunctionBoolDefault"));
        auto* PreviewNode=NewObject<UMaterialExpressionFunctionInput>(Preview);PreviewNode->InputType=FunctionInput_StaticBool;PreviewNode->bUsePreviewValueAsDefault=true;PreviewNode->PreviewValue.X=1;Preview->GetExpressionCollection().AddExpression(PreviewNode);
        auto* PreviewSwitch=NewObject<UMaterialExpressionStaticSwitch>(Preview);PreviewSwitch->Value.Connect(0,PreviewNode);PreviewSwitch->A.Connect(0,Scalar(Preview,0.6));Emit(Preview,PreviewSwitch);
        UMaterial* Parent=NewObject<UMaterial>(GetTransientPackage(),TEXT("ParameterSwitch"));
        auto* Parameter=NewObject<UMaterialExpressionStaticBoolParameter>(Parent);Parameter->ParameterName=TEXT("ChooseA");Parameter->DefaultValue=true;Parent->GetExpressionCollection().AddExpression(Parameter);
        auto* ParameterSwitch=NewObject<UMaterialExpressionStaticSwitch>(Parent);ParameterSwitch->Value.Connect(0,Parameter);ParameterSwitch->A.Connect(0,Scalar(Parent,0.2));ParameterSwitch->B.Connect(0,Scalar(Parent,0.8));Emit(Parent,ParameterSwitch);
        auto* Instance=NewObject<UMaterialInstanceConstant>(GetTransientPackage(),TEXT("ParameterOverride"));Instance->SetParentEditorOnly(Parent,false);Instance->SetStaticSwitchParameterValueEditorOnly(FMaterialParameterInfo(TEXT("ChooseA")),false);E.Material(Instance);
        UMaterial* Quality=NewObject<UMaterial>(GetTransientPackage(),TEXT("VisibleQualityBranch"));
        auto* QualitySwitch=NewObject<UMaterialExpressionRayTracingQualitySwitch>(Quality);QualitySwitch->Normal.Connect(0,Scalar(Quality,0.4));Emit(Quality,QualitySwitch);
        auto* Collection=NewObject<UMaterialParameterCollection>(GetTransientPackage(),TEXT("FixtureCollection"));
        FCollectionScalarParameter S;S.ParameterName=TEXT("Roughness");S.DefaultValue=0.25;Collection->ScalarParameters.Add(S);
        FCollectionVectorParameter V;V.ParameterName=TEXT("Tint");V.DefaultValue=FLinearColor(0.2,0.3,0.4,1);Collection->VectorParameters.Add(V);
        TestWorld->AddParameterCollectionInstance(Collection,false);
        auto* CollectionInstance=TestWorld->GetParameterCollectionInstance(Collection);
        if(!CollectionInstance || !CollectionInstance->SetScalarParameterValue(TEXT("Roughness"),0.65) || !CollectionInstance->SetVectorParameterValue(TEXT("Tint"),FLinearColor(0.8,0.6,0.4,1))) return 7;
        UMaterial* CollectionMat=NewObject<UMaterial>(GetTransientPackage(),TEXT("CollectionValues"));
        auto* ScalarNode=NewObject<UMaterialExpressionCollectionParameter>(CollectionMat);ScalarNode->Collection=Collection;ScalarNode->ParameterName=TEXT("Roughness");Emit(CollectionMat,ScalarNode);
        auto* VectorNode=NewObject<UMaterialExpressionCollectionParameter>(CollectionMat);VectorNode->Collection=Collection;VectorNode->ParameterName=TEXT("Tint");CollectionMat->GetExpressionCollection().AddExpression(VectorNode);CollectionMat->GetExpressionInputForProperty(MP_BaseColor)->Connect(0,VectorNode);
        E.Materials->RemoveField(Id(CollectionMat->GetPathName()));E.Material(CollectionMat);
        if(auto* RemapClass=LoadClass<UMaterialExpression>(nullptr,TEXT("/Script/InterchangeImport.MaterialExpressionMaterialXRemap")))
        {
            for(int32 Case=0;Case<3;++Case)
            {
                const TCHAR* Names[]={TEXT("RemapDefaults"),TEXT("RemapBounds"),TEXT("RemapExtrapolation")};
                auto* RemapMaterial=NewObject<UMaterial>(GetTransientPackage(),Names[Case]);
                auto* Remap=NewObject<UMaterialExpression>(RemapMaterial,RemapClass);
                auto* InputProperty=FindFProperty<FStructProperty>(RemapClass,TEXT("Input"));
                if(!InputProperty) return 8;
                InputProperty->ContainerPtrToValuePtr<FExpressionInput>(Remap)->Connect(0,Scalar(RemapMaterial,Case==0?0.25:Case==1?-1.0:3.0));
                if(Case)
                {
                    const TCHAR* Fields[]={TEXT("InputLowDefault"),TEXT("InputHighDefault"),TEXT("TargetLowDefault"),TEXT("TargetHighDefault")};
                    const float Bounds[]={Case==1?-2.0f:0.0f,Case==1?2.0f:1.0f,10.0f,Case==1?18.0f:20.0f};
                    for(int32 I=0;I<4;++I)
                    {
                        auto* Property=FindFProperty<FFloatProperty>(RemapClass,Fields[I]);if(!Property) return 8;
                        Property->SetPropertyValue_InContainer(Remap,Bounds[I]);
                    }
                }
                Emit(RemapMaterial,Remap);
            }
        }
        else return 8;
        for(bool Tangent:{false,true})
        {
            auto* TransformMaterial=NewObject<UMaterial>(GetTransientPackage(),Tangent?TEXT("TangentVectorTransform"):TEXT("LocalVectorTransform"));
            auto* Vector=NewObject<UMaterialExpressionConstant3Vector>(TransformMaterial);Vector->Constant=FLinearColor(0.2,0.3,0.4);
            TransformMaterial->GetExpressionCollection().AddExpression(Vector);
            auto* Transform=NewObject<UMaterialExpressionTransform>(TransformMaterial);
            Transform->Input.Connect(0,Vector);Transform->TransformSourceType=Tangent?TRANSFORMSOURCE_Tangent:TRANSFORMSOURCE_Local;Transform->TransformType=TRANSFORM_World;
            TransformMaterial->GetExpressionCollection().AddExpression(Transform);
            TransformMaterial->GetExpressionInputForProperty(MP_BaseColor)->Connect(0,Transform);
            E.Material(TransformMaterial);
        }
        for(bool Virtual:{false,true})
        {
            const TCHAR* FixtureName=Virtual?TEXT("VirtualNormalSampler"):TEXT("RegularNormalSampler");
            auto* NormalMaterial=NewObject<UMaterial>(GetTransientPackage(),FixtureName);
            auto* NormalTexture=NewObject<UTexture2D>(NormalMaterial);
            const FColor Pixels[4]={FColor(128,192,255),FColor(128,192,255),FColor(128,192,255),FColor(128,192,255)};
            NormalTexture->Source.Init(2,2,1,1,TSF_BGRA8,reinterpret_cast<const uint8*>(Pixels));
            NormalTexture->SRGB=false;NormalTexture->CompressionSettings=TC_Normalmap;NormalTexture->VirtualTextureStreaming=Virtual;
            auto* NormalSample=NewObject<UMaterialExpressionTextureSample>(NormalMaterial);
            NormalSample->Texture=NormalTexture;NormalSample->SamplerType=Virtual?SAMPLERTYPE_VirtualNormal:SAMPLERTYPE_Normal;
            NormalMaterial->GetExpressionCollection().AddExpression(NormalSample);
            NormalMaterial->GetExpressionInputForProperty(MP_Normal)->Connect(0,NormalSample);
            E.Material(NormalMaterial);
        }
        auto* SpecularMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("ScalarSpecularInput"));
        SpecularMaterial->GetExpressionInputForProperty(MP_Specular)->Connect(0,Scalar(SpecularMaterial,0.25f));
        E.Material(SpecularMaterial);
        auto* SpecularTextureMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("TextureSpecularInput"));
        auto* SpecularTexture=NewObject<UTexture2D>(SpecularTextureMaterial);
        const FColor SpecularPixels[4]={FColor(32,32,32),FColor(64,64,64),FColor(128,128,128),FColor(255,255,255)};
        SpecularTexture->Source.Init(2,2,1,1,TSF_BGRA8,reinterpret_cast<const uint8*>(SpecularPixels));SpecularTexture->SRGB=false;
        auto* SpecularSample=NewObject<UMaterialExpressionTextureSample>(SpecularTextureMaterial);
        SpecularSample->Texture=SpecularTexture;SpecularSample->SamplerType=SAMPLERTYPE_LinearColor;
        SpecularTextureMaterial->GetExpressionCollection().AddExpression(SpecularSample);
        SpecularTextureMaterial->GetExpressionInputForProperty(MP_Specular)->Connect(1,SpecularSample);
        E.Material(SpecularTextureMaterial);
        // Shared hidden inputs must not be recursively duplicated in a JSON
        // tree. The preceding diagnostic implementation expanded this fixture
        // sixfold per level, although it contains only eleven expressions.
        auto* DiagnosticMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("BoundedUnknownDiagnostics"));
        UMaterialExpression* Previous=Scalar(DiagnosticMaterial,0.3f);
        for(int32 Level=0;Level<10;++Level)
        {
            auto* Hidden=NewObject<UMaterialExpressionCustom>(DiagnosticMaterial);
            Hidden->Code=TEXT("return 0.3;");Hidden->OutputType=CMOT_Float1;
            for(int32 Pin=0;Pin<6;++Pin)
            {
                FCustomInput Input;Input.InputName=FName(*FString::Printf(TEXT("Input%d"),Pin));
                Input.Input.Connect(0,Previous);Hidden->Inputs.Add(Input);
            }
            DiagnosticMaterial->GetExpressionCollection().AddExpression(Hidden);Previous=Hidden;
        }
        DiagnosticMaterial->GetExpressionInputForProperty(MP_Roughness)->Connect(0,Previous);E.Material(DiagnosticMaterial);
        // Distinct channel values detect incorrect attribute routing.
        auto* AttributeMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("AttributeSetGetRouting"));
        auto* Make=NewObject<UMaterialExpressionMakeMaterialAttributes>(AttributeMaterial);
        Make->BaseColor.Connect(0,Scalar(AttributeMaterial,.2f));Make->Roughness.Connect(0,Scalar(AttributeMaterial,.7f));
        auto* Set=NewObject<UMaterialExpressionSetMaterialAttributes>(AttributeMaterial);
        Set->Inputs[0].Connect(0,Make);Set->ConnectInputAttribute(MP_Roughness,Scalar(AttributeMaterial,.35f));
        auto* Get=NewObject<UMaterialExpressionGetMaterialAttributes>(AttributeMaterial);Get->MaterialAttributes.Connect(0,Set);
        AttributeMaterial->GetExpressionInputForProperty(MP_BaseColor)->Connect(Get->CreateOrGetOutputAttribute(MP_BaseColor),Get);
        AttributeMaterial->GetExpressionInputForProperty(MP_Roughness)->Connect(Get->CreateOrGetOutputAttribute(MP_Roughness),Get);
        E.Material(AttributeMaterial);
        auto* BundleMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("AttributeFunctionRouting"));
        auto* Bundle=NewObject<UMaterialExpressionMakeMaterialAttributes>(BundleMaterial);
        Bundle->BaseColor.Connect(0,Scalar(BundleMaterial,.2f));Bundle->Roughness.Connect(0,Scalar(BundleMaterial,.7f));
        auto* BundleInput=NewObject<UMaterialExpressionFunctionInput>(BundleMaterial);BundleInput->InputType=FunctionInput_MaterialAttributes;
        auto* BundleGet=NewObject<UMaterialExpressionGetMaterialAttributes>(BundleMaterial);BundleGet->MaterialAttributes.Connect(0,BundleInput);
        auto* BundleOutput=NewObject<UMaterialExpressionFunctionOutput>(BundleMaterial);BundleOutput->A.Connect(BundleGet->CreateOrGetOutputAttribute(MP_Roughness),BundleGet);
        auto* BundleCall=NewObject<UMaterialExpressionMaterialFunctionCall>(BundleMaterial);
        FFunctionExpressionInput Argument;Argument.ExpressionInput=BundleInput;Argument.Input.Connect(0,Bundle);BundleCall->FunctionInputs.Add(Argument);
        FFunctionExpressionOutput Result;Result.ExpressionOutput=BundleOutput;BundleCall->FunctionOutputs.Add(Result);
        BundleMaterial->GetExpressionInputForProperty(MP_BaseColor)->Connect(0,BundleCall);E.Material(BundleMaterial);
        auto* QualityMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("QualitySwitchRouting"));
        auto* Switch=NewObject<UMaterialExpressionQualitySwitch>(QualityMaterial);Switch->Default.Connect(0,Scalar(QualityMaterial,.15f));
        for(int32 Level=0;Level<EMaterialQualityLevel::Num;++Level) Switch->Inputs[Level].Connect(0,Scalar(QualityMaterial,.1f*(Level+1)));
        Emit(QualityMaterial,Switch);
        auto* DefaultQualityMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("QualitySwitchDefaultRouting"));
        auto* DefaultQualitySwitch=NewObject<UMaterialExpressionQualitySwitch>(DefaultQualityMaterial);DefaultQualitySwitch->Default.Connect(0,Scalar(DefaultQualityMaterial,.65f));Emit(DefaultQualityMaterial,DefaultQualitySwitch);
        // Runtime-only switch/fade recovery must not evaluate the unavailable
        // branch, flatten material bundles or discard the leaf opacity mask.
        auto* VirtualMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("NonVirtualSurfaceBranch"));
        auto* VirtualSwitch=NewObject<UMaterialExpressionVirtualTextureFeatureSwitch>(VirtualMaterial);
        VirtualSwitch->No.Connect(0,Scalar(VirtualMaterial,.2f));
        VirtualSwitch->Yes.Connect(0,NewObject<UMaterialExpressionCustom>(VirtualMaterial));
        Emit(VirtualMaterial,VirtualSwitch);
        auto* MissingVirtualMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("MissingNonVirtualBranch"));
        auto* MissingVirtualSwitch=NewObject<UMaterialExpressionVirtualTextureFeatureSwitch>(MissingVirtualMaterial);
        MissingVirtualSwitch->Yes.Connect(0,Scalar(MissingVirtualMaterial,.9f));Emit(MissingVirtualMaterial,MissingVirtualSwitch);
        auto* VirtualBundleMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("NonVirtualAttributeFunction"));
        auto* VirtualBundle=NewObject<UMaterialExpressionMakeMaterialAttributes>(VirtualBundleMaterial);
        VirtualBundle->BaseColor.Connect(0,Scalar(VirtualBundleMaterial,.25f));VirtualBundle->Roughness.Connect(0,Scalar(VirtualBundleMaterial,.75f));
        auto* VirtualBundleSwitch=NewObject<UMaterialExpressionVirtualTextureFeatureSwitch>(VirtualBundleMaterial);
        VirtualBundleSwitch->No.Connect(0,VirtualBundle);VirtualBundleSwitch->Yes.Connect(0,NewObject<UMaterialExpressionCustom>(VirtualBundleMaterial));
        auto* VirtualInput=NewObject<UMaterialExpressionFunctionInput>(VirtualBundleMaterial);VirtualInput->InputType=FunctionInput_MaterialAttributes;
        auto* VirtualGet=NewObject<UMaterialExpressionGetMaterialAttributes>(VirtualBundleMaterial);VirtualGet->MaterialAttributes.Connect(0,VirtualInput);
        auto* VirtualOutput=NewObject<UMaterialExpressionFunctionOutput>(VirtualBundleMaterial);VirtualOutput->A.Connect(VirtualGet->CreateOrGetOutputAttribute(MP_Roughness),VirtualGet);
        auto* VirtualCall=NewObject<UMaterialExpressionMaterialFunctionCall>(VirtualBundleMaterial);
        FFunctionExpressionInput VirtualArgument;VirtualArgument.ExpressionInput=VirtualInput;VirtualArgument.Input.Connect(0,VirtualBundleSwitch);VirtualCall->FunctionInputs.Add(VirtualArgument);
        FFunctionExpressionOutput VirtualResult;VirtualResult.ExpressionOutput=VirtualOutput;VirtualCall->FunctionOutputs.Add(VirtualResult);
        VirtualBundleMaterial->GetExpressionInputForProperty(MP_BaseColor)->Connect(0,VirtualCall);E.Material(VirtualBundleMaterial);
        auto* FadedMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("StaticFoliageOpacityMask"));
        FadedMaterial->BlendMode=BLEND_Masked;FadedMaterial->OpacityMaskClipValue=.4f;FadedMaterial->TwoSided=true;FadedMaterial->SetShadingModel(MSM_TwoSidedFoliage);
        auto* MaskTexture=NewObject<UTexture2D>(FadedMaterial);
        const FColor MaskPixels[4]={FColor(255,255,255,32),FColor(255,255,255,96),FColor(255,255,255,160),FColor(255,255,255,224)};
        MaskTexture->Source.Init(2,2,1,1,TSF_BGRA8,reinterpret_cast<const uint8*>(MaskPixels));
        auto* MaskSample=NewObject<UMaterialExpressionTextureSample>(FadedMaterial);MaskSample->Texture=MaskTexture;
        auto* Fade=NewObject<UMaterialExpressionPerInstanceFadeAmount>(FadedMaterial);
        auto* MaskFade=NewObject<UMaterialExpressionMultiply>(FadedMaterial);MaskFade->A.Connect(4,MaskSample);MaskFade->B.Connect(0,Fade);
        FadedMaterial->GetExpressionInputForProperty(MP_OpacityMask)->Connect(0,MaskFade);E.Material(FadedMaterial);
        auto* MaskedVectorMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("NonVirtualInputChannelMask"));
        auto* MaskedVector=NewObject<UMaterialExpressionConstant3Vector>(MaskedVectorMaterial);MaskedVector->Constant=FLinearColor(.1f,.4f,.8f);
        auto* MaskedSwitch=NewObject<UMaterialExpressionVirtualTextureFeatureSwitch>(MaskedVectorMaterial);MaskedSwitch->No.Connect(0,MaskedVector);
        MaskedSwitch->No.Mask=1;MaskedSwitch->No.MaskR=0;MaskedSwitch->No.MaskG=1;MaskedSwitch->No.MaskB=0;MaskedSwitch->No.MaskA=0;
        MaskedSwitch->Yes.Connect(0,NewObject<UMaterialExpressionCustom>(MaskedVectorMaterial));Emit(MaskedVectorMaterial,MaskedSwitch);
        auto InputsFor=[&](UMaterial* M) { return E.Materials->GetObjectField(Id(M->GetPathName()))->GetObjectField(TEXT("inputs")); };
        auto HasScalar=[](const Obj& Node,double Expected) { return Node->GetStringField(TEXT("op"))==TEXT("constant") && Node->GetArrayField(TEXT("value")).Num()==1 && FMath::IsNearlyEqual(Node->GetArrayField(TEXT("value"))[0]->AsNumber(),Expected,1.e-6); };
        const Obj CapturedMask=InputsFor(FadedMaterial)->GetObjectField(TEXT("opacity"));
        const Obj CapturedChannels=InputsFor(MaskedVectorMaterial)->GetObjectField(TEXT("roughness"));
        const Obj MissingBranch=InputsFor(MissingVirtualMaterial)->GetObjectField(TEXT("roughness"));
        if(!HasScalar(InputsFor(VirtualMaterial)->GetObjectField(TEXT("roughness")),.2) ||
           !HasScalar(InputsFor(VirtualBundleMaterial)->GetObjectField(TEXT("base_color")),.75) ||
           MissingBranch->GetStringField(TEXT("op"))!=TEXT("unsupported") || !MissingBranch->GetStringField(TEXT("reason")).Contains(TEXT("No input")) ||
           CapturedMask->GetStringField(TEXT("op"))!=TEXT("multiply") || !HasScalar(CapturedMask->GetObjectField(TEXT("b")),1) ||
           CapturedMask->GetObjectField(TEXT("a"))->GetStringField(TEXT("op"))!=TEXT("mask") ||
           CapturedMask->GetObjectField(TEXT("a"))->GetObjectField(TEXT("input"))->GetStringField(TEXT("op"))!=TEXT("texture") ||
           CapturedMask->GetObjectField(TEXT("a"))->GetArrayField(TEXT("channels"))[0]->AsNumber()!=3 ||
           !FMath::IsNearlyEqual(E.Materials->GetObjectField(Id(FadedMaterial->GetPathName()))->GetNumberField(TEXT("opacity_threshold")),.4,1.e-6) ||
           CapturedChannels->GetStringField(TEXT("op"))!=TEXT("mask") || CapturedChannels->GetArrayField(TEXT("channels"))[0]->AsNumber()!=1)
        { UE_LOG(LogTemp,Error,TEXT("Virtual-texture/fade material recovery regression failed"));return 9; }
        Obj Manifest=Object();Manifest->SetNumberField(TEXT("schema_version"),1);Manifest->SetStringField(TEXT("map"),TEXT("BridgeTestMaterials"));
        Manifest->SetStringField(TEXT("serialization_fixture_label"),TEXT("Moss 苔藓 — café\n\"quoted\""));
        Manifest->SetObjectField(TEXT("materials"),E.Materials);Manifest->SetObjectField(TEXT("textures"),E.Textures);Manifest->SetObjectField(TEXT("meshes"),E.Meshes);
        Manifest->SetArrayField(TEXT("instances"),{});Manifest->SetArrayField(TEXT("instancers"),{});Manifest->SetArrayField(TEXT("issues"),E.Issues);Manifest->SetArrayField(TEXT("notes"),E.Notes);
        return Save(Manifest,Out/TEXT("manifest.json"))?0:4;
    }
    if(!Asset.IsEmpty())
    {
        UObject* SourceAsset=LoadObject<UObject>(nullptr,*(Asset+TEXT(".")+FPaths::GetCleanFilename(Asset)));
        UStaticMesh* SM=Cast<UStaticMesh>(SourceAsset);USkeletalMesh* SK=Cast<USkeletalMesh>(SourceAsset);
        if(!SM && !(SK && ExportSkeletalMeshes))
        { UE_LOG(LogTemp,Error,TEXT("Standalone asset must be an uncooked StaticMesh, or a SkeletalMesh with Export skeletal meshes enabled")); return 5; }
        FExport E; E.Out=Out; Configure(E);
        const FString Mesh=SM?E.Mesh(SM):E.SkeletalMesh(SK); if(Mesh.IsEmpty()) return 6;
        Arr Mats;
        if(SM) for(const FStaticMaterial& M:SM->GetStaticMaterials()) Mats.Add(S(E.Material(M.MaterialInterface)));
        else for(const FSkeletalMaterial& M:SK->GetMaterials()) Mats.Add(S(E.Material(M.MaterialInterface)));
        Obj I=Object(); I->SetStringField(TEXT("name"),SourceAsset->GetName()); I->SetStringField(TEXT("source"),SourceAsset->GetPathName()); I->SetStringField(TEXT("mesh"),Mesh); I->SetArrayField(TEXT("materials"),Mats); I->SetArrayField(TEXT("matrix"),Matrix(FTransform::Identity));
        if(SK) I->SetStringField(TEXT("mesh_kind"),TEXT("skeletal_rest_pose"));
        Obj Manifest=Object(); Manifest->SetNumberField(TEXT("schema_version"),1); Manifest->SetStringField(TEXT("map"),Asset);
        Manifest->SetBoolField(TEXT("export_skeletal_meshes"),ExportSkeletalMeshes);
        Manifest->SetObjectField(TEXT("materials"),E.Materials); Manifest->SetObjectField(TEXT("textures"),E.Textures); Manifest->SetObjectField(TEXT("meshes"),E.Meshes);
        Manifest->SetArrayField(TEXT("instances"),{V(I)}); Manifest->SetArrayField(TEXT("instancers"),{}); Manifest->SetArrayField(TEXT("issues"),E.Issues); Manifest->SetArrayField(TEXT("notes"),E.Notes);
        E.Policy(Manifest);
        return Save(Manifest,Out/TEXT("manifest.json"))?0:4;
    }
    if(VisibilityFixture)
    {
        MakeVisibilityFixture();Map=TEXT("BridgeTestVisibility");
    }
    else if(SplineFixture)
    {
        MakeSplineFixture(Out,Params);Map=TEXT("BridgeTestSplines");
    }
    else if(EditorFixture)
    {
        UWorld* TestWorld=GEditor->NewMap();
        UStaticMesh* Sphere=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Sphere.Sphere"));
        if(!Sphere) return 6;
        FStaticMeshCompilingManager::Get().FinishCompilation({Sphere});
        const int32 Before=Sphere->GetMeshDescription(0)->Triangles().Num();
        FixtureSource=Sphere;FixtureTriangles=Before;FixtureDirty=Sphere->GetOutermost()->IsDirty();
        auto Spawn=[&](const TCHAR* Name,UStaticMesh* Mesh,FVector Position)
        {
            auto* A=TestWorld->SpawnActor<AStaticMeshActor>();A->SetActorLabel(Name);
            A->GetStaticMeshComponent()->SetStaticMesh(Mesh);A->SetActorLocation(Position);
            return A;
        };
        auto* First=Spawn(TEXT("SelectedSphere"),Sphere,FVector(100,200,300));
        auto* Second=Spawn(TEXT("OtherSphere"),Sphere,FVector(500,200,300));
        Spawn(TEXT("ThirdSphere"),Sphere,FVector(900,200,300));
        UStaticMesh* Protected=NewObject<UStaticMesh>(GetTransientPackage(),TEXT("ProtectedCards"));
        Protected->AddSourceModel();Protected->CreateMeshDescription(0,*Sphere->GetMeshDescription(0));
        UMaterial* Leaf=NewObject<UMaterial>(GetTransientPackage(),TEXT("AlphaCards"));Leaf->TwoSided=true;Leaf->BlendMode=BLEND_Masked;
        Protected->GetStaticMaterials().Add(FStaticMaterial(Leaf));
        Spawn(TEXT("ProtectedFoliage"),Protected,FVector(1300,200,300));
        GEditor->SelectNone(false,true,false);
        if(!FParse::Param(*Params,TEXT("BridgeTestEmptySelection")))
        {
            GEditor->SelectActor(First,true,false);GEditor->SelectActor(Second,true,false);
            if(FParse::Param(*Params,TEXT("BridgeTestComponentSelection")))
                GEditor->SelectComponent(First->GetStaticMeshComponent(),true,false);
        }
        // Metadata used by the acceptance runner to prove source topology was
        // preserved. No source mesh is edited, committed or saved by the exporter.
        UE_LOG(LogTemp,Display,TEXT("BRIDGE_TEST_SOURCE_TRIANGLES: %d"),Before);
        Map=TEXT("BridgeTestEditor");
    }
    else if(SkeletalFixture)
    {
        UWorld* TestWorld=GEditor->NewMap();
        UStaticMesh* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
        if(!Cube || !Cube->GetMeshDescription(0)) return 6;
        USkeletalMesh* SK=NewObject<USkeletalMesh>(GetTransientPackage(),TEXT("ReferenceFixture"));
        SK->AddLODInfo(); SK->SetNumSourceModels(1);
        SK->CreateMeshDescription(0,FMeshDescription(*Cube->GetMeshDescription(0)));
        for(const FStaticMaterial& M:Cube->GetStaticMaterials())
            SK->GetMaterials().Add(FSkeletalMaterial(M.MaterialInterface,true,false,M.MaterialSlotName,M.ImportedMaterialSlotName));
        AActor* Actor=TestWorld->SpawnActor<AActor>(); Actor->SetActorLabel(TEXT("SkeletalFixture"));
        auto* Component=NewObject<USkeletalMeshComponent>(Actor,TEXT("ReferenceMesh"));
        Actor->AddInstanceComponent(Component); Actor->SetRootComponent(Component);
        Component->SetSkeletalMeshAsset(SK);Component->SetWorldLocation(FVector(100,200,50));
        Map=TEXT("BridgeTestSkeletal");
    }
    else if(DecalFixture)
    {
        UWorld* TestWorld=GEditor->NewMap();
        UStaticMesh* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
        if(!Cube) return 6;
        UMaterial* ReceiverMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("BridgeReceiverMaterial"));
        auto* ReceiverColor=NewObject<UMaterialExpressionConstant3Vector>(ReceiverMaterial); ReceiverColor->Constant=FLinearColor(0.5,0.3,0.15);
        ReceiverMaterial->GetExpressionCollection().AddExpression(ReceiverColor);
        ReceiverMaterial->GetExpressionInputForProperty(MP_BaseColor)->Connect(0,ReceiverColor);
        for(int32 Index=0;Index<3;++Index)
        {
            auto* Receiver=TestWorld->SpawnActor<AStaticMeshActor>(FVector(0,Index*120,Index==1?40:0),FRotator::ZeroRotator);
            Receiver->SetActorLabel(Index==0?TEXT("LowerSurface"):Index==1?TEXT("RaisedSurface"):TEXT("NoDecals"));
            auto* Component=Receiver->GetStaticMeshComponent(); Component->SetStaticMesh(Cube);
            Component->SetMaterial(0,ReceiverMaterial);
            Component->SetReceivesDecals(Index!=2);
        }
        UMaterial* DecalMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("BridgeDecalMaterial"));
        DecalMaterial->MaterialDomain=MD_DeferredDecal; DecalMaterial->BlendMode=BLEND_Translucent;
        auto* Color=NewObject<UMaterialExpressionConstant3Vector>(DecalMaterial); Color->Constant=FLinearColor(0.2,0.8,0.1);
        DecalMaterial->GetExpressionCollection().AddExpression(Color); DecalMaterial->GetExpressionInputForProperty(MP_BaseColor)->Connect(0,Color);
        auto* Decal=TestWorld->SpawnActor<ADecalActor>(FVector(0,100,50),FRotator(-90,0,0));
        Decal->SetActorLabel(TEXT("SharedTestDecal")); Decal->GetDecal()->SetDecalMaterial(DecalMaterial);
        Decal->GetDecal()->DecalSize=FVector(150,300,150);
        Map=TEXT("BridgeTestDecals");
    }
    else if(FoliageFixture)
    {
        UWorld* TestWorld=GEditor->NewMap();
        UStaticMesh* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
        if(!Cube) return 6;
        FAssetCompilingManager::Get().FinishAllCompilation();
        auto* IFA=AInstancedFoliageActor::GetInstancedFoliageActorForCurrentLevel(TestWorld,true);
        auto* Type=NewObject<UFoliageType_InstancedStaticMesh>(IFA);
        Type->SetStaticMesh(Cube);
        FFoliageInfo* Info=nullptr;
        UFoliageType* OwnedType=IFA->AddFoliageType(Type,&Info);
        if(!Info || !OwnedType) return 7;
        FFoliageInstance Item;
        Item.Location=FVector(100,200,300);
        Info->AddInstance(OwnedType,Item);
        Info->AddInstance(OwnedType,Item); // Intentional coincident authored instances must survive.
        Item.Location=FVector(400,500,600);
        Item.Rotation=FRotator(0,30,0);
        Info->AddInstance(OwnedType,Item);
        // An orphaned attachment, at a valid placement's position, must be omitted.
        Info->AddInstance(OwnedType,Item);
        const int32 OrphanId=123456;
        Info->Instances.Last().BaseId=OrphanId;
        auto* Component=Info->GetComponent();
        Component->InstancingRandomSeed=123;
        Component->SetWorldTransform(FTransform(FRotator(0,15,0),FVector(20,30,40),FVector(2)));
        Component->AddInstance(Info->Instances[0].GetInstanceWorldTransform(),true);
        auto* Generic=TestWorld->SpawnActor<AActor>();
        Generic->SetActorLabel(TEXT("GenericInstances"));
        auto* ISM=NewObject<UInstancedStaticMeshComponent>(Generic,TEXT("GenericISM"));
        Generic->SetRootComponent(ISM); Generic->AddInstanceComponent(ISM);
        ISM->SetStaticMesh(Cube); ISM->RegisterComponent(); ISM->InstancingRandomSeed=456;
        ISM->AddInstance(FTransform(FVector(700,800,900)));
        ISM->AddInstance(FTransform(FVector(700,800,900)));
        Map=TEXT("BridgeTestFoliage");
    }
    else if(Fixture)
    {
        // An in-memory acceptance fixture: no source project or map is saved.
        UWorld* TestWorld=GEditor->NewMap();
        ALandscape* Terrain=TestWorld->SpawnActor<ALandscape>(FVector(100,200,300),FRotator::ZeroRotator);
        Terrain->SetActorScale3D(FVector(100,100,100));
        UMaterial* TestMaterial=NewObject<UMaterial>(GetTransientPackage(),TEXT("BridgeLandscapeMaterial"));
        auto* Blend=NewObject<UMaterialExpressionLandscapeLayerBlend>(TestMaterial);
        TestMaterial->GetExpressionCollection().AddExpression(Blend);
        TArray<FLandscapeImportLayerInfo> LayerData;
        for(int32 Index=0;Index<2;++Index)
        {
            FName LayerName=Index==0?TEXT("Grass"):TEXT("Soil");
            FLayerBlendInput Layer; Layer.LayerName=LayerName; Layer.BlendType=LB_WeightBlend;
            Layer.ConstLayerInput=Index==0?FVector(0.1,0.6,0.1):FVector(0.4,0.15,0.05);
            Blend->Layers.Add(Layer);
            auto* Info=NewObject<ULandscapeLayerInfoObject>(GetTransientPackage(),LayerName);
            Info->SetLayerName(LayerName,false);
            FLandscapeImportLayerInfo Imported(LayerName); Imported.LayerInfo=Info;
            for(int32 Y=0;Y<29;++Y) for(int32 X=0;X<29;++X) Imported.LayerData.Add(Index==0?X*3+Y*5:255-X*3-Y*5);
            LayerData.Add(MoveTemp(Imported));
        }
        TestMaterial->GetExpressionInputForProperty(MP_BaseColor)->Connect(0,Blend);
        Terrain->LandscapeMaterial=TestMaterial;
        TArray<uint16> Heights;
        for(int32 Y=0;Y<29;++Y) for(int32 X=0;X<29;++X) Heights.Add(32768+(X-14)*64+(Y-14)*32);
        TMap<FGuid,TArray<uint16>> HeightLayers; HeightLayers.Add(FGuid(),MoveTemp(Heights));
        TMap<FGuid,TArray<FLandscapeImportLayerInfo>> WeightLayers; WeightLayers.Add(FGuid(),MoveTemp(LayerData));
        Terrain->Import(FGuid::NewGuid(),-14,-14,14,14,2,7,HeightLayers,nullptr,WeightLayers,ELandscapeImportAlphamapType::Additive,TArrayView<const FLandscapeLayer>());
        if(!FParse::Param(*Params,TEXT("BridgeTestPendingLayers")))
        {
            // This fixture has one edit layer. Populate its final cached source data
            // directly, matching a saved/composited single-layer terrain without a GPU.
            for(ULandscapeComponent* C:Terrain->LandscapeComponents)
                C->ForEachLayer([&](const FGuid&,FLandscapeLayerComponentData& Layer)
                {
                    C->SetHeightmap(Layer.HeightmapData.Texture);
                    TArray<UTexture2D*> Textures; for(UTexture2D* T:Layer.WeightmapData.Textures) Textures.Add(T);
                    C->SetWeightmapTextures(Textures);
                    C->SetWeightmapLayerAllocations(Layer.WeightmapData.LayerAllocations);
                });
        }
        if(FParse::Param(*Params,TEXT("BridgeTestHiddenLandscape")) && !Terrain->LandscapeComponents.IsEmpty())
            Terrain->LandscapeComponents[0]->SetVisibility(false);
        Map=TEXT("BridgeTestLandscape");
    }
    else if(!Current && !FEditorFileUtils::LoadMap(Map,false,true)) { UE_LOG(LogTemp,Error,TEXT("Cannot load map %s"),*Map); return 2; }
    UWorld* World=GEditor->GetEditorWorldContext().World(); if(!World) return 3;
    if(Current) Map=World->GetOutermost()->GetName();
    // No LoadAllActors or global FinishAllCompilation: assets are processed
    // serially and additional partition actor references are released per batch.
    FExport Export; Export.Out=Out; Configure(Export);
    if(FParse::Param(*Params,TEXT("BridgeMaterialsOnly")))
    {
        for(TActorIterator<AActor> It(World);It;++It)
        {
            if(IsBlockingVolumeClass(It->GetClass())) continue;
            TInlineComponentArray<UActorComponent*> Components(*It);
            for(UActorComponent* C:Components)
                if(auto* Mesh=Cast<UMeshComponent>(C)) Export.Slots(Mesh);
        }
        Obj Manifest=Object();Manifest->SetNumberField(TEXT("schema_version"),1);Manifest->SetStringField(TEXT("map"),Map);
        Manifest->SetObjectField(TEXT("materials"),Export.Materials);Manifest->SetObjectField(TEXT("textures"),Export.Textures);Manifest->SetObjectField(TEXT("meshes"),Export.Meshes);
        Manifest->SetArrayField(TEXT("instances"),{});Manifest->SetArrayField(TEXT("instancers"),{});Manifest->SetArrayField(TEXT("issues"),Export.Issues);Manifest->SetArrayField(TEXT("notes"),Export.Notes);
        return Save(Manifest,Out/TEXT("manifest.json"))?0:4;
    }
    if(FParse::Param(*Params,TEXT("BridgeAuditFoliage")))
    {
        Arr Groups;
        for(TActorIterator<AInstancedFoliageActor> It(World);It;++It)
            for(const auto& Pair:It->GetFoliageInfos())
            {
                const FFoliageInfo& Info=Pair.Value.Get();
                Obj Group=Object(); Group->SetStringField(TEXT("type"),Pair.Key->GetPathName());
                TMap<int32,int32> Counts; for(const FFoliageInstance& Instance:Info.Instances) Counts.FindOrAdd(Instance.BaseId)++;
                Arr Bases;
                for(const auto& Count:Counts)
                {
                    Obj Base=Object(); const auto Ptr=It->InstanceBaseCache.GetInstanceBasePtr(Count.Key);
                    Base->SetNumberField(TEXT("id"),Count.Key); Base->SetNumberField(TEXT("instances"),Count.Value);
                    Base->SetStringField(TEXT("path"),Ptr.ToString()); Base->SetBoolField(TEXT("resolved"),Ptr.Get()!=nullptr);
                    Base->SetBoolField(TEXT("invalid_id"),Count.Key==FFoliageInstanceBaseCache::InvalidBaseId);
                    const auto* Members=Info.ComponentHash.Find(Count.Key); Base->SetNumberField(TEXT("members"),Members?Members->Num():0);
                    Bases.Add(V(Base));
                }
                Group->SetArrayField(TEXT("bases"),Bases);Groups.Add(V(Group));
            }
        Obj Audit=Object();Audit->SetArrayField(TEXT("groups"),Groups);return Save(Audit,Out/TEXT("foliage-audit.json"))?0:4;
    }
    TSet<FString> Processed;
    TSet<UActorComponent*> SelectedComponents;
    TSet<AActor*> SelectedActors;
    if(Selected)
    {
        for(FSelectionIterator It(*GEditor->GetSelectedComponents());It;++It) if(auto* C=Cast<UActorComponent>(*It)) SelectedComponents.Add(C);
        for(FSelectionIterator It(*GEditor->GetSelectedActors());It;++It) if(auto* A=Cast<AActor>(*It)) SelectedActors.Add(A);
        if(SelectedComponents.IsEmpty() && SelectedActors.IsEmpty()) { UE_LOG(LogTemp,Error,TEXT("Select at least one actor or mesh component")); return 7; }
    }
    bool Aborted=false;
    int32 Count=0;
    auto ExportActor=[&](AActor* Actor)
    {
        if(!Actor || Processed.Contains(Actor->GetPathName())) return;
        // Always skip the complete volume actor, including any custom mesh,
        // decal or other attached components, before progress/asset extraction.
        if(IsBlockingVolumeClass(Actor->GetClass())) return;
        if(Export.ExcludeHidden && Export.HiddenActor(Actor))
        {Processed.Add(Actor->GetPathName());++Export.HiddenActors;return;}
        if(Selected && SelectedComponents.IsEmpty() && !SelectedActors.Contains(Actor) && !(IncludeDecals && Actor->FindComponentByClass<UDecalComponent>())) return;
        Processed.Add(Actor->GetPathName());
        const FPlatformMemoryStats Mem=FPlatformMemory::GetStats();
        if(FMath::Min(Mem.AvailablePhysical,Mem.AvailableVirtual)<2ull*1024*1024*1024)
        { UE_LOG(LogTemp,Error,TEXT("BRIDGE: live 2 GiB RAM/commit reserve reached before next actor; partial extraction not published")); Aborted=true; return; }
        if(Progress && !Progress(0.05f+0.25f*Count/(Count+100.0f),Actor->GetActorLabel())) { Aborted=true; return; }
        ++Count;
        if(auto* Landscape=Cast<ALandscapeProxy>(Actor)) { if(!FoliageOnly && (!Selected || SelectedActors.Contains(Actor))) Export.Landscape(Landscape); return; }
        if(LandscapeOnly) return;
        TInlineComponentArray<UActorComponent*> Components(Actor);
        for(UActorComponent* C:Components)
        {
            if(Selected && !SelectedComponents.IsEmpty() && !SelectedComponents.Contains(C) && !(IncludeDecals && Cast<UDecalComponent>(C))) continue;
            if(Selected && SelectedComponents.IsEmpty() && !SelectedActors.Contains(Actor) && !Cast<UDecalComponent>(C)) continue;
            if(Export.ExcludeHidden && Export.HiddenComponent(Cast<USceneComponent>(C)))
            {++Export.HiddenComponents;continue;}
            if(FParse::Param(*Params,TEXT("BridgeNoLights")) && Cast<ULightComponent>(C)) continue;
            if(FParse::Param(*Params,TEXT("BridgeNoCameras")) && Cast<UCameraComponent>(C)) continue;
            if(!IncludeDecals && Cast<UDecalComponent>(C)) continue;
            if(FoliageOnly && !Cast<UInstancedStaticMeshComponent>(C)) continue;
            if(auto* SM=Cast<UStaticMeshComponent>(C))
            {
                if(!SM->GetStaticMesh()) continue;
                auto* Spline=Cast<USplineMeshComponent>(SM);
                const FString Mesh=Export.Mesh(SM->GetStaticMesh(),Spline); if(Mesh.IsEmpty()) continue;
                Obj I=Object(); I->SetStringField(TEXT("name"),Actor->GetActorLabel()+TEXT("_")+SM->GetName()); I->SetStringField(TEXT("source"),SM->GetPathName()); I->SetStringField(TEXT("mesh"),Mesh); I->SetArrayField(TEXT("materials"),FoliageOnly?Arr{}:Export.Slots(SM));
                if(Spline) I->SetStringField(TEXT("mesh_kind"),TEXT("spline_deformed"));
                I->SetBoolField(TEXT("receives_decals"),SM->bReceivesDecals);
                const FVector Center=SM->Bounds.Origin; I->SetArrayField(TEXT("object_position"),Vec({Center.X,Center.Y,Center.Z}));
                Export.PaintedColors(SM,Mesh,I);
                // A spline's geometry is component-specific and is consumed
                // once here. Do not retain per-component paint remap arrays
                // for thousands of ropes after the paint has been transferred.
                if(Spline) {Export.SourcePositions.Remove(Mesh);Export.SourceNormals.Remove(Mesh);}
                I->SetBoolField(TEXT("visible"),SM->IsVisible() && !Actor->IsHidden());
                if(auto* ISM=Cast<UInstancedStaticMeshComponent>(SM))
                {
                    // Foliage render-component buffers may contain stale/rebuilt copies.
                    // The editor placement records are authoritative; do not position-deduplicate
                    // them, since two intentionally coincident placements are still two instances.
                    const FFoliageInfo* FoliageInfo=nullptr;
                    if(auto* IFA=Cast<AInstancedFoliageActor>(Actor))
                    {
                        for(const auto& Pair:IFA->GetFoliageInfos())
                            if(Pair.Value->GetComponent()==ISM) { FoliageInfo=&Pair.Value.Get(); break; }
                        if(!FoliageInfo && Cast<UFoliageInstancedStaticMeshComponent>(ISM))
                        {
                            Export.Issue(C->GetPathName()+TEXT(": foliage component has no authoritative placement records"));
                            continue;
                        }
                    }
                    const int32 SourceCount=FoliageInfo?FoliageInfo->Instances.Num():ISM->GetInstanceCount();
                    I->SetStringField(TEXT("instance_source"),FoliageInfo?TEXT("foliage_editor_records"):TEXT("component_instances"));
                    I->SetNumberField(TEXT("component_instance_count"),ISM->GetInstanceCount());
                    I->SetNumberField(TEXT("source_instance_count"),SourceCount);
                    if(FoliageInfo && SourceCount!=ISM->GetInstanceCount())
                        Export.Note(FString::Printf(TEXT("%s: exporting %d authored foliage placements instead of %d render-component entries"),*C->GetPathName(),SourceCount,ISM->GetInstanceCount()));
                    Arr Transforms,Centers,SourceIndices;
                    int32 Orphaned=0,Deleted=0;
                    Arr RandomValues;
                    FRandomStream RandomStream(ISM->InstancingRandomSeed);
                    auto SeedIt=ISM->AdditionalRandomSeeds.CreateConstIterator();
                    int32 ResetIndex=SeedIt ? SeedIt->StartInstanceIndex : INDEX_NONE;
                    for(int32 Index=0;Index<SourceCount;++Index)
                    {
                        if(Index==ResetIndex) { RandomStream=FRandomStream(SeedIt->RandomSeed); ++SeedIt; ResetIndex=SeedIt ? SeedIt->StartInstanceIndex : INDEX_NONE; }
                        const float RandomValue=RandomStream.GetFraction();
                        FTransform T;
                        bool Valid=false;
                        if(FoliageInfo)
                        {
                            const FFoliageInstance& Placement=FoliageInfo->Instances[Index];
                            if(Placement.Flags & FOLIAGE_InstanceDeleted) { ++Deleted; continue; }
                            // Match Unreal USD export's valid-base membership. Records for
                            // deleted/unresolved attachments can survive in both arrays.
                            // InvalidBaseId explicitly denotes intentionally unattached foliage.
                            if(Placement.BaseId!=FFoliageInstanceBaseCache::InvalidBaseId &&
                               !FoliageInfo->IFA->InstanceBaseCache.GetInstanceBasePtr(Placement.BaseId).Get())
                            { ++Orphaned; continue; }
                            T=Placement.GetInstanceWorldTransform().GetRelativeTransform(ISM->GetComponentTransform());
                            Valid=true;
                        }
                        else Valid=ISM->GetInstanceTransform(Index,T,false);
                        if(Valid)
                        {
                            Transforms.Add(A(Matrix(T))); RandomValues.Add(N(RandomValue));SourceIndices.Add(N(Index));
                            const FVector CenterWorld=(T*ISM->GetComponentTransform()).TransformPosition(ISM->GetStaticMesh()->GetBounds().Origin);
                            Centers.Add(A(Vec({CenterWorld.X,CenterWorld.Y,CenterWorld.Z})));
                        }
                        else Export.Issue(C->GetPathName()+TEXT(": could not read foliage instance transform"));
                    }
                    I->SetArrayField(TEXT("source_indices"),SourceIndices);
                    I->SetNumberField(TEXT("orphaned_instance_count"),Orphaned);
                    I->SetNumberField(TEXT("deleted_instance_count"),Deleted);
                    if(Orphaned || Deleted)
                        Export.Note(FString::Printf(TEXT("%s: skipped %d foliage records with unresolved base components and %d deleted records; exported %d valid placements"),*C->GetPathName(),Orphaned,Deleted,Transforms.Num()));
                    I->SetArrayField(TEXT("random_values"),RandomValues);
                    I->SetArrayField(TEXT("object_positions"),Centers);
                    I->SetArrayField(TEXT("matrix"),Matrix(ISM->GetComponentTransform())); I->SetArrayField(TEXT("transforms"),Transforms); Export.Instancers.Add(V(I));
                }
                else { I->SetArrayField(TEXT("matrix"),Matrix(SM->GetComponentTransform())); Export.Instances.Add(V(I)); }
            }
            else if(auto* L=Cast<ULightComponent>(C))
            {
                Obj J=Object(); J->SetStringField(TEXT("source"),C->GetPathName()); J->SetArrayField(TEXT("matrix"),Matrix(L->GetComponentTransform()));
                const FLinearColor Color=L->GetLightColor(); J->SetArrayField(TEXT("color"),Vec({Color.R,Color.G,Color.B})); J->SetNumberField(TEXT("intensity"),L->Intensity); J->SetBoolField(TEXT("visible"),L->IsVisible());
                if(Cast<UDirectionalLightComponent>(L)) J->SetStringField(TEXT("kind"),TEXT("distant"));
                else if(auto* Spot=Cast<USpotLightComponent>(L)) { J->SetStringField(TEXT("kind"),TEXT("spot")); J->SetNumberField(TEXT("angle"),Spot->OuterConeAngle); J->SetNumberField(TEXT("radius"),FMath::Max(Spot->SourceRadius,0.1f)); }
                else if(auto* Point=Cast<UPointLightComponent>(L)) { J->SetStringField(TEXT("kind"),TEXT("sphere")); J->SetNumberField(TEXT("radius"),FMath::Max(Point->SourceRadius,0.1f)); }
                else if(auto* Rect=Cast<URectLightComponent>(L)) { J->SetStringField(TEXT("kind"),TEXT("rect")); J->SetNumberField(TEXT("width"),Rect->SourceWidth); J->SetNumberField(TEXT("height"),Rect->SourceHeight); }
                else { Export.Note(C->GetPathName()+TEXT(": unsupported light type")); continue; }
                Export.Lights.Add(V(J));
            }
            else if(auto* Camera=Cast<UCameraComponent>(C))
            {
                Obj J=Object(); J->SetStringField(TEXT("source"),C->GetPathName()); J->SetArrayField(TEXT("matrix"),Matrix(Camera->GetComponentTransform()));
                J->SetNumberField(TEXT("fov"),Camera->FieldOfView); J->SetNumberField(TEXT("aspect"),Camera->AspectRatio); J->SetBoolField(TEXT("orthographic"),Camera->ProjectionMode==ECameraProjectionMode::Orthographic); J->SetNumberField(TEXT("ortho_width"),Camera->OrthoWidth); Export.Cameras.Add(V(J));
            }
            else if(auto* Decal=Cast<UDecalComponent>(C))
            {
                Obj J=Object(); J->SetStringField(TEXT("source"),C->GetPathName()); J->SetStringField(TEXT("name"),Actor->GetActorLabel()+TEXT("_")+C->GetName());
                J->SetStringField(TEXT("material"),Export.Material(Decal->GetDecalMaterial()));
                J->SetArrayField(TEXT("matrix"),Matrix(Decal->GetTransformIncludingDecalSize()));
                J->SetArrayField(TEXT("color"),Vec({Decal->DecalColor.R,Decal->DecalColor.G,Decal->DecalColor.B,Decal->DecalColor.A}));
                J->SetNumberField(TEXT("sort_order"),Decal->SortOrder); J->SetBoolField(TEXT("visible"),Decal->IsVisible() && !Actor->IsHidden());
                Export.Decals.Add(V(J));
                if(Decal->FadeDuration>0 || Decal->FadeInDuration>0) Export.Note(C->GetPathName()+TEXT(": decal lifetime/fade is frozen at full opacity; screen-size fading is not reproduced"));
            }
            else if(auto* SK=Cast<USkeletalMeshComponent>(C))
            {
                if(!ExportSkeletalMeshes)
                { Export.Note(C->GetPathName()+TEXT(": skeletal mesh omitted because Export skeletal meshes is disabled")); continue; }
                const FString Mesh=Export.SkeletalMesh(SK->GetSkeletalMeshAsset());if(Mesh.IsEmpty()) continue;
                Obj I=Object();I->SetStringField(TEXT("name"),Actor->GetActorLabel()+TEXT("_")+SK->GetName());
                I->SetStringField(TEXT("source"),SK->GetPathName());I->SetStringField(TEXT("mesh"),Mesh);
                I->SetStringField(TEXT("mesh_kind"),TEXT("skeletal_rest_pose"));
                I->SetArrayField(TEXT("materials"),Export.Slots(SK));I->SetArrayField(TEXT("matrix"),Matrix(SK->GetComponentTransform()));
                I->SetBoolField(TEXT("receives_decals"),SK->bReceivesDecals);I->SetBoolField(TEXT("visible"),SK->IsVisible() && !Actor->IsHidden());
                const FVector Center=SK->GetComponentTransform().TransformPosition(SK->GetSkeletalMeshAsset()->GetBounds().Origin);
                I->SetArrayField(TEXT("object_position"),Vec({Center.X,Center.Y,Center.Z}));Export.Instances.Add(V(I));
            }
        }
    };
    // A unified terrain must see all of its streaming proxies before the first
    // Landscape() call; otherwise the first loaded chunk wins the dedup key.
    TArray<FWorldPartitionReference> LandscapeRefs;
    if(!Selected && !Aborted)
        if(UWorldPartition* WP=World->GetWorldPartition())
            FWorldPartitionHelpers::ForEachActorDescInstance<ALandscapeProxy>(WP,[&](const FWorldPartitionActorDescInstance* Desc)
            { LandscapeRefs.Emplace(WP,Desc->GetGuid()); return true; });
    for(TActorIterator<AActor> It(World);It && !Aborted;++It) ExportActor(*It);
    if(!Selected)
    {
        if(UWorldPartition* WP=World->GetWorldPartition())
        {
            FWorldPartitionHelpers::FForEachActorWithLoadingParams Load;
            Load.bGCPerActor=true; Load.bKeepReferences=false;
            Load.FilterActorDesc=[](const FWorldPartitionActorDesc* Desc)
            {return Desc && !IsBlockingVolumeClass(Desc->GetActorNativeClass());};
            FWorldPartitionHelpers::ForEachActorWithLoading(WP,[&](const FWorldPartitionActorDescInstance* Desc)
            { if(Aborted) return false; ExportActor(Desc->GetActor()); return !Aborted; },Load);
        }
        // Traditional streaming levels are visited one at a time and restored.
        for(ULevelStreaming* L:World->GetStreamingLevels())
        {
            if(Aborted) break;
            const bool Loaded=L->ShouldBeLoaded(),Visible=L->GetShouldBeVisibleFlag();
            L->SetShouldBeLoaded(true); World->FlushLevelStreaming(EFlushLevelStreamingType::Full);
            if(ULevel* Level=L->GetLoadedLevel()) for(AActor* Actor:Level->Actors) { if(Aborted) break; ExportActor(Actor); }
            L->SetShouldBeLoaded(Loaded); L->SetShouldBeVisible(Visible);
            World->FlushLevelStreaming(EFlushLevelStreamingType::Full);
        }
    }
    if(Aborted) return 8;
    if(Export.Instances.IsEmpty() && Export.Instancers.IsEmpty())
    { UE_LOG(LogTemp,Error,TEXT("No supported mesh placements in the export selection")); return 7; }
    if(FixtureSource && (FixtureSource->GetMeshDescription(0)->Triangles().Num()!=FixtureTriangles || FixtureSource->GetOutermost()->IsDirty()!=FixtureDirty))
    { UE_LOG(LogTemp,Error,TEXT("Source-asset mutation detected by native fixture")); return 9; }
    Obj Manifest=Object(); Manifest->SetNumberField(TEXT("schema_version"),1); Manifest->SetStringField(TEXT("map"),Map); Manifest->SetStringField(TEXT("engine"),FEngineVersion::Current().ToString());
    Manifest->SetBoolField(TEXT("export_skeletal_meshes"),ExportSkeletalMeshes);
    Manifest->SetObjectField(TEXT("materials"),Export.Materials); Manifest->SetObjectField(TEXT("textures"),Export.Textures); Manifest->SetObjectField(TEXT("meshes"),Export.Meshes);
    Manifest->SetArrayField(TEXT("instances"),Export.Instances); Manifest->SetArrayField(TEXT("instancers"),Export.Instancers); Manifest->SetArrayField(TEXT("issues"),Export.Issues); Manifest->SetArrayField(TEXT("notes"),Export.Notes);
    Manifest->SetArrayField(TEXT("decals"),Export.Decals);
    Manifest->SetArrayField(TEXT("lights"),Export.Lights); Manifest->SetArrayField(TEXT("cameras"),Export.Cameras);
    Export.Policy(Manifest);
    if(!Save(Manifest,Out/TEXT("manifest.json"))) return 4;
    UE_LOG(LogTemp,Display,TEXT("BRIDGE_COMPLETE: %d meshes, %d materials, %d instancer groups"),Export.Meshes->Values.Num(),Export.Materials->Values.Num(),Export.Instancers.Num());
    return 0;
}

int32 UUnrealUsdExtractCommandlet::Main(const FString& Params)
{
    int32 Count=0;
    return BridgeEditor::Extract(Params,[&](float,const FString& Actor)
    {
        ++Count;
        if(Count==1 || Count%20==0)
        {UE_LOG(LogTemp,Display,TEXT("BRIDGE EXTRACT PROGRESS: actor %d | %s"),Count,*Actor);}
        return true;
    });
}
