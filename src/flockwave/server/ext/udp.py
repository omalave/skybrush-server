"""Extension that provides UDP socket-based communication channels for the
server.

This extension enables the server to communicate with clients by expecting
requests on a certain UDP port. Responses will be sent to the same host and
port where the request was sent from.
"""

import trio.socket

from contextlib import closing, ExitStack
from functools import partial
from trio import CapacityLimiter, open_nursery
from typing import Optional, Tuple

from flockwave.server.encoders import JSONEncoder
from flockwave.server.model import CommunicationChannel
from flockwave.server.networking import (
    create_async_socket,
    format_socket_address,
    get_socket_address,
)
from flockwave.server.utils import overridden


app = None
encoder = JSONEncoder()
log = None
sock = None


class UDPChannel(CommunicationChannel):
    """Object that represents a UDP communication channel between a
    server and a single client.

    The word "channel" is not really adequate here because UDP is a
    connectionless protocol. That's why notifications are not currently
    handled in this channel - I am yet to figure out how to do this
    properly.
    """

    def __init__(self, sock: trio.socket.socket):
        """Constructor."""
        self.address = None
        self.sock = sock

    def bind_to(self, client):
        """Binds the communication channel to the given client.

        Parameters:
            client (Client): the client to bind the channel to
        """
        if client.id and client.id.startswith("udp://"):
            host, _, port = client.id[6:].partition(":")
            self.address = host, int(port)
        else:
            raise ValueError("client has no ID or address yet")

    async def send(self, message):
        """Inherited."""
        await self.sock.sendto(encoder.dumps(message), self.address)


############################################################################


def get_address(in_subnet_of: Optional[str] = None) -> str:
    """Returns the address where we are listening for incoming UDP packets.

    Parameters:
        in_subnet_of: when not `None` and we are listening on multiple (or
            all) interfaces, this address is used to pick a reported address
            that is in the same subnet as the given address

    Returns:
        the address where we are listening
    """
    global sock
    return get_socket_address(sock)


def get_ssdp_location(address) -> Optional[str]:
    """Returns the SSDP location descriptor of the UDP channel.

    Parameters:
        address: when not `None` and we are listening on multiple (or all)
            interfaces, this address is used to pick a reported address that
            is in the same subnet as the given address
    """
    global sock
    return (
        format_socket_address(sock, format="udp://{host}:{port}", in_subnet_of=address)
        if sock
        else None
    )


async def handle_message(message: bytes, sender: Tuple[str, int]) -> None:
    """Handles a single message received from the given sender.

    Parameters:
        message: the incoming message, waiting to be parsed
        sender: the IP address and port of the sender
    """
    client_id = "udp://{0}:{1}".format(*sender)

    try:
        message = encoder.loads(message)
    except ValueError as ex:
        log.warn(f"Malformed JSON message received from {client_id} - {message[:20]}")
        log.exception(ex)
        return

    with app.client_registry.use(client_id, "udp") as client:
        await app.message_hub.handle_incoming_message(message, client)


async def handle_message_safely(
    message: bytes, sender: Tuple[str, int], *, limit: CapacityLimiter
) -> None:
    """Handles a single message received from the given sender, ensuring
    that exceptions do not propagate through and the number of concurrent
    requests being processed is limited.

    Parameters:
        message: the incoming message, waiting to be parsed
        sender: the IP address and port of the sender
        limit: Trio capacity limiter that ensures that we are not processing
            too many requests concurrently
    """
    async with limit:
        try:
            return await handle_message(message, sender)
        except Exception as ex:
            log.exception(ex)


############################################################################


async def task(app, configuration, logger):
    """Background task that is active while the extension is loaded."""
    address = configuration.get("host", ""), configuration.get("port", 5001)
    pool_size = configuration.get("pool_size", 1000)

    sock = create_async_socket(trio.socket.SOCK_DGRAM)
    await sock.bind(address)

    with ExitStack() as stack:
        stack.enter_context(overridden(globals(), app=app, log=logger, sock=sock))
        stack.enter_context(closing(sock))
        stack.enter_context(
            app.channel_type_registry.use(
                "udp",
                factory=partial(UDPChannel, sock),
                address=get_address,
                ssdp_location=get_ssdp_location,
            )
        )

        limit = CapacityLimiter(pool_size)
        handler = partial(handle_message_safely, limit=limit)

        async with open_nursery() as nursery:
            while True:
                data = await sock.recvfrom(65536)
                nursery.start_soon(handler, *data)