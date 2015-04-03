kgbsorta - A tool for managing hardlinks on kgb.

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
the shell parameters -d DAYS and -m MINUTES or default to 7 days.

Usage:
    kgbsorter
    kgbsorter lock FILE...
    kgbsorter unlock FILE...
    kgbsorter cleanup SHARE [-d DAYS]

Options:
    -h --help               show this
    