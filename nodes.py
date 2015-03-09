import os
import logging
import arrow

logger = logging.getLogger('FileSystem')


def traverse_path(path):
    for i, elem in enumerate(path.split(os.path.sep)):
        yield os.path.sep.join(path.split(os.path.sep)[0:i + 1])


class Share(object):
    def __init__(self, path):
        self.path = path
        if not os.path.exists(self.path) and os.path.isdir(self.path):
            msg = "Directory not found: {}".format(self.path)
            logger.critical(msg)
            raise IOError(msg)

    def __repr__(self):
        return self.path

    def rel_path(self, path):
        assert isinstance(path, str), "Expecting type str: {} -> {}".format(path, type(path))
        assert path.startswith(self.path), "Not a child path of self: {}".format(path)

        return path[len(self.path) + 1:]

    @property
    def childs(self):
        output = []
        for sub_node in os.listdir(self.path):
            node_name = os.path.join(self.path, sub_node)
            if os.path.isfile(node_name):
                node = ChildNode(node_name, self)
                output.append(node)
        return output

    @property
    def subs(self):
        output = []
        for root, dirs, files in os.walk(self.path):
            for f in files:
                node_name = self.rel_path(os.path.join(root, f))
                node = ChildNode(node_name, self)
                output.append(node)
        return output

    @property
    def store(self):
        prefix = os.path.sep.join(self.path.split(os.path.sep)[:-1])
        basename = self.path.split(os.path.sep)[-1]
        store_path = os.path.join(prefix, '.' + basename)
        return Store(store_path, self)

    def check_link(self, rel_path, src):
        """Check if rel_path beneath self is a hard-link to given file

        :param rel_path: str    - relative path to file beneath this FSNode
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
        """Create hardlink of source file and parent directories recursively

        :param rel_path: str    - relative path to file beneath this FSNode
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
        assert isinstance(rel_path, str), "Expecting type str: {} -> {}".format(rel_path, type(rel_path))
        assert len(rel_path) > 0, "Expecting non-empty string!"

        if self.check_link(rel_path, src):
            node = ChildNode(rel_path, self)
            node.remove()
            return True

        return False


class Store(Share):
    def __init__(self, path, share):
        Share.__init__(self, path)
        self.share = share


class ChildNode(object):
    def __init__(self, rel_path, share):
        self.rel_path = rel_path if not rel_path.startswith('/') else rel_path[1:]
        self.share = share

    def __repr__(self):
        return self.abspath

    @property
    def abspath(self):
        return os.path.join(self.share.path, self.rel_path)

    @property
    def exists(self):
        return os.path.exists(self.abspath)

    @property
    def islink(self):
        return os.path.islink(self.abspath)

    @property
    def isfile(self):
        return os.path.isfile(self.abspath)

    @property
    def isdir(self):
        return os.path.isdir(self.abspath)

    @property
    def childs(self):
        output = []
        for basename in os.listdir(self.abspath):
            node_path = os.path.join(self.rel_path, basename)
            node = ChildNode(node_path, self.share)
            output.append(node)
        return output

    @property
    def subs(self):
        output = []
        for root, dirs, files in os.walk(self.abspath):
            for f_path in files:
                node_path = self.share.rel_path(os.path.join(root, f_path))
                node = ChildNode(node_path, self.share)
                output.append(node)
        return output

    def mkdir(self):
        os.mkdir(self.abspath)
        logger.info("Created directory:", self.abspath)

    def rmdir(self, force=False):
        if force is False:
            os.rmdir(self.abspath)
            logger.info("Deleted directory:", self.abspath)
        elif force is True:
            import shutil
            shutil.rmtree(self.abspath)
            logger.info("Recursively deleted:", self.abspath)

    def link_to(self, src):
        os.link(src.abspath, self.abspath)

    def remove(self):
        os.remove(self.abspath)

    def older_than(self, days):
        time_delta = arrow.now() - arrow.get(os.path.getctime(self.abspath))
        return time_delta.days > days