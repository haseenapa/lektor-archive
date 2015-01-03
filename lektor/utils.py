import os
import sys
import tempfile

from urlparse import urlparse

from contextlib import contextmanager


def slugify(value):
    # XXX: not good enough
    return u'-'.join(value.strip().split()).lower()


@contextmanager
def atomic_open(filename, mode='wb'):
    fd, tmp_filename = tempfile.mkstemp(
        dir=os.path.dirname(filename), prefix='.__atomic-write')
    try:
        with os.fdopen(fd, 'wb') as f:
            yield f
    except:
        exc_info = sys.exc_info()
        try:
            os.remove(tmp_filename)
        except OSError:
            pass
        raise exc_info[0], exc_info[1], exc_info[2]

    os.rename(tmp_filename, filename)


class Url(object):

    def __init__(self, value):
        self.url = value
        self.host = urlparse(value).netloc

    def __unicode__(self):
        return self.url

    def __str__(self):
        return self.url


def is_unsafe_to_delete(path, base):
    a = os.path.abspath(path)
    b = os.path.abspath(base)
    diff = os.path.relpath(a, b)
    first = diff.split(os.path.sep)[0]
    return first in (os.path.curdir, os.path.pardir)


def prune_file_and_folder(name, base):
    if is_unsafe_to_delete(name, base):
        return False
    try:
        os.remove(name)
    except OSError:
        try:
            os.rmdir(name)
        except OSError:
            return False
    head, tail = os.path.split(name)
    if not tail:
        head, tail = os.path.split(head)
    while head and tail:
        try:
            if is_unsafe_to_delete(head, base):
                return False
            os.rmdir(head)
        except OSError:
            break
        head, tail = os.path.split(head)
    return True
