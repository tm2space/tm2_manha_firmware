// ============================================================================
// ESP32-CAM  –  WiFi AP Image Server
// ============================================================================
//
// Features:
//   - WiFi Access-Point with configurable SSID / password
//   - Web gallery UI served from flash (PROGMEM)
//   - HTTP/JSON API for listing, viewing, capturing, and deleting images
//   - SD card storage (SPI for XIAO, SD_MMC for AI-Thinker / others)
//   - Serial command interface for Satkit Pico integration
//
// Board selection:
//   Uncomment exactly ONE camera model in board_config.h before compiling.
//   The default is CAMERA_MODEL_AI_THINKER.
// ============================================================================

#include "esp_camera.h"
#include <WiFi.h>
#include <SPI.h>
#include <time.h>
#include "soc/soc.h"          // WRITE_PERI_REG / brownout
#include "soc/rtc_cntl_reg.h" // RTC_CNTL_BROWN_OUT_REG
#include "esp_pm.h"           // DFS (dynamic frequency scaling)
#include "esp_sleep.h"        // light sleep wake sources
#include "driver/gpio.h"      // direct PWDN drive
#include "driver/uart.h"      // UART wake threshold
#include "esp_crc.h"          // esp_crc32_le for frame CRC
#include "nvs_flash.h"        // nvs_flash_erase for factory reset

#include <Preferences.h>

#include "app_httpd.h"

#if ENABLE_CAPTIVE_PORTAL
#include <DNSServer.h>
#endif

#if ENABLE_MDNS
#include <ESPmDNS.h>
#endif

// ── Configuration ───────────────────────────────────────────────────────────

const char *IMAGE_DIR = "/images";

// SD_MMC pin overrides (only for ESP32-S3 GPIO-matrix boards using SD_MMC)
#if !USE_SD_SPI && defined(SOC_SDMMC_USE_GPIO_MATRIX) && !defined(BOARD_HAS_SDMMC)
static const int SD_MMC_CLK_PIN = 39;
static const int SD_MMC_CMD_PIN = 40;
static const int SD_MMC_D0_PIN  = 47;
#endif

#if !USE_SD_SPI
static const bool SD_MMC_1BIT_MODE = true;
#endif

// ── Camera Settings ─────────────────────────────────────────────────────────

static Preferences prefs;
CamSettings cam_settings;

// Named presets — index 0 is the default applied on first boot
// Struct field order: framesize, quality, brightness, contrast, saturation,
//   special_effect, wb_mode, awb, awb_gain, aec, aec2, ae_level,
//   agc, agc_gain, gainceiling, bpc, wpc, raw_gma, lenc,
//   hmirror, vflip
//
// gainceiling: 0=2x, 1=4x, 2=8x, 3=16x, 4=32x, 5=64x, 6=128x
const Preset PRESETS[] = {
    //                  fs               q  br  co  sa  fx wb  awb ag aec ae2 ael agc  ag gc bpc wpc gma len hm vf
    {"Default",      {FRAMESIZE_SVGA,  12,  0,  0,  0,  0, 0,  1, 1,  1, 1,  0,  1,  0, 2,  1,  1,  1,  1, 0, 1}},
    {"High Quality", {FRAMESIZE_UXGA,  10,  0,  1,  0,  0, 0,  1, 1,  1, 1,  0,  1,  0, 2,  1,  1,  1,  1, 0, 1}},
    {"Low Light",    {FRAMESIZE_SVGA,  12,  1,  0,  0,  0, 0,  1, 1,  1, 1,  1,  1, 20, 5,  1,  1,  1,  1, 0, 1}},
    {"Fast Capture", {FRAMESIZE_QVGA,  20,  0,  0,  0,  0, 0,  1, 1,  1, 1,  0,  1,  0, 2,  1,  1,  1,  1, 0, 1}},
};
const int NUM_PRESETS = sizeof(PRESETS) / sizeof(PRESETS[0]);

void apply_settings()
{
    sensor_t *s = esp_camera_sensor_get();
    if (!s)
        return;

    s->set_framesize(s, (framesize_t)cam_settings.framesize);

    s->set_quality(s, cam_settings.quality);
    s->set_brightness(s, cam_settings.brightness);
    s->set_contrast(s, cam_settings.contrast);
    s->set_saturation(s, cam_settings.saturation);
    s->set_special_effect(s, cam_settings.special_effect);
    s->set_wb_mode(s, cam_settings.wb_mode);
    s->set_whitebal(s, cam_settings.awb);
    s->set_awb_gain(s, cam_settings.awb_gain);
    s->set_exposure_ctrl(s, cam_settings.aec);
    s->set_aec2(s, cam_settings.aec2);
    s->set_ae_level(s, cam_settings.ae_level);
    s->set_gain_ctrl(s, cam_settings.agc);
    s->set_agc_gain(s, cam_settings.agc_gain);
    s->set_gainceiling(s, (gainceiling_t)cam_settings.gainceiling);
    s->set_bpc(s, cam_settings.bpc);
    s->set_wpc(s, cam_settings.wpc);
    s->set_raw_gma(s, cam_settings.raw_gma);
    s->set_lenc(s, cam_settings.lenc);
    s->set_hmirror(s, cam_settings.hmirror);
    s->set_vflip(s, cam_settings.vflip);

    log_send("[CAM] Settings applied (fs=%d q=%d)\n", cam_settings.framesize,
             cam_settings.quality);
}

void save_settings()
{
    prefs.begin("cam", false);
    prefs.putBytes("s", &cam_settings, sizeof(cam_settings));
    prefs.putBool("saved", true);
    prefs.end();
}

static void load_settings()
{
    prefs.begin("cam", true);
    bool has_saved = prefs.getBool("saved", false);
    if (has_saved)
    {
        prefs.getBytes("s", &cam_settings, sizeof(cam_settings));
        log_send("[NVS] Settings loaded\n");
    }
    else
    {
        cam_settings = PRESETS[0].s;
        log_send("[NVS] Using default\n");
    }
    prefs.end();
}

void reset_settings()
{
    nvs_flash_erase();
    nvs_flash_init();
    cam_settings = PRESETS[0].s;
    apply_settings();
    log_send("[NVS] Factory reset\n");
}

void camSettingsToJson(const CamSettings &cs, JsonObject obj)
{
    obj["framesize"]      = cs.framesize;
    obj["quality"]        = cs.quality;
    obj["brightness"]     = cs.brightness;
    obj["contrast"]       = cs.contrast;
    obj["saturation"]     = cs.saturation;
    obj["special_effect"] = cs.special_effect;
    obj["wb_mode"]        = cs.wb_mode;
    obj["awb"]            = cs.awb;
    obj["awb_gain"]       = cs.awb_gain;
    obj["aec"]            = cs.aec;
    obj["aec2"]           = cs.aec2;
    obj["ae_level"]       = cs.ae_level;
    obj["agc"]            = cs.agc;
    obj["agc_gain"]       = cs.agc_gain;
    obj["gainceiling"]    = cs.gainceiling;
    obj["bpc"]            = cs.bpc;
    obj["wpc"]            = cs.wpc;
    obj["raw_gma"]        = cs.raw_gma;
    obj["lenc"]           = cs.lenc;
    obj["hmirror"]        = cs.hmirror;
    obj["vflip"]          = cs.vflip;
}

void jsonToCamSettings(JsonObject obj, CamSettings &cs)
{
    cs.framesize      = obj["framesize"]      | cs.framesize;
    cs.quality        = obj["quality"]        | cs.quality;
    cs.brightness     = obj["brightness"]     | cs.brightness;
    cs.contrast       = obj["contrast"]       | cs.contrast;
    cs.saturation     = obj["saturation"]     | cs.saturation;
    cs.special_effect = obj["special_effect"] | cs.special_effect;
    cs.wb_mode        = obj["wb_mode"]        | cs.wb_mode;
    cs.awb            = obj["awb"]            | cs.awb;
    cs.awb_gain       = obj["awb_gain"]       | cs.awb_gain;
    cs.aec            = obj["aec"]            | cs.aec;
    cs.aec2           = obj["aec2"]           | cs.aec2;
    cs.ae_level       = obj["ae_level"]       | cs.ae_level;
    cs.agc            = obj["agc"]            | cs.agc;
    cs.agc_gain       = obj["agc_gain"]       | cs.agc_gain;
    cs.gainceiling    = obj["gainceiling"]    | cs.gainceiling;
    cs.bpc            = obj["bpc"]            | cs.bpc;
    cs.wpc            = obj["wpc"]            | cs.wpc;
    cs.raw_gma        = obj["raw_gma"]        | cs.raw_gma;
    cs.lenc           = obj["lenc"]           | cs.lenc;
    cs.hmirror        = obj["hmirror"]        | cs.hmirror;
    cs.vflip          = obj["vflip"]          | cs.vflip;
}

void camInfoToJson(JsonObject obj)
{
    sensor_t *s = esp_camera_sensor_get();
    if (s)
    {
        obj["pid"]    = s->id.PID;
        obj["sensor"] = s->id.PID == OV3660_PID ? "OV3660"
                      : s->id.PID == OV2640_PID ? "OV2640"
                      : s->id.PID == OV5640_PID ? "OV5640"
                                                 : "Unknown";
    }

    struct FsEntry { framesize_t fs; const char *name; int w; int h; };
    static const FsEntry FS_TABLE[] = {
        {FRAMESIZE_QQVGA,   "QQVGA",    160,  120},
        {FRAMESIZE_HQVGA,   "HQVGA",    240,  176},
        {FRAMESIZE_QVGA,    "QVGA",     320,  240},
        {FRAMESIZE_CIF,     "CIF",      400,  296},
        {FRAMESIZE_HVGA,    "HVGA",     480,  320},
        {FRAMESIZE_VGA,     "VGA",      640,  480},
        {FRAMESIZE_SVGA,    "SVGA",     800,  600},
        {FRAMESIZE_XGA,     "XGA",     1024,  768},
        {FRAMESIZE_HD,      "HD",      1280,  720},
        {FRAMESIZE_SXGA,    "SXGA",    1280, 1024},
        {FRAMESIZE_UXGA,    "UXGA",    1600, 1200},
        {FRAMESIZE_QXGA,    "QXGA",    2048, 1536},
    };

    JsonArray arr = obj["framesizes"].to<JsonArray>();
    for (const auto &e : FS_TABLE)
    {
        JsonObject f = arr.add<JsonObject>();
        f["value"]   = (int)e.fs;
        f["name"]    = e.name;
        f["width"]   = e.w;
        f["height"]  = e.h;
    }
}

// ── Globals ─────────────────────────────────────────────────────────────────

HwState hw = {};
static WebuiState webui = {};

// Tracks WAKE_PREP deadline. Non-zero => sensor is held awake pending
// a follow-up CAPTURE; loop() auto-parks the sensor after
// WAKE_PREP_TIMEOUT_MS to avoid a stuck-on drain.
static unsigned long wake_prep_deadline_ms = 0;
#if ENABLE_CAPTIVE_PORTAL
static DNSServer dnsServer;
#endif

// ── Forward declarations ────────────────────────────────────────────────────
static bool init_camera();
static bool init_sd();
static void init_wifi_ap();
static void serial_cmd_poll();
static String next_filename();
static void ensure_image_dir();

// ============================================================================
// Serial Command Interface
// ============================================================================
// Framed protocol on Serial (UART0) between Pico (satkit) and ESP32-CAM.
//
// Frame layout (32-bit aligned, 8-byte overhead):
//   [PREAMBLE 0xAA][SYNC 0x55][LEN 1B][TYPE 1B]    // 4-byte header
//   [PAYLOAD  0..255 B]
//   [CRC32_LE 4B]                                  // 4-byte trailer
//
// CRC32 = esp_crc32_le(0, &frame[1], 3 + LEN)  — CRC covers [SYNC..PAYLOAD]
// and EXCLUDES the PREAMBLE byte. Matches Python binascii.crc32.
//
// PREAMBLE (0xAA) is the UART light-sleep wake byte. Because the wake
// machinery may drop or garble this byte during the DFS clock ramp, the
// receiver syncs on SYNC (0x55) instead of PREAMBLE and the CRC does not
// cover PREAMBLE. The PREAMBLE is still transmitted every frame to trigger
// the UART RX wake threshold.
//
// Response TYPE = request TYPE | 0x80 (ACK) or | 0xC0 (NACK). NACK payload is
// a 1-byte error code (see FR_ERR_* constants).

// ── Frame constants ─────────────────────────────────────────────────────────
#define FR_PREAMBLE        0xAA
#define FR_SYNC            0x55
#define FR_ACK_BIT         0x80
#define FR_NACK_BIT        0xC0
#define FR_MAX_PAYLOAD     255
#define FR_HEADER_LEN      4
#define FR_CRC_LEN         4
#define FR_CRC_BODY_OFF    1      // CRC starts at tx[1] (after PREAMBLE)

// ── Request opcodes ─────────────────────────────────────────────────────────
#define MANHA_CAM_CMD_CAPTURE       0x01  // -> ACK payload: filename bytes (UTF-8)
#define MANHA_CAM_CMD_STATUS        0x02  // -> ACK payload: u32_le image_count, u8 webui_active
#define MANHA_CAM_CMD_SET_SETTINGS  0x03  // req payload: count + count*2 KV bytes -> ACK: applied u8
#define MANHA_CAM_CMD_GET_SETTINGS  0x04  // -> ACK payload: 21 pairs (42 bytes)
#define MANHA_CAM_CMD_WEBUI_ON      0x05  // -> ACK payload: ip as 4 bytes
#define MANHA_CAM_CMD_WEBUI_OFF     0x06  // -> ACK payload: empty
#define MANHA_CAM_CMD_WAKE_PREP     0x08  // -> ACK payload: empty (sensor brought out of PWDN)

// ── NACK error codes ────────────────────────────────────────────────────────
#define FR_ERR_UNKNOWN_CMD  0x01
#define FR_ERR_BAD_PAYLOAD  0x02
#define FR_ERR_CAPTURE      0x03
#define FR_ERR_BAD_COUNT    0x04

// ── Settings key mapping ─────────────────────────────────────────────────────
// Keys are sequential: MANHA_CAM_CFG_FRAMESIZE (0x01) .. MANHA_CAM_CFG_VFLIP (0x15).
// Matches the field order in CamSettings.
#define MANHA_CAM_CFG_FRAMESIZE     0x01
#define MANHA_CAM_CFG_QUALITY       0x02
#define MANHA_CAM_CFG_BRIGHTNESS    0x03
#define MANHA_CAM_CFG_CONTRAST      0x04
#define MANHA_CAM_CFG_SATURATION    0x05
#define MANHA_CAM_CFG_SPECIAL_EFFECT 0x06
#define MANHA_CAM_CFG_WB_MODE       0x07
#define MANHA_CAM_CFG_AWB           0x08
#define MANHA_CAM_CFG_AWB_GAIN      0x09
#define MANHA_CAM_CFG_AEC           0x0A
#define MANHA_CAM_CFG_AEC2          0x0B
#define MANHA_CAM_CFG_AE_LEVEL      0x0C
#define MANHA_CAM_CFG_AGC           0x0D
#define MANHA_CAM_CFG_AGC_GAIN      0x0E
#define MANHA_CAM_CFG_GAINCEILING   0x0F
#define MANHA_CAM_CFG_BPC           0x10
#define MANHA_CAM_CFG_WPC           0x11
#define MANHA_CAM_CFG_RAW_GMA       0x12
#define MANHA_CAM_CFG_LENC          0x13
#define MANHA_CAM_CFG_HMIRROR       0x14
#define MANHA_CAM_CFG_VFLIP         0x15

static bool set_setting_by_key(uint8_t key, uint8_t val)
{
    switch (key)
    {
    case MANHA_CAM_CFG_FRAMESIZE:      cam_settings.framesize      = val; break;
    case MANHA_CAM_CFG_QUALITY:        cam_settings.quality        = val; break;
    case MANHA_CAM_CFG_BRIGHTNESS:     cam_settings.brightness     = (int8_t)val; break;
    case MANHA_CAM_CFG_CONTRAST:       cam_settings.contrast       = (int8_t)val; break;
    case MANHA_CAM_CFG_SATURATION:     cam_settings.saturation     = (int8_t)val; break;
    case MANHA_CAM_CFG_SPECIAL_EFFECT: cam_settings.special_effect = val; break;
    case MANHA_CAM_CFG_WB_MODE:        cam_settings.wb_mode        = val; break;
    case MANHA_CAM_CFG_AWB:            cam_settings.awb            = val ? 1 : 0; break;
    case MANHA_CAM_CFG_AWB_GAIN:       cam_settings.awb_gain       = val ? 1 : 0; break;
    case MANHA_CAM_CFG_AEC:            cam_settings.aec            = val ? 1 : 0; break;
    case MANHA_CAM_CFG_AEC2:           cam_settings.aec2           = val ? 1 : 0; break;
    case MANHA_CAM_CFG_AE_LEVEL:       cam_settings.ae_level       = (int8_t)val; break;
    case MANHA_CAM_CFG_AGC:            cam_settings.agc            = val ? 1 : 0; break;
    case MANHA_CAM_CFG_AGC_GAIN:       cam_settings.agc_gain       = val; break;
    case MANHA_CAM_CFG_GAINCEILING:    cam_settings.gainceiling    = val; break;
    case MANHA_CAM_CFG_BPC:            cam_settings.bpc            = val ? 1 : 0; break;
    case MANHA_CAM_CFG_WPC:            cam_settings.wpc            = val ? 1 : 0; break;
    case MANHA_CAM_CFG_RAW_GMA:        cam_settings.raw_gma        = val ? 1 : 0; break;
    case MANHA_CAM_CFG_LENC:           cam_settings.lenc           = val ? 1 : 0; break;
    case MANHA_CAM_CFG_HMIRROR:        cam_settings.hmirror        = val ? 1 : 0; break;
    case MANHA_CAM_CFG_VFLIP:          cam_settings.vflip          = val ? 1 : 0; break;
    default:   return false;
    }
    return true;
}

static uint8_t get_setting_by_key(uint8_t key)
{
    switch (key)
    {
    case MANHA_CAM_CFG_FRAMESIZE:      return cam_settings.framesize;
    case MANHA_CAM_CFG_QUALITY:        return cam_settings.quality;
    case MANHA_CAM_CFG_BRIGHTNESS:     return (uint8_t)cam_settings.brightness;
    case MANHA_CAM_CFG_CONTRAST:       return (uint8_t)cam_settings.contrast;
    case MANHA_CAM_CFG_SATURATION:     return (uint8_t)cam_settings.saturation;
    case MANHA_CAM_CFG_SPECIAL_EFFECT: return cam_settings.special_effect;
    case MANHA_CAM_CFG_WB_MODE:        return cam_settings.wb_mode;
    case MANHA_CAM_CFG_AWB:            return cam_settings.awb;
    case MANHA_CAM_CFG_AWB_GAIN:       return cam_settings.awb_gain;
    case MANHA_CAM_CFG_AEC:            return cam_settings.aec;
    case MANHA_CAM_CFG_AEC2:           return cam_settings.aec2;
    case MANHA_CAM_CFG_AE_LEVEL:       return (uint8_t)cam_settings.ae_level;
    case MANHA_CAM_CFG_AGC:            return cam_settings.agc;
    case MANHA_CAM_CFG_AGC_GAIN:       return cam_settings.agc_gain;
    case MANHA_CAM_CFG_GAINCEILING:    return cam_settings.gainceiling;
    case MANHA_CAM_CFG_BPC:            return cam_settings.bpc;
    case MANHA_CAM_CFG_WPC:            return cam_settings.wpc;
    case MANHA_CAM_CFG_RAW_GMA:        return cam_settings.raw_gma;
    case MANHA_CAM_CFG_LENC:           return cam_settings.lenc;
    case MANHA_CAM_CFG_HMIRROR:        return cam_settings.hmirror;
    case MANHA_CAM_CFG_VFLIP:          return cam_settings.vflip;
    default:   return 0;
    }
}

// ── Frame send helper ───────────────────────────────────────────────────────
static void send_framed(uint8_t type, const uint8_t *payload, uint8_t len)
{
    // Buffer: 4 header + 255 payload + 4 CRC = 263 max
    static uint8_t tx[FR_HEADER_LEN + FR_MAX_PAYLOAD + FR_CRC_LEN];
    tx[0] = FR_PREAMBLE;
    tx[1] = FR_SYNC;
    tx[2] = len;
    tx[3] = type;
    if (len > 0 && payload)
        memcpy(tx + FR_HEADER_LEN, payload, len);

    // CRC excludes PREAMBLE (tx[0]) — it may not survive the UART wake path.
    uint32_t crc = esp_crc32_le(0, tx + FR_CRC_BODY_OFF,
                                FR_HEADER_LEN - FR_CRC_BODY_OFF + len);
    tx[FR_HEADER_LEN + len + 0] = (uint8_t)(crc & 0xFF);
    tx[FR_HEADER_LEN + len + 1] = (uint8_t)((crc >> 8) & 0xFF);
    tx[FR_HEADER_LEN + len + 2] = (uint8_t)((crc >> 16) & 0xFF);
    tx[FR_HEADER_LEN + len + 3] = (uint8_t)((crc >> 24) & 0xFF);

    Serial.write(tx, FR_HEADER_LEN + len + FR_CRC_LEN);
}

static inline void send_ack(uint8_t req_type, const uint8_t *payload, uint8_t len)
{
    send_framed(req_type | FR_ACK_BIT, payload, len);
}

static inline void send_nack(uint8_t req_type, uint8_t err_code)
{
    send_framed(req_type | FR_NACK_BIT, &err_code, 1);
}

// ── Frame dispatch ──────────────────────────────────────────────────────────
static void handle_frame(uint8_t type, const uint8_t *payload, uint8_t len)
{
    switch (type)
    {
    case MANHA_CAM_CMD_CAPTURE:
    {
        String fname;
        if (capture_and_save(fname))
            send_ack(type, (const uint8_t *)fname.c_str(), fname.length());
        else
            send_nack(type, FR_ERR_CAPTURE);
        break;
    }
    case MANHA_CAM_CMD_STATUS:
    {
        webui.last_status_poll = millis();
        uint32_t cnt = hw.image_count;
        uint8_t p[5] = {
            (uint8_t)(cnt & 0xFF),
            (uint8_t)((cnt >> 8) & 0xFF),
            (uint8_t)((cnt >> 16) & 0xFF),
            (uint8_t)((cnt >> 24) & 0xFF),
            (uint8_t)(webui.active ? 1 : 0),
        };
        send_ack(type, p, 5);
        break;
    }
    case MANHA_CAM_CMD_SET_SETTINGS:
    {
        if (len < 1)
        {
            send_nack(type, FR_ERR_BAD_PAYLOAD);
            break;
        }
        uint8_t num_pairs = payload[0];
        if (num_pairs == 0 || num_pairs > 21 || (len - 1) != num_pairs * 2)
        {
            send_nack(type, FR_ERR_BAD_COUNT);
            break;
        }
        xSemaphoreTake(hw.cam_mutex, portMAX_DELAY);
        int applied = 0;
        for (int i = 0; i < num_pairs; i++)
        {
            uint8_t k = payload[1 + i * 2];
            uint8_t v = payload[1 + i * 2 + 1];
            if (set_setting_by_key(k, v))
                applied++;
        }
        apply_settings();
        save_settings();
        xSemaphoreGive(hw.cam_mutex);
        uint8_t a = (uint8_t)applied;
        send_ack(type, &a, 1);
        break;
    }
    case MANHA_CAM_CMD_GET_SETTINGS:
    {
        uint8_t buf[42]; // 21 KV pairs × 2 bytes
        int idx = 0;
        xSemaphoreTake(hw.cam_mutex, portMAX_DELAY);
        for (uint8_t k = MANHA_CAM_CFG_FRAMESIZE; k <= MANHA_CAM_CFG_VFLIP; k++)
        {
            buf[idx++] = k;
            buf[idx++] = get_setting_by_key(k);
        }
        xSemaphoreGive(hw.cam_mutex);
        send_ack(type, buf, (uint8_t)idx);
        break;
    }
    case MANHA_CAM_CMD_WEBUI_ON:
    {
        webui_start();
        IPAddress ip = WiFi.softAPIP();
        uint8_t p[4] = { ip[0], ip[1], ip[2], ip[3] };
        send_ack(type, p, 4);
        break;
    }
    case MANHA_CAM_CMD_WEBUI_OFF:
    {
        webui_stop();
        send_ack(type, nullptr, 0);
        break;
    }
    case MANHA_CAM_CMD_WAKE_PREP:
    {
        xSemaphoreTake(hw.cam_mutex, portMAX_DELAY);
        cam_sensor_power_up_locked();
        wake_prep_deadline_ms = millis() + WAKE_PREP_TIMEOUT_MS;
        xSemaphoreGive(hw.cam_mutex);
        send_ack(type, nullptr, 0);
        break;
    }
    default:
        send_nack(type, FR_ERR_UNKNOWN_CMD);
        break;
    }
}

// ── Frame parser state machine ──────────────────────────────────────────────
// Syncs on SYNC (0x55). PREAMBLE bytes before SYNC are silently skipped
// in the IDLE state — they may be absent/garbled after a wake event, and
// they are not covered by the CRC anyway.
enum FrameState : uint8_t {
    FR_IDLE = 0,
    FR_LEN,
    FR_TYPE,
    FR_PAYLOAD,
    FR_CRC,
};

static void serial_cmd_poll()
{
    static FrameState state = FR_IDLE;
    static uint8_t exp_len = 0;
    static uint8_t fr_type = 0;
    static uint8_t payload_buf[FR_MAX_PAYLOAD];
    static uint16_t payload_idx = 0;
    static uint8_t crc_buf[FR_CRC_LEN];
    static uint8_t crc_idx = 0;

    while (Serial.available())
    {
        uint8_t b = (uint8_t)Serial.read();
        switch (state)
        {
        case FR_IDLE:
            if (b == FR_SYNC)
                state = FR_LEN;
            // Any other byte (including PREAMBLE or noise) is ignored.
            break;
        case FR_LEN:
            exp_len = b;
            payload_idx = 0;
            state = FR_TYPE;
            break;
        case FR_TYPE:
            fr_type = b;
            crc_idx = 0;
            state = (exp_len == 0) ? FR_CRC : FR_PAYLOAD;
            break;
        case FR_PAYLOAD:
            payload_buf[payload_idx++] = b;
            if (payload_idx >= exp_len)
            {
                crc_idx = 0;
                state = FR_CRC;
            }
            break;
        case FR_CRC:
            crc_buf[crc_idx++] = b;
            if (crc_idx >= FR_CRC_LEN)
            {
                // CRC body: [SYNC, LEN, TYPE, payload]
                uint8_t hdr[3] = { FR_SYNC, exp_len, fr_type };
                uint32_t calc = esp_crc32_le(0, hdr, 3);
                if (exp_len > 0)
                    calc = esp_crc32_le(calc, payload_buf, exp_len);
                uint32_t rx = (uint32_t)crc_buf[0]
                            | ((uint32_t)crc_buf[1] << 8)
                            | ((uint32_t)crc_buf[2] << 16)
                            | ((uint32_t)crc_buf[3] << 24);
                if (calc == rx)
                    handle_frame(fr_type, payload_buf, exp_len);
                else
                    log_send("[FR] CRC mismatch rx=%08x calc=%08x type=0x%02x len=%u\n",
                             (unsigned)rx, (unsigned)calc, fr_type, exp_len);
                state = FR_IDLE;
            }
            break;
        }
    }
}

// ============================================================================
// Camera (init pattern matches CameraWebServer example)
// ============================================================================
static bool init_camera()
{
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer   = LEDC_TIMER_0;
    config.pin_d0       = Y2_GPIO_NUM;
    config.pin_d1       = Y3_GPIO_NUM;
    config.pin_d2       = Y4_GPIO_NUM;
    config.pin_d3       = Y5_GPIO_NUM;
    config.pin_d4       = Y6_GPIO_NUM;
    config.pin_d5       = Y7_GPIO_NUM;
    config.pin_d6       = Y8_GPIO_NUM;
    config.pin_d7       = Y9_GPIO_NUM;
    config.pin_xclk     = XCLK_GPIO_NUM;
    config.pin_pclk     = PCLK_GPIO_NUM;
    config.pin_vsync    = VSYNC_GPIO_NUM;
    config.pin_href     = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn     = PWDN_GPIO_NUM;
    config.pin_reset    = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.frame_size   = FRAMESIZE_UXGA;
    config.pixel_format = PIXFORMAT_JPEG;
    config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
    config.fb_location  = CAMERA_FB_IN_PSRAM;
    config.jpeg_quality = 12;
    config.fb_count     = 1;

    if (config.pixel_format == PIXFORMAT_JPEG)
    {
        if (psramFound())
        {
            config.jpeg_quality = 10;
            config.fb_count     = 2;
            config.grab_mode    = CAMERA_GRAB_LATEST;
        }
        else
        {
            config.frame_size  = FRAMESIZE_SVGA;
            config.fb_location = CAMERA_FB_IN_DRAM;
        }
    }

#if defined(CAMERA_MODEL_ESP_EYE)
    pinMode(13, INPUT_PULLUP);
    pinMode(14, INPUT_PULLUP);
#endif

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK)
    {
        log_send("[CAM] Init failed with error 0x%x\n", err);
        return false;
    }

    sensor_t *s = esp_camera_sensor_get();
    if (s)
    {
        if (s->id.PID == OV3660_PID)
        {
            s->set_vflip(s, 1);
            s->set_brightness(s, 1);
            s->set_saturation(s, -2);
        }
        if (config.pixel_format == PIXFORMAT_JPEG)
        {
            s->set_framesize(s, FRAMESIZE_QVGA);
        }
#if defined(CAMERA_MODEL_M5STACK_WIDE) || defined(CAMERA_MODEL_M5STACK_ESP32CAM)
        s->set_vflip(s, 1);
        s->set_hmirror(s, 1);
#endif
#if defined(CAMERA_MODEL_ESP32S3_EYE)
        s->set_vflip(s, 1);
#endif
    }

    log_send("[CAM] Initialised OK\n");
    return true;
}

// ============================================================================
// SD Card
// ============================================================================
static bool init_sd()
{
#if USE_SD_SPI
    if (!SD.begin(SD_SPI_CS))
    {
        log_send("[SD] SPI mount failed\n");
        return false;
    }
#else
#if defined(SOC_SDMMC_USE_GPIO_MATRIX) && !defined(BOARD_HAS_SDMMC)
    SD_MMC.setPins(SD_MMC_CLK_PIN, SD_MMC_CMD_PIN, SD_MMC_D0_PIN);
#endif
    if (!SD_MMC.begin("/sdcard", SD_MMC_1BIT_MODE))
    {
        log_send("[SD] SD_MMC mount failed\n");
        return false;
    }
#endif

    uint8_t ct = SDFS.cardType();
    if (ct == CARD_NONE)
    {
        log_send("[SD] No card\n");
        return false;
    }
    const char *t = (ct == CARD_MMC)    ? "MMC"
                    : (ct == CARD_SD)   ? "SDSC"
                    : (ct == CARD_SDHC) ? "SDHC"
                                        : "?";
    log_send("[SD] %s  %.1f MB total  %.1f MB used\n", t, SDFS.totalBytes() / 1048576.0,
             SDFS.usedBytes() / 1048576.0);
    ensure_image_dir();
    return true;
}

static void ensure_image_dir()
{
    if (!SDFS.exists(IMAGE_DIR))
        SDFS.mkdir(IMAGE_DIR);
}

// ============================================================================
// Capture & save
// ============================================================================
static String next_filename()
{
    char buf[32];
    snprintf(buf, sizeof(buf), "/img_%05lu.jpg", (unsigned long)hw.name_counter++);
    return String(IMAGE_DIR) + String(buf);
}

// Sensor power-gate helpers. Both must be called with hw.cam_mutex held
// (or during single-threaded boot).
static void cam_sensor_power_down_locked()
{
    if (!hw.cam_powered) return;
    digitalWrite(PWDN_GPIO_NUM, HIGH);
    hw.cam_powered = false;
    wake_prep_deadline_ms = 0;
    log_send("[CAM] PWDN down\n");
}

static void cam_sensor_power_up_locked()
{
    if (hw.cam_powered) return;
    digitalWrite(PWDN_GPIO_NUM, LOW);
    delay(CAM_IDLE_PWDN_DELAY_MS);
    apply_settings();
    hw.cam_powered = true;
    log_send("[CAM] PWDN up, resettled\n");
}

bool capture_and_save(String &out_filename)
{
    if (!hw.sd_ok)
    {
        log_send("[CAM] No SD\n");
        return false;
    }
    xSemaphoreTake(hw.cam_mutex, portMAX_DELAY);

    cam_sensor_power_up_locked();

    camera_fb_t *fb = esp_camera_fb_get();

    if (!fb)
    {
        log_send("[CAM] fb_get failed\n");
        cam_sensor_power_down_locked();
        xSemaphoreGive(hw.cam_mutex);
        return false;
    }

    out_filename = next_filename();
    File file    = SDFS.open(out_filename.c_str(), FILE_WRITE);
    if (!file)
    {
        log_send("[SD] open %s failed\n", out_filename.c_str());
        esp_camera_fb_return(fb);
        cam_sensor_power_down_locked();
        xSemaphoreGive(hw.cam_mutex);
        return false;
    }
    size_t written = file.write(fb->buf, fb->len);
    file.close();
    esp_camera_fb_return(fb);
    cam_sensor_power_down_locked();
    if (written > 0)
        hw.image_count++;
    xSemaphoreGive(hw.cam_mutex);
    log_send("[CAM] %s (%u B)\n", out_filename.c_str(), (unsigned)written);
    return (written > 0);
}

// ============================================================================
// WiFi AP
// ============================================================================
static void init_wifi_ap()
{
    WiFi.mode(WIFI_AP);
    if (!WiFi.softAP(AP_SSID, AP_PASS, 1, 0, AP_MAX_CONN))
    {
        log_send("[WiFi] AP creation failed\n");
        while (1)
            delay(1000);
    }
    IPAddress ip = WiFi.softAPIP();
    log_send("[WiFi] AP \"%s\" -> http://%s/\n", AP_SSID, ip.toString().c_str());
}

// ============================================================================
// WebUI (WiFi AP + HTTP) control
// ============================================================================
static void webui_start()
{
    if (webui.active) return;
    init_wifi_ap();
    WiFi.setSleep(WIFI_PS_MIN_MODEM);
    log_send("[WiFi] modem sleep ON\n");
#if ENABLE_CAPTIVE_PORTAL
    dnsServer.start(53, "*", WiFi.softAPIP());
#endif
#if ENABLE_MDNS
    if (MDNS.begin(MDNS_HOSTNAME))
    {
        MDNS.addService("http", "tcp", 80);
        log_send("[mDNS] http://%s.local/\n", MDNS_HOSTNAME);
    }
    else
    {
        log_send("[mDNS] start failed\n");
    }
#endif
    start_http_server();
    webui.active = true;
}

static void webui_stop()
{
    if (!webui.active) return;
#if ENABLE_CAPTIVE_PORTAL
    dnsServer.stop();
#endif
#if ENABLE_MDNS
    MDNS.end();
#endif
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_OFF);
    webui.active = false;
}

static void power_mgmt_init()
{
    esp_pm_config_esp32_t cfg = {
        .max_freq_mhz = CPU_FREQ_MAX_MHZ,
        .min_freq_mhz = CPU_FREQ_MIN_MHZ,
        .light_sleep_enable = true,
    };
    esp_err_t rc = esp_pm_configure(&cfg);
    if (rc != ESP_OK)
    {
        log_send("[PM] DFS unavailable (rc=0x%x)\n", rc);
    }
    else
    {
        log_send("[PM] DFS %d-%d MHz + light sleep\n",
                 CPU_FREQ_MIN_MHZ, CPU_FREQ_MAX_MHZ);
    }

    // UART0 wake: CPU resumes full clock when >=3 positive edges seen on RX.
    // First wake byte (the 0xAA preamble) is consumed by wake machinery.
    uart_set_wakeup_threshold(UART_NUM_0, UART_WAKE_THRESHOLD);
    esp_sleep_enable_uart_wakeup(UART_NUM_0);
    log_send("[PM] UART0 wake enabled (threshold=%d)\n", UART_WAKE_THRESHOLD);
}

// ============================================================================
// Setup & Loop
// ============================================================================
void setup()
{
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    Serial.begin(115200);
    Serial.setDebugOutput(false);

    log_send("\n========= ESP32-CAM AP Server =========\n");

    hw.cam_mutex = xSemaphoreCreateMutex();

    if (!init_camera())
    {
        log_send("[FATAL] Camera init failed\n");
        while (true)
            delay(1000);
    }

    load_settings();
    apply_settings();

    // Boot-time: sensor is up after init_camera/apply_settings. Park it.
    hw.cam_powered = true;
    cam_sensor_power_down_locked();

    hw.sd_ok = init_sd();
    if (!hw.sd_ok)
        log_send("[WARN] SD not available - capture will fail\n");

    if (hw.sd_ok)
    {
        File root = SDFS.open(IMAGE_DIR);
        if (root && root.isDirectory())
        {
            while (File f = root.openNextFile())
            {
                String n = f.name();
                if (n.startsWith("img_") && n.endsWith(".jpg"))
                {
                    long num = n.substring(4, n.length() - 4).toInt();
                    if ((uint32_t)num >= hw.name_counter)
                        hw.name_counter = num + 1;
                    hw.image_count++;
                }
                f.close();
            }
            root.close();
        }
    }

    // Boot in flight mode — no WiFi/HTTP. Send 0x05 via UART to enable.
    webui.last_status_poll = millis();
    power_mgmt_init();
    log_send("[INIT] Ready (flight mode).\n");
}

void loop()
{
#if ENABLE_CAPTIVE_PORTAL
    if (webui.active)
        dnsServer.processNextRequest();
#endif
    serial_cmd_poll();

    // Watchdog: auto-start WebUI if Pico stops polling STATUS
    if (!webui.active && millis() - webui.last_status_poll >= STATUS_WATCHDOG_MS)
    {
        log_send("[WDG] STATUS not polled for %ds, starting WebUI\n",
                 STATUS_WATCHDOG_MS / 1000);
        webui_start();
    }

    // Watchdog: auto-park sensor if WAKE_PREP not followed by CAPTURE in time.
    if (wake_prep_deadline_ms != 0 && (long)(millis() - wake_prep_deadline_ms) >= 0)
    {
        log_send("[WDG] WAKE_PREP expired, parking sensor\n");
        xSemaphoreTake(hw.cam_mutex, portMAX_DELAY);
        cam_sensor_power_down_locked();
        xSemaphoreGive(hw.cam_mutex);
    }

    if (webui.active && millis() - webui.last_log_flush >= LOG_FLUSH_FREQ_MS)
    {
        log_flush();
        webui.last_log_flush = millis();
    }

    delay(webui.active ? BUSY_LOOP_DELAY_MS : IDLE_LOOP_DELAY_MS);
}
