// ============================================================================
//  ai-proxy 接入示例 —— Unity / BepInEx / MelonLoader / RimWorld / 任何 C# 插件
//  作者：AWA　　本插件全由 DSH 开发
//
//  这个文件是独立的，不依赖任何插件框架，可以直接抄进你的项目。
//  放在 Unity 里时，注意回调要切回主线程（下面有说明）。
// ============================================================================

using System;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;

namespace AiProxy
{
    public static class AiClient
    {
        // ── 改这两行 ──
        private const string Endpoint = "http://127.0.0.1:8787/v1/chat/completions";
        private const string Token    = "my-token-1";     // 令牌，不是真 Key
        private const string Model    = "deepseek-chat";

        // 让模型输出极简格式，省掉 JSON 解析
        private const string DefaultSystem =
            "你是一个审核助手。回答必须只有一行，格式：YES|理由。理由不超过 30 字。";

        private static readonly HttpClient Http = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(60)
        };

        /// <summary>问一句，返回纯文本。失败返回 null。</summary>
        public static async Task<string> AskAsync(string userText, string system = null)
        {
            string payload = "{"
                + "\"model\":" + Json(Model) + ","
                + "\"messages\":["
                +   "{\"role\":\"system\",\"content\":" + Json(system ?? DefaultSystem) + "},"
                +   "{\"role\":\"user\",\"content\":" + Json(userText) + "}"
                + "],"
                + "\"max_tokens\":100,"
                + "\"temperature\":0.2"
                + "}";

            try
            {
                using (var req = new HttpRequestMessage(HttpMethod.Post, Endpoint))
                {
                    req.Headers.Add("Authorization", "Bearer " + Token);
                    req.Content = new StringContent(payload, Encoding.UTF8, "application/json");

                    using (HttpResponseMessage resp = await Http.SendAsync(req).ConfigureAwait(false))
                    {
                        string body = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
                        if (!resp.IsSuccessStatusCode)
                        {
                            Log("[AI] HTTP " + (int)resp.StatusCode + "  " + Truncate(body, 200));
                            return null;
                        }
                        return ExtractContent(body);
                    }
                }
            }
            catch (Exception e)
            {
                Log("[AI] 请求失败: " + e.Message);
                return null;
            }
        }

        /// <summary>
        /// 同步版（会阻塞当前线程）。
        /// ★ 不要在游戏主线程调用 —— 会卡住游戏。用 AskAsync。
        /// </summary>
        public static string Ask(string userText, string system = null)
        {
            return AskAsync(userText, system).GetAwaiter().GetResult();
        }

        // ── 下面都是工具方法，不用改 ──

        /// <summary>把字符串转义成 JSON 字符串字面量。</summary>
        private static string Json(string s)
        {
            if (s == null) return "\"\"";
            var sb = new StringBuilder("\"");
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"':  sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n");  break;
                    case '\r': sb.Append("\\r");  break;
                    case '\t': sb.Append("\\t");  break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else sb.Append(c);
                        break;
                }
            }
            return sb.Append('"').ToString();
        }

        /// <summary>从响应 JSON 里抠出 choices[0].message.content。</summary>
        public static string ExtractContent(string json)
        {
            const string key = "\"content\":";
            int i = json.IndexOf(key, StringComparison.Ordinal);
            if (i < 0) return null;
            i += key.Length;
            while (i < json.Length && json[i] == ' ') i++;
            if (i >= json.Length || json[i] != '"') return null;
            i++;

            var sb = new StringBuilder();
            while (i < json.Length)
            {
                char c = json[i];
                if (c == '\\' && i + 1 < json.Length)
                {
                    char n = json[++i];
                    switch (n)
                    {
                        case 'n':  sb.Append('\n'); break;
                        case 'r':  sb.Append('\r'); break;
                        case 't':  sb.Append('\t'); break;
                        case '"':  sb.Append('"');  break;
                        case '\\': sb.Append('\\'); break;
                        case 'u':
                            if (i + 4 < json.Length)
                            {
                                sb.Append((char)Convert.ToInt32(json.Substring(i + 1, 4), 16));
                                i += 4;
                            }
                            break;
                        default: sb.Append(n); break;
                    }
                }
                else if (c == '"')
                {
                    break;
                }
                else
                {
                    sb.Append(c);
                }
                i++;
            }
            return sb.ToString();
        }

        private static string Truncate(string s, int n)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return s.Length <= n ? s : s.Substring(0, n) + "...";
        }

        private static void Log(string s)
        {
            // 换成你项目的日志方法
            Console.WriteLine(s);
        }
    }
}

// ============================================================================
//  Unity 用法（回调一定要切回主线程）
// ============================================================================
//
//  using System.Collections.Concurrent;
//  using System.Collections.Generic;
//  using UnityEngine;
//
//  public class AiExample : MonoBehaviour
//  {
//      private static readonly ConcurrentQueue<System.Action> MainQueue
//          = new ConcurrentQueue<System.Action>();
//
//      void Update()
//      {
//          while (MainQueue.TryDequeue(out var job)) job();
//      }
//
//      void Start()
//      {
//          RunAi("这个玩家命中率 92%，爆头率 88%，正常吗");
//      }
//
//      void RunAi(string text)
//      {
//          // 不在主线程等，避免卡住游戏
//          System.Threading.Tasks.Task.Run(async () =>
//          {
//              string ans = await AiProxy.AiClient.AskAsync(text);
//              // 切回主线程再用
//              MainQueue.Enqueue(() =>
//              {
//                  if (ans != null) Debug.Log("[AI] " + ans);
//              });
//          });
//      }
//  }