-- ============================================================================
--  ai-proxy 接入示例 —— GMod / FiveM（Lua）
--  作者：AWA　　本插件全由 DSH 开发
--
--  GMod 用 http.Post，FiveM 用 PerformHttpRequest。
--  下面的 AskAI 会自动判断在哪个环境里。
-- ============================================================================

local AI_URL   = "http://127.0.0.1:8787/v1/chat/completions"
local AI_TOKEN = "my-token-1"

local SYSTEM = "回答必须只有一行，格式：YES|理由。理由不超过 30 字。"

local function buildPayload(userText)
    local body = {
        model = "deepseek-chat",
        messages = {
            { role = "system", content = SYSTEM },
            { role = "user",   content = userText },
        },
        max_tokens = 100,
        temperature = 0.2,
    }

    -- GMod 和 FiveM 的 JSON 函数名不一样
    if util and util.TableToJSON then
        return util.TableToJSON(body)          -- GMod
    elseif json and json.encode then
        return json.encode(body)               -- FiveM
    end
    return nil
end

local function parseAnswer(raw)
    local obj
    if util and util.JSONToTable then
        obj = util.JSONToTable(raw)            -- GMod
    elseif json and json.decode then
        obj = json.decode(raw)                 -- FiveM
    end

    if not obj or not obj.choices or not obj.choices[1] then
        return nil
    end
    return obj.choices[1].message.content
end

--- 问 AI 一句话，异步返回。
--- @param userText string
--- @param onDone function(answer)  失败时 answer 为 nil
function AskAI(userText, onDone)
    local payload = buildPayload(userText)
    if not payload then
        if onDone then onDone(nil) end
        return
    end

    local headers = {
        ["Content-Type"]  = "application/json",
        ["Authorization"] = "Bearer " .. AI_TOKEN,
    }

    local function handle(code, raw)
        if code ~= 200 then
            print("[AI] HTTP " .. tostring(code) .. "  " .. tostring(raw))
            if onDone then onDone(nil) end
            return
        end
        local ans = parseAnswer(raw)
        if onDone then onDone(ans) end
    end

    -- GMod
    if http and http.Post then
        http.Post(AI_URL, payload, function(body, size, hdrs, code)
            handle(code, body)
        end, headers)
        return
    end

    -- FiveM / RedM
    if PerformHttpRequest then
        PerformHttpRequest(AI_URL, function(code, body, hdrs)
            handle(code, body)
        end, "POST", payload, headers)
        return
    end

    print("[AI] 当前环境没有可用的 HTTP 函数")
    if onDone then onDone(nil) end
end

-- ── 用法 ──
--[[
AskAI("这个玩家命中率 92%，爆头率 88%，正常吗", function(ans)
    if ans then
        print("[AI] " .. ans)
        -- GMod: 解析 YES|理由
        local ok, reason = string.match(ans, "^([^|]+)|(.+)$")
        if ok then print("判定: " .. ok .. "  理由: " .. reason) end
    else
        print("[AI] 没有拿到回答")
    end
end)
]]