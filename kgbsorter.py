"""kgbsorter

All shares are obtained from /etc/samba/smb.conf. Shares within the
samba configuration file that end with the string 'protected' are
considered to be protected from use.

For each share exported on kgb a corresponding hidden hardlink
basedir exists next to it with the same name as the share.
Considering the share /mnt/foobar, the corresponding hardlink
basedir would be /mnt/.foobar.

A file within the share is considered as 'locked' if a corresponding
hardlink exists with the exact same relative path name within the
hardlink basedir. If no hardlink to this file with the corresponding
name exists within the hardlink basedir, it is considered as
'unlocked' and will be deleted after N days, whereby N may be
configured to an arbitrary number of days greater than zero.

Usage: kgbsorter.py [lock | unlock | cleanup [-d <DAYS>]] FILE...

Options:
    -h --help       show this
    -v --verbose    more output
    -q --quiet      less output
"""
__author = ['Brian Wiborg <baccenfutter@c-base.org>']
__version__ = '0.1.0-alpha'
__date__ = '2014-06-15'

import os
import re
from fs_hopper import File, Directory

DEFAULT_CONF = '/etc/samba/smb.conf'
DEFAULT_DAYS = 14


class Share(Directory):
    @classmethod
    def get_shares(cls, use_smb_conf=''):
        config_file = use_smb_conf or DEFAULT_CONF
        haystack = open(config_file).readlines()
        needle = re.compile(r'.*path.*=.*"(.*)".*')
        fork = re.compile(r'.*#.*protected.*')
        for line in haystack:
            match = needle.match(line)
            if match:
                if not fork.match(match.group(0)):
                    yield match.group(1)

    @classmethod
    def get_share_of(cls, path):
        for share in cls.get_shares():
            if path.startswith(share):
                return (
                    Share(share),
                    path[len(share) + 1:],
                )

    def lock(self, target):
        """lock a file within this share as 'sorted'"""

    def unlock(self, target):
        """unlock a file within this share from being 'sorted'"""

    def cleanup(self, days=DEFAULT_DAYS):
        """cleanup this share now"""
        pass