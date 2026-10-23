# cf31-touchscreen-calibrate

Touchscreen calibration primarily for the Panasonic Toughbook CF-31/CF-19 Fujitsu touch panel
on Wayland, where `xinput_calibrator` and GNOME's touchscreen settings cannot see the
device at all.

Tested working on a CF-31 Mk5/CF-19 Mk4/CF-19 Mk5/CF-19 Mk7, Ubuntu 24.04, GNOME/Wayland.

> **LLM-generated.** Written by Claude (Anthropic), from live diagnosis of a real PC,
> and confirmed working on that hardware. It runs as root and writes a udev rule — read
> it before you run it.

## Why the usual tools fail

Two independent reasons.

**1. for some devices udev classifies it as a mouse.** The panel reports `ABS_X`/`ABS_Y`, but signals
contact with `BTN_LEFT` instead of `BTN_TOUCH` and never sets `INPUT_PROP_DIRECT`:

```
B: PROP=0
B: KEY=70000 0 0 0 0     <- BTN_LEFT/RIGHT/MIDDLE, no BTN_TOUCH
B: ABS=3                 <- ABS_X, ABS_Y
```

udev needs one of those two markers to tag a device as a touchscreen. With neither, it
tags it `ID_INPUT_MOUSE` and never `ID_INPUT_TOUCHSCREEN`. Calibration tools filter for
touchscreen-tagged devices, so to them this panel does not exist.

**2. Wayland.** `xinput --set-prop "Coordinate Transformation Matrix"` cannot set
properties on anything, so the classic X11 recipes fail regardless of the above.

## The fix

libinput reads a `LIBINPUT_CALIBRATION_MATRIX` udev property and applies it to the
device's absolute axes — independent of the compositor, and independent of how udev
classified it. Confirm your panel will accept one:

```
$ sudo libinput list-devices
Calibration:      identity matrix     # not "n/a", so a matrix will be applied
```

## Usage

```
sudo python3 calibrate-touchscreen.py
```

The script first asks for the Toughbook model. For another device, select Unknown and enter its input device name, USB vendor/product ID and whether contact is reported using BTN_TOUCH or BTN_LEFT.

Then it grabs the device (so calibration touches don't click things underneath), asks you to
touch **top-left, top-right and bottom-left**, and solves the affine transform — handling
offset, scale, inversion, axis swap and mild rotation. It then writes
`/etc/udev/rules.d/99-touchscreen-calibration.rules` and re-binds the panel's USB
port so the matrix applies without a reboot.

Touch as close to the edge of the glass as you can; those three points set the accuracy
everywhere else. Re-run to refine. Python 3 standard library only.

Check the panel is actually present first:

```
grep -c Fujitsu /proc/bus/input/devices    # 1 = present, 0 = see below
```

To revert:

```
sudo rm /etc/udev/rules.d/99-touchscreen-calibration.rules && sudo reboot
```

## Don't force `ID_INPUT_TOUCHSCREEN=1` on non-`BTN_TOUCH` devices

The tempting fix is a udev rule re-tagging the panel as a touchscreen so the normal tools
can see it. Don't. libinput's touch path expects `BTN_TOUCH` or multitouch (`ABS_MT_*`)
slots, and the panel may have neither — re-tagging tends to kill touch input rather than fix
it. Calibrating it as the absolute pointer it already is avoids that risk.

## If the panel never enumerates

On the CF-31 Mk5 development unit it appeared on only one of five consecutive boots. On the failing
boots its USB port logged nothing at all — a clean absence, not a marginal connection,
which would instead show `error -71` and enumeration retries. It was not USB power
management (autosuspend was already off), and `panasonic_laptop` exposes no toggle. That
points at a BIOS touchscreen setting or an intermittently-seated hinge cable.

```
for b in 0 -1 -2 -3 -4; do
  printf 'boot %3s : %s\n' "$b" \
    "$(sudo journalctl -k -b $b 2>/dev/null | grep -acE 'Touch Panel')"
done
```

## Licence

Public domain / CC0.
