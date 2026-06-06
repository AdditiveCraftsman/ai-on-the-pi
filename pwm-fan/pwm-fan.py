#!/usr/bin/env python3

import pigpio
import time
import signal
import sys
import logging

# ── Configuration ──────────────────────────────────────────
GPIO_PIN    = 18      # Hardware PWM pin (GPIO 18 = header pin 12)
PWM_FREQ    = 250     # Hz — standard for PC fans
POLL_SEC    = 5       # Seconds between temperature checks
HYSTERESIS  = 2.0     # °C dead band — prevents oscillation near thresholds

# Temperature curve: (temp_°C, fan_duty_%)
# Fan stays at 0% below 45°C, ramps linearly to 100% at 70°C
TEMP_CURVE = [
    (45.0,   0),
    (50.0,  25),
    (55.0,  50),
    (60.0,  70),
    (65.0,  85),
    (70.0, 100),
]

# ── Logging ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [fan] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger()

# ── Helpers ────────────────────────────────────────────────
def read_temp():
    with open('/sys/class/thermal/thermal_zone0/temp') as f:
        return int(f.read().strip()) / 1000.0

def temp_to_duty(temp, last_duty):
    """Map temperature to duty cycle with hysteresis."""
    if temp <= TEMP_CURVE[0][0]:
        return 0
    if temp >= TEMP_CURVE[-1][0]:
        return 100
    for i in range(len(TEMP_CURVE) - 1):
        t_lo, d_lo = TEMP_CURVE[i]
        t_hi, d_hi = TEMP_CURVE[i + 1]
        if t_lo <= temp <= t_hi:
            ratio = (temp - t_lo) / (t_hi - t_lo)
            target = d_lo + ratio * (d_hi - d_lo)
            break
    if abs(target - last_duty) < HYSTERESIS:
        return last_duty
    return round(target)

def set_fan(pi, duty):
    """Set fan speed. duty is 0–100."""
    pi.hardware_PWM(GPIO_PIN, PWM_FREQ, duty * 10000)

# ── Shutdown handler ───────────────────────────────────────
pi_global = None

def shutdown(signum, frame):
    log.info('Shutting down — setting fan to 100% for safety')
    if pi_global:
        set_fan(pi_global, 100)
        pi_global.stop()
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT,  shutdown)

# ── Main ───────────────────────────────────────────────────
def main():
    global pi_global
    pi = pigpio.pi()
    if not pi.connected:
        log.error('Cannot connect to pigpiod — is the daemon running?')
        sys.exit(1)
    pi_global = pi

    log.info('Fan controller started — GPIO %d, %d Hz', GPIO_PIN, PWM_FREQ)

    # Startup safety: run at 100% for 5 seconds
    log.info('Startup safety: fan at 100% for 5 seconds')
    set_fan(pi, 100)
    time.sleep(5)

    last_duty = 100

    while True:
        temp = read_temp()
        duty = temp_to_duty(temp, last_duty)
        if duty != last_duty:
            log.info('Temp %.1f°C → fan %d%%', temp, duty)
            set_fan(pi, duty)
            last_duty = duty
        time.sleep(POLL_SEC)

if __name__ == '__main__':
    main()
