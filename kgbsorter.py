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

Usage:
    kgbsorter.py lock FILE...
    kgbsorter.py unlock FILE...
    kgbsorter.py cleanup FILE... [-d DAYS | -m MINUTES]

Options:
    -h --help               show this
"""
__author = ['Brian Wiborg <baccenfutter@c-base.org>']
__version__ = '0.1.0-alpha'
__date__ = '2014-06-15'

import os
import re
from docopt import docopt
from datetime import datetime, timedelta
from fs_hopper import Directory

DEFAULT_CONF = '/etc/samba/smb.conf'
DEFAULT_DAYS = 14
DEFAULT_MINS = 0


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
            print("Target already locked: %s" % abs_path_target)
            return
        directory = os.path.split(abs_path_hardlink)[0]
        if not os.path.exists(directory):
            os.makedirs(directory)
        print("Locking: %s" % abs_path_target)
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
            print("Target not locked: %s" % abs_path_target)
            return
        print("Unlocking: %s" % abs_path_target)
        os.remove(abs_path_hardlink)

    def recover_file(self, rel_path):
        abs_path_target = os.path.join(self.name, rel_path)
        abs_path_hardlink = os.path.join(self.get_hardlink_basedir().name, rel_path)
        # if the path exists, we need to check if it is really a hardlink to
        # this file and otherwise be rude
        if os.path.exists(abs_path_target):
            if os.stat(abs_path_target).st_ino == os.stat(abs_path_hardlink).st_ino:
                return
            else:
                print("Deleting rogue target: %s" % abs_path_target),
                if os.path.isfile(abs_path_target):
                    os.remove(abs_path_target)
                elif os.path.isdir(abs_path_target):
                    import shutil
                    shutil.rmtree(abs_path_target)

        print("Recovering file: %s" % abs_path_target)
        os.link(abs_path_hardlink, abs_path_target)

    def cleanup_share(self, days=DEFAULT_DAYS, minutes=DEFAULT_MINS):
        """cleanup this share from all unsorted files

        :param: int     - max age of an unsorted file in days
        :param: int     - max age of an unsorted file in minutes
        """
        # ensure all locked files are in place
        for root, directory, files in os.walk(self.get_hardlink_basedir().name):
            for file in files:
                # join root and file, then cut of of the hardlink basedir for
                # the recover_file() function
                rel_path = os.path.join(root, file)[len(self.name) + 2:]
                self.recover_file(rel_path)

            # remove all empty directories
            if not files:
                tomb_path = os.path.join(root, directory)
                print("Removing empty: %s" % tomb_path)
                os.rmdir(tomb_path)


        # remove all unlocked files from share, older than sum of days + minutes
        for root, directory, files in os.walk(self.name):
            for file in files:
                rel_path = os.path.join(root, file)
                c_time = os.path.getctime(rel_path)
                if datetime.fromtimestamp(c_time) < datetime.now() - timedelta(days=days, minutes=minutes):
                    if os.stat(rel_path).st_nlink > 1:
                        print("Removing: %s" % rel_path)
                        os.remove(rel_path)

            # remove all emtpy directories
            if not files:
                tomb_path = os.path.join(root, directory)
                print("Removing empty: %s" % tomb_path)
                os.rmdir(tomb_path)

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


if __name__ == '__main__':
    args = docopt(__doc__, version=__version__)
    abs_paths = [os.path.abspath(os.path.realpath(f)) for f in args['FILE']]
    if args['lock']:
        Share.locker(abs_paths)
    elif args['unlock']:
        Share.unlocker(abs_paths)
    elif args['cleanup']:
        days = args['DAYS'] or DEFAULT_DAYS
        minutes = args['MINUTES'] or DEFAULT_MINS

