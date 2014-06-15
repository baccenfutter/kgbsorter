"""kgbsorter

A tool for managing hardlinks on kgb.

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

Usage: kgbsorter.py [lock | unlock | cleanup [-d DAYS]] FILE...

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
from docopt import docopt
from fs_hopper import File, Directory

DEFAULT_CONF = '/etc/samba/smb.conf'
DEFAULT_DAYS = 14


class Share(Directory):
    @classmethod
    def get_shares(cls, use_smb_conf=''):
        config_file = use_smb_conf or DEFAULT_CONF
        haystack = open(config_file).readlines()
        needle = re.compile(r'[^#]*path.*=.*"(.*)".*')
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

    def get_hardlink_basedir(self):
        dir_name, base_name = os.path.split(self.name)
        return Directory(os.path.join(dir_name, '.' + base_name))

    def lock_file(self, rel_path):
        """Lock a file within this share as 'sorted'

        :param: rel_path    - relative path from root of share
        """
        abs_path_target = os.path.join(self.name, rel_path)
        abs_path_hardlink = os.path.join(self.get_hardlink_basedir().name, rel_path)
        if not os.path.exists(abs_path_target):
            raise IOError("File or directory not found: %s" % abs_path_target)
        if os.path.exists(abs_path_hardlink):
            print "Target already locked: %s" % abs_path_target
            return
        directory = os.path.split(abs_path_hardlink)[0]
        if not os.path.exists(directory):
            os.makedirs(directory)
        print "Locking: %s" % abs_path_target
        os.link(abs_path_target, abs_path_hardlink)

    def unlock_file(self, rel_path):
        """Unlock a file within this share from being 'sorted'

        :param: rel_path    - relative path from root of share
        """
        abs_path_target = os.path.join(self.name, rel_path)
        abs_path_hardlink = os.path.join(self.get_hardlink_basedir().name, rel_path)
        if not os.path.exists(abs_path_target):
            raise IOError("File or directory not found: %s" % abs_path_target)
        if not os.path.exists(abs_path_hardlink):
            print "Target not locked: %s" % abs_path_target
            return
        print "Unlocking: %s" % abs_path_target
        os.remove(abs_path_hardlink)

    @classmethod
    def locker(cls, targets=[]):
        """Lock a file or directory within this share as 'sorted'

        :param:     targets - list of target files
        """
        for target in targets:
            share, sub = cls.get_share_of(target) or (None, None)
            if share:
                abs_path = os.path.join(share.name, sub)
                if not os.path.exists(abs_path):
                    raise IOError("File or directory not found: %s" % abs_path)

                if os.path.isfile(abs_path):
                    share.lock_file(sub)
                elif os.path.isdir(abs_path):
                    cls.locker([d.name for d in Directory(abs_path).get_childs()])
                else:
                    raise NotImplementedError("Regular files only!")
            else:
                raise IOError("Not within a samba share: %s" % target)

    @classmethod
    def unlocker(cls, targets=[]):
        """Unlock a file within this share from being 'sorted'

        :param:     targets     - list of target files
        """
        for target in targets:
            share, sub = cls.get_share_of(target) or (None, None)
            if share:
                abs_path = os.path.join(share.name, sub)
                if not os.path.exists(abs_path):
                    raise IOError("File or directory not found: %s" % abs_path)

                if os.path.isfile(abs_path):
                    share.unlock_file(sub)
                elif os.path.isdir(abs_path):
                    cls.unlocker([d.name for d in Directory(abs_path).get_childs()])
                else:
                    raise NotImplementedError("Regular files only!")
            else:
                raise IOError("Not within a samba share: %s" % target)

    def cleanup(self, days=DEFAULT_DAYS):
        """cleanup this share now"""
        pass

if __name__ == '__main__':
    args = docopt(__doc__, version=__version__)
    print args

