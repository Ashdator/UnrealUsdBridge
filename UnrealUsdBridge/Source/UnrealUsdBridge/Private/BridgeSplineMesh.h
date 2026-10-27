#pragma once

#include "Components/SplineMeshComponent.h"

namespace BridgeSpline
{
    // Input is the built static-mesh local position, before component/world
    // transform. CalcSliceTransform handles bounds, Hermite tangents, axis,
    // roll, offset, scale interpolation and custom boundary extrapolation.
    inline bool Deform(const USplineMeshComponent* Spline,const FVector3f& Position,
        const FVector3f& Normal,FVector3f& OutPosition,FVector3f& OutNormal)
    {
        const auto Axis=Spline->GetForwardAxis();
        const FTransform Slice=Spline->CalcSliceTransform(USplineMeshComponent::GetAxisValueRef(Position,Axis));
        if(Slice.ContainsNaN()) return false;
        FVector CrossSection(Position);USplineMeshComponent::GetAxisValueRef(CrossSection,Axis)=0;
        OutPosition=FVector3f(Slice.TransformPosition(CrossSection));
        // The renderer's SplineMeshCalcSliceRot uses rotation plus scale signs,
        // not taper magnitudes. Apply it exactly once per exported corner.
        const FVector Scale=Slice.GetScale3D();
        const FVector Signs(Scale.X<0?-1:1,Scale.Y<0?-1:1,Scale.Z<0?-1:1);
        OutNormal=FVector3f(Slice.TransformVectorNoScale(FVector(Normal)*Signs).GetSafeNormal());
        return !OutPosition.ContainsNaN() && !OutNormal.ContainsNaN() && !OutNormal.IsNearlyZero();
    }

    inline bool ReverseWinding(const USplineMeshComponent* Spline)
    {
        // Match FSplineMeshSceneProxy::SetupMeshBatchForSpline culling.
        const FVector2D Scale=Spline->GetStartScale();
        return (Scale.X<0)!=(Scale.Y<0);
    }
}
