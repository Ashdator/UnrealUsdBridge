#pragma once
#include "CoreMinimal.h"

namespace BridgeEditor
{
    // Game-thread only. Current-world mode reads unsaved actor placements.
    // False from Progress cancels between actors without publishing a manifest.
    UNREALUSDBRIDGE_API int32 Extract(const FString& Params,
        TFunction<bool(float,const FString&)> Progress = {});
}
