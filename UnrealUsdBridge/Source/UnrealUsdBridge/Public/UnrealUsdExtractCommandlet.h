#pragma once
#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "UnrealUsdExtractCommandlet.generated.h"

UCLASS()
class UNREALUSDBRIDGE_API UUnrealUsdExtractCommandlet : public UCommandlet
{
    GENERATED_BODY()
public:
    UUnrealUsdExtractCommandlet();
    virtual int32 Main(const FString& Params) override;
};
