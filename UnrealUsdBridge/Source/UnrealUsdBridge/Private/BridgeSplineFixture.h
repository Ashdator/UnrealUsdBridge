#pragma once

// Small in-memory acceptance fixture. Only invoked by -BridgeTestSplines;
// does not save a map, mesh, material or actor into the source project.
namespace Bridge
{
inline UWorld* MakeSplineFixture(const FString& Out,const FString& Params)
{
    UWorld* World=GEditor->NewMap();
    auto MakeMaterial=[](const TCHAR* Name,FLinearColor Color)
    {
        auto* M=NewObject<UMaterial>(GetTransientPackage(),Name);
        auto* C=NewObject<UMaterialExpressionConstant3Vector>(M);C->Constant=Color;
        M->GetExpressionCollection().AddExpression(C);M->GetExpressionInputForProperty(MP_BaseColor)->Connect(0,C);
        return M;
    };
    UMaterial* Red=MakeMaterial(TEXT("SplineRed"),FLinearColor(.8,.1,.1));
    UMaterial* Green=MakeMaterial(TEXT("SplineGreen"),FLinearColor(.1,.8,.1));
    UMaterial* Blue=MakeMaterial(TEXT("SplineOverrideBlue"),FLinearColor(.1,.1,.8));
    Obj Expectations=Object();Arr Cases;
    GEditor->SelectNone(false,true,false);
    for(int32 Axis=0;Axis<3;++Axis)
    {
        FMeshDescription D;FStaticMeshAttributes Attr(D);Attr.Register();
        auto UV=Attr.GetVertexInstanceUVs();UV.SetNumChannels(2);
        auto Positions=Attr.GetVertexPositions();auto Normals=Attr.GetVertexInstanceNormals();
        auto Tangents=Attr.GetVertexInstanceTangents();auto Signs=Attr.GetVertexInstanceBinormalSigns();auto Colors=Attr.GetVertexInstanceColors();
        FPolygonGroupID Groups[2]={D.CreatePolygonGroup(),D.CreatePolygonGroup()};
        Attr.GetPolygonGroupMaterialSlotNames()[Groups[0]]=TEXT("Red");Attr.GetPolygonGroupMaterialSlotNames()[Groups[1]]=TEXT("Green");
        const FVector2f Ring[4]={{-2,-1},{2,-1},{2,1},{-2,1}};
        const FVector2f FaceNormals[4]={{0,-1},{1,0},{0,1},{-1,0}};
        int32 UID=0;
        for(int32 Segment=0;Segment<16;++Segment) for(int32 Face=0;Face<4;++Face)
        {
            const int32 Pattern[6]={0,1,2,0,2,3};
            for(int32 Tri=0;Tri<2;++Tri)
            {
                TArray<FVertexInstanceID> Corners;
                for(int32 C=0;C<3;++C)
                {
                    const int32 Corner=Pattern[Tri*3+C];
                    const bool End=Corner==1 || Corner==2;const bool Next=Corner>=2;
                    const FVector2f R=Ring[(Face+(Next?1:0))%4];
                    FVector3f P(0),N(0),T(0);P[Axis]=(Segment+(End?1:0))*6.25f;
                    P[(Axis+1)%3]=R.X;P[(Axis+2)%3]=R.Y;
                    N[(Axis+1)%3]=FaceNormals[Face].X;N[(Axis+2)%3]=FaceNormals[Face].Y;T[Axis]=1;
                    FVertexID V=D.CreateVertex();Positions[V]=P;
                    FVertexInstanceID VI=D.CreateVertexInstance(V);Corners.Add(VI);
                    Normals[VI]=N;Tangents[VI]=T;Signs[VI]=1;Colors[VI]=FVector4f(.2,.4,.6,1);
                    UV.Set(VI,0,FVector2f(P[Axis]/100.f,Next?1:0));
                    UV.Set(VI,1,FVector2f(float(UID++),Face));
                }
                D.CreateTriangle(Groups[Face%2],Corners);
            }
        }
        UStaticMesh* Mesh=NewObject<UStaticMesh>(GetTransientPackage(),*FString::Printf(TEXT("SplineSource%d"),Axis));
        auto& Settings=Mesh->AddSourceModel().BuildSettings;
        Settings.bRecomputeNormals=false;Settings.bRecomputeTangents=false;Settings.bGenerateLightmapUVs=false;
        Settings.BuildScale3D=FVector(1.25,.75,1.5); // Test build scale before deformation.
        Mesh->CreateMeshDescription(0,D);
        Mesh->GetStaticMaterials().Add(FStaticMaterial(Red,TEXT("Red"),TEXT("Red")));
        Mesh->GetStaticMaterials().Add(FStaticMaterial(Green,TEXT("Green"),TEXT("Green")));
        FBox Box(ForceInit);for(FVertexID V:D.Vertices().GetElementIDs())Box+=FVector(Positions[V])*Settings.BuildScale3D;
        Mesh->SetExtendedBounds(FBoxSphereBounds(Box));
        const int32 TrianglesBefore=Mesh->GetMeshDescription(0)->Triangles().Num();
        for(int32 Variant=0;Variant<2;++Variant)
        {
            AActor* Actor=World->SpawnActor<AActor>();Actor->SetActorLabel(FString::Printf(TEXT("CurvedRope_%d_%d"),Axis,Variant));
            auto* Spline=NewObject<USplineMeshComponent>(Actor,TEXT("SplineRope"));
            Actor->SetRootComponent(Spline);Actor->AddInstanceComponent(Spline);Spline->SetStaticMesh(Mesh);
            Spline->SetForwardAxis(static_cast<ESplineMeshAxis::Type>(Axis),false);
            Spline->SetBoundaryMin(-10,false);Spline->SetBoundaryMax(140,false);
            Spline->SetStartAndEnd(FVector(10,20,30),FVector(200,Variant?100:250,0),FVector(300,120,60),FVector(160,-100,20),false);
            Spline->SetStartScale(FVector2D(Variant?-1:1,.5),false);Spline->SetEndScale(FVector2D(Variant?-1.5:1.5,2),false);
            Spline->SetStartRoll(.2,false);Spline->SetEndRoll(.9,false);
            Spline->SetStartOffset(FVector2D(2,-3),false);Spline->SetEndOffset(FVector2D(-4,5),false);
            Spline->bSmoothInterpRollScale=true;Spline->SetSplineUpDir(FVector::UpVector,false);
            Spline->SetMaterial(1,Blue);
            Spline->SetWorldTransform(FTransform(FRotator(10,35,5),FVector(500,Axis*200,100),FVector(2,.5,1.25)));
            if(Variant) Spline->SetVisibility(false);
            if(Axis==0 && Variant==0) GEditor->SelectActor(Actor,true,false);
            // Independent position oracle: Unreal's mesh-merge deformation on
            // a built-source copy. Each triangle has distinct vertex instances.
            FMeshDescription Built=D;FStaticMeshOperations::ApplyTransform(Built,FTransform(FQuat::Identity,FVector::ZeroVector,Settings.BuildScale3D));
            Spline->PropagateSplineDeformationToMesh(Built);
            FStaticMeshConstAttributes Expected(Built);Arr Vertices;
            for(FVertexInstanceID VI:Built.VertexInstances().GetElementIDs())
            {
                Obj E=Object();const FVector3f P=Expected.GetVertexPositions()[Built.GetVertexInstanceVertex(VI)];
                E->SetNumberField(TEXT("id"),Expected.GetVertexInstanceUVs().Get(VI,1).X);
                E->SetArrayField(TEXT("position"),Vec({P.X,P.Y,P.Z}));Vertices.Add(V(E));
            }
            Obj Case=Object();Case->SetStringField(TEXT("component"),Spline->GetPathName());Case->SetArrayField(TEXT("vertices"),Vertices);
            Case->SetArrayField(TEXT("matrix"),Matrix(Spline->GetComponentTransform()));Case->SetBoolField(TEXT("mirrored"),Variant!=0);
            Cases.Add(V(Case));
        }
        if(Mesh->GetMeshDescription(0)->Triangles().Num()!=TrianglesBefore)
            UE_LOG(LogTemp,Fatal,TEXT("Spline fixture source changed"));
    }
    // Even volumes with a custom static mesh component must be skipped as a
    // complete actor, rather than accidentally exporting the child mesh.
    for(bool Camera:{false,true})
    {
        UClass* Class=Camera?ACameraBlockingVolume::StaticClass():ABlockingVolume::StaticClass();
        AActor* Blocker=World->SpawnActor<AActor>(Class);
        Blocker->SetActorLabel(Camera?TEXT("CameraBlockingVolume_DO_NOT_EXPORT"):TEXT("BlockingVolume_DO_NOT_EXPORT"));
        auto* Decoy=NewObject<UStaticMeshComponent>(Blocker,TEXT("VolumeDecoyMesh"));Blocker->AddInstanceComponent(Decoy);
        Decoy->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube")));
        if(FParse::Param(*Params,TEXT("BridgeTestOnlyBlockingSelection"))) GEditor->SelectActor(Blocker,true,false);
    }
    if(FParse::Param(*Params,TEXT("BridgeTestOnlyBlockingSelection")))
    {
        TArray<AActor*> Remove;
        for(FSelectionIterator It(*GEditor->GetSelectedActors());It;++It)
            if(auto* Actor=Cast<AActor>(*It)) if(!IsBlockingVolumeClass(Actor->GetClass())) Remove.Add(Actor);
        for(AActor* Actor:Remove) GEditor->SelectActor(Actor,false,false);
    }
    if(FParse::Param(*Params,TEXT("BridgeTestComponentSelection")))
        for(FSelectionIterator It(*GEditor->GetSelectedActors());It;++It)
            if(auto* Actor=Cast<AActor>(*It)) GEditor->SelectComponent(Actor->GetRootComponent(),true,false);
    Expectations->SetArrayField(TEXT("cases"),Cases);Save(Expectations,Out/TEXT("spline-expectations.json"));
    return World;
}
}
