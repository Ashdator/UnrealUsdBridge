#pragma once
namespace Bridge
{
inline UWorld* MakeVisibilityFixture()
{
    UWorld* World=GEditor->NewMap();GEditor->SelectNone(false,true,false);
    auto* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
    auto* Cylinder=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    auto* Sphere=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    auto Spawn=[&](const TCHAR* Label,UStaticMesh* Mesh)
    {
        auto* Actor=World->SpawnActor<AStaticMeshActor>();Actor->SetActorLabel(Label);
        Actor->GetStaticMeshComponent()->SetStaticMesh(Mesh);return Actor;
    };
    auto* Visible=Spawn(TEXT("VisibleMesh"),Cube);
    auto* GameHidden=Spawn(TEXT("HiddenInGameActor"),Cylinder);GameHidden->SetActorHiddenInGame(true);
    auto* EditorHidden=Spawn(TEXT("HiddenInEditorActor"),Cylinder);EditorHidden->SetIsTemporarilyHiddenInEditor(true);
    auto* ComponentHidden=Spawn(TEXT("HiddenComponent"),Cylinder);ComponentHidden->GetStaticMeshComponent()->SetVisibility(false);
    auto* ComponentGameHidden=Spawn(TEXT("HiddenInGameComponent"),Cylinder);ComponentGameHidden->GetStaticMeshComponent()->SetHiddenInGame(true);
    auto* HiddenChild=NewObject<UStaticMeshComponent>(Visible,TEXT("HiddenChildMesh"));Visible->AddInstanceComponent(HiddenChild);
    HiddenChild->SetStaticMesh(Sphere);HiddenChild->SetVisibility(false);
    GEditor->SelectActor(Visible,true,false);GEditor->SelectActor(GameHidden,true,false);
    return World;
}
}
