#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

//
// WARNING!!! PSRAM IC required for UXGA resolution and high JPEG quality
//            Ensure ESP32 Wrover Module or other board with PSRAM is selected
//            Partial images will be transmitted if image exceeds buffer size
//
//            You must select partition scheme from the board menu that has at least 3MB APP space.

// ===================
// Select camera model
// ===================
//#define CAMERA_MODEL_WROVER_KIT           // Has PSRAM
//#define CAMERA_MODEL_ESP_EYE              // Has PSRAM
//#define CAMERA_MODEL_ESP32S3_EYE          // Has PSRAM
//#define CAMERA_MODEL_M5STACK_PSRAM        // Has PSRAM
//#define CAMERA_MODEL_M5STACK_V2_PSRAM     // M5Camera version B Has PSRAM
//#define CAMERA_MODEL_M5STACK_WIDE         // Has PSRAM
//#define CAMERA_MODEL_M5STACK_ESP32CAM     // No PSRAM
//#define CAMERA_MODEL_M5STACK_UNITCAM      // No PSRAM
//#define CAMERA_MODEL_M5STACK_CAMS3_UNIT   // Has PSRAM
#define CAMERA_MODEL_AI_THINKER           // Has PSRAM
//#define CAMERA_MODEL_TTGO_T_JOURNAL       // No PSRAM
// #define CAMERA_MODEL_XIAO_ESP32S3           // Has PSRAM
// ** Espressif Internal Boards **
//#define CAMERA_MODEL_ESP32_CAM_BOARD
//#define CAMERA_MODEL_ESP32S2_CAM_BOARD
//#define CAMERA_MODEL_ESP32S3_CAM_LCD
//#define CAMERA_MODEL_DFRobot_FireBeetle2_ESP32S3  // Has PSRAM
//#define CAMERA_MODEL_DFRobot_Romeo_ESP32S3        // Has PSRAM

// ── Captive Portal ──────────────────────────────────────────────────────────
#define ENABLE_CAPTIVE_PORTAL 1       // 1 = auto-open web UI on AP connect, 0 = disabled

// ── Logging ─────────────────────────────────────────────────────────────────
#define ENABLE_SERIAL_LOG  1          // 1 = LOG_SERIAL writes to UART, 0 = silent
#define LOG_FILE           "/logs.txt"
#define MAX_LOG_BYTES      16384      // max log file size before truncation
#define LOG_BUF_SIZE       512        // RAM buffer, flushed to SD periodically

#include "camera_pins.h"

#endif  // BOARD_CONFIG_H