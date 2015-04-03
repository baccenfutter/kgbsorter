import os
import arrow


def traverse_path(path):
    """Path traversal generator

    The types in this module sometimes want to traverse relative
    paths starting a a specific base directory. This function will
    take a path string and with each iteration return a deeper path
    level reading from left to right.

    Example:
    If you pass the path string 'foo/bar/baz' this function will
    return: ['foo', 'foo/bar', 'foo/bar/baz']

    :param path: str    - path to traverse
    :return: generator  - path traversal list
    """
    for i, elem in enumerate(path.split(os.path.sep)):
        yield os.path.sep.join(path.split(os.path.sep)[0:i + 1])


class Share(object):
    """Representation of a SMB share base directory within the filesystem"""

    def __init__(self, path):
        """
        :param path: str    - absolute path of share
        """
        self.path = os.path.abspath(os.path.realpath(path))

        if not os.path.isdir(self.path):
            msg = "Directory not found: {}".format(self.path)
            raise IOError(msg)

    def __repr__(self):
        return self.path

    def rel_path(self, path):
        """Given a path beneath this share, obtain its relative path component

        :param path: str    - absolute path of node beneath this share
        :return: str        - relative path of node beneath this share
        """
        assert isinstance(path, str), "Expecting type str: {} -> {}".format(path, type(path))
        assert path.startswith(self.path), "Not a child path of self: {}".format(path)

        return path[len(self.path) + 1:]

    @property
    def childs(self):
        """Obtain a list of all child nodes inside this share

        :return: list   - list of instances of ChildNode
        """
        output = []
        for sub_node in os.listdir(self.path):
            node_name = os.path.join(self.path, sub_node)
            if os.path.isfile(node_name):
                node = ChildNode(node_name, self)
                output.append(node)
        return output

    @property
    def subs(self):
        """Obtain list of all sub-nodes inside this share

        :return: list   - list of instances of ChildNode
        """
        output = []
        for root, dirs, files in os.walk(self.path):
            for f in files:
                node_name = self.rel_path(os.path.join(root, f))
                node = ChildNode(node_name, self)
                output.append(node)
        return output

    @property
    def store(self):
        """Obtain the corresponding hardlink store of this share

        :return: obj    - instance of Store
        """
        prefix = os.path.sep.join(self.path.split(os.path.sep)[:-1])
        basename = self.path.split(os.path.sep)[-1]
        store_path = os.path.join(prefix, '.' + basename)
        return Store(store_path, self)

    def check_link(self, rel_path, src):
        """Check if rel_path beneath self is a hard-link to given file

        :param rel_path: str    - relative path to file beneath this share
        :param src: object      - instance of FSNode representing the src file
        :return: bool           - True if file exists at stated location
        """
        assert isinstance(rel_path, str), "Expecting type str: {} -> {}".format(rel_path, type(rel_path))
        assert len(rel_path) > 0, "Expecting non-empty string!"
        assert isinstance(src, ChildNode), "Expecting type ChildNode: {} -> {}".format(src, type(src))

        for sub_path in traverse_path(rel_path):
            node = ChildNode(sub_path, self)

            if len(sub_path) == len(rel_path):  # leaf
                if not (node.exists and node.isfile):
                    break
                if os.stat(node.abspath).st_ino == os.stat(src.abspath).st_ino:
                    return True
            else:   # branch
                if not (node.exists and node.isdir):
                    break

        return False

    def ensure_link(self, rel_path, src):
        """Ensure existence of hardlink to source file and its parent directories recursively

        :param rel_path: str    - relative path to file beneath this share
        :param src: object      - instance of FSNode representing the src file
        :return: bool           - True if file was created
                                  False if file already existed
        """
        assert isinstance(rel_path, str), "Expecting type str: {}".format(rel_path)
        assert len(rel_path) > 0, "Expecting non-empty string!"

        for sub_path in traverse_path(rel_path):
            node = ChildNode(sub_path, self)

            if len(sub_path) == len(rel_path):  # leaf
                if not node.exists:
                    node.link_to(src)
                    return True
                else:
                    if node.isfile:
                        if not os.stat(node.abspath).st_ino == os.stat(src.abspath).st_ino:
                            node.remove()
                            node.link_to(src)
                            return True
                    elif node.isdir:
                        node.rmdir(force=True)
                        node.link_to(src)
                        return True
                    else:
                        raise NotImplementedError

            else:   # branch
                if not node.exists:
                    node.mkdir()
                else:
                    if node.isfile:
                        node.remove()
                        node.mkdir()

        return False

    def ensure_unlink(self, rel_path, src):
        """Ensure non-existence of hardlink to source file

        :param rel_path: str    - relative path to file beneath this share
        :param src: obj         - instance of share
        :return: bool           - Status of operation
                                    True: deleted a hardlink
                                    False: didn't delete a hardlink
        """
        assert isinstance(rel_path, str), "Expecting type str: {} -> {}".format(rel_path, type(rel_path))
        assert len(rel_path) > 0, "Expecting non-empty string!"

        if self.check_link(rel_path, src):
            node = ChildNode(rel_path, self)
            node.remove()
            return True

        return False


class Store(Share):
    """Representation of a hardlink store corresponding to an instance of Share"""

    def __init__(self, path, share):
        """
        :param path: str    - absolute path of store in filesystem
        :param share:       - corresponding instance of Share
        """
        Share.__init__(self, os.path.abspath(os.path.realpath(path)))
        self.share = share


class ChildNode(object):
    """Representation of a child-node beneath a share of store"""

    def __init__(self, rel_path, share):
        """
        :param rel_path: str    - relative path beneath parenting directory node
        :param share: obj       - instance if Share
        """
        self.rel_path = rel_path if not rel_path.startswith('/') else rel_path[1:]
        self.share = share

    def __repr__(self):
        return self.abspath

    @property
    def abspath(self):
        """Obtain the absolute path of this node in the filesystem"""
        return os.path.join(self.share.path, self.rel_path)

    @property
    def exists(self):
        """Check the existence of this node in the filesystem"""
        return os.path.exists(self.abspath)

    @property
    def islink(self):
        """Check if this node is a link"""
        return os.path.islink(self.abspath)

    @property
    def isfile(self):
        """Check if this node is a file"""
        return os.path.isfile(self.abspath)

    @property
    def isdir(self):
        """Check if this node is a directory"""
        return os.path.isdir(self.abspath)

    @property
    def childs(self):
        """Obtain list of all children of this location in the filesystem"""
        output = []
        for basename in os.listdir(self.abspath):
            node_path = os.path.join(self.rel_path, basename)
            node = ChildNode(node_path, self.share)
            output.append(node)
        return output

    @property
    def subs(self):
        """Obtain a list of all sub-nodes if this location in the filesystem"""
        output = []
        for root, dirs, files in os.walk(self.abspath):
            for f_path in files:
                node_path = self.share.rel_path(os.path.join(root, f_path))
                node = ChildNode(node_path, self.share)
                output.append(node)
        return output

    def mkdir(self):
        """Perform mkdir on self"""
        os.mkdir(self.abspath)

    def rmdir(self, force=False):
        """Perform rmdir on self"""
        if force is False:
            os.rmdir(self.abspath)
        elif force is True:
            import shutil
            shutil.rmtree(self.abspath)

    def link_to(self, src):
        """Perform ln on self pointing to src

        :param src: obj     - instance of Share
        """
        os.link(src.abspath, self.abspath)

    def remove(self):
        """Perform rm on self"""
        os.remove(self.abspath)

    def older_than(self, days):
        """Check if self has a create date older than N days

        :param days: int    - number of days
        """
        time_delta = arrow.now() - arrow.get(os.path.getmtime(self.abspath))
        return time_delta.days > days