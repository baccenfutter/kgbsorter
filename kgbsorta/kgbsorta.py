#!/usr/bin/env  python2.7
# -*- coding: utf-8 -*-
"""kgbsorta - A tool for managing hardlinks on kgb.

A share is a directory in the filesystem. Every share has a
buddy-directory sitting next to it with the same name as the share
except that it is hidden. This directory is called the store.
Considering the share /mnt/foobar the buddy-directory would be
/mnt/.foobar. This directory is used as a mirror-directory for
hardlinks and should not be writable though SMB/CIFS but may be
readable.

A file within the share is considered as 'locked' if a corresponding
hardlink exists with the exact same relative path name underneath the
store directory. If no hardlink to this file with the corresponding
name exists underneath the store directory, it is considered as
'unlocked' and will be deleted by the cleanup procedure.

The cleanup procedure runs in two steps. First, it will recursively
iterate over all files underneath the hardlink base-directory and
ensure that all these file-names exist as a hardlink relative to the
share's base-directory. Second, it will recursively iterate over all
files underneath the share base-directory and delete all files that
are not locked and older than N days, whereby N may be configured via
the shell parameters -d DAYS which defaults to seven(7).

Usage:
    kgbsorter
    kgbsorter lock FILE...
    kgbsorter unlock FILE...
    kgbsorter cleanup SHARE [-d DAYS]

Options:
    -h --help               show this
"""
__author = ['Brian Wiborg <baccenfutter@c-base.org>']
__version__ = '0.1.0-alpha'
__date__ = '2015-03-08'

import sys
sys.path.append("/usr/local/src/kgbsorta")

from ConfigParser import SafeConfigParser

from docopt import docopt
import os

from kgbsorta.nodes import Share, ChildNode


DEFAULT_DAYS = 7


class KgbSorta(object):
    """API Main Class

    Use this class for embedding this software in your other software.
    """

    def __init__(self):
        self.config = SafeConfigParser()
        self.config.read([
            'config.ini',
            '/etc/kgbsorta.conf.d/shares.ini',
            os.path.expanduser('~/.config/kgbsorta/shares.ini'),
        ])

    @property
    def shares(self):
        """Obtain list of all existing shares defined in the configuration"""
        return [self.config.get(sec, 'path') for sec in self.config.sections()]

    def get_share(self, path):
        """Transform path string into instance of Share

        :param path: str    - absolute path of share
        :return: obj        - instance of Share
        """
        if not os.path.exists(path):
            raise IOError("File or directory not found: {}".format(path))

        if not isinstance(path, str):
            raise TypeError("Expecting type str: {} -> {}".format(path, type(path)))

        for share_path in self.shares:
            if path.startswith(share_path):
                return Share(share_path)

    def get_path(self, path):
        """Transform path string into instance of ChildNode

        :param path: str    - absolute path of a location in the filesystem
        :return: obj        - instance if ChildNode
        """
        share = self.get_share(path)

        if not share:
            raise IOError("Not inside a share: {}".format(path))

        child = ChildNode(share.rel_path(path), share)
        return child

    def get(self, path):
        """Wrapper for get_share() and get_path()

        :param path: str    - absolute path of a location in the filesystem
        :return: tuple      - (<instance of Share>, <instance of ChildNode>)
        """
        path = self.get_path(path)
        return path.share, path

    def lock(self, *files):
        """Lock any given set of files

        :param files: tuple     - collection of files in the filesystem to lock
        """
        for given_file in files:
            abspath = os.path.abspath(os.path.realpath(given_file))

            parent_node = self.get_path(abspath)

            candidates = []
            if parent_node.isdir:
                candidates = parent_node.subs
            elif parent_node.isfile:
                candidates = [parent_node]
            else:
                raise NotImplementedError

            for this_path in filter(lambda x: x.isfile, candidates):
                # ensure link
                node = self.get_path(this_path.abspath)
                node.share.store.ensure_link(node.rel_path, node)

    def unlock(self, *files):
        """Unlock any given set of files

        :param files: tuple     - collection of files in the filesystem to unlock
        """
        for given_file in files:
            abspath = os.path.abspath(os.path.realpath(given_file))

            parent_node = self.get_path(abspath)

            candidates = []
            if parent_node.isdir:
                candidates = parent_node.subs
            elif parent_node.isfile:
                candidates = [parent_node]
            else:
                raise NotImplementedError

            for this_path in filter(lambda x: x.isfile, candidates):
                # ensure unlink
                node = self.get_path(this_path.abspath)
                node.share.store.ensure_unlink(node.rel_path, node)

    def cleanup(self, share_path, days=DEFAULT_DAYS):
        """Cleanup a given share

        :param share_path: str  - absolute path of share
        """
        share = self.get_share(share_path)
        store = share.store

        to_be_deleted = os.path.join(share.path, 'to_be_deleted_soon.txt')
        tbd_file = open(to_be_deleted, 'w')
        tbd_file.write('all files listed here will be deleted within the next 24h!\n')

        # iterate over all file-nodes in store and ensure hardlinks
        # in share for each of them.
        for node in store.subs:
            node.share.share.ensure_link(node.rel_path, node)

        # iterate over all file-nodes in share and delete all of them
        # if they are not hard-linked in store or older than cleanup
        # timeout.
        for node in share.subs:
            if node.share.store.check_link(node.rel_path, node):
                continue
            if node.older_than(days):
                node.remove()
            if node.older_than(days - 1):
                tbd_file.write(node.relpath + '\n')

        tbd_file.close()


if __name__ == '__main__':
    try:
        args = docopt(__doc__, version=__version__)
        sorta = KgbSorta()
        if args['lock']:
            sorta.lock(*args['FILE'])
        elif args['unlock']:
            sorta.unlock(*args['FILE'])

        elif args['cleanup']:
            sorta.cleanup(args['SHARE'])

        else:
            print __doc__
            raise SystemExit(0)
    except Exception as e:
        print e.message

