# cf31-touchscreen-calibrate

Touchscreen calibration for the Panasonic Toughbook CF-31 (and CF-19) resistive
touch panel on modern Linux — where `xinput_calibrator` and every other
traditional calibration tool silently fails to find the device.

Tested on a CF-31 Mk5 running Ubuntu 24.04 with GNOME on Wayland.

## The problem

The panel is a `Fujitsu Component USB Touch Panel` (USB ID `0430:0502`,
sold as the "Panasonic CF-19 HID Touch Panel"). It works — it reports absolute
coordinates and moves the cursor — but **no calibration tool can see it**, for two
independent reasons.

### 1. udev classifies it as a mouse, not a touchscreen

The panel reports `ABS_X`/`ABS_Y`, but it signals contact with
`BTN_LEFT`/`BTN_RIGHT`/`BTN_MIDDLE` instead of `BTN_TOUCH`, and it never sets the
`INPUT_PROP_DIRECT` property:

```
B: PROP=0
B: KEY=70000 0 0 0 0     <- BTN_LEFT / BTN_RIGHT / BTN_MIDDLE, no BTN_TOUCH
B: ABS=3                 <- ABS_X, ABS_Y
```

udev's input classifier needs `BTN_TOUCH` or `INPUT_PROP_DIRECT` to tag a device as
a touchscreen. With neither present it tags the panel as a *mouse*:

```
$ udevadm info /dev/input/eventN | grep ID_INPUT
E: ID_INPUT=1
E: ID_INPUT_MOUSE=1      <- and no ID_INPUT_TOUCHSCREEN
```

`xinput_calibrator`, GNOME's touchscreen settings, and similar tools all filter for
touchscreen-tagged devices. To them this panel simply does not exist as a
touchscreen — it presents as an absolute-positioning mouse.

### 2. Wayland

Under Wayland the compositor owns input. `xinput --set-prop "Coordinate
Transformation Matrix"` cannot set properties on anything, so the classic X11
recipes cannot work regardless of point 1.

## The fix

libinput reads a **`LIBINPUT_CALIBRATION_MATRIX`** udev property and applies it to a
device's absolute axes at the libinput layer — independent of the compositor, and
independent of whether udev tagged the device a touchscreen or a mouse. That makes
it the one calibration route that works here.

You can confirm libinput will accept a matrix for your panel:

```
$ sudo libinput list-devices
...
Calibration:      identity matrix     <- not "n/a", so a matrix will be applied
```

This script measures the correct matrix and installs it.

## Usage

```
sudo python3 calibrate-touchscreen.py
```

It will:

1. Find the panel and read its axis ranges.
2. `EVIOCGRAB` the device, so your calibration touches don't fling the cursor
   around or click things underneath.
3. Ask you to touch three corners — **top-left, top-right, bottom-left**.
4. Solve the affine transform from those three points. This handles offset, scale,
   axis inversion, axis swap and mild rotation.
5. Show you the matrix and offer to write
   `/etc/udev/rules.d/99-cf31-touchscreen-calibration.rules`.
6. Reload udev and re-bind the panel's USB port so the matrix applies immediately,
   without a reboot.

Touch each corner as close to the edge of the glass as you can — the accuracy of
those three touches sets the accuracy everywhere else. Re-run it to refine.

No dependencies beyond Python 3 and the standard library.

### Check the panel is actually present first

```
grep -c Fujitsu /proc/bus/input/devices    # 1 = present, 0 = absent
```

See [Known hardware issue](#known-hardware-issue-panel-missing-at-boot) below —
on some units the panel frequently fails to enumerate at all, and calibrating a
device that isn't there is a frustrating way to spend an evening.

### Reverting

```
sudo rm /etc/udev/rules.d/99-cf31-touchscreen-calibration.rules
sudo reboot
```

## Do not force `ID_INPUT_TOUCHSCREEN=1`

The obvious-looking fix is a udev rule re-tagging the panel as a touchscreen so the
normal tools can see it. **Don't.** libinput's touchscreen path expects either
`BTN_TOUCH` or multitouch (`ABS_MT_*`) slots, and this panel provides neither.
Re-tagging it is likely to break touch input entirely rather than improve it.

Calibrating it as the absolute pointer it already is — which is what this script
does — gets working touch without that risk.

## Known hardware issue: panel missing at boot

On the unit this was developed against, the touch panel enumerated on only **one of
five consecutive boots**. On the failing boots its USB port logged nothing at all:

```
boot   0 : panel_lines=7   ok
boot  -1 : panel_lines=0   <-- PANEL DID NOT ENUMERATE
boot  -2 : panel_lines=0   <-- PANEL DID NOT ENUMERATE
boot  -3 : panel_lines=0   <-- PANEL DID NOT ENUMERATE
boot  -4 : panel_lines=0   <-- PANEL DID NOT ENUMERATE
```

Note this is a *clean absence*, not a marginal connection — a failing cable or
controller produces `error -71`, `device not accepting address`, and enumeration
retries in the kernel log. Here the port reports no device whatsoever.

It is not USB power management (autosuspend was already off for that port), and
there is no software toggle — the `panasonic_laptop` driver exposes hotkeys only.
That points at a BIOS touchscreen setting or an intermittently-seated display cable,
which on these machines runs through the hinge.

If calibration "never works" on your unit, check this before anything else:

```
for b in 0 -1 -2 -3 -4; do
  printf 'boot %3s : %s\n' "$b" \
    "$(sudo journalctl -k -b $b 2>/dev/null | grep -acE 'Touch Panel')"
done
```

## Licence

Public domain / CC0 — do what you like with it.
