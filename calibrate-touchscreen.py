#!/usr/bin/env python3
"""3-point affine calibration for the Panasonic CF-31/CF-19 Fujitsu touch panel.

This panel reports ABS_X/ABS_Y but signals contact with BTN_LEFT rather than
BTN_TOUCH, and never sets INPUT_PROP_DIRECT. udev therefore tags it
ID_INPUT_MOUSE and never ID_INPUT_TOUCHSCREEN, so xinput_calibrator and GNOME's
touchscreen settings cannot see it at all. Under Wayland, xinput cannot set
properties either.

libinput reads LIBINPUT_CALIBRATION_MATRIX from udev and applies it to the
device's absolute axes regardless of that misclassification, which makes it the
one calibration route that works here. This script measures the matrix and
installs it.
"""
import fcntl, struct, os, sys, re

DEV_NAME = "Fujitsu Component USB Touch Panel"
RULE = "/etc/udev/rules.d/99-cf31-touchscreen-calibration.rules"
USB_ID = ("0430", "0502")
EV_KEY, EV_ABS, BTN_LEFT, ABS_X, ABS_Y = 1, 3, 0x110, 0, 1
FMT, SZ = 'llHHi', 24


def find_device():
    """Return (devnode, sysfs_path) for the touch panel."""
    blob = open('/proc/bus/input/devices').read()
    for chunk in blob.split('\n\n'):
        if DEV_NAME not in chunk:
            continue
        ev = re.search(r'(event\d+)', chunk)
        sysfs = re.search(r'S: Sysfs=(\S+)', chunk)
        if ev:
            return '/dev/input/' + ev.group(1), (sysfs.group(1) if sysfs else '')
    sys.exit("Could not find '%s' in /proc/bus/input/devices.\n"
             "If the panel is absent, see the README - on some units it fails\n"
             "to enumerate at boot entirely." % DEV_NAME)


def usb_port(sysfs):
    """Derive the USB port id (e.g. '1-8') from the device's sysfs path."""
    m = re.search(r'/usb\d+/(\d+-[\d.]+)/', sysfs)
    return m.group(1) if m else None


def absinfo(fd, axis):
    ioc = (2 << 30) | (SZ << 16) | (0x45 << 8) | (0x40 + axis)
    return struct.unpack('6i', fcntl.ioctl(fd, ioc, b'\x00' * SZ))


def grab(fd, on):
    ioc = (1 << 30) | (4 << 16) | (0x45 << 8) | 0x90
    try:
        fcntl.ioctl(fd, ioc, struct.pack('i', 1 if on else 0))
    except OSError:
        print("  (warning: could not grab device; the cursor will jump as you touch)")


def median(vals):
    return sorted(vals)[len(vals) // 2]


def capture(fd, label):
    """Block until one complete touch (press..release); return median raw (x, y)."""
    print("\n  >>> Touch and HOLD the %s corner, then lift your finger." % label)
    xs, ys, cur, touching = [], [], {}, False
    while True:
        _, _, typ, code, val = struct.unpack(FMT, os.read(fd, SZ))
        if typ == EV_ABS and code in (ABS_X, ABS_Y):
            cur[code] = val
        elif typ == EV_KEY and code == BTN_LEFT:
            if val == 1:
                touching, xs, ys = True, [], []
            elif val == 0 and touching:
                if len(xs) >= 3:
                    x, y = median(xs), median(ys)
                    print("      captured raw x=%d y=%d  (%d samples)" % (x, y, len(xs)))
                    return x, y
                print("      too few samples - hold a little longer, try again.")
                touching = False
        if touching and ABS_X in cur and ABS_Y in cur:
            xs.append(cur[ABS_X]); ys.append(cur[ABS_Y])


def solve3(A, b):
    """Solve a 3x3 linear system by Gauss-Jordan with partial pivoting."""
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(3):
        p = max(range(c, 3), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            sys.exit("Degenerate calibration - the three touches were too close together.")
        M[c], M[p] = M[p], M[c]
        for r in range(3):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, 4):
                    M[r][k] -= f * M[c][k]
    return [M[i][3] / M[i][i] for i in range(3)]


def main():
    if os.geteuid() != 0:
        sys.exit("Run with sudo.")
    dev, sysfs = find_device()
    port = usb_port(sysfs)
    fd = os.open(dev, os.O_RDONLY)
    _, xmin, xmax, _, _, _ = absinfo(fd, ABS_X)
    _, ymin, ymax, _, _, _ = absinfo(fd, ABS_Y)
    print("Device   : %s  (%s)" % (dev, DEV_NAME))
    print("Ranges   : X %d..%d   Y %d..%d" % (xmin, xmax, ymin, ymax))
    print("USB port : %s" % (port or "unknown (will need a reboot to apply)"))
    print("\nTouch each corner as close to the very edge of the glass as you can.")
    print("Accuracy here sets accuracy everywhere. Ctrl-C to abort.")

    grab(fd, True)
    try:
        pts = [capture(fd, l) for l in ("TOP-LEFT", "TOP-RIGHT", "BOTTOM-LEFT")]
    finally:
        grab(fd, False)

    norm = [((x - xmin) / float(xmax - xmin), (y - ymin) / float(ymax - ymin))
            for x, y in pts]
    A = [[u, v, 1.0] for u, v in norm]
    m = solve3(A, [0.0, 1.0, 0.0]) + solve3(A, [0.0, 0.0, 1.0])

    print("\n" + "=" * 62)
    print("Calibration matrix:\n  %s" % " ".join("%.6f" % v for v in m))
    if (abs(norm[1][0] - norm[0][0]) + abs(norm[1][1] - norm[0][1]) < 0.15 or
            abs(norm[2][0] - norm[0][0]) + abs(norm[2][1] - norm[0][1]) < 0.15):
        print("  WARNING: corners were very close together; result may be poor.")
    if abs(m[1]) > abs(m[0]) and abs(m[3]) > abs(m[4]):
        print("  Note: X and Y are SWAPPED on this panel (the matrix corrects it).")
    print("=" * 62)

    line = ('SUBSYSTEM=="input", ATTRS{idVendor}=="%s", ATTRS{idProduct}=="%s", '
            'ENV{LIBINPUT_CALIBRATION_MATRIX}="%s"\n'
            % (USB_ID[0], USB_ID[1], " ".join("%.6f" % v for v in m)))
    try:
        answer = input("\nWrite this to %s ? [y/N] " % RULE)
    except EOFError:
        answer = ''
    if answer.strip().lower() != 'y':
        print("Not written. The rule would have been:\n  " + line)
        return

    with open(RULE, 'w') as f:
        f.write("# Panasonic CF-31/CF-19 Fujitsu touch panel (USB %s:%s).\n" % USB_ID)
        f.write("# The panel reports ABS_X/ABS_Y with no BTN_TOUCH and no\n")
        f.write("# INPUT_PROP_DIRECT, so udev tags it ID_INPUT_MOUSE and ordinary\n")
        f.write("# calibration tools cannot see it. libinput applies this matrix\n")
        f.write("# regardless of that misclassification.\n")
        f.write("# Regenerate with calibrate-touchscreen.py; delete to reset.\n")
        f.write(line)
    print("Wrote %s" % RULE)
    os.system("udevadm control --reload-rules")

    if port:
        print("Re-binding USB port %s so the matrix takes effect..." % port)
        for act in ("unbind", "bind"):
            os.system("echo -n %s > /sys/bus/usb/drivers/usb/%s 2>/dev/null" % (port, act))
        print("Done. Test it; re-run to refine if the cursor is still off.")
    else:
        print("Could not determine the USB port - reboot to apply.")
    print("If touch stops responding entirely, delete %s and reboot." % RULE)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted - nothing was changed.")
