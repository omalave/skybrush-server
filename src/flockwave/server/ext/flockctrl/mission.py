"""String templates to be used for parametrized mission file generation for
the flockctrl system.
"""

from base64 import b64decode
from functools import partial
from importlib.resources import read_text
from io import BytesIO
from math import ceil, hypot
from typing import Iterable, Tuple
from zipfile import ZipFile, ZIP_DEFLATED

from flockwave.gps.vectors import FlatEarthToGPSCoordinateTransformation

__all__ = ("get_template", "gps_coordinate_to_string")


_template_pkg = __name__.rpartition(".")[0] + ".templates"


#: Type specification for a 3D XYZ-style coordinate
XYZ = Tuple[float, float, float]

#: Type specification for a trajectory consisting of a sequence of
#: timestamps, the corresponding waypoints and the corresponding auxiliary
#: Bexier control points
Trajectory = Tuple[float, XYZ, Iterable[XYZ]]


def get_template(name: str, *, encoding: str = "utf-8", errors: str = "strict") -> str:
    """Returns the contents of a template file from the `templates/` subdirectory,
    used for mission generation.

    Parameters:
        name: name of the template file
        encoding: the encoding of the file
        errors: specifies how to handle encoding errors in the input file;
            forwarded directly to `importlib.resources.read_text()`.

    Returns:
        the loaded template file
    """
    dirs, _, name = name.rpartition("/")
    package = ".".join([_template_pkg] + (dirs.split("/") if dirs else []))
    return read_text(package, name, encoding=encoding, errors=errors)


def get_all_points_from_trajectory(trajectory: Trajectory) -> Iterable[XYZ]:
    """Given a trajectory, returns an iterable that will iterate over all the
    points of the trajectory.

    For each item in the trajectory, the Bezier control points are iterated
    first, followed by the waypoint itself.
    """
    for _, point, control_points in trajectory:
        yield from control_points
        yield point


def get_maximum_altitude_with_safety_margin(
    trajectory: Trajectory, margin: float = 20, steps: int = 10
) -> float:
    """Proposes a safety limit to use for the altitude component of the geofence
    in the uploaded mission file.

    Parameters:
        trajectory: the trajectory that the UAV will fly
        margin: margin to add to the AGL of the point with the largest AGL
        steps: integer number to round the result to

    Returns:
        the smallest multiple of `steps` that is larger than or equal to the
        AGL of the highest point in the trajectory plus the margin
    """
    try:
        largest_z = max(
            point[2] for point in get_all_points_from_trajectory(trajectory)
        )
    except ValueError:
        largest_z = 0
    return int(ceil((largest_z + margin) / steps)) * steps


def get_maximum_distance_with_safety_margin(
    trajectory: Trajectory, margin: float = 20, steps: int = 10
) -> float:
    """Proposes a safety limit to use for the distance component of the
    circular geofence in the uploaded mission file.

    Parameters:
        trajectory: the trajectory that the UAV will fly
        margin: margin to add to the distance of the farthest point (in the
            horizontal plane)
        steps: integer number to round the result to

    Returns:
        the smallest multiple of `steps` that is larger than or equal to the
        distance of the farthest point in the trajectory plus the margin
    """
    xys = [(point[0], point[1]) for point in get_all_points_from_trajectory(trajectory)]

    if not xys:
        max_distance = 0
    else:
        origin_x, origin_y = xys[0]
        max_distance = max(hypot(origin_x - x, origin_y - y) for x, y in xys)

    return int(ceil((max_distance + margin) / steps)) * steps


def generate_mission_file_from_show_specification(show) -> bytes:
    """Generates a full uploadable mission ZIP file from a drone light show
    specification in Skybrush format.

    Returns:
        the uploadable mission ZIP file as a raw bytes object
    """
    # TODO: move this to a proper place, I do not know where...
    # TODO: generalize all conversions in flockwave.gps.vectors
    def to_neu(pos, type_string):
        """Convert a flat earth coordinate to 'neu' type."""
        if type_string == "neu":
            pos_neu = (pos[0], pos[1], pos[2])
        elif type_string == "nwu":
            pos_neu = (pos[0], -pos[1], pos[2])
        elif type_string == "ned":
            pos_neu = (pos[0], pos[1], -pos[2])
        elif type_string == "nwd":
            pos_neu = (pos[0], -pos[1], -pos[2])
        else:
            raise NotImplementedError("GPS coordinate system type unknown.")

        return pos_neu

    # parse coordinate system
    coordinate_system = show.get("coordinateSystem")
    try:
        trans = FlatEarthToGPSCoordinateTransformation.from_json(coordinate_system)
    except Exception:
        raise RuntimeError("Invalid or missing coordinate system specification")

    # pin down to_neu to the transformation type
    to_neu = partial(to_neu, type_string=trans.type)

    # parse home coordinate
    if "home" in show:
        home = to_neu(show["home"])
    else:
        raise RuntimeError("No home coordinate in show specification")

    # parse trajectory
    if "trajectory" in show:
        trajectory = show["trajectory"]
        takeoff_time = trajectory["takeoffTime"]
        points = trajectory["points"]
    else:
        raise RuntimeError("No trajectory in show specification")

    # convert all points in trajectory to NEU coordinates
    points = [
        (t, to_neu(point), map(to_neu, control_points))
        for t, point, control_points in points
    ]

    # create waypoints
    last_t = 0
    waypoints = []
    for t, point, _ in points:
        # add takeoff time to waypoints
        t += takeoff_time
        waypoints.append(
            "waypoint={x} {y} {z} {vxy} {vz} T{t} 6".format(
                x=point[0],
                y=point[1],
                z=point[2],
                vxy=8,  # TODO: get from show
                vz=2.9,  # TODO: get from show
                t=t - last_t,
            )
        )
        last_t = t

    # derive the properties of the geofence
    max_altitude = get_maximum_altitude_with_safety_margin(points)
    max_distance = get_maximum_distance_with_safety_margin(points)

    # create waypoint file template
    waypoint_str = get_template("waypoints.cfg").format(
        angle=trans.orientation,
        ground_altitude=0,  # TODO: use this if needed
        origin=gps_coordinate_to_string(lat=trans.origin.lat, lon=trans.origin.lon),
        waypoints="\n".join(waypoints),
    )

    # create empty waypoint file template
    waypoint_ground_str = get_template("waypoints.cfg").format(
        angle=trans.orientation,
        ground_altitude=0,  # TODO: use this if needed
        origin=gps_coordinate_to_string(lat=trans.origin.lat, lon=trans.origin.lon),
        waypoints="waypoint={} {} -100 4 2 T1000 6".format(home[0], home[1]),
    )

    # gather parameters that are used in the mission and choreography file
    # templates
    params = {
        "altitude_setpoint": 5,  # TODO: get from show if needed
        "max_flying_height": max_altitude,
        "max_flying_range": max_distance,
        "orientation": -1,  # TODO: get from show
        "velocity_xy": 5,  # TODO: get from show
        "velocity_z": 2,  # TODO: get from show
        "max_velocity_xy": 8,  # TODO: get from show
        "max_velocity_z": 2.9,  # TODO: get from show
    }

    # create mission files
    mission_str = get_template("show/mission.cfg").format(**params)

    # create choreography file
    choreography_str = get_template("show/choreography.cfg").format(**params)

    # parse lights
    lights = show.get("lights", None)
    light_data = b64decode(lights["data"])

    # create mission.zip
    # create the zipfile and write content to it
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zip_archive:
        zip_archive.writestr("waypoints.cfg", waypoint_str)
        zip_archive.writestr("waypoints_ground.cfg", waypoint_ground_str)
        zip_archive.writestr("choreography.cfg", choreography_str)
        zip_archive.writestr("mission.cfg", mission_str)
        zip_archive.writestr("light_show.bin", light_data)
        zip_archive.writestr("_meta/version", "1")
        zip_archive.writestr("_meta/name", show.get("name", "drone-show"))
        zip_archive.close()

    return buffer.getvalue()


def gps_coordinate_to_string(lat: float, lon: float, amsl: float = None) -> str:
    """Return a string to be used in waypoint files when absolute coordinates
    are needed.

    Parameters:
        lat: latitude in degrees
        lon: longitude in degrees
        amsl: above mean sea level in meters (optional)

    Return:
        gps coordinate string in flockctrl format
    """
    lat_sign = "N" if lat >= 0 else "S"
    lon_sign = "E" if lon >= 0 else "W"
    retval = f"{lat_sign}{lat:.7f} {lon_sign}{lon:.7f}"

    if amsl is not None:
        amsl_sign = "U" if amsl >= 0 else "D"
        retval += f" {amsl_sign}{amsl:.3f}"

    return retval
