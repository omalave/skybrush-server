"""Default configuration for the Flockwave server.

This script will be evaluated first when the server attempts to load its
configuration. The variables declared in this script will then be placed in
a Python namespace, and any additional configuration files will be evaluated
in the context of this namespace so other configuration files get a chance
to override all the things declared here.
"""

import platform

ON_MAC = platform.system().lower() == "darwin"

# Secret key to encode cookies and session data
SECRET_KEY = b'\xa6\xd6\xd3a\xfd\xd9\x08R\xd2U\x05\x10'\
    b'\xbf\x8c2\t\t\x94\xb5R\x06z\xe5\xef'

# Configure the command execution manager
COMMAND_EXECUTION_MANAGER = {
    "timeout": 30
}

# Declare the list of extensions to load
EXTENSIONS = {
    "api.v1": {},
    "debug": {
        "route": "/debug"
    },
    "_fake_uavs": {
        "count": 3,
        "delay": 1.9,
        "id_format": "COLLMOT-{0:02}",
        "center": {
            # ELTE kert
            "lat": 47.473360,
            "lon": 19.062159,
            "agl": 20
        },
        "radius": 50,
        "time_of_single_cycle": 10
    },
    "flockctrl": {
        "id_format": "{0:02}",
        "connections": {
            "xbee": "serial:/tmp/xbee",
            # "xbee": "serial:/dev/ttyUSB.xbee?baud=115200"
            "wireless": {
                "broadcast": "udp-broadcast:192.168.1.0/24?port=4243",
                "unicast": "udp-subnet:192.168.1.0/24"
            }
        }
    },
    "gps": {
        # "connection": "/dev/cu.usbmodem1411",
        "connection": "gpsd",
        "id_format": "BEACON:{0}"
    },
    "radiation": {
        "sources": [
            {
                "lat": 47.473313,
                "lon": 19.062818,
                "intensity": 50000
            }
        ],
        "background_intensity": 10
    },
    "socketio": {},
    "smpte_timecode": {
        "connection": "midi:IAC Driver Bus 1"
    },
    "ssdp": {},
    "system_clock": {},
    "tcp": {},
    "udp": {}
}

# smpte_timecode seems to have some problems on a Mac - it consumes 15% CPU
# even when idle. Also, it is not needed on Heroku.
if ON_MAC:
    del EXTENSIONS["smpte_timecode"]
