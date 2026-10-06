// ============================================================================
//  ai-proxy 接入示例 —— Minecraft（Forge / Fabric / Bukkit / Spigot / Paper）
//  作者：AWA　　本插件全由 DSH 开发
//
//  需要 Java 11 或更新（java.net.http.HttpClient）。
// ============================================================================

package com.example.aiproxy;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.function.Consumer;

public final class AiClient {

    private static final String ENDPOINT = "http://127.0.0.1:8787/v1/chat/completions";
    private static final String TOKEN    = "my-token-1";   // 令牌，不是真 Key
    private static final String MODEL    = "deepseek-chat";

    private static final String SYSTEM =
            "回答必须只有一行，格式：YES|理由。理由不超过 30 字。";

    private static final HttpClient HTTP = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    private AiClient() { }

    /** 问一句，返回纯文本。失败返回 null。★ 不要在服务端主线程直接调用。 */
    public static String ask(String userText) {
        String body = "{"
                + "\"model\":" + json(MODEL) + ","
                + "\"messages\":["
                +   "{\"role\":\"system\",\"content\":" + json(SYSTEM) + "},"
                +   "{\"role\":\"user\",\"content\":" + json(userText) + "}"
                + "],"
                + "\"max_tokens\":100,"
                + "\"temperature\":0.2"
                + "}";

        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(ENDPOINT))
                .timeout(Duration.ofSeconds(60))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + TOKEN)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        try {
            HttpResponse<String> resp = HTTP.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) {
                System.out.println("[AI] HTTP " + resp.statusCode() + "  "
                        + truncate(resp.body(), 200));
                return null;
            }
            return extractContent(resp.body());
        } catch (Exception e) {
            System.out.println("[AI] 请求失败: " + e.getMessage());
            return null;
        }
    }

    /**
     * 异步版 —— 服务端插件必须用这个。
     * Minecraft 服务端不能阻塞主线程，否则服务器会卡住。
     */
    public static CompletableFuture<String> askAsync(String userText) {
        return CompletableFuture.supplyAsync(() -> ask(userText));
    }

    /** 异步 + 回调。回调里要注意切回主线程再动游戏状态。 */
    public static void askAsync(String userText, Consumer<String> onDone) {
        askAsync(userText).thenAccept(onDone);
    }

    // ── 工具 ──

    private static String json(String s) {
        if (s == null) return "\"\"";
        StringBuilder sb = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"':  sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n");  break;
                case '\r': sb.append("\\r");  break;
                case '\t': sb.append("\\t");  break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
            }
        }
        return sb.append('"').toString();
    }

    private static String extractContent(String json) {
        String key = "\"content\":";
        int i = json.indexOf(key);
        if (i < 0) return null;
        i += key.length();
        while (i < json.length() && json.charAt(i) == ' ') i++;
        if (i >= json.length() || json.charAt(i) != '"') return null;
        i++;

        StringBuilder sb = new StringBuilder();
        while (i < json.length()) {
            char c = json.charAt(i);
            if (c == '\\' && i + 1 < json.length()) {
                char n = json.charAt(++i);
                switch (n) {
                    case 'n':  sb.append('\n'); break;
                    case 'r':  sb.append('\r'); break;
                    case 't':  sb.append('\t'); break;
                    case '"':  sb.append('"');  break;
                    case '\\': sb.append('\\'); break;
                    case 'u':
                        if (i + 4 < json.length()) {
                            sb.append((char) Integer.parseInt(json.substring(i + 1, i + 5), 16));
                            i += 4;
                        }
                        break;
                    default: sb.append(n);
                }
            } else if (c == '"') {
                break;
            } else {
                sb.append(c);
            }
            i++;
        }
        return sb.toString();
    }

    private static String truncate(String s, int n) {
        if (s == null) return "";
        return s.length() <= n ? s : s.substring(0, n) + "...";
    }

    // ── 用法 ──
    // AiClient.askAsync("这个玩家命中率 92%，正常吗", ans -> {
    //     if (ans == null) return;
    //     String[] parts = ans.split("\\|", 2);
    //     String verdict = parts[0];
    //     String reason  = parts.length > 1 ? parts[1] : "";
    //     Bukkit.getScheduler().runTask(plugin, () -> {
    //         // 这里回到主线程，可以安全操作游戏状态
    //         Bukkit.broadcastMessage("[AI] " + verdict + " —— " + reason);
    //     });
    // });
}