#!/usr/bin/env bash
set -euo pipefail

# ── PWM Fan Installer for Raspberry Pi 3B ─────────────────
# Repo: github.com/AdditiveCraftsman/ai-on-the-pi
# Usage: sudo ./install-pwm-fan.sh [--curve standard|gaming]

# ── Colors ─────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $1"; exit 1; }

# ── Must be root ───────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    fail "This script must be run as root. Use: sudo $0 $*"
fi

# ── Parse arguments ────────────────────────────────────────
CURVE="standard"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --curve)
            shift
            CURVE="${1:-}"
            if [[ "$CURVE" != "standard" && "$CURVE" != "gaming" ]]; then
                fail "Invalid curve: '$CURVE'. Use --curve standard or --curve gaming"
            fi
            shift
            ;;
        -h|--help)
            echo "Usage: sudo $0 [--curve standard|gaming]"
            echo ""
            echo "Curves:"
            echo "  standard  — Fan off below 45°C, 100% at 70°C (default)"
            echo "  gaming    — Fan on at 40°C, 100% at 65°C (aggressive, for RetroPie)"
            exit 0
            ;;
        *)
            fail "Unknown option: $1. Use --help for usage."
            ;;
    esac
done

info "Selected fan curve: $CURVE"

# ── Detect OS ──────────────────────────────────────────────
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    OS_NAME="${ID:-unknown}"
    OS_VERSION="${VERSION_ID:-unknown}"
    info "Detected OS: $PRETTY_NAME"
else
    OS_NAME="unknown"
    warn "Could not detect OS — proceeding anyway"
fi

# ── Resolve script directory ───────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
info "Install source: $SCRIPT_DIR"

# ── Step 1: Install pigpiod ────────────────────────────────
info "Step 1/6: Installing pigpiod daemon..."

PIGPIOD_INSTALLED=false

# Try apt first (works on Pi OS, fails on Kali)
if apt-cache show pigpio &>/dev/null; then
    info "pigpio found in apt repos — installing via apt..."
    if apt install -y pigpio python3-pigpio &>/dev/null; then
        ok "pigpiod installed via apt"
        PIGPIOD_INSTALLED=true
    else
        warn "apt install failed — falling back to source build"
    fi
fi

# Fall back to source build
if [[ "$PIGPIOD_INSTALLED" == "false" ]]; then
    info "Building pigpiod from source..."

    # Check for build dependencies
    apt install -y git build-essential &>/dev/null || warn "Could not install build tools — they may already exist"

    BUILD_DIR=$(mktemp -d)
    cd "$BUILD_DIR"

    git clone https://github.com/joan2937/pigpio.git &>/dev/null || fail "Failed to clone pigpio repo"
    cd pigpio

    info "Compiling (this takes 1-2 minutes on Pi 3B)..."
    make CFLAGS="-O3 -Wall -pthread -fpic -Wno-incompatible-pointer-types -std=gnu99" &>/dev/null \
        || fail "pigpio build failed"

    make install &>/dev/null || fail "pigpio install failed"
    ok "pigpiod built and installed from source"

    # Install Python bindings via pip
    info "Installing Python pigpio bindings..."
    pip3 install pigpio --break-system-packages &>/dev/null \
        || warn "pip install pigpio failed — may already be installed"

    # Clean up
    cd /
    rm -rf "$BUILD_DIR"

    PIGPIOD_INSTALLED=true
fi

# Verify binary
if ! command -v pigpiod &>/dev/null; then
    fail "pigpiod binary not found after install"
fi
ok "pigpiod binary verified: $(pigpiod -v)"

# ── Step 2: Write fan script with selected curve ───────────
info "Step 2/6: Deploying fan script ($CURVE curve)..."

if [[ "$CURVE" == "gaming" ]]; then
    CURVE_BLOCK='TEMP_CURVE = [
    (40.0,  10),
    (45.0,  30),
    (50.0,  55),
    (55.0,  75),
    (60.0,  90),
    (65.0, 100),
]'
else
    CURVE_BLOCK='TEMP_CURVE = [
    (45.0,   0),
    (50.0,  25),
    (55.0,  50),
    (60.0,  70),
    (65.0,  85),
    (70.0, 100),
]'
fi

cat > /usr/local/bin/pwm-fan.py << FANEOF
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
# Curve profile: $CURVE
$CURVE_BLOCK

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
    """Set fan speed. duty is 0-100."""
    pi.hardware_PWM(GPIO_PIN, PWM_FREQ, duty * 10000)

# ── Shutdown handler ───────────────────────────────────────
pi_global = None

def shutdown(signum, frame):
    log.info('Shutting down -- setting fan to 100% for safety')
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
        log.error('Cannot connect to pigpiod -- is the daemon running?')
        sys.exit(1)
    pi_global = pi

    log.info('Fan controller started -- GPIO %d, %d Hz, curve: $CURVE', GPIO_PIN, PWM_FREQ)

    # Startup safety: run at 100% for 5 seconds
    log.info('Startup safety: fan at 100% for 5 seconds')
    set_fan(pi, 100)
    time.sleep(5)

    last_duty = 100

    while True:
        temp = read_temp()
        duty = temp_to_duty(temp, last_duty)
        if duty != last_duty:
            log.info('Temp %.1f C -> fan %d%%', temp, duty)
            set_fan(pi, duty)
            last_duty = duty
        time.sleep(POLL_SEC)

if __name__ == '__main__':
    main()
FANEOF

chmod +x /usr/local/bin/pwm-fan.py
ok "Fan script deployed with $CURVE curve"

# ── Step 3: Deploy pigpiod service ─────────────────────────
info "Step 3/6: Installing pigpiod systemd service..."

cat > /etc/systemd/system/pigpiod.service << 'SVCEOF'
[Unit]
Description=Pigpio daemon
After=network.target

[Service]
Type=forking
ExecStart=/usr/local/bin/pigpiod
ExecStop=/bin/systemctl kill pigpiod
Restart=on-failure

[Install]
WantedBy=multi-user.target
SVCEOF

ok "pigpiod.service installed"

# ── Step 4: Deploy fan service ─────────────────────────────
info "Step 4/6: Installing pwm-fan systemd service..."

cat > /etc/systemd/system/pwm-fan.service << 'SVCEOF'
[Unit]
Description=PWM fan controller
After=pigpiod.service
Requires=pigpiod.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/pwm-fan.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

ok "pwm-fan.service installed"

# ── Step 5: Enable and start services ──────────────────────
info "Step 5/6: Enabling and starting services..."

# Kill any manually started pigpiod first
killall pigpiod &>/dev/null || true
sleep 1

systemctl daemon-reload

systemctl enable pigpiod &>/dev/null
systemctl start pigpiod
sleep 2

if ! systemctl is-active --quiet pigpiod; then
    fail "pigpiod failed to start — check: journalctl -u pigpiod"
fi
ok "pigpiod is running"

systemctl enable pwm-fan &>/dev/null
systemctl start pwm-fan
sleep 3

if ! systemctl is-active --quiet pwm-fan; then
    fail "pwm-fan failed to start — check: journalctl -u pwm-fan"
fi
ok "pwm-fan is running"

# ── Step 6: Summary ───────────────────────────────────────
info "Step 6/6: Verifying..."

TEMP=$(cat /sys/class/thermal/thermal_zone0/temp)
TEMP_C=$((TEMP / 1000))

echo ""
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  PWM Fan Install Complete${NC}"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "  Curve:       ${CYAN}$CURVE${NC}"
echo -e "  GPIO pin:    ${CYAN}18 (header pin 12)${NC}"
echo -e "  PWM freq:    ${CYAN}250 Hz${NC}"
echo -e "  Current temp: ${CYAN}${TEMP_C}°C${NC}"
echo -e "  pigpiod:     $(systemctl is-active pigpiod)"
echo -e "  pwm-fan:     $(systemctl is-active pwm-fan)"
echo ""
echo -e "  ${YELLOW}Monitor:${NC}  journalctl -u pwm-fan -f"
echo -e "  ${YELLOW}Restart:${NC}  sudo systemctl restart pwm-fan"
echo -e "  ${YELLOW}Edit curve:${NC} sudo nano /usr/local/bin/pwm-fan.py"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
