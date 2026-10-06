// ============================================================================
//  ai-proxy 接入示例 —— 虚幻引擎 C++
//  作者：AWA　　本插件全由 DSH 开发
//
//  在 Build.cs 里加依赖：
//      PrivateDependencyModuleNames.AddRange(new string[] {
//          "HTTP", "Json", "JsonUtilities"
//      });
// ============================================================================

#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace AiProxy
{
    static const FString Endpoint = TEXT("http://127.0.0.1:8787/v1/chat/completions");
    static const FString Token    = TEXT("my-token-1");
    static const FString Model    = TEXT("deepseek-chat");

    // 让模型输出极简格式，省掉 JSON 解析
    static const FString SystemPrompt =
        TEXT("回答必须只有一行，格式：YES|理由。理由不超过 30 字。");

    /**
     * 问 AI 一句话。
     * @param UserText  要问的内容
     * @param OnDone    回调，参数是回答文本（失败为空字符串）
     */
    inline void Ask(
        const FString& UserText,
        TFunction<void(const FString&)> OnDone)
    {
        // ── 拼 JSON ──
        TSharedPtr<FJsonObject> Root = MakeShareable(new FJsonObject);
        Root->SetStringField(TEXT("model"), Model);
        Root->SetNumberField(TEXT("max_tokens"), 100);
        Root->SetNumberField(TEXT("temperature"), 0.2);

        TArray<TSharedPtr<FJsonValue>> Msgs;

        {
            TSharedPtr<FJsonObject> M = MakeShareable(new FJsonObject);
            M->SetStringField(TEXT("role"), TEXT("system"));
            M->SetStringField(TEXT("content"), SystemPrompt);
            Msgs.Add(MakeShareable(new FJsonValueObject(M)));
        }
        {
            TSharedPtr<FJsonObject> M = MakeShareable(new FJsonObject);
            M->SetStringField(TEXT("role"), TEXT("user"));
            M->SetStringField(TEXT("content"), UserText);
            Msgs.Add(MakeShareable(new FJsonValueObject(M)));
        }

        Root->SetArrayField(TEXT("messages"), Msgs);

        FString Body;
        {
            TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Body);
            FJsonSerializer::Serialize(Root.ToSharedRef(), Writer);
        }

        // ── 发请求 ──
        TSharedRef<IHttpRequest> Req = FHttpModule::Get().CreateRequest();
        Req->SetURL(Endpoint);
        Req->SetVerb(TEXT("POST"));
        Req->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
        Req->SetHeader(TEXT("Authorization"), TEXT("Bearer ") + Token);
        Req->SetContentAsString(Body);

        Req->OnProcessRequestComplete().BindLambda(
            [OnDone](FHttpRequestPtr, FHttpResponsePtr Resp, bool bOk)
            {
                if (!bOk || !Resp.IsValid())
                {
                    UE_LOG(LogTemp, Warning, TEXT("[AI] 请求失败"));
                    if (OnDone) OnDone(FString());
                    return;
                }

                const int32 Code = Resp->GetResponseCode();
                if (Code != 200)
                {
                    UE_LOG(LogTemp, Warning, TEXT("[AI] HTTP %d  %s"),
                        Code, *Resp->GetContentAsString().Left(200));
                    if (OnDone) OnDone(FString());
                    return;
                }

                // ── 解析 ──
                TSharedPtr<FJsonObject> Json;
                TSharedRef<TJsonReader<>> Reader =
                    TJsonReaderFactory<>::Create(Resp->GetContentAsString());

                if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
                {
                    if (OnDone) OnDone(FString());
                    return;
                }

                const TArray<TSharedPtr<FJsonValue>>* Choices = nullptr;
                if (!Json->TryGetArrayField(TEXT("choices"), Choices) || Choices->Num() == 0)
                {
                    if (OnDone) OnDone(FString());
                    return;
                }

                TSharedPtr<FJsonObject> First = (*Choices)[0]->AsObject();
                if (!First.IsValid())
                {
                    if (OnDone) OnDone(FString());
                    return;
                }

                TSharedPtr<FJsonObject> Msg = First->GetObjectField(TEXT("message"));
                FString Content = Msg.IsValid() ? Msg->GetStringField(TEXT("content")) : FString();

                UE_LOG(LogTemp, Log, TEXT("[AI] %s"), *Content);
                if (OnDone) OnDone(Content);
            });

        Req->ProcessRequest();
    }
}

// ── 用法 ──
// AiProxy::Ask(TEXT("这个玩家命中率 92%，正常吗"), [](const FString& Ans)
// {
//     if (!Ans.IsEmpty())
//     {
//         // Ans 形如 "YES|看起来正常"
//         FString Verdict, Reason;
//         if (Ans.Split(TEXT("|"), &Verdict, &Reason))
//         {
//             UE_LOG(LogTemp, Log, TEXT("判定=%s 理由=%s"), *Verdict, *Reason);
//         }
//     }
// });