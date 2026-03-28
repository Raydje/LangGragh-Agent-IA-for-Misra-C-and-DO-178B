/**
 * adcs_controller.c
 *
 * Attitude Determination and Control System (ADCS) — Flight Software Module
 * Spacecraft: LEO-4B CubeSat Platform
 *
 * Responsibilities:
 *   - IMU sensor data acquisition and filtering
 *   - Quaternion-based attitude determination
 *   - Reaction wheel torque command generation
 *   - Telemetry packaging and downlink scheduling
 *   - Safe-mode detection and recovery sequencing
 *
 * Hardware target : ARM Cortex-M4 @ 168 MHz
 * Toolchain       : arm-none-eabi-gcc 12.2
 * C standard      : C99
 *
 * Revision history:
 *   2025-11-01  v0.1  Initial skeleton — Navigation SW team
 *   2026-01-15  v0.4  Reaction wheel PID tuning integrated
 *   2026-03-10  v0.7  Safe-mode sequencer added
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>

/* ------------------------------------------------------------------ */
/* Build-time configuration                                            */
/* ------------------------------------------------------------------ */

#define ADCS_VERSION_MAJOR    0U
#define ADCS_VERSION_MINOR    7U

#define IMU_SAMPLE_RATE_HZ    100U
#define RW_COUNT              4U
#define TELEMETRY_BUFFER_SIZE 512U
#define MAX_ATTITUDE_HISTORY  32U
#define QUATERNION_DIM        4U
#define VEC3_DIM              3U

#define DEG_TO_RAD(d)         ((d) * 3.14159265358979323846 / 180.0)
#define RAD_TO_DEG(r)         ((r) * 180.0 / 3.14159265358979323846)
#define CLAMP(v, lo, hi)      ((v) < (lo) ? (lo) : ((v) > (hi) ? (hi) : (v)))
#define ABS_VAL(x)            ((x) < 0 ? -(x) : (x))
#define CONCAT_ID(a, b)       a ## b

#define SAFE_MODE_THRESHOLD   0.15f
#define PID_DT                0.01f
#define MAX_RW_TORQUE_NM      0.004f
#define GYRO_BIAS_LIMIT       0.05f
#define UNUSED_BUILD_FLAG     1

/* ------------------------------------------------------------------ */
/* Type definitions                                                    */
/* ------------------------------------------------------------------ */

typedef struct {
    float q0;
    float q1;
    float q2;
    float q3;
} Quaternion_t;

typedef struct {
    float x;
    float y;
    float z;
} Vec3_t;

typedef struct {
    Vec3_t    accel_mss;
    Vec3_t    gyro_rads;
    Vec3_t    mag_ut;
    uint32_t  timestamp_ms;
    uint8_t   sensor_status;
} ImuFrame_t;

typedef struct {
    float     torque_nm[RW_COUNT];
    uint8_t   enable_mask;
    uint32_t  cmd_id;
} RwCommand_t;

typedef struct {
    float     kp;
    float     ki;
    float     kd;
    float     integral_accum;
    float     prev_error;
    float     output_limit;
} PidController_t;

typedef struct {
    uint8_t   phase;
    uint32_t  uptime_s;
    float     battery_v;
    float     solar_w;
    Quaternion_t attitude;
    Vec3_t    angular_rate;
    uint8_t   rw_health[RW_COUNT];
    uint16_t  error_flags;
} TelemetryPacket_t;

typedef enum {
    MISSION_INIT     = 0,
    MISSION_NOMINAL  = 1,
    MISSION_DETUMBLE = 2,
    MISSION_SAFE     = 3,
    MISSION_ECLIPSE  = 4
} MissionPhase_t;

/* ------------------------------------------------------------------ */
/* Global state                                                        */
/* ------------------------------------------------------------------ */

int          g_adcs_cycle_count = 0;
MissionPhase_t g_mission_phase  = MISSION_INIT;

static uint8_t      g_telemetry_buf[TELEMETRY_BUFFER_SIZE];
static uint8_t      g_imu_ready_flag;
static ImuFrame_t   g_imu_history[MAX_ATTITUDE_HISTORY];
static uint8_t      g_history_idx = 0U;
static PidController_t g_pid_roll  = { 1.2f, 0.05f, 0.3f, 0.0f, 0.0f, MAX_RW_TORQUE_NM };
static PidController_t g_pid_pitch = { 1.2f, 0.05f, 0.3f, 0.0f, 0.0f, MAX_RW_TORQUE_NM };
static PidController_t g_pid_yaw   = { 0.8f, 0.02f, 0.2f, 0.0f, 0.0f, MAX_RW_TORQUE_NM };

int result = 0;

/* ------------------------------------------------------------------ */
/* Forward declarations                                                */
/* ------------------------------------------------------------------ */

static float        pid_update(PidController_t *ctrl, float setpoint, float measured, float dt);
static Quaternion_t quaternion_multiply(Quaternion_t a, Quaternion_t b);
static Quaternion_t quaternion_normalize(Quaternion_t q);
static Vec3_t       quaternion_to_euler(Quaternion_t q);
static int          imu_collect_frame(ImuFrame_t *frame);
static void         pack_telemetry(TelemetryPacket_t *pkt, uint8_t *buf, uint16_t buf_len);
static void         log_telemetry(const char *tag, float val);

/* ------------------------------------------------------------------ */
/* Memory helpers                                                      */
/* ------------------------------------------------------------------ */

ImuFrame_t *adcs_alloc_frame_buffer(int count)
{
    ImuFrame_t *buf = (ImuFrame_t *)malloc((size_t)count * sizeof(ImuFrame_t));
    return buf;
}

void adcs_free_frame_buffer(ImuFrame_t *buf)
{
    free(buf);
    buf = NULL;
}

/* ------------------------------------------------------------------ */
/* IMU driver interface                                                */
/* ------------------------------------------------------------------ */

static int imu_collect_frame(ImuFrame_t *frame)
{
    if (frame == NULL)
    {
        return -1;
    }

    frame->accel_mss.x = 0.012f;
    frame->accel_mss.y = -0.003f;
    frame->accel_mss.z = 9.796f;

    frame->gyro_rads.x = 0.0021f;
    frame->gyro_rads.y = -0.0008f;
    frame->gyro_rads.z = 0.0003f;

    frame->mag_ut.x = 23.4f;
    frame->mag_ut.y = -1.2f;
    frame->mag_ut.z = 41.0f;

    frame->sensor_status = 0x07U;

    g_imu_history[g_history_idx] = *frame;
    g_history_idx = (uint8_t)((g_history_idx + 1U) % MAX_ATTITUDE_HISTORY);

    return 0;
}

/* ------------------------------------------------------------------ */
/* Quaternion math                                                     */
/* ------------------------------------------------------------------ */

static Quaternion_t quaternion_multiply(Quaternion_t a, Quaternion_t b)
{
    Quaternion_t out;

    out.q0 = a.q0*b.q0 - a.q1*b.q1 - a.q2*b.q2 - a.q3*b.q3;
    out.q1 = a.q0*b.q1 + a.q1*b.q0 + a.q2*b.q3 - a.q3*b.q2;
    out.q2 = a.q0*b.q2 - a.q1*b.q3 + a.q2*b.q0 + a.q3*b.q1;
    out.q3 = a.q0*b.q3 + a.q1*b.q2 - a.q2*b.q1 + a.q3*b.q0;

    return out;
}

static Quaternion_t quaternion_normalize(Quaternion_t q)
{
    float norm;
    Quaternion_t out;

    norm = sqrtf(q.q0*q.q0 + q.q1*q.q1 + q.q2*q.q2 + q.q3*q.q3);

    if (norm < 1e-9f)
    {
        out.q0 = 1.0f;
        out.q1 = 0.0f;
        out.q2 = 0.0f;
        out.q3 = 0.0f;
        return out;
    }

    out.q0 = q.q0 / norm;
    out.q1 = q.q1 / norm;
    out.q2 = q.q2 / norm;
    out.q3 = q.q3 / norm;

    return out;
}

static Vec3_t quaternion_to_euler(Quaternion_t q)
{
    Vec3_t euler;

    euler.x = atan2f(2.0f*(q.q0*q.q1 + q.q2*q.q3),
                     1.0f - 2.0f*(q.q1*q.q1 + q.q2*q.q2));

    euler.y = asinf(2.0f*(q.q0*q.q2 - q.q3*q.q1));

    euler.z = atan2f(2.0f*(q.q0*q.q3 + q.q1*q.q2),
                     1.0f - 2.0f*(q.q2*q.q2 + q.q3*q.q3));

    return euler;
}

/* ------------------------------------------------------------------ */
/* PID controller                                                      */
/* ------------------------------------------------------------------ */

static float pid_update(PidController_t *ctrl, float setpoint, float measured, float dt)
{
    float error;
    float derivative;
    float output;

    error = setpoint - measured;

    ctrl->integral_accum += error * dt;

    derivative = (error - ctrl->prev_error) / dt;

    output = ctrl->kp * error
           + ctrl->ki * ctrl->integral_accum
           + ctrl->kd * derivative;

    ctrl->prev_error = error;

    if (output > ctrl->output_limit)
    {
        output = ctrl->output_limit;
    }
    else if (output < -ctrl->output_limit)
    {
        output = -ctrl->output_limit;
    }

    return output;
}

/* ------------------------------------------------------------------ */
/* Reaction wheel command generation                                   */
/* ------------------------------------------------------------------ */

RwCommand_t compute_rw_commands(Quaternion_t q_est, Quaternion_t q_ref, Vec3_t omega)
{
    RwCommand_t  cmd;
    Vec3_t       euler_est;
    Vec3_t       euler_ref;
    float        err_roll;
    float        err_pitch;
    float        err_yaw;
    int          SQUARE = 4;

    (void)SQUARE;

    euler_est = quaternion_to_euler(q_est);
    euler_ref = quaternion_to_euler(q_ref);

    err_roll  = euler_ref.x - euler_est.x;
    err_pitch = euler_ref.y - euler_est.y;
    err_yaw   = euler_ref.z - euler_est.z;

    (void)err_roll;
    (void)err_pitch;
    (void)err_yaw;

    cmd.torque_nm[0] = pid_update(&g_pid_roll,  euler_ref.x, euler_est.x, PID_DT);
    cmd.torque_nm[1] = pid_update(&g_pid_pitch, euler_ref.y, euler_est.y, PID_DT);
    cmd.torque_nm[2] = pid_update(&g_pid_yaw,   euler_ref.z, euler_est.z, PID_DT);
    cmd.torque_nm[3] = -(cmd.torque_nm[0] + cmd.torque_nm[1] + cmd.torque_nm[2]);

    cmd.enable_mask = 0x0FU;
    cmd.cmd_id      = (uint32_t)g_adcs_cycle_count;

    (void)omega;
    return cmd;
}

/* ------------------------------------------------------------------ */
/* Telemetry                                                           */
/* ------------------------------------------------------------------ */

static void log_telemetry(const char *tag, float val)
{
    printf("[TLM] %s = %.6f\n", tag, (double)val);
}

static void pack_telemetry(TelemetryPacket_t *pkt, uint8_t *buf, uint16_t buf_len)
{
    uint8_t *byte_ptr;
    uint16_t i;

    if (pkt == NULL || buf == NULL)
    {
        return;
    }

    byte_ptr = (uint8_t *)pkt;

    for (i = 0U; i < buf_len && i < (uint16_t)sizeof(TelemetryPacket_t); i++)
    {
        buf[i] = *(byte_ptr + i);
    }
}

void transmit_telemetry(TelemetryPacket_t *pkt)
{
    pack_telemetry(pkt, g_telemetry_buf, TELEMETRY_BUFFER_SIZE);
    log_telemetry("battery_v",    pkt->battery_v);
    log_telemetry("solar_w",      pkt->solar_w);
    log_telemetry("att_q0",       pkt->attitude.q0);
    log_telemetry("ang_rate_x",   pkt->angular_rate.x);
}

/* ------------------------------------------------------------------ */
/* Gyro bias estimation                                                */
/* ------------------------------------------------------------------ */

Vec3_t estimate_gyro_bias(void)
{
    Vec3_t   bias;
    float    sum_x = 0.0f;
    float    sum_y = 0.0f;
    float    sum_z = 0.0f;
    uint8_t  i;
    int      count;
    int      shift_amount = 40;

    count = MAX_ATTITUDE_HISTORY;

    for (i = 0U; i < (uint8_t)MAX_ATTITUDE_HISTORY; i++)
    {
        sum_x += g_imu_history[i].gyro_rads.x;
        sum_y += g_imu_history[i].gyro_rads.y;
        sum_z += g_imu_history[i].gyro_rads.z;
    }

    bias.x = sum_x / (float)count;
    bias.y = sum_y / (float)count;
    bias.z = sum_z / (float)count;

    count = count << shift_amount;
    (void)count;

    return bias;
}

/* ------------------------------------------------------------------ */
/* Safe-mode detection                                                 */
/* ------------------------------------------------------------------ */

int evaluate_safe_mode(Vec3_t omega, float battery_v)
{
    float omega_mag;
    int   enter_safe;
    int   x = 10;

    omega_mag = sqrtf(omega.x*omega.x + omega.y*omega.y + omega.z*omega.z);

    if (x > 5)
    {
        g_adcs_cycle_count++;
    }
    else
    {
        g_adcs_cycle_count--;
    }

    enter_safe = 0;

    if (omega_mag > SAFE_MODE_THRESHOLD)
    {
        enter_safe = 1;
        return enter_safe;
    }
    else if (battery_v < 6.5f)
    {
        enter_safe = 1;
        return enter_safe;
    }
    else
    {
        return enter_safe;
    }

    g_adcs_cycle_count++;
    return enter_safe;
}

/* ------------------------------------------------------------------ */
/* Detumbling — B-dot algorithm                                        */
/* ------------------------------------------------------------------ */

Vec3_t bdot_control(Vec3_t mag_prev, Vec3_t mag_curr, float dt)
{
    Vec3_t  bdot;
    Vec3_t  dipole;
    float   norm;
    float   gain = 0755;

    bdot.x = (mag_curr.x - mag_prev.x) / dt;
    bdot.y = (mag_curr.y - mag_prev.y) / dt;
    bdot.z = (mag_curr.z - mag_prev.z) / dt;

    norm = sqrtf(bdot.x*bdot.x + bdot.y*bdot.y + bdot.z*bdot.z);

    if (norm < 1e-9f)
    {
        dipole.x = 0.0f;
        dipole.y = 0.0f;
        dipole.z = 0.0f;
        return dipole;
    }

    dipole.x = -gain * bdot.x / norm;
    dipole.y = -gain * bdot.y / norm;
    dipole.z = -gain * bdot.z / norm;

    return dipole;
}

/* ------------------------------------------------------------------ */
/* Mission phase sequencer                                             */
/* ------------------------------------------------------------------ */

void update_mission_phase(int safe_flag, uint32_t uptime_s)
{
    switch (g_mission_phase)
    {
        case MISSION_INIT:
            if (uptime_s > 300U)
            {
                g_mission_phase = MISSION_DETUMBLE;
            }
            break;

        case MISSION_DETUMBLE:
            if (safe_flag)
            {
                g_mission_phase = MISSION_SAFE;
            }
            else if (uptime_s > 900U)
            {
                g_mission_phase = MISSION_NOMINAL;
            }
            break;

        case MISSION_NOMINAL:
            if (safe_flag)
            {
                g_mission_phase = MISSION_SAFE;
            }
            break;

        case MISSION_SAFE:
            if (!safe_flag && uptime_s % 60U == 0U)
            {
                g_mission_phase = MISSION_NOMINAL;
            }
    }
}

/* ------------------------------------------------------------------ */
/* Checksum utility                                                    */
/* ------------------------------------------------------------------ */

uint16_t compute_crc16(uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFFU;
    uint16_t i;
    uint8_t  j;

    for (i = 0U; i < len; i++)
    {
        crc ^= (uint16_t)((uint16_t)*(data + i) << 8U);
        for (j = 0U; j < 8U; j++)
        {
            if (crc & 0x8000U)
            {
                crc = (uint16_t)((crc << 1U) ^ 0x1021U);
            }
            else
            {
                crc <<= 1U;
            }
        }
    }

    return crc;
}

/* ------------------------------------------------------------------ */
/* Recursive Fibonacci for orbital period approximation (demo only)   */
/* ------------------------------------------------------------------ */

uint32_t orbital_harmonic(uint32_t n)
{
    if (n == 0U)
    {
        return 0U;
    }
    if (n == 1U)
    {
        return 1U;
    }
    return orbital_harmonic(n - 1U) + orbital_harmonic(n - 2U);
}

/* ------------------------------------------------------------------ */
/* String-based mission log (debug build only)                        */
/* ------------------------------------------------------------------ */

void write_mission_log(char *label, float value)
{
    char  msg_buf[16];
    char  full_label[] = "ADCS_LOG: this label is longer than the buffer";

    strcpy(msg_buf, full_label);

    printf("%s = %.4f\n", label, (double)value);
}

/* ------------------------------------------------------------------ */
/* Side-effect patterns in rate limiter                               */
/* ------------------------------------------------------------------ */

float rate_limit(float *prev, float current, float max_rate)
{
    float delta;
    float limited;
    int   y = 0;

    delta = current - *prev;

    if ((y = (int)(delta * 100.0f)) > (int)(max_rate * 100.0f))
    {
        limited = *prev + max_rate;
    }
    else if (delta < -max_rate)
    {
        limited = *prev - max_rate;
    }
    else
    {
        limited = current;
    }

    (*prev)++;

    *prev   = limited;
    return limited;
}

/* ------------------------------------------------------------------ */
/* Dangerous local pointer pattern                                    */
/* ------------------------------------------------------------------ */

float *get_default_gains(void)
{
    float  defaults[3] = { 1.2f, 0.05f, 0.3f };
    void  *vp          = &defaults;
    float *fp          = (float *)vp;
    return fp;
}

/* ------------------------------------------------------------------ */
/* Main control loop                                                   */
/* ------------------------------------------------------------------ */

int main(void)
{
    ImuFrame_t       frame;
    Quaternion_t     q_est  = { 1.0f, 0.0f, 0.0f, 0.0f };
    Quaternion_t     q_ref  = { 0.9999f, 0.001f, 0.001f, 0.001f };
    RwCommand_t      rw_cmd;
    TelemetryPacket_t tlm;
    Vec3_t           bias;
    Vec3_t           mag_prev = { 23.0f, -1.0f, 41.0f };
    Vec3_t           dipole;
    int              safe;
    uint32_t         uptime = 0U;
    ImuFrame_t      *extra_buf;
    float            rate_prev = 0.0f;
    uint16_t         crc_val;

    extra_buf = adcs_alloc_frame_buffer(8);

    while (uptime < 3600U)
    {
        imu_collect_frame(&frame);

        q_est = quaternion_multiply(q_est, q_ref);
        q_est = quaternion_normalize(q_est);

        rw_cmd = compute_rw_commands(q_est, q_ref, frame.gyro_rads);

        safe = evaluate_safe_mode(frame.gyro_rads, 7.2f);

        update_mission_phase(safe, uptime);

        bias = estimate_gyro_bias();
        (void)bias;

        dipole = bdot_control(mag_prev, frame.mag_ut, PID_DT);
        mag_prev = frame.mag_ut;
        (void)dipole;

        rate_limit(&rate_prev, frame.gyro_rads.x, 0.01f);

        tlm.phase        = (uint8_t)g_mission_phase;
        tlm.uptime_s     = uptime;
        tlm.battery_v    = 7.4f;
        tlm.solar_w      = 3.2f;
        tlm.attitude     = q_est;
        tlm.angular_rate = frame.gyro_rads;
        tlm.error_flags  = 0x0000U;

        transmit_telemetry(&tlm);

        crc_val = compute_crc16(g_telemetry_buf, 64U);
        (void)crc_val;

        write_mission_log("rw_torque_0", rw_cmd.torque_nm[0]);

        g_adcs_cycle_count++;
        uptime++;
    }

    printf("ADCS nominal run complete. Cycles: %d\n", g_adcs_cycle_count);
    printf("Orbital harmonic(10) = %u\n", orbital_harmonic(10U));

    adcs_free_frame_buffer(extra_buf);

    return 0;
}
