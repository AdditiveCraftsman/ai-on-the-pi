# PWM Fan Control

Temperature-controlled PWM fan for Raspberry Pi 3B using pigpio hardware PWM.

## Features
- Smooth temperature curve (not just on/off)
- Hysteresis dead band prevents fan oscillation
- Graceful shutdown: fan goes to 100% if script exits
- Startup safety: fan runs at 100% for 5 seconds on boot
- Logs speed changes to systemd journal

## Hardware
- GPIO 18 (header pin 12) — hardware PWM
- 2N2222 NPN transistor + 1kΩ resistor + 1N4007 flyback diode
- 5V 2-wire fan

## Temperature curve
| Temp | Fan speed |
|------|-----------|
| ≤ 45°C | 0% |
| 50°C | 25% |
| 55°C | 50% |
| 60°C | 70% |
| 65°C | 85% |
| ≥ 70°C | 100% |

## Install

### 1. Build and install pigpiod from source
```bash
sudo apt install git -y
git clone https://github.com/joan2937/pigpio.git
cd pigpio
make CFLAGS="-O3 -Wall -pthread -fpic -Wno-incompatible-pointer-types -std=gnu99"
sudo make install
cd ~
```

### 2. Install Python bindings
```bash
sudo pip3 install pigpio --break-system-packages
```

### 3. Deploy service files and script
```bash
sudo cp pwm-fan.py /usr/local/bin/pwm-fan.py
sudo chmod +x /usr/local/bin/pwm-fan.py
sudo cp pigpiod.service /etc/systemd/system/pigpiod.service
sudo cp pwm-fan.service /etc/systemd/system/pwm-fan.service
```

### 4. Enable and start
```bash
sudo systemctl daemon-reload
sudo systemctl enable pigpiod && sudo systemctl start pigpiod
sudo systemctl enable pwm-fan && sudo systemctl start pwm-fan
```

### 5. Verify
```bash
sudo systemctl status pwm-fan
journalctl -u pwm-fan -f
```

## Tested on
- Raspberry Pi 3B Rev 1.2
- Kali Linux (Debian-based)
- Raspberry Pi OS Bookworm/Trixie
