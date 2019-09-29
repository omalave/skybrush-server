"""Flockwave server extension that adds support for drone flocks using the
``flockctrl`` protocol.
"""

from __future__ import absolute_import

from datetime import datetime
from pytz import utc

from flockwave.server.connections import create_connection, reconnecting
from flockwave.server.ext.base import UAVExtensionBase
from flockwave.server.model import ConnectionPurpose
from flockwave.server.utils import datetime_to_unix_timestamp

from .driver import FlockCtrlDriver
from .packets import FlockCtrlClockSynchronizationPacket
from .wireless import WirelessCommunicationManager

__all__ = ("construct", "dependencies")


class FlockCtrlDronesExtension(UAVExtensionBase):
    """Extension that adds support for drone flocks using the ``flockctrl``
    protocol.
    """

    def __init__(self):
        super(FlockCtrlDronesExtension, self).__init__()
        self._driver = None

        self._wireless_broadcast_link = None
        self._wireless_unicast_link = None
        self._wireless_communicator = WirelessCommunicationManager(self)
        self._wireless_communicator.on_packet.connect(
            self._handle_inbound_packet, sender=self._wireless_communicator
        )

    def _create_driver(self):
        return FlockCtrlDriver()

    def configure(self, configuration):
        connection_config = configuration.get("connections", {})
        self.wireless_broadcast_link = self._configure_lowlevel_connection(
            connection_config.get("wireless", {}).get("broadcast")
        )
        self.wireless_unicast_link = self._configure_lowlevel_connection(
            connection_config.get("wireless", {}).get("unicast")
        )
        super(FlockCtrlDronesExtension, self).configure(configuration)

    def on_app_changed(self, old_app, new_app):
        super(FlockCtrlDronesExtension, self).on_app_changed(old_app, new_app)

        if old_app is not None:
            registry = old_app.import_api("clocks").registry
            registry.clock_changed.disconnect(self._on_clock_changed, sender=registry)

        if new_app is not None:
            registry = new_app.import_api("clocks").registry
            registry.clock_changed.connect(self._on_clock_changed, sender=registry)

    def teardown(self):
        self.wireless_lowlevel_link = None

    @property
    def wireless_broadcast_link(self):
        return self._wireless_broadcast_link

    @wireless_broadcast_link.setter
    def wireless_broadcast_link(self, value):
        if self._wireless_broadcast_link is not None:
            self._wireless_communicator.broadcast_connection = None
            self._wireless_broadcast_link.close()
            self.app.connection_registry.remove("Wireless")

        self._wireless_broadcast_link = value

        if self._wireless_broadcast_link is not None:
            self.app.connection_registry.add(
                self._wireless_broadcast_link,
                "Wireless",
                description="Upstream wireless connection",
                purpose=ConnectionPurpose.uavRadioLink,
            )

            self._wireless_communicator.port = self._wireless_broadcast_link.port
            self._wireless_broadcast_link.open()
            self._wireless_communicator.broadcast_connection = (
                self._wireless_broadcast_link
            )

    @property
    def wireless_unicast_link(self):
        return self._wireless_unicast_link

    @wireless_unicast_link.setter
    def wireless_unicast_link(self, value):
        if self._wireless_unicast_link is not None:
            self._wireless_communicator.unicast_connection = None
            self._wireless_unicast_link.close()

        self._wireless_unicast_link = value

        if self._wireless_unicast_link is not None:
            self._wireless_unicast_link.open()
            self._wireless_communicator.unicast_connection = self._wireless_unicast_link

    def _configure_lowlevel_connection(self, specifier):
        """Configures a low-level wireless connection object from the given
        connection specifier parsed from the extension configuration.

        Parameters:
            specifier (Optional[str]): the connection specifier URL that
                tells the extension how to construct the connection object.
                ``None`` means that no connection should be constructed.

        Returns:
            Optional[Connection]: the constructed low-level connection object
                or ``None`` if the specifier was ``None``
        """
        if specifier:
            return reconnecting(create_connection(specifier))
        else:
            return None

    def configure_driver(self, driver, configuration):
        """Configures the driver that will manage the UAVs created by
        this extension.

        It is assumed that the driver is already set up in ``self.driver``
        when this function is called, and it is already associated to the
        server application.

        Parameters:
            driver (UAVDriver): the driver to configure
            configuration (dict): the configuration dictionary of the
                extension
        """
        driver.id_format = configuration.get("id_format", "{0:02}")
        driver.log = self.log.getChild("driver")
        driver.create_device_tree_mutator = self.create_device_tree_mutation_context
        driver.send_packet = self.send_packet

    def _handle_inbound_packet(self, sender, packet):
        """Handles an inbound data packet from a communication link."""
        self._driver.handle_inbound_packet(packet)

    def send_packet(self, packet, destination=None):
        """Requests the extension to send the given FlockCtrl packet to the
        given destination.

        Parameters:
            packet (FlockCtrlPacket): the packet to send
            destination (Optional[bytes]): the long destination address to
                send the packet to. ``None`` means to send a broadcast
                packet.
        """
        medium, address = destination
        if medium == "wireless":
            comm = self._wireless_communicator
        else:
            raise ValueError("unknown medium: {0!r}".format(medium))
        comm.send_packet(packet, address)

    def _on_clock_changed(self, sender, clock):
        """Handler that is called when one of the clocks changed in the
        server application.

        FlockCtrl drones are interested in the MIDI clock only, therefore
        we only send a clock synchronization message to the drones if the
        clock that changed has ID = ``mtc``.
        """
        if clock.id != "mtc":
            return

        now = datetime.now(utc)
        now_as_timestamp = datetime_to_unix_timestamp(now)
        packet = FlockCtrlClockSynchronizationPacket(
            sequence_id=0,  # TODO(ntamas)
            clock_id=5,  # MIDI timecode clock in FlockCtrl
            running=clock.running,
            local_timestamp=now,
            ticks=clock.ticks_given_time(now_as_timestamp),
            ticks_per_second=clock.ticks_per_second,
        )
        self.send_packet(packet)


construct = FlockCtrlDronesExtension
dependencies = ("clocks",)