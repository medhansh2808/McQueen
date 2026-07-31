#include <errno.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <unistd.h>

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#define SERVO_GPIO GPIO_NUM_18
#define MOTOR_IN1_GPIO GPIO_NUM_25
#define MOTOR_IN2_GPIO GPIO_NUM_26
#define MOTOR_PWM_GPIO GPIO_NUM_27

#define LEFT_ANGLE 55
#define CENTER_ANGLE 90
#define RIGHT_ANGLE 125
#define REVERSE_STEERING true
#define SERVO_STEP_DEGREES 1
#define SERVO_UPDATE_MS 5

#define REVERSE_MOTOR false
#define MAX_THROTTLE_COMMAND 1000
#define MAX_MOTOR_PWM 255
#define THROTTLE_STEP 25
#define MOTOR_UPDATE_MS 10
#define DIRECTION_PAUSE_MS 200
#define FAILSAFE_MS 300
#define STATUS_UPDATE_MS 67

#define SERVO_LEDC_MODE LEDC_HIGH_SPEED_MODE
#define SERVO_LEDC_TIMER LEDC_TIMER_0
#define SERVO_LEDC_CHANNEL LEDC_CHANNEL_0
#define SERVO_DUTY_MAX 65535U

#define MOTOR_LEDC_MODE LEDC_HIGH_SPEED_MODE
#define MOTOR_LEDC_TIMER LEDC_TIMER_1
#define MOTOR_LEDC_CHANNEL LEDC_CHANNEL_1

#define WIFI_CONNECTED_BIT BIT0

static const char *TAG = "mcqueen";
static EventGroupHandle_t wifi_events;
static QueueHandle_t command_queue;
static portMUX_TYPE status_lock = portMUX_INITIALIZER_UNLOCKED;

typedef enum {
    COMMAND_NORMAL = 0,
    COMMAND_ESTOP,
} command_type_t;

typedef struct {
    command_type_t type;
    int steering;
    int throttle;
    bool motor_enabled;
} vehicle_command_t;

typedef struct {
    int commanded_steering;
    int actual_servo_angle;
    int commanded_throttle;
    int actual_throttle;
    bool failsafe;
    bool wifi_source_active;
} status_snapshot_t;

static status_snapshot_t shared_status = {
    .commanded_steering = 0,
    .actual_servo_angle = CENTER_ANGLE,
    .commanded_throttle = 0,
    .actual_throttle = 0,
    .failsafe = true,
    .wifi_source_active = false,
};

static int clamp_int(int value, int minimum, int maximum)
{
    if (value < minimum) return minimum;
    if (value > maximum) return maximum;
    return value;
}

static int move_towards(int current, int target, int step)
{
    if (current < target) {
        current += step;
        if (current > target) current = target;
    } else if (current > target) {
        current -= step;
        if (current < target) current = target;
    }
    return current;
}

static int steering_to_angle(int steering)
{
    steering = clamp_int(steering, -1000, 1000);
    if (REVERSE_STEERING) steering = -steering;

    int angle = LEFT_ANGLE +
        ((steering + 1000) * (RIGHT_ANGLE - LEFT_ANGLE)) / 2000;
    return clamp_int(angle, LEFT_ANGLE, RIGHT_ANGLE);
}

static void publish_status(
    int commanded_steering,
    int actual_servo_angle,
    int commanded_throttle,
    int actual_throttle,
    bool failsafe,
    bool wifi_source_active)
{
    portENTER_CRITICAL(&status_lock);
    shared_status.commanded_steering = commanded_steering;
    shared_status.actual_servo_angle = actual_servo_angle;
    shared_status.commanded_throttle = commanded_throttle;
    shared_status.actual_throttle = actual_throttle;
    shared_status.failsafe = failsafe;
    shared_status.wifi_source_active = wifi_source_active;
    portEXIT_CRITICAL(&status_lock);
}

static status_snapshot_t read_status(void)
{
    status_snapshot_t result;
    portENTER_CRITICAL(&status_lock);
    result = shared_status;
    portEXIT_CRITICAL(&status_lock);
    return result;
}

static void servo_write_angle(int angle)
{
    angle = clamp_int(angle, 0, 180);
    uint32_t pulse_us = 500U + ((uint32_t)angle * 2000U) / 180U;
    uint32_t duty = (pulse_us * SERVO_DUTY_MAX) / 20000U;

    ESP_ERROR_CHECK(ledc_set_duty(
        SERVO_LEDC_MODE, SERVO_LEDC_CHANNEL, duty));
    ESP_ERROR_CHECK(ledc_update_duty(
        SERVO_LEDC_MODE, SERVO_LEDC_CHANNEL));
}

static void motor_write_pwm(uint32_t duty)
{
    if (duty > MAX_MOTOR_PWM) duty = MAX_MOTOR_PWM;
    ESP_ERROR_CHECK(ledc_set_duty(
        MOTOR_LEDC_MODE, MOTOR_LEDC_CHANNEL, duty));
    ESP_ERROR_CHECK(ledc_update_duty(
        MOTOR_LEDC_MODE, MOTOR_LEDC_CHANNEL));
}

static void motor_write_throttle(int throttle)
{
    throttle = clamp_int(
        throttle, -MAX_THROTTLE_COMMAND, MAX_THROTTLE_COMMAND);
    if (REVERSE_MOTOR) throttle = -throttle;

    uint32_t pwm = ((uint32_t)abs(throttle) * MAX_MOTOR_PWM) / MAX_THROTTLE_COMMAND;

    if (throttle > 0) {
        gpio_set_level(MOTOR_IN1_GPIO, 1);
        gpio_set_level(MOTOR_IN2_GPIO, 0);
        motor_write_pwm(pwm);
    } else if (throttle < 0) {
        gpio_set_level(MOTOR_IN1_GPIO, 0);
        gpio_set_level(MOTOR_IN2_GPIO, 1);
        motor_write_pwm(pwm);
    } else {
        motor_write_pwm(0);
        gpio_set_level(MOTOR_IN1_GPIO, 0);
        gpio_set_level(MOTOR_IN2_GPIO, 0);
    }
}

static void configure_outputs(void)
{
    gpio_config_t motor_gpio = {
        .pin_bit_mask = (1ULL << MOTOR_IN1_GPIO) | (1ULL << MOTOR_IN2_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&motor_gpio));
    gpio_set_level(MOTOR_IN1_GPIO, 0);
    gpio_set_level(MOTOR_IN2_GPIO, 0);

    ledc_timer_config_t servo_timer = {
        .speed_mode = SERVO_LEDC_MODE,
        .duty_resolution = LEDC_TIMER_16_BIT,
        .timer_num = SERVO_LEDC_TIMER,
        .freq_hz = 50,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&servo_timer));

    ledc_channel_config_t servo_channel = {
        .gpio_num = SERVO_GPIO,
        .speed_mode = SERVO_LEDC_MODE,
        .channel = SERVO_LEDC_CHANNEL,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = SERVO_LEDC_TIMER,
        .duty = 0,
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&servo_channel));

    ledc_timer_config_t motor_timer = {
        .speed_mode = MOTOR_LEDC_MODE,
        .duty_resolution = LEDC_TIMER_8_BIT,
        .timer_num = MOTOR_LEDC_TIMER,
        .freq_hz = 20000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&motor_timer));

    ledc_channel_config_t motor_channel = {
        .gpio_num = MOTOR_PWM_GPIO,
        .speed_mode = MOTOR_LEDC_MODE,
        .channel = MOTOR_LEDC_CHANNEL,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = MOTOR_LEDC_TIMER,
        .duty = 0,
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&motor_channel));

    servo_write_angle(CENTER_ANGLE);
    motor_write_throttle(0);
}

static void control_task(void *argument)
{
    (void)argument;

    int commanded_steering = 0;
    int target_servo_angle = CENTER_ANGLE;
    int actual_servo_angle = CENTER_ANGLE;
    int commanded_throttle = 0;
    int target_throttle = 0;
    int actual_throttle = 0;

    bool failsafe = true;
    bool wifi_source_active = false;
    bool direction_pause = false;

    TickType_t last_command = xTaskGetTickCount();
    TickType_t last_servo_update = last_command;
    TickType_t last_motor_update = last_command;
    TickType_t direction_pause_started = 0;
    TickType_t last_wake = last_command;

    while (true) {
        vehicle_command_t command;
        while (xQueueReceive(command_queue, &command, 0) == pdTRUE) {
            if (command.type == COMMAND_ESTOP) {
                commanded_steering = 0;
                target_servo_angle = CENTER_ANGLE;
                actual_servo_angle = CENTER_ANGLE;
                commanded_throttle = 0;
                target_throttle = 0;
                actual_throttle = 0;
                direction_pause = false;
                failsafe = false;
                wifi_source_active = false;
                servo_write_angle(CENTER_ANGLE);
                motor_write_throttle(0);
            } else {
                commanded_steering = clamp_int(command.steering, -1000, 1000);
                target_servo_angle = steering_to_angle(commanded_steering);
                commanded_throttle = command.motor_enabled
                    ? clamp_int(command.throttle,
                        -MAX_THROTTLE_COMMAND, MAX_THROTTLE_COMMAND)
                    : 0;
                target_throttle = commanded_throttle;
                failsafe = false;
                wifi_source_active = true;
            }
            last_command = xTaskGetTickCount();
        }

        TickType_t now = xTaskGetTickCount();

        if (now - last_command > pdMS_TO_TICKS(FAILSAFE_MS)) {
            commanded_steering = 0;
            target_servo_angle = CENTER_ANGLE;
            commanded_throttle = 0;
            target_throttle = 0;
            failsafe = true;
            wifi_source_active = false;
        }

        if (now - last_servo_update >= pdMS_TO_TICKS(SERVO_UPDATE_MS)) {
            last_servo_update = now;
            int next_angle = move_towards(
                actual_servo_angle, target_servo_angle, SERVO_STEP_DEGREES);
            if (next_angle != actual_servo_angle) {
                actual_servo_angle = next_angle;
                servo_write_angle(actual_servo_angle);
            }
        }

        if (now - last_motor_update >= pdMS_TO_TICKS(MOTOR_UPDATE_MS)) {
            last_motor_update = now;

            if (direction_pause) {
                motor_write_throttle(0);
                if (now - direction_pause_started >=
                    pdMS_TO_TICKS(DIRECTION_PAUSE_MS)) {
                    direction_pause = false;
                }
            } else {
                bool changing_direction =
                    (actual_throttle > 0 && target_throttle < 0) ||
                    (actual_throttle < 0 && target_throttle > 0);
                int ramp_target = changing_direction ? 0 : target_throttle;
                int next_throttle = move_towards(
                    actual_throttle, ramp_target, THROTTLE_STEP);

                if (next_throttle != actual_throttle) {
                    actual_throttle = next_throttle;
                    motor_write_throttle(actual_throttle);
                }

                if (changing_direction && actual_throttle == 0) {
                    direction_pause = true;
                    direction_pause_started = now;
                    motor_write_throttle(0);
                }
            }
        }

        publish_status(
            commanded_steering,
            actual_servo_angle,
            commanded_throttle,
            actual_throttle,
            failsafe,
            wifi_source_active);

        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(5));
    }
}

static void submit_command(const vehicle_command_t *command)
{
    xQueueOverwrite(command_queue, command);
}

static void initialise_wifi(void)
{
    wifi_events = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t wifi_init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_init));
    esp_netif_create_default_wifi_ap();

    wifi_config_t config = {0};
    strlcpy((char *)config.ap.ssid,
        CONFIG_MCQUEEN_AP_SSID, sizeof(config.ap.ssid));
    strlcpy((char *)config.ap.password,
        CONFIG_MCQUEEN_AP_PASSWORD, sizeof(config.ap.password));
    config.ap.ssid_len = strlen(CONFIG_MCQUEEN_AP_SSID);
    config.ap.channel = CONFIG_MCQUEEN_AP_CHANNEL;
    config.ap.max_connection = 4;
    config.ap.authmode = strlen(CONFIG_MCQUEEN_AP_PASSWORD) >= 8
        ? WIFI_AUTH_WPA2_PSK
        : WIFI_AUTH_OPEN;
    config.ap.pmf_cfg.capable = true;
    config.ap.pmf_cfg.required = false;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &config));
    ESP_ERROR_CHECK(esp_wifi_start());

    /* The default ESP-IDF SoftAP interface uses 192.168.4.1. */
    xEventGroupSetBits(wifi_events, WIFI_CONNECTED_BIT);
    ESP_LOGI(TAG, "Kachow hotspot ready");
    ESP_LOGI(TAG, "SSID: %s", CONFIG_MCQUEEN_AP_SSID);
    ESP_LOGI(TAG, "Car IP: 192.168.4.1");
}

typedef struct {
    bool peer_valid;
    struct sockaddr_in peer;
    char session[32];
    bool session_valid;
    bool session_armed;
    uint32_t last_sequence;
    int64_t echo_timestamp_ms;
} udp_client_t;

static bool valid_token(const char *token)
{
    return strcmp(token, CONFIG_MCQUEEN_CONTROL_TOKEN) == 0;
}

static void process_packet(
    char *line,
    const struct sockaddr_in *sender,
    udp_client_t *client)
{
    char type = 0;
    char token[64] = {0};
    char session[32] = {0};
    uint32_t sequence = 0;
    int64_t timestamp_ms = 0;

    int fields = sscanf(line,
        "%c,%63[^,],%31[^,],%" SCNu32 ",%" SCNd64,
        &type, token, session, &sequence, &timestamp_ms);
    if (fields != 5 || !valid_token(token)) return;

    if (!client->session_valid || strcmp(client->session, session) != 0) {
        strlcpy(client->session, session, sizeof(client->session));
        client->session_valid = true;
        client->session_armed = false;
        client->last_sequence = 0;
    } else if (sequence <= client->last_sequence) {
        return;
    }

    client->last_sequence = sequence;
    client->echo_timestamp_ms = timestamp_ms;
    client->peer = *sender;
    client->peer_valid = true;

    if (type == 'H') return;

    if (type == 'E') {
        client->session_armed = false;
        vehicle_command_t stop = {.type = COMMAND_ESTOP};
        submit_command(&stop);
        return;
    }

    if (type != 'C') return;

    int steering = 0;
    int throttle = 0;
    int motor_enabled = 0;
    fields = sscanf(line,
        "C,%63[^,],%31[^,],%" SCNu32 ",%" SCNd64 ",%d,%d,%d",
        token, session, &sequence, &timestamp_ms,
        &steering, &throttle, &motor_enabled);
    if (fields != 7) return;

    steering = clamp_int(steering, -1000, 1000);
    throttle = clamp_int(
        throttle, -MAX_THROTTLE_COMMAND, MAX_THROTTLE_COMMAND);

    ESP_LOGI(TAG,
        "RX steer=%d throttle=%d motor_enabled=%d effective=%d",
        steering,
        throttle,
        motor_enabled,
        (motor_enabled != 0) || (throttle != 0));

    if (!client->session_armed) {
        if (steering == 0 && throttle == 0) {
            client->session_armed = true;
        } else {
            return;
        }
    }

    vehicle_command_t command = {
        .type = COMMAND_NORMAL,
        .steering = steering,
        .throttle = throttle,
        .motor_enabled = (motor_enabled != 0) || (throttle != 0),
    };
    submit_command(&command);
}

static void send_status_packet(int socket_fd, const udp_client_t *client)
{
    if (!client->peer_valid || !client->session_valid) return;

    status_snapshot_t status = read_status();
    int rssi = -1; /* SoftAP mode: station RSSI is not reported here. */

    char buffer[256];
    int length = snprintf(buffer, sizeof(buffer),
        "S,%s,%" PRIu32 ",%" PRId64 ",%d,%d,%d,%d,%d,%s,%d\n",
        client->session,
        client->last_sequence,
        client->echo_timestamp_ms,
        status.commanded_steering,
        status.actual_servo_angle,
        status.commanded_throttle,
        status.actual_throttle,
        status.failsafe ? 1 : 0,
        status.wifi_source_active ? "WIFI" : "NONE",
        rssi);

    if (length > 0 && length < (int)sizeof(buffer)) {
        sendto(socket_fd, buffer, (size_t)length, 0,
            (const struct sockaddr *)&client->peer, sizeof(client->peer));
    }
}

static void udp_task(void *argument)
{
    (void)argument;

    while (true) {
        xEventGroupWaitBits(wifi_events, WIFI_CONNECTED_BIT,
            pdFALSE, pdTRUE, portMAX_DELAY);

        int socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
        if (socket_fd < 0) {
            ESP_LOGE(TAG, "socket failed: errno %d", errno);
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        struct timeval timeout = {.tv_sec = 0, .tv_usec = 20000};
        setsockopt(socket_fd, SOL_SOCKET, SO_RCVTIMEO,
            &timeout, sizeof(timeout));

        struct sockaddr_in local = {
            .sin_family = AF_INET,
            .sin_port = htons(CONFIG_MCQUEEN_UDP_PORT),
            .sin_addr.s_addr = htonl(INADDR_ANY),
        };

        if (bind(socket_fd, (struct sockaddr *)&local, sizeof(local)) < 0) {
            ESP_LOGE(TAG, "bind failed: errno %d", errno);
            close(socket_fd);
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        ESP_LOGI(TAG, "UDP controller listening on port %d",
            CONFIG_MCQUEEN_UDP_PORT);

        udp_client_t client = {0};
        TickType_t last_status = xTaskGetTickCount();

        while (xEventGroupGetBits(wifi_events) & WIFI_CONNECTED_BIT) {
            char buffer[256];
            struct sockaddr_in sender = {0};
            socklen_t sender_size = sizeof(sender);
            ssize_t received = recvfrom(socket_fd, buffer, sizeof(buffer) - 1,
                0, (struct sockaddr *)&sender, &sender_size);

            if (received > 0) {
                buffer[received] = '\0';
                char *newline = strpbrk(buffer, "\r\n");
                if (newline) *newline = '\0';
                process_packet(buffer, &sender, &client);
            } else if (received < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                ESP_LOGW(TAG, "recvfrom failed: errno %d", errno);
                break;
            }

            TickType_t now = xTaskGetTickCount();
            if (now - last_status >= pdMS_TO_TICKS(STATUS_UPDATE_MS)) {
                send_status_packet(socket_fd, &client);
                last_status = now;
            }
        }

        close(socket_fd);
    }
}

void app_main(void)
{
    esp_err_t result = nvs_flash_init();
    if (result == ESP_ERR_NVS_NO_FREE_PAGES ||
        result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    } else {
        ESP_ERROR_CHECK(result);
    }

    command_queue = xQueueCreate(1, sizeof(vehicle_command_t));
    if (command_queue == NULL) abort();

    configure_outputs();
    initialise_wifi();

    BaseType_t control_created = xTaskCreatePinnedToCore(
        control_task, "vehicle_control", 4096, NULL, 5, NULL, 1);
    BaseType_t udp_created = xTaskCreate(
        udp_task, "udp_server", 6144, NULL, 4, NULL);

    if (control_created != pdPASS || udp_created != pdPASS) abort();

    ESP_LOGI(TAG, "Kachow direct-hotspot controller ready");
    ESP_LOGI(TAG, "Local motor failsafe: %d ms", FAILSAFE_MS);

    /* app_main returns; dedicated tasks continue running. */
}
