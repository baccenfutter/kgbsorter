#!/usr/bin/env  python2.7
"""kgbsorter

A tool for managing hardlinks on kgb.

All shares are obtained from /etc/samba/smb.conf. Shares within the
samba configuration file that end with a comment carrying the string
'protected' are considered to be protected from use.

Every share has a buddy-directory sitting next to it with the same
name as the share except that it is hidden. Considering the share
/mnt/foobar the buddy-directory would be /mnt/.foobar. This directory
is used as a mirror-directory for hardlinks and should not be
writable though SMB/CIFS but may be readable.

A file within the share is considered as 'locked' if a corresponding
hardlink exists with the exact same relative path name underneath the
hardlink basedir. If no hardlink to this file with the corresponding
name exists underneath the hardlink basedir, it is considered as
'unlocked' and will be deleted by the cleanup procedure.

The cleanup procedure runs in two steps. First, it will recursively
iterate over all files underneath the hardlink base-directory and
ensure that all these file-names exist as a hardlink relative to the
share's base-directory. Second, it will recursively iterate over all
files underneath the share base-directory and delete all files that
are not locked and older than N days, whereby N may be configured via
the shell parameters -d DAYS and -m MINUTES or default to 7 days.

Usage:
    kgbsorter
    kgbsorter lock FILE...
    kgbsorter unlock FILE...
    kgbsorter cleanup SHARE [-d DAYS | -m MINUTES]

Options:
    -h --help               show this
"""
__author = ['Brian Wiborg <baccenfutter@c-base.org>']
__version__ = '0.1.0-alpha'
__date__ = '2014-06-15'

from fs_hopper import Directory
from docopt import docopt
import os
import re

DEFAULT_CONF = '/etc/samba/smb.conf'
DEFAULT_DAYS = 7
DEFAULT_MINS = 0


class SmbNode(Directory):
    @classmethod
    def get_shares(cls, use_smb_conf=''):
        """Generate for all available shares according to /etc/samba/smb.conf

        :param use_smb_conf:    str         - optional custom path to smb.conf
        :return: generator                  - a list of strings
        """
        config_file = use_smb_conf or DEFAULT_CONF
        haystack = open(config_file).readlines()
        needle = re.compile(r'[^#]*path.*=.*"(.*)".*')
        fork = re.compile(r'.*#.*protected.*')
        output = []
        for line in haystack:
            match = needle.match(line)
            if match:
                if not fork.match(match.group(0)):
                    output.append(match.group(1))
        return output

    @property
    def share_basedir(self):
        """Obtain base-directory of self

        :return: object     - instance of SmbNode(basedir)
        :raise: IOError    - if self doesn't lay within a share
        """
        shares = filter(lambda x: self.name.startswith(x), SmbNode.get_shares())
        if not shares:
            raise IOError("Doesn't lay within a share: {}".format(self))

        share = shares[0]
        return SmbNode(share)

    @property
    def store_basedir(self):
        """Obtain base-directory of this share's store

        :return: object     - instance of SmbNode(store_basedir)
        :raise: IOError     - if self doesn't lay within a share
        """

        try:
            basedir = self.share_basedir
        except IOError, e:
            raise IOError(e)

        dirname = os.path.sep.join(basedir.name.split(os.path.sep)[:-1])
        basename = basedir.name.split(os.path.sep)[-1]
        store_path = os.path.join(dirname, '.' + basename)
        store = SmbNode(store_path)
        return store

    @property
    def rel_path(self):
        """Obtain relative path inside share

        :return: str
        """
        return self.name[len(self.share_basedir.name) + 1:]

    @property
    def subs(self):
        return [SmbNode(sub.name) for sub in self.get_subs()]

    @property
    def childs(self):
        return [SmbNode(child.name) for child in self.get_childs()]

    def __link(self, src, dst):
        """Create hardlink of src at dst

        :param src:
        :param dst:
        :return:
        """

    def lock(self):
        """Lock this file or all files beneath this directory

        :return: list   - list of files actually locked
        :raise: IOError - if file doesn't exist within a share
        """

        locked_files = []

        if not self.exists():
            raise IOError("File or directory not found: {}".format(self))

        basedir = self.share_basedir
        if not basedir:
            raise IOError("Not within share: {}".format(self))

        if self.is_dir():
            for child in self.childs:
                locked_files += child.lock()

        elif self.is_file():
            store_basedir = self.store_basedir
            rel_path = self.rel_path
            dirs = rel_path.split(os.path.sep)[:-1]
            basename = rel_path.split(os.path.sep)[-1]

            # recursively create the sub-directory structure
            dir_cursor = store_basedir
            for d in dirs:
                subdir = SmbNode(os.path.join(dir_cursor.name, d))
                if subdir.exists():
                    if subdir.is_dir():
                        dir_cursor = subdir
                    elif subdir.is_file():
                        subdir.delete()
                    else:
                        raise NotImplementedError
                else:
                    subdir.mkdir()
                    dir_cursor = subdir
            dst = SmbNode(os.path.join(dir_cursor.name, basename))

            # create the actual hardlink
            if not dst.exists():
                os.link(self.name, dst.name)
                locked_files.append(self)

        else:
            raise NotImplementedError("Not a regular file: {}".format(self))

        return locked_files

    def unlock(self):
        """Unlock this file or all files beneath this directory

        :return: list       - list of actually unlocked directories
        """
        unlocked_files = []

        if not self.exists():
            raise IOError("File or directory not found: {}".format(self))

        basedir = self.share_basedir
        if not basedir:
            raise IOError("Doesn't lay within a share: {}".format(self))

        if self.is_dir():
            for child in self.childs:
                unlocked_files += child.unlock()

        elif self.is_file():
            store_basedir = self.store_basedir
            rel_path = self.rel_path
            dirs = rel_path.split(os.path.sep)[:-1]
            basename = rel_path.split(os.path.sep)[-1]

            # recursively follow directory structure to target file
            dir_cursor = store_basedir
            for d in dirs:
                subdir = SmbNode(os.path.join(store_basedir.name, d))
                if subdir.exists():
                    if subdir.is_dir():
                        dir_cursor = subdir
                    elif subdir.is_file():
                        return unlocked_files
                    else:
                        raise NotImplementedError
                else:
                    return unlocked_files
            dst = SmbNode(os.path.join(dir_cursor.name, basename))

            # check if link exists and if it is really a hardlink to the
            # file in the share
            if dst.exists() and dst.is_file():
                if os.stat(dst.name).st_ino == os.stat(self.name).st_ino:
                    os.remove(dst.name)
                    unlocked_files.append(self)

        return unlocked_files


class KgbSorter(object):
    def __init__(self, args):
        self.args = args

    @property
    def abs_paths(self):
        return [os.path.abspath(os.path.realpath(f)) for f in args['FILE']]

    def list_shares(self):
        return SmbNode.get_shares()

    def lock(self, *paths):
        locked_nodes = []
        for path in paths:
            share = SmbNode(path)
            locked_nodes += share.lock()
        return locked_nodes

    def unlock(self, *paths):
        unlocked_nodes = []
        for path in paths:
            share = SmbNode(path)
            unlocked_nodes += share.unlock()
        return unlocked_nodes

    def cleanup(self):
        pass


if __name__ == '__main__':
    args = docopt(__doc__, version=__version__)
    kgb_sorter = KgbSorter(args)
    if args['lock']:
        files = kgb_sorter.lock(*kgb_sorter.abs_paths)
        if files:
            for f in files:
                print f
    elif args['unlock']:
        files = kgb_sorter.unlock(*kgb_sorter.abs_paths)
        if files:
            for f in files:
                print f

    elif args['cleanup']:
        kgb_sorter.cleanup()
    else:
        print "Available shares:"
        for share in kgb_sorter.list_shares():
            print share
