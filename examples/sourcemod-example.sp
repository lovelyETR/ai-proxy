// ============================================================================
//  ai-proxy 接入示例 —— 起源引擎 / SourceMod（SourcePawn）
//  作者：AWA　　本插件全由 DSH 开发
//
//  需要 SourceMod 1.11 或更新（自带 httpclient）。
//  老的 1.10 要装 SteamWorks 或 System2 扩展。
// ============================================================================

#include <sourcemod>
#include <httpclient>

#define AI_URL   "http://127.0.0.1:8787/v1/chat/completions"
#define AI_TOKEN "my-token-1"

public Plugin myinfo =
{
    name        = "AI 接口示例",
    author      = "AWA",
    description = "演示怎么从 SourceMod 调 ai-proxy",
    version     = "1.0"
};

public void OnPluginStart()
{
    RegConsoleCmd("sm_ai", Cmd_Ai, "问 AI 一句话");
}

public Action Cmd_Ai(int client, int args)
{
    char text[256];
    if (args < 1)
    {
        GetCmdArgString(text, sizeof(text));
    }
    else
    {
        GetCmdArgString(text, sizeof(text));
    }

    if (text[0] == '\0')
    {
        ReplyToCommand(client, "[AI] 用法: sm_ai <要问的话>");
        return Plugin_Handled;
    }

    ReplyToCommand(client, "[AI] 正在问...");

    // 用极简格式，省掉 JSON 解析
    char body[1024];
    Format(body, sizeof(body),
        "{\"model\":\"deepseek-chat\",\"messages\":["
        "{\"role\":\"system\",\"content\":\"回答必须只有一行，格式：YES|理由。理由不超过 30 字。\"},"
        "{\"role\":\"user\",\"content\":\"%s\"}"
        "],\"max_tokens\":100,\"temperature\":0.2}", text);

    HTTPClient hc = new HTTPClient(AI_URL);
    hc.SetHeader("Content-Type", "application/json");
    hc.SetHeader("Authorization", "Bearer " AI_TOKEN);

    DataPack pack = new DataPack();
    pack.WriteCell(GetClientUserId(client));

    hc.Post(body, OnAiResponse, pack);
    return Plugin_Handled;
}

void OnAiResponse(HTTPStatus status, const char[] data, any value, const char[] error)
{
    DataPack pack = view_as<DataPack>(value);
    pack.Reset();
    int userid = pack.ReadCell();
    delete pack;

    int client = GetClientOfUserId(userid);

    if (status != HTTPStatus_OK)
    {
        PrintToServer("[AI] 请求失败: %s", error);
        if (client > 0) ReplyToCommand(client, "[AI] 请求失败: %s", error);
        return;
    }

    char content[512];
    if (!ExtractJsonString(data, "content", content, sizeof(content)))
    {
        PrintToServer("[AI] 解析失败: %s", data);
        return;
    }

    PrintToServer("[AI] 回答: %s", content);
    if (client > 0) ReplyToCommand(client, "[AI] %s", content);
}

// 简易 JSON 字符串提取 —— 够用就行，不用引 JSON 库
bool ExtractJsonString(const char[] json, const char[] key, char[] out, int maxlen)
{
    char needle[64];
    Format(needle, sizeof(needle), "\"%s\":", key);

    int pos = StrContains(json, needle);
    if (pos < 0) return false;
    pos += strlen(needle);

    while (json[pos] == ' ') pos++;
    if (json[pos] != '"') return false;
    pos++;

    int i = 0;
    while (json[pos] != '"' && json[pos] != '\0' && i < maxlen - 1)
    {
        if (json[pos] == '\\' && json[pos + 1] != '\0')
        {
            pos++;
            if (json[pos] == 'n') out[i++] = '\n';
            else if (json[pos] == 't') out[i++] = '\t';
            else out[i++] = json[pos];
        }
        else
        {
            out[i++] = json[pos];
        }
        pos++;
    }
    out[i] = '\0';
    return true;
}