# Hardware guide

This script controls a fan via PWM on GPIO 18. You have two options for the hardware side.

## Option A: Transistor circuit (what this project uses)

Use this if you already have a basic 2-wire 5V fan (power + ground only, no signal wire).

### Parts list

| Part | Purpose | Cost |
|------|---------|------|
| 2N2222 NPN transistor | Switches fan power on/off rapidly (PWM) | ~$0.50 |
| 1kΩ resistor | Limits current from GPIO to transistor base | ~$0.10 |
| 1N4007 diode | Absorbs voltage spike when fan turns off (flyback protection) | ~$0.10 |
| Female-to-male dupont wires | Connect GPIO header to breadboard | ~$3 for 40-pack |
| Any 5V 2-wire fan | The fan being controlled | varies |

Any NPN transistor works (2N2222, 2N3904, BC547). For higher-current fans, use an IRLZ44N N-channel MOSFET instead.

### Wiring

### How it works

1. GPIO 18 sends a PWM signal (250 Hz square wave, duty cycle 0-100%)
2. The 1kΩ resistor limits current to the transistor base (~3.3mA)
3. When the base gets current, the transistor allows current to flow from collector to emitter
4. This completes the circuit: 5V → fan → collector → emitter → GND
5. The fan spins proportionally to the duty cycle
6. The flyback diode protects the transistor from voltage spikes when the fan's motor coil deenergizes

### Important notes

- **GPIO pins are 3.3V logic.** Never connect 5V directly to any GPIO pin.
- **The fan runs on the 5V rail**, not GPIO. GPIO only controls the transistor.
- **Flyback diode is not optional.** Without it, inductive kickback from the fan motor can damage the transistor or the Pi.
- **Thermal paste** fills air gaps between heatsink and chip. It has no adhesive properties — heatsinks need mechanical retention (clip, tape, press-fit case).

## Option B: Buy a PWM-capable fan (no circuit needed)

If you don't want to build a transistor circuit, buy a fan with a built-in PWM signal wire. These connect directly to GPIO — no transistor, no resistor, no diode.

### What to look for

- **5V fan** (not 12V — the Pi only has 5V available)
- **3-wire or 4-wire** (the extra wire is the PWM control signal)
- **30mm or 40mm size** (fits Pi 3B cases)

### Recommended fans

| Fan | Voltage | Size | PWM | Notes |
|-----|---------|------|-----|-------|
| Noctua NF-A4x10 5V PWM | 5V | 40mm | 4-wire | Quietest option, ~$15. Direct GPIO control. |
| GeeekPi Pi fan | 5V | 30mm | 3-wire | Cheap (~$6), designed for Pi, noisier |
| Argon MINI fan | 5V | 30mm | PWM | Comes with some Argon cases |

### Wiring (4-wire PWM fan)
No transistor, no resistor, no diode. The fan has its own internal driver.

### Wiring (3-wire fan without PWM)

A 3-wire fan with just power/ground/tachometer (no PWM input) still needs the transistor circuit from Option A. The third wire is RPM feedback, not PWM control.

## GPIO 18 pin location
3V3  (1) (2)  5V     ← Pin 2: 5V power
  GPIO2  (3) (4)  5V     ← Pin 4: 5V power
  GPIO3  (5) (6)  GND    ← Pin 6: Ground
  GPIO4  (7) (8)  GPIO14
    GND  (9) (10) GPIO15
 GPIO17 (11) (12) GPIO18 ← Pin 12: PWM signal
 GPIO27 (13) (14) GND
 GPIO22 (15) (16) GPIO23
    3V3 (17) (18) GPIO24
 GPIO10 (19) (20) GND
  GPIO9 (21) (22) GPIO25
 GPIO11 (23) (24) GPIO8
    GND (25) (26) GPIO7
## After hardware is connected

Run the installer:

```bash
git clone https://github.com/AdditiveCraftsman/ai-on-the-pi.git
cd ai-on-the-pi/pwm-fan
sudo ./install-pwm-fan.sh --curve standard   # or --curve gaming
```
