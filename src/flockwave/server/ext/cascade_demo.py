"""Experimental extension to demonstrate the connection between an ERP system
and a Skybrush server, in collaboration with Cascade Ltd
"""

from base64 import b64encode
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from inspect import isawaitable
from io import BytesIO
from time import time
from trio import open_memory_channel
from typing import Dict, List, Tuple
from zipfile import ZipFile, ZIP_DEFLATED

from flockwave.server.errors import NotSupportedError
from flockwave.gps.vectors import GPSCoordinate
from .base import ExtensionBase
from .dock.model import Dock

# TODO(ntamas): hack hack hack, this is a temporary solution, we are not supposed
# to import the internals of one extension from another one; extensions are
# supposed to be independent and they must interact with each other via their
# published API objects
from flockwave.server.ext.flockctrl.mission import get_template

WAYPOINT_INIT_STR = """# this is a waypoint file generated by flockwave-server

[init]
#angle=
ground_altitude=0
#origin=

[waypoints]
yaw=auto 30 0

"""

WAYPOINT_GROUND_STR = """motoroff=10"""

WAYPOINT_STR = """
# taking off towards station '{station}'
motoron=5
takeoff=5 4 1 0
waypoint=N{lat:.8f} E{lon:.8f} {agl:.2f} {velocity_xy:.2f} {velocity_z:.2f} 5 0
# landing at station '{station}'
land=4 1 1
motoroff=10
"""


@dataclass
class Station:
    """Model object representing a single station in the demo."""

    id: str
    position: GPSCoordinate

    @classmethod
    def from_json(cls, obj: Tuple[float, float], id: str):
        """Creates a station from its JSON representation."""
        pos = GPSCoordinate(lon=obj[0], lat=obj[1], agl=0)
        return cls(id=id, position=pos)

    def create_dock(self) -> Dock:
        """Creates a docking station object from this specification."""
        dock = Dock(id=self.id)
        dock.update_status(position=self.position)
        return dock


class TripStatus(Enum):
    """Enum class representing the possible statuses of a trip."""

    NEW = "new"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    ERROR = "error"


@dataclass
class Trip:
    """Model object representing a single scheduled trip of a UAV in the demo."""

    uav_id: str
    start_time: float
    route: List[str]
    status: TripStatus = TripStatus.NEW


class ERPSystemConnectionDemoExtension(ExtensionBase):
    """Experimental extension to demonstrate the connection between an ERP system
    and a Skybrush server, in collaboration with Cascade Ltd
    """

    def __init__(self):
        super().__init__()

        self._stations = {}
        self._trips = defaultdict(Trip)
        self._command_queue_rx = self._command_queue_tx = None

    def configure(self, configuration) -> None:
        super().configure(configuration)
        self.configure_stations(configuration.get("stations"))

    def configure_stations(self, stations: Dict[str, Dict]) -> None:
        """Parses the list of stations from the configuration file so they
        can be added as docks later.
        """
        stations = stations or {}
        station_ids = sorted(stations.keys())
        self._stations = dict(
            (station_id, Station.from_json(stations[station_id], id=station_id))
            for station_id in station_ids
        )

        if self._stations:
            self.log.info(
                f"Loaded {len(self._stations)} stations.",
                extra={"semantics": "success"},
            )

    def generate_choreography_file_for_trip(
        self, trip: Trip, velocity_xy: float = 4, velocity_z: float = 1, agl: float = 5
    ) -> str:
        """Generate a choreography file from a given route between stations."""
        return get_template("choreography.cfg").format(
            altitude_setpoint=agl, velocity_xy=velocity_xy, velocity_z=velocity_z
        )

    def generate_mission_for_trip(
        self, trip: Trip, velocity_xy: float = 4, velocity_z: float = 1, agl: float = 5
    ) -> bytes:
        """Generate a complete mission file as an in-memory .zip buffer
        for the given UAV with the given parameters."""
        # generate individual files to be contained in the zip file
        waypoint_ground_str = WAYPOINT_INIT_STR + WAYPOINT_GROUND_STR
        waypoint_str = self.generate_waypoint_file_for_trip(
            trip, velocity_xy=velocity_xy, velocity_z=velocity_z, agl=agl
        )
        choreography_str = self.generate_choreography_file_for_trip(
            trip, velocity_xy=velocity_xy, velocity_z=velocity_z, agl=agl
        )
        mission_str = self.generate_mission_file_for_trip(trip)

        # create the zipfile and write content to it
        buffer = BytesIO()
        zip_archive = ZipFile(buffer, "w", ZIP_DEFLATED)
        zip_archive.writestr("waypoints.cfg", waypoint_str)
        zip_archive.writestr("waypoints_ground.cfg", waypoint_ground_str)
        zip_archive.writestr("choreography.cfg", choreography_str)
        zip_archive.writestr("mission.cfg", mission_str)
        zip_archive.writestr("_meta/version", "1")
        zip_archive.writestr("_meta/name", "cascade_demo")
        zip_archive.close()

        return buffer.getvalue()

    def generate_mission_file_for_trip(self, trip: Trip) -> str:
        """Generate a mission file from a given route between stations."""
        return get_template("mission.cfg")

    def generate_waypoint_file_for_trip(
        self, trip: Trip, velocity_xy: float = 4, velocity_z: float = 1, agl: float = 5
    ) -> str:
        """Generate a waypoint file from a given route between stations."""
        waypoint_str_parts = [WAYPOINT_INIT_STR]
        for name in trip.route:
            pos = self._stations[name].position
            waypoint_str_parts.append(
                WAYPOINT_STR.format(
                    station=name,
                    lat=pos.lat,
                    lon=pos.lon,
                    agl=agl,
                    velocity_xy=velocity_xy,
                    velocity_z=velocity_z,
                )
            )

        return "".join(waypoint_str_parts)

    async def handle_trip_addition(self, message, sender, hub) -> None:
        """Handles the addition of a new trip to the list of scheduled trips."""
        uav_id = message.body.get("uavId")
        if not isinstance(uav_id, str):
            return hub.reject(message, "Missing UAV ID or it is not a string")

        start_time_ms = message.body.get("startTime")
        try:
            start_time_ms = int(start_time_ms)
        except Exception:
            pass
        if not isinstance(start_time_ms, int):
            return hub.reject(message, "Missing start time or it is not an integer")

        start_time_sec = start_time_ms / 1000
        if start_time_sec < time():
            return hub.reject(message, "Start time is in the past")

        route = message.body.get("route")
        if not isinstance(route, list) or not route:
            return hub.reject(message, "Route is not specified or is empty")

        if any(not isinstance(station, str) for station in route):
            return hub.reject(message, "Station names in route must be strings")

        self._trips[uav_id] = Trip(
            uav_id=uav_id, start_time=start_time_sec, route=route
        )

        await self._command_queue_tx.send(uav_id)

        self.log.info(
            f"Trip successfully received.", extra={"semantics": "success", "id": uav_id}
        )

        return hub.acknowledge(message)

    def handle_trip_cancellation(self, message, sender, hub) -> None:
        """Cancels the current trip on a given drone."""
        uav_id = message.body.get("uavId")
        if not isinstance(uav_id, str):
            return hub.reject(message, "Missing UAV ID or it is not a string")

        trip = self._trips.pop(uav_id, None)
        if trip is None:
            return hub.reject(message, "UAV has no scheduled trip")

        self.log.info(f"Trip cancelled.", extra={"semantics": "failure", "id": uav_id})

        return hub.acknowledge(message)

    async def manage_trips(self, queue) -> None:
        """Background task that waits for UAV IDs in a queue and then uploads
        the trip corresponding to the given UAV to the UAV itself.
        """
        async with queue:
            async for uav_id in queue:
                await self.upload_trip_to_uav(uav_id)

    async def run(self) -> None:
        handlers = {
            "X-TRIP-ADD": self.handle_trip_addition,
            "X-TRIP-CANCEL": self.handle_trip_cancellation,
        }

        docks = [station.create_dock() for station in self._stations.values()]

        with self.app.message_hub.use_message_handlers(handlers):
            with self.app.object_registry.use(*docks):
                self._command_queue_tx, self._command_queue_rx = open_memory_channel(32)
                async with self._command_queue_tx:
                    await self.manage_trips(self._command_queue_rx)

    async def upload_trip_to_uav(self, uav_id: str) -> None:
        """Uploads the current trip belonging to the given UAV if needed."""
        extra = {"id": uav_id}
        trip = self._trips.get(uav_id)
        if trip is None:
            self.log.warn(
                f"upload_trip_to_uav() called with no scheduled trip", extra=extra
            )
            return

        if trip.status != TripStatus.NEW:
            self.log.warn(
                f"Trip status is {trip.status!r}, this might be a bug?", extra=extra
            )
            return

        uav = self.app.find_uav_by_id(uav_id)
        if not uav:
            self.log.warn(
                f"Cannot upload trip to UAV, no such UAV in registry", extra=extra
            )
            return

        self.log.info(f"Uplading trip...", extra=extra)
        trip.status = TripStatus.UPLOADING
        try:
            mission_data = self.generate_mission_for_trip(trip)

            # HACK HACK HACK; find a better way to do this than a hidden
            # __mission_upload command
            response = uav.driver.send_command(
                [uav], "__mission_upload", (b64encode(mission_data).decode("ascii"),)
            )
            if uav not in response:
                self.log.error(
                    f"Cannot upload trip, UAV driver did not respond to mission upload request.",
                    extra=extra,
                )
            else:
                result = response[uav]
                if isawaitable(result):
                    await result

            # print(response[uav])

        except NotSupportedError:
            self.log.error(
                f"Cannot upload trip, UAV does not support mission uploads.",
                extra=extra,
            )
            trip.status = TripStatus.ERROR

        except Exception:
            self.log.exception(
                f"Unexpected error while uploading trip to UAV.", extra=extra
            )
            trip.status = TripStatus.ERROR
        else:
            extra["semantics"] = "success"
            self.log.info(f"Trip uploaded successfully.", extra=extra)
            trip.status = TripStatus.UPLOADED


construct = ERPSystemConnectionDemoExtension
dependencies = ("dock",)
