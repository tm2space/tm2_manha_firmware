#ifndef APP_HTTPD_H
#define APP_HTTPD_H

#include "esp_camera.h"
#include "esp_http_server.h"
#include <ArduinoJson.h>
#include <FS.h>

#include "board_config.h"

// ── SD filesystem ───────────────────────────────────────────────────────────
#if defined(CAMERA_MODEL_XIAO_ESP32S3)
#include "SD.h"
#define SDFS SD
#else
#include "SD_MMC.h"
#define SDFS SD_MMC
#endif

// ── Camera settings ─────────────────────────────────────────────────────────

struct CamSettings
{
    uint8_t framesize;      // 0=QQVGA .. 13=UXGA
    uint8_t quality;        // 10-63 (lower = better)
    int8_t brightness;      // -2 to 2
    int8_t contrast;        // -2 to 2
    int8_t saturation;      // -2 to 2
    uint8_t special_effect; // 0=None,1=Neg,2=Gray,3=Red,4=Green,5=Blue,6=Sepia
    uint8_t wb_mode;        // 0=Auto,1=Sunny,2=Cloudy,3=Office,4=Home
    uint8_t awb;            // 0/1
    uint8_t awb_gain;       // 0/1
    uint8_t aec;            // 0/1
    uint8_t aec2;           // 0/1 (DSP AEC)
    int8_t ae_level;        // -2 to 2
    uint8_t agc;            // 0/1
    uint8_t agc_gain;       // 0-30
    uint8_t gainceiling;    // 0-6 (maps to 2x..128x)
    uint8_t bpc;            // 0/1 black pixel correction
    uint8_t wpc;            // 0/1 white pixel correction
    uint8_t raw_gma;        // 0/1 gamma correction
    uint8_t lenc;           // 0/1 lens correction
    uint8_t hmirror;        // 0/1
    uint8_t vflip;          // 0/1
    uint8_t _spare[3];        // explicit 32-bit alignment (21 → 24 bytes)
};

struct Preset
{
    const char *name;
    CamSettings s;
};

// ── Runtime state ───────────────────────────────────────────────────────────

struct HwState {
    uint32_t image_counter;         // 4
    SemaphoreHandle_t cam_mutex;    // 4  (pointer)
    bool sd_ok;                     // 1
    uint8_t _spare[3];               // explicit 32-bit alignment (9 → 12 bytes)
};

struct WebuiState {
    unsigned long last_status_poll; // 4
    unsigned long last_log_flush;   // 4
    bool active;                    // 1
    uint8_t _spare[3];               // explicit 32-bit alignment (9 → 12 bytes)
};

extern HwState hw;
extern const char *IMAGE_DIR;
extern CamSettings cam_settings;
extern const Preset PRESETS[];
extern const int NUM_PRESETS;

// ── Functions ───────────────────────────────────────────────────────────────

bool capture_and_save(String &out_filename);
void apply_settings();
void save_settings();
void camSettingsToJson(const CamSettings &cs, JsonObject obj);
void jsonToCamSettings(JsonObject obj, CamSettings &cs);
void camInfoToJson(JsonObject obj);
void reset_settings();

// ── Logging ─────────────────────────────────────────────────────────────────

class NullPrint : public Print
{
public:
    size_t write(uint8_t) override { return 1; }
    size_t write(const uint8_t *, size_t len) override { return len; }
};

#if ENABLE_SERIAL_LOG
#define LOG_SERIAL Serial
#else
extern NullPrint null_print;
#define LOG_SERIAL null_print
#endif

#define LOG_FLUSH_FREQ_MS 5000

void log_send(const char *fmt, ...);
void log_flush();

// ── HTTP server ─────────────────────────────────────────────────────────────

void start_http_server();

#endif // APP_HTTPD_H
