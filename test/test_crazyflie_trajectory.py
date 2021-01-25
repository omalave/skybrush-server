import gzip
import sys

from binascii import hexlify
from json import load
from pathlib import Path

from flockwave.server.ext.crazyflie.trajectory import (
    encode_trajectory,
    TrajectoryEncoding,
)
from skybrush.trajectory import TrajectorySpecification

fixture_dir = Path(sys.modules[__name__].__file__).parent / "fixtures"


def test_figure8():
    with gzip.open(fixture_dir / "figure8.json.gz") as fp:
        trajectory = load(fp)

    trajectory = TrajectorySpecification(trajectory)
    data = encode_trajectory(trajectory, encoding=TrajectoryEncoding.COMPRESSED)
    assert data == (
        b"@\x1f\x04)\x00\x00\x00\x00\x10\xd0\x07\xe8\x03\x05\xd0\x07(#\xec,\x05\xd0\x07\x10'\x04)\x05\xd0\x07(#\x1c%\x05\xd0\x07"
        b"@\x1f\x04)\x05\xd0\x07X\x1b\xec,\x05\xd0\x07p\x17\x04)\x05\xd0\x07X\x1b\x1c%\x05\xd0\x07"
        b"@\x1f\x04)\x10\xb8\x0b\x00\x00\x00\x00\x00"
    )


def test_show_5cf_demo():
    with gzip.open(fixture_dir / "show_5cf_demo.json.gz") as fp:
        show = load(fp)

    expected = (
        b"\xd8'X\x1b\xf4\x01\x00\x00\x105\x0b\xb2\x07\x10S\x08\xd0\x07\x04\xd9"
        b"\x1a\xe6(\x04O\x08\x04)\x01\xe4\x00<(\x01\x8b\x05P-\x01\xe4\x00\xb4-\x01"
        b'\xd4\x00Z-\x01\xfe\x0cV"\x01\xd4\x00\xfc!\x01\xe4\x00`"\x01\x8b\x05t\''
        b"\x01\xe4\x00\xd8'\x05\x90\x01\xc4'\xfa(\x05\xc8\x00\x9c'\xf0(\x05\x90\x01B'"
        b"\x82(\x05\x90\x01\x10'\xa6'\x05\xc8\x00$'$'\x05\x90\x01\xba'\x02&\x05"
        b"\x90\x01\xf0(0%\x05\xc8\x00\xc2)\xfe$\x05\x90\x01\x84+0%\x05\x90\x01\x14"
        b"-H&\x05\xc8\x00\xa0-\x1a'\x05\x90\x01\x18.\x04)\x05\x90\x01\xa0-\xf8*"
        b"\x05\xc8\x00\n-\xc0+\x05\x90\x01\x84+\xd8,\x05\x90\x01\xc2)\n-\x05\xc8\x00"
        b"\xf0(\xd8,\x05\x90\x01\xba'\xfc+\x05\x90\x01$'\xe4*\x05\xc8\x00\x10'X"
        b"*\x05\x90\x01B'\x86)\x05\x90\x01\x9c'\x18)\x05\x90\x01\xd8'\x04)\x00\x8d"
        b"\x01\x05\x90\x01\x9c'\x18)\x05\x90\x01B'\x86)\x05\x90\x01\x10'b*\x05\xc8"
        b"\x00$'\xe4*\x05\x90\x01\xba'\x06,\x05\x90\x01\xf0(\xd8,\x05\xc8\x00\xc2)"
        b"\n-\x05\x90\x01\x84+\xd8,\x05\xc8\x00V,`,\x05\x90\x01\xa0-\xee*\x05"
        b"\x90\x01\x18.\x04)\x05\xc8\x00\xfa-\x00(\x05\x90\x01\n-H&\x05\x90\x01\x84"
        b"+0%\x05\xc8\x00\x9e*\xfe$\x05\x90\x01\xf0(0%\x05\x90\x01\xba'\x0c&"
        b"\x05\xc8\x00V'\x98&\x05\x90\x01\x10'\xb0'\x05\x90\x01B'\x82(\x05\xc8\x00"
        b"t'\xc8(\x05\x90\x01\xc4'\xfa(\x05\x8d\x01\xd8'\x04)\x04\xc8\x00T)\x05"
        b"\x90\x01\x9c'\xf8*\x05\x90\x01\xfc&\x92,\x05\xc8\x00\x8e&P-\x05\x90\x01v"
        b"%\xa4.\x05\x90\x01\x18$\xb2/\x05\xc8\x00Z#\x160\x05\x90\x01\xc0!\xa20"
        b"\x05\x90\x01\x08 \xd40\x05\xc8\x00,\x1f\xca0\x05\x90\x01~\x1df0\x05\x90\x01"
        b"\xf8\x1b\xb2/\x05\xc8\x00D\x1b0/\x05\x90\x01\x04\x1a\x04.\x05\x90"
        b"\x01\x14\x19\x92,\x05\xc8\x00\xba\x18\xca+\x05\x90\x01L\x18&*\x05"
        b"\x90\x018\x18\x04)\x04\xc8\x00T)\x05\x90\x01t\x18\xf8*\x05\x90"
        b"\x01\x14\x19\x92,\x05\xc8\x00\x82\x19P-\x05\x90\x01\x9a\x1a\xa4.\x05"
        b"\x90\x01\xf8\x1b\xb2/\x05\xc8\x00\xb6\x1c\x160\x05\x90\x01P\x1e\xa20"
        b'\x05\x90\x01\x08 \xd40\x05\xc8\x00\xe4 \xca0\x05\x90\x01\x92"f0\x05\x90\x01'
        b"\x18$\xb2/\x05\xc8\x00\xcc$0/\x05\x90\x01\x0c&\x04.\x05\x90\x01\xfc&\x92"
        b",\x05\xc8\x00V'\xca+\x05\x90\x01\xc4'&*\x05\x90\x01\xd8'\x04)\x01\x80"
        b"\x0f\xe4%\x04\xe8\x00T)\x05\x90\x01\x9e%\xd0*\x05\x90\x01\xfe$$,\x05\xc8"
        b'\x00\x86$\xc4,\x05\x90\x01n#\xc8-\x05\x90\x01\x1a"|.\x05\xc8\x00\\!'
        b"\xb8.\x05\x90\x01\xe0\x1f\xe0.\x05\x90\x01d\x1e\xa4.\x05\xc8\x00\xb0"
        b"\x1d^.\x05\x90\x01f\x1c\xa0-\x05\x90\x01X\x1b\x88,\x05\xc8\x00\xea\x1a\xe8+"
        b"\x05\x90\x01^\x1a\x80*\x05\x90\x01,\x1a\x04)\x05\xc8\x006\x1aF(\x05\x90\x01"
        b"\x9a\x1a\xca&\x05\x90\x01X\x1b\x80%\x05\xc8\x00\xda\x1b\xea$\x05\x90"
        b'\x01\x06\x1d\xfa#\x05\x90\x01d\x1ed#\x05\xc8\x00"\x1f<#\x05\x90\x01\x9e '
        b'2#\x05\x90\x01\x1a"\x8c#\x05\xc8\x00\xce"\xdc#\x05\x90\x01\x04$\xb8$\x05'
        b"\x90\x01\xfe$\xe4%\x05\xc8\x00X%\x84&\x05\x90\x01\xd0%\xf6'\x05\x90\x01\xe4"
        b"%\x04)\x11\x90\x0f\xca&b\x07\x14\xd8\x00T)N\x07\x15\xc8\x00\xac&\x1c*"
        b"0\x07\x15\x90\x01*&\xc0+\xf4\x06\x15\xc8\x00\xc6%\x88,\xe0\x06\x15\xc8\x00D"
        b'%<-\xd6\x06\x05\xc8\x00\xae$\xdc-\x15\x90\x01F#\xea.\xea\x06\x15\xc8\x00~"D/'
        b"\xfe\x06\x15\xc8\x00\xac!\x8a/\x12\x07\x15\xc8\x00\xda \xbc/:\x07"
        b'\x11\x90\x01"\x1f\x94\x07\x15\xc8\x00P\x1e\x94/\xc6\x07\x15\xc8\x00~'
        b"\x1dN/\xf8\x07\x15\xc8\x00\xc0\x1c\xf4.4\x08\x15\x90\x01l\x1b\xf0"
        b"-\xac\x08\x15\xc8\x00\xe0\x1aF-\xe8\x08\x15\xc8\x00h\x1a\x9c,$\t\x15\xc8\x00"
        b"\x0e\x1a\xd4+`\t\x15\x90\x01\xaa\x190*\xc4\t\x15\xc8\x00\x96\x19^)\xf6\t"
        b"\x15\xc8\x00\xaa\x19\x82(\x1e\n\x15\xc8\x00\xdc\x19\xa6'<\n\x15\x90"
        b"\x01\x86\x1a\x16&n\n\x15\xc8\x00\xfe\x1aX%x\n\x15\xc8\x00\x8a\x1b\xae$\x82"
        b"\n\x15\xc8\x004\x1c\x18$x\n\x15\x90\x01\xa6\x1d2#Z\n\x15\xc8\x00x\x1e"
        b'\xe2"F\n\x15\xc8\x00J\x1f\xb0"(\n\x15\xc8\x00& \x9c"\x00\n\x15\x90'
        b'\x01\xd4!\xba"\x9c\t\x15\xc8\x00\xa6"\xf6"j\t\x15\xc8\x00n#P#.\t\x15\xc8\x00'
        b'"$\xbe#\xf2\x08\x15\x90\x01X%\xe0$z\x08\x15\xc8\x00\xda%\x8a%>\x08'
        b"\x15\xc8\x00>&H&\x0c\x08\x15\xc8\x00\x84&\x1a'\xd0\x07\x15\x90\x01\xca&\xb4"
        b"(l\x07\x14\xc8\x00\x04)b\x07\x11y\x13\xd8'\xd0\x07\x10D\x0b\x12\x02\x10\x83"
        b"\x00\xf4\x01\x00\x00\x00"
    )

    drone = show["swarm"]["drones"][0]
    trajectory = TrajectorySpecification(drone["settings"]["trajectory"])
    data = encode_trajectory(trajectory, encoding=TrajectoryEncoding.COMPRESSED)
    assert data == expected
