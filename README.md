# cf31-touchscreen-calibrate

Touchscreen calibration for the Panasonic Toughbook CF-31/CF-19 Fujitsu touch panel
on Wayland, where `xinput_calibrator` and GNOME's touchscreen settings cannot see the
device at all.

Tested working on a CF-19 Mk4, Ubuntu 24.04, GNOME/Wayland.

> **LLM-generated.** Written by Claude (Anthropic), from live diagnosis of a real CF-31,
> and confirmed working on that hardware. It runs as root and writes a udev rule — read
> it before you run it.


## Usage

```
sudo python3 calibrate-touchscreen.py
```

It grabs the device (so calibration touches don't click things underneath), asks you to
touch **top-left, top-right and bottom-left**, and solves the affine transform — handling
offset, scale, inversion, axis swap and mild rotation. It then writes
`/etc/udev/rules.d/99-cf19-mk4-touchscreen-calibration.rules` and re-binds the panel's USB
port so the matrix applies without a reboot.

Touch as close to the edge of the glass as you can; those three points set the accuracy
everywhere else. Re-run to refine. Python 3 standard library only.

Check the panel is actually present first:

```
grep -c Fujitsu /proc/bus/input/devices    # 1 = present, 0 = see below
```

To revert:

```
sudo rm /etc/udev/rules.d/99-cf19-mk4-touchscreen-calibration.rules && sudo reboot
```

## Licence

Public domain / CC0.
