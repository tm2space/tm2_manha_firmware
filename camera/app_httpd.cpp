// ============================================================================
// ESP32-CAM  –  HTTP Server & API Handlers
// ============================================================================

#include "app_httpd.h"
#include "web_ui.h"
#include <vector>
#include <Update.h>

// ── Logging ─────────────────────────────────────────────────────────────────

#if !ENABLE_SERIAL_LOG
NullPrint null_print;
#endif

static char log_buf[LOG_BUF_SIZE];
static size_t log_buf_pos = 0;

void log_flush()
{
    if (!hw.sd_ok || log_buf_pos == 0)
        return;

    File f = SDFS.open(LOG_FILE, FILE_APPEND);
    if (!f)
        return;

    if (f.size() >= MAX_LOG_BYTES)
    {
        f.close();
        f = SDFS.open(LOG_FILE, FILE_WRITE);
        if (!f)
            return;
    }

    f.write((const uint8_t *)log_buf, log_buf_pos);
    f.close();
    log_buf_pos = 0;
}

void log_send(const char *fmt, ...)
{
    char line[256];
    va_list args;
    va_start(args, fmt);
    int len = vsnprintf(line, sizeof(line), fmt, args);
    va_end(args);
    if (len <= 0)
        return;
    if ((size_t)len >= sizeof(line))
        len = sizeof(line) - 1;

    LOG_SERIAL.print(line);

    size_t remaining = LOG_BUF_SIZE - log_buf_pos;
    size_t to_copy   = ((size_t)len < remaining) ? (size_t)len : remaining;
    memcpy(log_buf + log_buf_pos, line, to_copy);
    log_buf_pos += to_copy;

    if (log_buf_pos >= LOG_BUF_SIZE - 64)
        log_flush();
}

// ── Helpers (file-local) ────────────────────────────────────────────────────

static String get_qp_name(httpd_req_t *req)
{
    size_t qlen = httpd_req_get_url_query_len(req) + 1;
    if (qlen <= 1 || qlen > 256)
        return "";
    char qbuf[256];
    httpd_req_get_url_query_str(req, qbuf, sizeof(qbuf));
    char v[128] = {0};
    httpd_query_key_value(qbuf, "name", v, sizeof(v));
    return String(v);
}

static String resolve_path(const String &n)
{
    if (n.startsWith(IMAGE_DIR))
        return n;
    return String(IMAGE_DIR) + "/" + n;
}

static esp_err_t send_json(httpd_req_t *req, JsonDocument &doc)
{
    String out;
    serializeJson(doc, out);
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, out.c_str(), out.length());
}

// ============================================================================
// Route Handlers
// ============================================================================

static esp_err_t handler_index(httpd_req_t *req)
{
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, INDEX_HTML, strlen(INDEX_HTML));
}

static esp_err_t handler_api_status(httpd_req_t *req)
{
    uint32_t count = 0;
    if (hw.sd_ok)
    {
        File root = SDFS.open(IMAGE_DIR);
        if (root && root.isDirectory())
        {
            while (File f = root.openNextFile())
            {
                count++;
                f.close();
            }
            root.close();
        }
    }
    double free_mb = hw.sd_ok ? (SDFS.totalBytes() - SDFS.usedBytes()) / 1048576.0 : 0;

    JsonDocument doc;
    doc["sd"]      = hw.sd_ok;
    doc["images"]  = count;
    doc["free_mb"] = serialized(String(free_mb, 1));
    return send_json(req, doc);
}

static esp_err_t handler_api_images(httpd_req_t *req)
{
    JsonDocument doc;
    JsonArray files = doc["files"].to<JsonArray>();

    if (hw.sd_ok)
    {
        File root = SDFS.open(IMAGE_DIR);
        if (root && root.isDirectory())
        {
            while (File e = root.openNextFile())
            {
                if (!e.isDirectory())
                {
                    JsonObject f = files.add<JsonObject>();
                    f["name"]    = String(e.name());
                    f["size"]    = e.size();
                }
                e.close();
            }
            root.close();
        }
    }
    return send_json(req, doc);
}

static esp_err_t handler_api_image(httpd_req_t *req)
{
    String name = get_qp_name(req);
    if (name.isEmpty())
    {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing ?name=");
        return ESP_FAIL;
    }
    File file = SDFS.open(resolve_path(name).c_str(), FILE_READ);
    if (!file)
    {
        httpd_resp_send_err(req, HTTPD_404_NOT_FOUND, "Not found");
        return ESP_FAIL;
    }
    httpd_resp_set_type(req, "image/jpeg");
    char disp[192];
    snprintf(disp, sizeof(disp), "inline; filename=\"%s\"", name.c_str());
    httpd_resp_set_hdr(req, "Content-Disposition", disp);
    uint8_t buf[2048];
    while (file.available())
    {
        size_t n = file.read(buf, sizeof(buf));
        if (httpd_resp_send_chunk(req, (const char *)buf, n) != ESP_OK)
            break;
    }
    file.close();
    httpd_resp_send_chunk(req, NULL, 0);
    return ESP_OK;
}

static esp_err_t handler_api_capture(httpd_req_t *req)
{
    String fname;
    bool ok = capture_and_save(fname);

    JsonDocument doc;
    doc["ok"] = ok;
    if (ok)
        doc["filename"] = fname;
    else
        doc["error"] = "capture_failed";
    return send_json(req, doc);
}

static esp_err_t handler_api_delete_image(httpd_req_t *req)
{
    String name = get_qp_name(req);
    if (name.isEmpty())
    {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing ?name=");
        return ESP_FAIL;
    }

    JsonDocument doc;
    doc["ok"] = SDFS.remove(resolve_path(name).c_str());
    return send_json(req, doc);
}

static esp_err_t handler_api_clear(httpd_req_t *req)
{
    File root    = SDFS.open(IMAGE_DIR);
    uint32_t del = 0;
    if (root && root.isDirectory())
    {
        std::vector<String> names;
        while (File f = root.openNextFile())
        {
            if (!f.isDirectory())
                names.push_back(String(IMAGE_DIR) + "/" + f.name());
            f.close();
        }
        root.close();
        for (auto &p : names)
            if (SDFS.remove(p.c_str()))
                del++;
    }

    JsonDocument doc;
    doc["ok"]      = true;
    doc["deleted"] = del;
    return send_json(req, doc);
}

// ── Settings & Presets API ──────────────────────────────────────────────────

static esp_err_t handler_api_get_settings(httpd_req_t *req)
{
    JsonDocument doc;
    JsonObject obj = doc.to<JsonObject>();
    camSettingsToJson(cam_settings, obj);
    return send_json(req, doc);
}

static esp_err_t handler_api_post_settings(httpd_req_t *req)
{
    int total = req->content_len;
    if (total <= 0 || total > 768)
    {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Bad body");
        return ESP_FAIL;
    }
    char body[769];
    int received = 0;
    while (received < total)
    {
        int ret = httpd_req_recv(req, body + received, total - received);
        if (ret <= 0)
        {
            httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Recv fail");
            return ESP_FAIL;
        }
        received += ret;
    }
    body[total] = '\0';

    JsonDocument input;
    if (deserializeJson(input, body))
    {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON");
        return ESP_FAIL;
    }

    jsonToCamSettings(input.as<JsonObject>(), cam_settings);
    apply_settings();
    save_settings();

    JsonDocument doc;
    JsonObject obj = doc.to<JsonObject>();
    camSettingsToJson(cam_settings, obj);
    return send_json(req, doc);
}

static esp_err_t handler_api_reset_settings(httpd_req_t *req)
{
    reset_settings();

    JsonDocument doc;
    JsonObject obj = doc.to<JsonObject>();
    camSettingsToJson(cam_settings, obj);
    return send_json(req, doc);
}

static esp_err_t handler_api_presets(httpd_req_t *req)
{
    JsonDocument doc;
    JsonArray arr = doc.to<JsonArray>();
    for (int i = 0; i < NUM_PRESETS; i++)
    {
        JsonObject p  = arr.add<JsonObject>();
        p["name"]     = PRESETS[i].name;
        JsonObject s  = p["settings"].to<JsonObject>();
        camSettingsToJson(PRESETS[i].s, s);
    }
    return send_json(req, doc);
}

// ── Camera Info API ─────────────────────────────────────────────────────────

static esp_err_t handler_api_camera_info(httpd_req_t *req)
{
    JsonDocument doc;
    JsonObject obj = doc.to<JsonObject>();
    camInfoToJson(obj);
    return send_json(req, doc);
}

// ── Log API ─────────────────────────────────────────────────────────────────

static esp_err_t handler_api_get_logs(httpd_req_t *req)
{
    log_flush();

    size_t offset = 0;
    char qbuf[32] = {0};
    if (httpd_req_get_url_query_len(req) > 0)
    {
        httpd_req_get_url_query_str(req, qbuf, sizeof(qbuf));
        char val[16] = {0};
        if (httpd_query_key_value(qbuf, "offset", val, sizeof(val)) == ESP_OK)
            offset = (size_t)atol(val);
    }

    JsonDocument doc;

    if (!hw.sd_ok || !SDFS.exists(LOG_FILE))
    {
        doc["offset"] = 0;
        doc["size"]   = 0;
        doc["lines"]  = "";
        return send_json(req, doc);
    }

    File f = SDFS.open(LOG_FILE, FILE_READ);
    if (!f)
    {
        doc["offset"] = 0;
        doc["size"]   = 0;
        doc["lines"]  = "";
        return send_json(req, doc);
    }

    size_t fsize = f.size();

    if (offset > fsize)
        offset = 0;

    String lines;
    if (offset < fsize)
    {
        f.seek(offset);
        lines = f.readString();
    }
    f.close();

    doc["offset"] = fsize;
    doc["size"]   = fsize;
    doc["lines"]  = lines;
    return send_json(req, doc);
}

static esp_err_t handler_api_clear_logs(httpd_req_t *req)
{
    log_buf_pos = 0;
    if (hw.sd_ok && SDFS.exists(LOG_FILE))
        SDFS.remove(LOG_FILE);

    JsonDocument doc;
    doc["ok"] = true;
    return send_json(req, doc);
}

// ── OTA Firmware Update ─────────────────────────────────────────────────────

static esp_err_t handler_api_ota(httpd_req_t *req)
{
    int total = req->content_len;
    if (total <= 0)
    {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Empty body");
        return ESP_FAIL;
    }

    log_send("[OTA] Starting update (%d bytes)\n", total);

    if (!Update.begin(total))
    {
        log_send("[OTA] Not enough space\n");
        // drain remaining body so httpd doesn't re-trigger handler
        char drain[512];
        int left = total;
        while (left > 0) {
            int r = httpd_req_recv(req, drain, (left < (int)sizeof(drain)) ? left : (int)sizeof(drain));
            if (r <= 0) break;
            left -= r;
        }
        httpd_resp_set_hdr(req, "Connection", "close");
        JsonDocument doc;
        doc["ok"]    = false;
        doc["error"] = "Not enough space for update";
        return send_json(req, doc);
    }

    uint8_t buf[4096];
    int remaining = total;
    bool failed   = false;

    while (remaining > 0)
    {
        int to_read = (remaining < (int)sizeof(buf)) ? remaining : (int)sizeof(buf);
        int ret     = httpd_req_recv(req, (char *)buf, to_read);
        if (ret <= 0)
        {
            log_send("[OTA] Receive error\n");
            failed = true;
            break;
        }
        if (Update.write(buf, ret) != (size_t)ret)
        {
            log_send("[OTA] Write error\n");
            failed = true;
            break;
        }
        remaining -= ret;
    }

    JsonDocument doc;

    if (failed || !Update.end(true))
    {
        Update.abort();
        // drain any unsent body data
        while (remaining > 0) {
            int r = httpd_req_recv(req, (char *)buf, (remaining < (int)sizeof(buf)) ? remaining : (int)sizeof(buf));
            if (r <= 0) break;
            remaining -= r;
        }
        httpd_resp_set_hdr(req, "Connection", "close");
        log_send("[OTA] Update failed\n");
        doc["ok"]    = false;
        doc["error"] = "Update failed";
        return send_json(req, doc);
    }

    log_send("[OTA] Success, rebooting in 2s\n");
    doc["ok"]  = true;
    doc["msg"] = "Firmware updated. Rebooting...";
    esp_err_t result = send_json(req, doc);

    // Give the HTTP response time to reach the client, then reboot
    vTaskDelay(2000 / portTICK_PERIOD_MS);
    ESP.restart();

    return result;
}

// ── Method dispatchers ──────────────────────────────────────────────────────

static esp_err_t handler_image_dispatch(httpd_req_t *req)
{
    if (req->method == HTTP_GET)
        return handler_api_image(req);
    if (req->method == HTTP_DELETE)
        return handler_api_delete_image(req);
    httpd_resp_send_err(req, HTTPD_405_METHOD_NOT_ALLOWED, "Bad method");
    return ESP_FAIL;
}

static esp_err_t handler_images_dispatch(httpd_req_t *req)
{
    if (req->method == HTTP_GET)
        return handler_api_images(req);
    if (req->method == HTTP_DELETE)
        return handler_api_clear(req);
    httpd_resp_send_err(req, HTTPD_405_METHOD_NOT_ALLOWED, "Bad method");
    return ESP_FAIL;
}

// ── Captive Portal ──────────────────────────────────────────────────────────

#if ENABLE_CAPTIVE_PORTAL
static esp_err_t handler_captive_redirect(httpd_req_t *req, httpd_err_code_t err)
{
    httpd_resp_set_status(req, "302 Found");
    httpd_resp_set_hdr(req, "Location", "http://192.168.4.1/");
    httpd_resp_send(req, NULL, 0);
    return ESP_OK;
}
#endif

// ============================================================================
// Register routes & start server
// ============================================================================

static httpd_handle_t http_server = NULL;

void start_http_server()
{
    httpd_config_t config   = HTTPD_DEFAULT_CONFIG();
    config.max_uri_handlers = 16;
    config.stack_size       = 8192;

    if (httpd_start(&http_server, &config) != ESP_OK)
    {
        log_send("[HTTP] Server start FAILED\n");
        return;
    }

    httpd_uri_t u;

    u = {.uri = "/", .method = HTTP_GET, .handler = handler_index, .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);

    u = {.uri = "/api/status", .method = HTTP_GET, .handler = handler_api_status, .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);

    u = {.uri      = "/api/images",
         .method   = HTTP_GET,
         .handler  = handler_images_dispatch,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);
    u = {.uri      = "/api/images",
         .method   = HTTP_DELETE,
         .handler  = handler_images_dispatch,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);

    u = {.uri      = "/api/image",
         .method   = HTTP_GET,
         .handler  = handler_image_dispatch,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);
    u = {.uri      = "/api/image",
         .method   = HTTP_DELETE,
         .handler  = handler_image_dispatch,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);

    u = {.uri      = "/api/capture",
         .method   = HTTP_POST,
         .handler  = handler_api_capture,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);

    u = {.uri      = "/api/settings",
         .method   = HTTP_GET,
         .handler  = handler_api_get_settings,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);
    u = {.uri      = "/api/settings",
         .method   = HTTP_POST,
         .handler  = handler_api_post_settings,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);
    u = {.uri      = "/api/presets",
         .method   = HTTP_GET,
         .handler  = handler_api_presets,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);
    u = {.uri      = "/api/settings/reset",
         .method   = HTTP_POST,
         .handler  = handler_api_reset_settings,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);

    u = {.uri      = "/api/camera/info",
         .method   = HTTP_GET,
         .handler  = handler_api_camera_info,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);

    u = {.uri      = "/api/logs",
         .method   = HTTP_GET,
         .handler  = handler_api_get_logs,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);
    u = {.uri      = "/api/logs",
         .method   = HTTP_DELETE,
         .handler  = handler_api_clear_logs,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);

    u = {.uri      = "/api/ota",
         .method   = HTTP_POST,
         .handler  = handler_api_ota,
         .user_ctx = NULL};
    httpd_register_uri_handler(http_server, &u);

#if ENABLE_CAPTIVE_PORTAL
    httpd_register_err_handler(http_server, HTTPD_404_NOT_FOUND, handler_captive_redirect);
#endif

    log_send("[HTTP] Server started on port 80\n");
}
