
#include <errno.h>
#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "nvs_flash.h"

#include "app_config.h"

#define WIFI_SSID "KACHOW-CAR"
#define WIFI_PASS "kachow123"
#define UDP_PORT 5007

#define MOTOR_IN1_GPIO GPIO_NUM_25
#define MOTOR_IN2_GPIO GPIO_NUM_26
#define MOTOR_PWM_GPIO GPIO_NUM_27
#define SERVO_GPIO GPIO_NUM_18

#define MOTOR_TIMER LEDC_TIMER_0
#define MOTOR_CHANNEL LEDC_CHANNEL_0
#define MOTOR_MODE LEDC_LOW_SPEED_MODE
#define MOTOR_DUTY_MAX 1023
#define MOTOR_DUTY_LIMIT 716

#define SERVO_TIMER LEDC_TIMER_1
#define SERVO_CHANNEL LEDC_CHANNEL_1
#define SERVO_MODE LEDC_LOW_SPEED_MODE
#define SERVO_PERIOD_US 20000
#define SERVO_MIN_US 1000
#define SERVO_MAX_US 2000

#define FAILSAFE_US 300000
#define DIRECTION_NEUTRAL_US 200000
#define CONTROL_PERIOD_MS 10
#define THROTTLE_STEP 25
#define STEER_STEP 25

static const char *TAG = "kachow_reverse";

static volatile int target_throttle = 0;
static volatile int target_steer = 0;
static volatile int64_t last_command_us = 0;

static int clamp_i(int x, int lo, int hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static int sign_i(int x) {
    return (x > 0) - (x < 0);
}

static void motor_set_signed(int signed_command) {
    signed_command = clamp_i(signed_command, -1000, 1000);
    int magnitude = abs(signed_command);
    uint32_t duty = (uint32_t)((magnitude * MOTOR_DUTY_LIMIT) / 1000);

    if (signed_command > 0) {
        gpio_set_level(MOTOR_IN1_GPIO, 1);
        gpio_set_level(MOTOR_IN2_GPIO, 0);
    } else if (signed_command < 0) {
        gpio_set_level(MOTOR_IN1_GPIO, 0);
        gpio_set_level(MOTOR_IN2_GPIO, 1);
    } else {
        gpio_set_level(MOTOR_IN1_GPIO, 0);
        gpio_set_level(MOTOR_IN2_GPIO, 0);
        duty = 0;
    }

    ESP_ERROR_CHECK(ledc_set_duty(MOTOR_MODE, MOTOR_CHANNEL, duty));
    ESP_ERROR_CHECK(ledc_update_duty(MOTOR_MODE, MOTOR_CHANNEL));
}

static void servo_set_command(int command) {
    command = clamp_i(command, -1000, 1000);
    int pulse_us = 1500 + (command * 500) / 1000;
    pulse_us = clamp_i(pulse_us, SERVO_MIN_US, SERVO_MAX_US);
    uint32_t duty = (uint32_t)(((uint64_t)pulse_us * 65535ULL) / SERVO_PERIOD_US);
    ESP_ERROR_CHECK(ledc_set_duty(SERVO_MODE, SERVO_CHANNEL, duty));
    ESP_ERROR_CHECK(ledc_update_duty(SERVO_MODE, SERVO_CHANNEL));
}

static void configure_outputs(void) {
    gpio_config_t io = {
        .pin_bit_mask = (1ULL << MOTOR_IN1_GPIO) | (1ULL << MOTOR_IN2_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = false,
        .pull_down_en = false,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io));
    gpio_set_level(MOTOR_IN1_GPIO, 0);
    gpio_set_level(MOTOR_IN2_GPIO, 0);

    ledc_timer_config_t motor_timer = {
        .speed_mode = MOTOR_MODE,
        .duty_resolution = LEDC_TIMER_10_BIT,
        .timer_num = MOTOR_TIMER,
        .freq_hz = 20000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&motor_timer));

    ledc_channel_config_t motor_channel = {
        .gpio_num = MOTOR_PWM_GPIO,
        .speed_mode = MOTOR_MODE,
        .channel = MOTOR_CHANNEL,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = MOTOR_TIMER,
        .duty = 0,
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&motor_channel));

    ledc_timer_config_t servo_timer = {
        .speed_mode = SERVO_MODE,
        .duty_resolution = LEDC_TIMER_16_BIT,
        .timer_num = SERVO_TIMER,
        .freq_hz = 50,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&servo_timer));

    ledc_channel_config_t servo_channel = {
        .gpio_num = SERVO_GPIO,
        .speed_mode = SERVO_MODE,
        .channel = SERVO_CHANNEL,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = SERVO_TIMER,
        .duty = 0,
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&servo_channel));

    motor_set_signed(0);
    servo_set_command(0);
}

static void wifi_ap_start(void) {
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));

    wifi_config_t cfg = {0};
    snprintf((char *)cfg.ap.ssid, sizeof(cfg.ap.ssid), "%s", WIFI_SSID);
    snprintf((char *)cfg.ap.password, sizeof(cfg.ap.password), "%s", WIFI_PASS);
    cfg.ap.ssid_len = strlen(WIFI_SSID);
    cfg.ap.channel = 1;
    cfg.ap.max_connection = 4;
    cfg.ap.authmode = WIFI_AUTH_WPA2_PSK;
    cfg.ap.pmf_cfg.required = false;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &cfg));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "AP ready: %s, UDP %d", WIFI_SSID, UDP_PORT);
}

static bool parse_packet(char *buf, int *steer, int *throttle) {
    char *tokens[24] = {0};
    int count = 0;
    char *save = NULL;
    for (char *tok = strtok_r(buf, ",\r\n", &save);
         tok && count < 24;
         tok = strtok_r(NULL, ",\r\n", &save)) {
        tokens[count++] = tok;
    }

    if (APP_STEER_FIELD_INDEX >= count || APP_THROTTLE_FIELD_INDEX >= count) {
        ESP_LOGW(TAG, "Packet has %d fields, need steer=%d throttle=%d",
                 count, APP_STEER_FIELD_INDEX, APP_THROTTLE_FIELD_INDEX);
        return false;
    }

    char *end1 = NULL;
    char *end2 = NULL;
    long s = strtol(tokens[APP_STEER_FIELD_INDEX], &end1, 10);
    long t = strtol(tokens[APP_THROTTLE_FIELD_INDEX], &end2, 10);

    if (end1 == tokens[APP_STEER_FIELD_INDEX] ||
        end2 == tokens[APP_THROTTLE_FIELD_INDEX]) {
        ESP_LOGW(TAG, "Steer/throttle fields are not integers");
        return false;
    }

    *steer = clamp_i((int)s, -1000, 1000);
    *throttle = clamp_i((int)t, -1000, 1000);
    return true;
}

static void udp_task(void *arg) {
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "socket failed: errno=%d", errno);
        vTaskDelete(NULL);
        return;
    }

    struct sockaddr_in addr = {
        .sin_family = AF_INET,
        .sin_port = htons(UDP_PORT),
        .sin_addr.s_addr = htonl(INADDR_ANY),
    };

    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        ESP_LOGE(TAG, "bind failed: errno=%d", errno);
        close(sock);
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "Listening on UDP %d; steer field=%d throttle field=%d",
             UDP_PORT, APP_STEER_FIELD_INDEX, APP_THROTTLE_FIELD_INDEX);

    char rx[512];
    while (1) {
        struct sockaddr_in source = {0};
        socklen_t source_len = sizeof(source);
        int len = recvfrom(sock, rx, sizeof(rx) - 1, 0,
                           (struct sockaddr *)&source, &source_len);
        if (len < 0) {
            ESP_LOGW(TAG, "recvfrom errno=%d", errno);
            continue;
        }

        rx[len] = '\0';
        char parse_copy[512];
        snprintf(parse_copy, sizeof(parse_copy), "%s", rx);

        int s = 0;
        int t = 0;
        if (parse_packet(parse_copy, &s, &t)) {
            target_steer = s;
            target_throttle = t;
            last_command_us = esp_timer_get_time();
            ESP_LOGI(TAG, "RX steer=%d throttle=%d", s, t);
        }
    }
}

static void control_task(void *arg) {
    int current_throttle = 0;
    int current_steer = 0;
    int active_direction = 0;
    int64_t neutral_until_us = 0;

    while (1) {
        const int64_t now = esp_timer_get_time();
        int requested_throttle = target_throttle;
        int requested_steer = target_steer;

        if (last_command_us == 0 || now - last_command_us > FAILSAFE_US) {
            requested_throttle = 0;
            requested_steer = 0;
        }

        int requested_direction = sign_i(requested_throttle);

        if (active_direction != 0 &&
            requested_direction != 0 &&
            requested_direction != active_direction) {
            requested_throttle = 0;
        }

        if (current_throttle < requested_throttle) {
            current_throttle += THROTTLE_STEP;
            if (current_throttle > requested_throttle) current_throttle = requested_throttle;
        } else if (current_throttle > requested_throttle) {
            current_throttle -= THROTTLE_STEP;
            if (current_throttle < requested_throttle) current_throttle = requested_throttle;
        }

        if (current_throttle == 0) {
            if (active_direction != 0 && requested_direction != active_direction) {
                active_direction = 0;
                neutral_until_us = now + DIRECTION_NEUTRAL_US;
            }

            if (active_direction == 0 &&
                requested_direction != 0 &&
                now >= neutral_until_us) {
                active_direction = requested_direction;
            }
        }

        int output_throttle = 0;
        if (active_direction != 0) {
            int magnitude = abs(current_throttle);
            output_throttle = active_direction * magnitude;
        }

        motor_set_signed(output_throttle);

        if (current_steer < requested_steer) {
            current_steer += STEER_STEP;
            if (current_steer > requested_steer) current_steer = requested_steer;
        } else if (current_steer > requested_steer) {
            current_steer -= STEER_STEP;
            if (current_steer < requested_steer) current_steer = requested_steer;
        }
        servo_set_command(current_steer);

        vTaskDelay(pdMS_TO_TICKS(CONTROL_PERIOD_MS));
    }
}

void app_main(void) {
    esp_err_t nvs = nvs_flash_init();
    if (nvs == ESP_ERR_NVS_NO_FREE_PAGES || nvs == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    } else {
        ESP_ERROR_CHECK(nvs);
    }

    configure_outputs();
    wifi_ap_start();

    xTaskCreate(udp_task, "udp", 4096, NULL, 5, NULL);
    xTaskCreate(control_task, "control", 4096, NULL, 6, NULL);
}
