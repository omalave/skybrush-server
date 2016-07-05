"""Device and channel-related model classes."""

from __future__ import absolute_import

from collections import Counter
from flockwave.spec.schema import get_enum_from_schema, \
    get_complex_object_schema
from itertools import islice
from six import add_metaclass, iteritems

from. errors import ClientNotSubscribedError, NoSuchPathError
from .metamagic import ModelMeta

__all__ = ("ChannelNode", "ChannelOperation", "ChannelType", "DeviceClass",
           "DeviceTree", "DeviceNode", "DeviceTreeNodeType", "UAVNode",
           "DeviceTreeSubscriptionManager")

ChannelOperation = get_enum_from_schema("channelOperation",
                                        "ChannelOperation")
ChannelType = get_enum_from_schema("channelType", "ChannelType")
DeviceClass = get_enum_from_schema("deviceClass", "DeviceClass")
DeviceTreeNodeType = get_enum_from_schema("deviceTreeNodeType",
                                          "DeviceTreeNodeType")

_channel_type_mapping = {
    int: "number",
    float: "number",
    str: "string",
    bool: "boolean",
    object: "object"
}


def _channel_type_from_object(cls, obj):
    """Converts a Python type object to a corresponding channel type
    object. Also accepts ChannelType objects as input, in which case
    the object is returned as is.

    Parameters:
        obj (Union[ChannelType, type]): the type object to convert to
            a ChannelType

    Returns:
        ChannelType: the appropriate channel type corresponding to the
            Python type
    """
    if isinstance(obj, ChannelType):
        return obj
    else:
        try:
            name = _channel_type_mapping[obj]
        except KeyError:
            raise TypeError("{0!r} cannot be converted to a "
                            "ChannelType".format(obj))
        return cls[name]

ChannelType.from_object = classmethod(_channel_type_from_object)


@add_metaclass(ModelMeta)
class DeviceTreeNodeBase(object):
    """Class representing a single node in a Flockwave device tree."""

    class __meta__:
        schema = get_complex_object_schema("deviceTreeNode")

    def __init__(self):
        """Constructor."""
        self._subscribers = None

    def collect_channel_values(self):
        """Creates a Python dictionary that maps the IDs of the children of
        this node as follows:

          - channel nodes (i.e. instances of ChannelNode_) will be mapped
            to their current values

          - every other node ``node`` will be mapped to the result of
            ``node.collect_channel_values()``, recursively

        Returns:
            dict: a Python dictionary constructed as described above
        """
        return dict(
            (key, child.collect_channel_values())
            for key, child in iteritems(self.children)
        )

    def count_subscriptions_of(self, client):
        """Count how many times the given client is subscribed to changes
        in channel values of this node or any of its sub-nodes.

        Parameters:
            client (Client): the client to test

        Returns:
            int: the number of times time given client is subscribed to this
                node
        """
        return self._subscribers[client] if self._subscribers else 0

    def iterchildren(self):
        """Iterates over the children of this node.

        Yields:
            (str, DeviceTreeNodeBase): the ID of the child node and the
                child node itself, for all children
        """
        if hasattr(self, "children"):
            return iteritems(self.children)
        else:
            return ()

    def traverse_dfs(self, own_id=None):
        """Returns a generator that yields all the nodes in the subtree of
        this node, including the node itself, in depth-first order.

        Parameters:
            own_id (Optional[str]): the ID of this node in its parent, if
                known. This will be yielded in the traversal results for
                the node itself.

        Yields:
            (str, DeviceTreeNode): each node in the subtree of this node,
                including the node itself, and its associated ID in its
                parent, in depth-first order. The ID will be the value of
                the ``own_id`` parameter for this node.
        """
        queue = [(own_id, self)]
        while queue:
            id, node = queue.pop()
            yield id, node
            queue.extend(node.iterchildren())

    def _add_child(self, id, node):
        """Adds the given node as a child node to this node.

        Parameters:
            id (str): the ID of the node
            node (DeviceTreeNodeBase): the node to add

        Returns:
            DeviceTreeNodeBase: the node that was added

        Throws:
            ValueError: if another node with the same ID already exists for
                this node
        """
        if not hasattr(self, "children"):
            self.children = {}
        if id in self.children:
            raise ValueError("another child node already exists with "
                             "ID={0!r}".format(id))
        self.children[id] = node
        return node

    def _remove_child(self, node):
        """Removes the given child node from this node.

        Parameters:
            node (DeviceTreeNodeBase): the node to remove

        Returns:
            DeviceTreeNodeBase: the node that was removed

        Throws:
            ValueError: if the node is not a child of this node
        """
        for id, child_node in self.iterchildren():
            if child_node == node:
                return self._remove_child_by_id(id)
        raise ValueError("the given node is not a child of this node")

    def _remove_child_by_id(self, id):
        """Removes the child node with the given ID from this node.

        Parameters:
            id (str): the ID of the node to remove

        Returns:
            DeviceTreeNodeBase: the node that was removed

        Throws:
            ValueError: if there is no such child with the given ID
        """
        try:
            return self.children.pop(id)
        except KeyError:
            raise ValueError("no child exists with the given ID: {0!r}"
                             .format(id))

    def _subscribe(self, client):
        """Subscribes the given client object to this node and its subtree.
        The client will get notified whenever one of the channels in the
        subtree of this node (or in the node itself if the node is a channel
        node) receives a new value.

        A client may be subscribed to this node multiple times; the node
        will track how many times the client has subscribed to the node and
        the client must unsubscribe exactly the same number of times to stop
        receiving notifications.

        Parameters:
            client (Client): the client to notify when a channel value
                changes in the subtree of this node.
        """
        if self._subscribers is None:
            # Create the subscriber counter lazily because most nodes
            # will not have any subscribers
            self._subscribers = Counter()
        self._subscribers[client] += 1

    def _unsubscribe(self, client, force=False):
        """Unsubscribes the given client object from this node and its
        subtree.

        Parameters:
            client (Client): the client to unsubscribe
            force (bool): whether to force an unsubscription of the client
                even if it is subscribed multiple times. Setting this
                argument to ``True`` will suppress ClientNotSubscribedError_
                exceptions if the client is not subscribed.

        Throws:
            KeyError: if the client is not subscribed to this node and
                ``force`` is ``False``
        """
        if self.count_subscriptions_of(client) > 0:
            if force:
                del self._subscribers[client]
            else:
                self._subscribers[client] -= 1
        elif not force:
            raise KeyError(client)


class ChannelNode(DeviceTreeNodeBase):
    """Class representing a device node in a Flockwave device tree."""

    def __init__(self, channel_type, operations=None):
        """Constructor.

        Parameters:
            channel_type (ChannelType): the type of the channel
            operations (List[ChannelOperation]): the allowed operations of
                the channel. Defaults to ``[ChannelOperation.read]`` if
                set to ``None``.
        """
        super(ChannelNode, self).__init__()

        if operations is None:
            operations = [ChannelOperation.read]

        self.type = DeviceTreeNodeType.channel
        self.subtype = channel_type
        self.operations = list(operations)
        self.value = None

    def collect_channel_values(self):
        """Returns the value of the channel itself."""
        return self.value

    @property
    def subtype(self):
        """Alias to ``subType``."""
        return self.subType

    @subtype.setter
    def subtype(self, value):
        self.subType = value


class DeviceNode(DeviceTreeNodeBase):
    """Class representing a device node in a Flockwave device tree."""

    def __init__(self, device_class=DeviceClass.misc):
        """Constructor."""
        super(DeviceNode, self).__init__()
        self.type = DeviceTreeNodeType.device
        self.device_class = device_class

    def add_channel(self, id, type):
        """Adds a new channel with the given identifier to this device
        node.

        Parameters:
            id (str): the identifier of the channel being added.
            type (ChannelType): the type of the channel

        Returns:
            ChannelNode: the channel node that was added.
        """
        channel_type = ChannelType.from_object(type)
        return self._add_child(id, ChannelNode(channel_type=channel_type))

    def add_device(self, id):
        """Adds a new device with the given identifier as a sub-device
        to this device node.

        Parameters:
            id (str): the identifier of the device being added.

        Returns:
            DeviceNode: the device tree node that was added.
        """
        return self._add_child(id, DeviceNode())

    @property
    def device_class(self):
        """Alias to ``deviceClass``."""
        return self.deviceClass

    @device_class.setter
    def device_class(self, value):
        self.deviceClass = value


class RootNode(DeviceTreeNodeBase):
    """Class representing the root node in a Flockwave device tree."""

    def __init__(self):
        """Constructor."""
        super(RootNode, self).__init__()
        self.type = DeviceTreeNodeType.root

    def add_child(self, id, node):
        """Adds a new child node with the given ID to this root node.

        Parameters:
            id (str): the ID of the node to add
            node (UAVNode): the node to add; root nodes may only have UAV
                nodes as children.

        Returns:
            UAVNode: the node that was added

        Throws:
            ValueError: if another node with the same ID already exists for
                the root node
        """
        return self._add_child(id, node)

    def remove_child(self, node):
        """Removes the given child node from the root node.

        Parameters:
            node (UAVNode): the node to remove

        Returns:
            UAVNode: the node that was removed
        """
        return self._remove_child(node)

    def remove_child_by_id(self, id):
        """Removes the child node with the given ID from the root node.

        Parameters:
            id (str): the ID of the child node to remove

        Returns:
            UAVNode: the node that was removed
        """
        return self._remove_child_by_id(id)


class UAVNode(DeviceTreeNodeBase):
    """Class representing a UAV node in a Flockwave device tree."""

    def __init__(self):
        """Constructor."""
        super(UAVNode, self).__init__()
        self.type = DeviceTreeNodeType.uav

    def add_device(self, id):
        """Adds a new device with the given identifier to this UAV node.

        Parameters:
            id (str): the identifier of the device being added.

        Returns:
            DeviceNode: the device tree node that was added.
        """
        return self._add_child(id, DeviceNode())


class DeviceTreePath(object):
    """A path in a device tree from its root to one of its nodes. Leaf and
    branch nodes are both allowed.

    Device tree paths have a natural string representation that looks like
    standard filesystem paths: ``/node1/node2/node3/.../leaf``. This class
    allows you to construct a device tree path from a string. When a device
    tree path is printed as a string, it will also be formatted in this
    style.
    """

    def __init__(self, path=u"/"):
        """Constructor.

        Parameters:
            path (Union[str, DeviceTreePath]): the string representation of
                the path, or another path object to clone.
        """
        if isinstance(path, DeviceTreePath):
            self._parts = list(path._parts)
        else:
            self.path = path

    def iterparts(self):
        """Returns a generator that iterates over the parts of the path.

        Yields:
            str: the parts of the path
        """
        return islice(self._parts, 1, None)

    @property
    def path(self):
        """The path, formatted as a string.

        Returns:
            str: the path, formatted as a string
        """
        return u"/".join(self._parts)

    @path.setter
    def path(self, value):
        parts = value.split(u"/")
        if parts[0] != u"":
            raise ValueError("path must start with a slash")
        if parts[-1] == u"":
            parts.pop()
        try:
            parts.index(u"", 1)
        except ValueError:
            # This is okay, this is what we wanted
            pass
        else:
            raise ValueError("path must not contain an empty component")
        self._parts = parts

    def __str__(self):
        return unicode(self).encode("utf-8")

    def __unicode__(self):
        return self.path


class DeviceTree(object):
    """A device tree of a UAV that lists the devices and channels that
    the UAV provides.
    """

    def __init__(self):
        """Constructor. Creates an empty device tree."""
        self._root = RootNode()
        self._uav_registry = None

    @property
    def json(self):
        """The JSON representation of the device tree."""
        return self._root.json

    @property
    def root(self):
        """The root node of the device tree."""
        return self._root

    def resolve(self, path):
        """Resolves the given path in the tree and returns the node that
        corresponds to the given path.

        Parameters:
            path (Union[str, DeviceTreePath]): the path to resolve. Strings
                will be converted to a DeviceTreePath_ automatically.

        Returns:
            DeviceTreeNode: the node at the given path in the tree

        Throws:
            NoSuchPathError: if the given path cannot be resolved in the tree
        """
        if not isinstance(path, DeviceTreePath):
            path = DeviceTreePath(path)

        node = self.root
        for part in path.iterparts():
            try:
                node = node.children[part]
            except KeyError:
                raise NoSuchPathError(path)

        return node

    def traverse_dfs(self):
        """Returns a generator that yields all the nodes in the tree in
        depth-first order.

        Yields:
            (str, DeviceTreeNode): each node in the tree and its associated
                ID in its parent, in depth-first order. The ID will be
                ``None`` for the root node.
        """
        return self.root.traverse_dfs()

    @property
    def uav_registry(self):
        """The UAV registry that the device tree watches. The device tree
        will attach new UAV nodes when a new UAV is added to the registry,
        and similarly detach old UAV nodes when UAVs are removed from the
        registry.
        """
        return self._uav_registry

    @uav_registry.setter
    def uav_registry(self, value):
        if self._uav_registry == value:
            return

        if self._uav_registry is not None:
            self._uav_registry.added.disconnect(
                self._on_uav_added, sender=self._uav_registry
            )
            self._uav_registry.removed.disconnect(
                self._on_uav_removed, sender=self._uav_registry
            )

        self._uav_registry = value

        if self._uav_registry is not None:
            self._uav_registry.added.connect(
                self._on_uav_added, sender=self._uav_registry
            )
            self._uav_registry.removed.connect(
                self._on_uav_removed, sender=self._uav_registry
            )

    def _on_uav_added(self, sender, uav):
        """Handler called when a new UAV is registered in the server.

        Parameters:
            sender (UAVRegisty): the UAV registry
            uav (UAV): the UAV that was added
        """
        self.root.add_child(uav.id, uav.device_tree_node)

    def _on_uav_removed(self, sender, uav):
        """Handler called when a UAV is deregistered from the server.

        Parameters:
            sender (UAVRegisty): the UAV registry
            uav (UAV): the UAV that was removed
        """
        self.root.remove_child_by_id(uav.id)


class DeviceTreeSubscriptionManager(object):
    """Object that is responsible for managing the subscriptions of clients
    to the nodes of a device tree.
    """

    def __init__(self, tree):
        """Constructor.

        Parameters:
            tree (DeviceTree): the tree whose subscriptions this object will
                manage
        """
        self._tree = tree
        self._client_registry = None

    @property
    def client_registry(self):
        """The client registry that the device tree watches. The device tree
        will remove the subscriptions of clients from the tree when a
        client is removed from this registry.
        """
        return self._client_registry

    @client_registry.setter
    def client_registry(self, value):
        if self._client_registry == value:
            return

        if self._client_registry is not None:
            self._client_registry.removed.disconnect(
                self._on_client_removed, sender=self._client_registry
            )

        self._client_registry = value

        if self._client_registry is not None:
            self._client_registry.removed.connect(
                self._on_client_removed, sender=self._client_registry
            )

    def _collect_subscriptions(self, client, path, node, result):
        """Finds all the subscriptions of the given client in the subtree
        of the given tree node (including the node itself) and adds tem to
        the given result object.

        Parameters:
            client (Client): the client whose subscriptions we want to
                collect
            path (DeviceTreePath): the path that leads to the root node. It
                will be mutated so make sure that you clone the original
                path of the node before passing it here.
            node (DeviceTreeNode): the root node that the search starts
                from
            result (Counter): the counter object that counts the
                subscriptions
        """
        count = node.count_subscriptions_of(client)
        if count > 0:
            result[unicode(path)] += count
        for child_id, child in node.iterchildren():
            path._parts.append(child_id)
            self._collect_subscriptions(client, path, child, result)
            path._parts.pop()

    def _on_client_removed(self, sender, client):
        """Handler called when a client disconnected from the server."""
        for _, node in self._tree.traverse_dfs():
            node._unsubscribe(client, force=True)

    def list_subscriptions(self, client, path_filter):
        """Lists all the device tree paths that a client is subscribed
        to.

        Parameters:
            client (Client): the client whose subscriptions we want to
                retrieve
            path_filter (Optional[iterable]): iterable that yields strings
                or DeviceTreePath_ objects. The result will include only
                those subscriptions that are contained in at least one of
                the subtrees matched by the path filters.

        Returns:
            Counter: a counter object mapping device tree paths to the
                number of times the client has subscribed to them,
                multiplied by the number of times they were matched by
                the path filter.
        """
        if path_filter is None:
            path_filter = (u"/", )

        result = Counter()
        for path in path_filter:
            node = self._tree.resolve(path)
            path_clone = DeviceTreePath(path)
            self._collect_subscriptions(client, path_clone, node, result)

        return result

    def subscribe(self, client, path):
        """Subscribes the given client to the given device tree path.

        The same client may be subscribed to the same node multiple times;
        the same amount of unsubscription requests must follow to ensure
        that the client stops receiving notifications.

        Parameters:
            path (Union[str, DeviceTreePath]): the path to resolve. Strings
                will be converted to a DeviceTreePath_ automatically.
            client (Client): the client to subscribe

        Throws:
            NoSuchPathError: if the given path cannot be resolved in the tree
        """
        self._tree.resolve(path)._subscribe(client)

    def unsubscribe(self, client, path, force=False):
        """Unsubscribes the given client from the given device tree path.

        The same client may be subscribed to the same node multiple times;
        the same amount of unsubscription requests must follow to ensure
        that the client stops receiving notifications. Alternatively, you
        may set the ``force`` argument to ``True`` to force the removal
        of the client from the node no matter how many times it has
        subscribed before.

        Parameters:
            path (Union[str, DeviceTreePath]): the path to resolve. Strings
                will be converted to a DeviceTreePath_ automatically.
            client (Client): the client to unsubscribe
            force (bool): whether to force an unsubscription of the client
                even if it is subscribed multiple times. Setting this
                argument to ``True`` will suppress ClientNotSubscribedError_
                exceptions if the client is not subscribed.

        Throws:
            NoSuchPathError: if the given path cannot be resolved in the tree
            ClientNotSubscribedError: if the given client is not subscribed
                to the node and ``force`` is ``False``
        """
        try:
            self._tree.resolve(path)._unsubscribe(client, force)
        except KeyError:
            raise ClientNotSubscribedError(client, path)