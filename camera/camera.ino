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

#include <Preferences.h>

#include "app_httpd.h"

#if ENABLE_CAPTIVE_PORTAL
#include <DNSServer.h>
#endif

// ── LED Flash (from CameraWebServer example) ───────────────────────────────
#if defined(LED_GPIO_NUM)
#include "esp32-hal-ledc.h"
static int led_duty = 0;
static void setup_led_flash()
{
    ledcAttach(LED_GPIO_NUM, 5000, 8);
}
static void enable_led(bool en)
{
    ledcWrite(LED_GPIO_NUM, en ? led_duty : 0);
}
#endif

// ── Configuration ───────────────────────────────────────────────────────────

static const char *AP_SSID   = "Manha-CAM";
static const char *AP_PASS   = "space1234";
static const int AP_CHANNEL  = 6;
static const int AP_MAX_CONN = 4;

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

static const uint8_t SETTINGS_VERSION = 1;

// Named presets — index 0 is the default applied on first boot
// Struct field order: framesize, quality, brightness, contrast, saturation,
//   special_effect, wb_mode, awb, awb_gain, aec, aec2, ae_level,
//   agc, agc_gain, gainceiling, bpc, wpc, raw_gma, lenc,
//   hmirror, vflip, flash_duty
//
// gainceiling: 0=2x, 1=4x, 2=8x, 3=16x, 4=32x, 5=64x, 6=128x
const Preset PRESETS[] = {
    //                  fs               q  br  co  sa  fx wb  awb ag aec ae2 ael agc  ag gc bpc wpc gma len hm vf  fl
    {"Default",      {FRAMESIZE_SVGA,  12,  0,  0,  0,  0, 0,  1, 1,  1, 1,  0,  1,  0, 2,  1,  1,  1,  1, 0, 0,   0}},
    {"High Quality", {FRAMESIZE_UXGA,  10,  0,  1,  0,  0, 0,  1, 1,  1, 1,  0,  1,  0, 2,  1,  1,  1,  1, 0, 0,   0}},
    {"Low Light",    {FRAMESIZE_SVGA,  12,  1,  0,  0,  0, 0,  1, 1,  1, 1,  1,  1, 20, 5,  1,  1,  1,  1, 0, 0, 1}},
    {"Fast Capture", {FRAMESIZE_QVGA,  20,  0,  0,  0,  0, 0,  1, 1,  1, 1,  0,  1,  0, 2,  1,  1,  1,  1, 0, 0, 0}},
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

#if defined(LED_GPIO_NUM)
    led_duty = cam_settings.flash ? 255 : 0;
#endif
    log_send("[CAM] Settings applied (fs=%d q=%d flash=%d)\n", cam_settings.framesize,
             cam_settings.quality, cam_settings.flash);
}

void save_settings()
{
    prefs.begin("cam", false);
    prefs.putUChar("ver", SETTINGS_VERSION);
    prefs.putBytes("s", &cam_settings, sizeof(cam_settings));
    prefs.putBool("saved", true);
    prefs.end();
}

static void load_settings()
{
    prefs.begin("cam", true);
    uint8_t ver    = prefs.getUChar("ver", 0);
    bool has_saved = prefs.getBool("saved", false);
    if (has_saved && ver == SETTINGS_VERSION)
    {
        prefs.getBytes("s", &cam_settings, sizeof(cam_settings));
        log_send("[NVS] Settings v%d loaded\n", ver);
    }
    else
    {
        cam_settings = PRESETS[0].s;
        if (has_saved)
            log_send("[NVS] Version mismatch (got %d, want %d), using defaults\n",
                     ver, SETTINGS_VERSION);
        else
            log_send("[NVS] No saved settings, using defaults\n");
    }
    prefs.end();
}

void reset_settings()
{
    prefs.begin("cam", false);
    prefs.clear();
    prefs.end();
    cam_settings = PRESETS[0].s;
    apply_settings();
    save_settings();
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
    obj["flash"]          = cs.flash;
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
    cs.flash          = obj["flash"]          | cs.flash;
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

static uint32_t image_counter = 0;
static SemaphoreHandle_t cam_mutex;
bool sd_ok = false;
static unsigned long last_log_flush = 0;
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
// Protocol: Satkit Pico sends 1-byte commands on Serial (UART0).

// ── Serial commands ──────────────────────────────────────────────────────────
#define MANHA_CAM_CMD_CAPTURE       0x01  // -> ACK:<filename>\n or NACK:capture_failed\n
#define MANHA_CAM_CMD_STATUS        0x02  // -> ACK:count=<N>\n
#define MANHA_CAM_CMD_SET_SETTINGS  0x03  // key-value pairs + 0x00 terminator
#define MANHA_CAM_CMD_GET_SETTINGS  0x04  // -> 0x04 + key-value pairs + 0x00\n

// ── Settings key mapping ─────────────────────────────────────────────────────
// Keys are sequential: MANHA_CAM_CFG_FRAMESIZE (0x01) .. MANHA_CAM_CFG_FLASH (0x16).
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
#define MANHA_CAM_CFG_FLASH         0x16

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
    case MANHA_CAM_CFG_FLASH:          cam_settings.flash          = val ? 1 : 0; break;
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
    case MANHA_CAM_CFG_FLASH:          return cam_settings.flash;
    default:   return 0;
    }
}

static void serial_cmd_poll()
{
    if (!Serial.available())
        return;
    uint8_t cmd = Serial.read();

    switch (cmd)
    {
    case MANHA_CAM_CMD_CAPTURE:
    {
        String fname;
        if (capture_and_save(fname))
        {
            Serial.print("ACK:");
            Serial.println(fname);
        }
        else
        {
            Serial.println("NACK:capture_failed");
        }
        break;
    }
    case MANHA_CAM_CMD_STATUS:
    {
        File root      = SDFS.open(IMAGE_DIR);
        uint32_t count = 0;
        if (root && root.isDirectory())
        {
            while (File f = root.openNextFile())
            {
                count++;
                f.close();
            }
            root.close();
        }
        Serial.printf("ACK:count=%u\n", count);
        break;
    }
    case MANHA_CAM_CMD_SET_SETTINGS:
    {
        uint8_t buf[64];
        int pos       = 0;
        bool timed_out = false;
        unsigned long start = millis();

        // Read key-value pairs until 0x00 terminator or timeout
        while (millis() - start < 500)
        {
            if (!Serial.available())
            {
                delay(1);
                continue;
            }
            uint8_t b = Serial.read();
            if (b == 0x00)
                break;
            if (pos < (int)sizeof(buf))
                buf[pos++] = b;
        }

        if (pos < 2 || pos % 2 != 0)
        {
            Serial.println("NACK:bad_payload");
            break;
        }

        int applied = 0;
        for (int i = 0; i < pos; i += 2)
        {
            if (set_setting_by_key(buf[i], buf[i + 1]))
                applied++;
        }
        apply_settings();
        save_settings();
        Serial.printf("ACK:settings=%d\n", applied);
        break;
    }
    case MANHA_CAM_CMD_GET_SETTINGS:
    {
        Serial.write(MANHA_CAM_CMD_GET_SETTINGS);
        for (uint8_t key = MANHA_CAM_CFG_FRAMESIZE; key <= MANHA_CAM_CFG_FLASH; key++)
        {
            Serial.write(key);
            Serial.write(get_setting_by_key(key));
        }
        Serial.write(0x00);
        Serial.println();
        break;
    }
    default:
        Serial.printf("NACK:unknown_cmd=0x%02X\n", cmd);
        break;
    }
}

bool external_trigger_capture(String &out_filename)
{
    return capture_and_save(out_filename);
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
    snprintf(buf, sizeof(buf), "/img_%05lu.jpg", (unsigned long)image_counter++);
    return String(IMAGE_DIR) + String(buf);
}

bool capture_and_save(String &out_filename)
{
    if (!sd_ok)
    {
        log_send("[CAM] No SD\n");
        return false;
    }
    xSemaphoreTake(cam_mutex, portMAX_DELAY);

#if defined(LED_GPIO_NUM)
    enable_led(true);
    vTaskDelay(150 / portTICK_PERIOD_MS);
    camera_fb_t *fb = esp_camera_fb_get();
    enable_led(false);
#else
    camera_fb_t *fb = esp_camera_fb_get();
#endif

    if (!fb)
    {
        log_send("[CAM] fb_get failed\n");
        xSemaphoreGive(cam_mutex);
        return false;
    }

    out_filename = next_filename();
    File file    = SDFS.open(out_filename.c_str(), FILE_WRITE);
    if (!file)
    {
        log_send("[SD] open %s failed\n", out_filename.c_str());
        esp_camera_fb_return(fb);
        xSemaphoreGive(cam_mutex);
        return false;
    }
    size_t written = file.write(fb->buf, fb->len);
    file.close();
    esp_camera_fb_return(fb);
    xSemaphoreGive(cam_mutex);
    log_send("[CAM] %s (%u B)\n", out_filename.c_str(), (unsigned)written);
    return (written > 0);
}

// ============================================================================
// WiFi AP
// ============================================================================
static void init_wifi_ap()
{
    WiFi.mode(WIFI_AP);
    if (!WiFi.softAP(AP_SSID, AP_PASS, AP_CHANNEL, 0, AP_MAX_CONN))
    {
        log_send("[WiFi] AP creation failed\n");
        while (1)
            delay(1000);
    }
    IPAddress ip = WiFi.softAPIP();
    log_send("[WiFi] AP \"%s\" -> http://%s/\n", AP_SSID, ip.toString().c_str());
}

// ============================================================================
// Setup & Loop
// ============================================================================
void setup()
{
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    Serial.begin(115200);
#if ENABLE_SERIAL_LOG
    Serial.setDebugOutput(true);
#endif

    log_send("\n========= ESP32-CAM AP Server =========\n");

    cam_mutex = xSemaphoreCreateMutex();

    if (!init_camera())
    {
        log_send("[FATAL] Camera init failed\n");
        while (true)
            delay(1000);
    }

    load_settings();
    apply_settings();

#if defined(LED_GPIO_NUM)
    setup_led_flash();
#endif

    sd_ok = init_sd();
    if (!sd_ok)
        log_send("[WARN] SD not available - capture will fail\n");

    if (sd_ok)
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
                    if ((uint32_t)num >= image_counter)
                        image_counter = num + 1;
                }
                f.close();
            }
            root.close();
        }
    }

    init_wifi_ap();
#if ENABLE_CAPTIVE_PORTAL
    dnsServer.start(53, "*", WiFi.softAPIP());
#endif
    start_http_server();

    log_send("[INIT] Ready.\n");
}

void loop()
{
#if ENABLE_CAPTIVE_PORTAL
    dnsServer.processNextRequest();
#endif
    serial_cmd_poll();

    if (millis() - last_log_flush >= LOG_FLUSH_FREQ_MS)
    {
        log_flush();
        last_log_flush = millis();
    }

    delay(10);
}
