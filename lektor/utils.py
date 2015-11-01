import os
import sys
import re
import json
import codecs
import uuid
import subprocess
import tempfile
import posixpath
import traceback
import unicodedata
import multiprocessing
from Queue import Queue
from threading import Thread
from datetime import datetime
from contextlib import contextmanager

from urlparse import urlparse

from werkzeug.http import http_date
from werkzeug import urls
from werkzeug.posixemulation import rename
from jinja2 import is_undefined
from markupsafe import Markup


is_windows = (os.name == 'nt')

_slash_escape = '\\/' not in json.dumps('/')

_slashes_re = re.compile(r'/+')
_last_num_re = re.compile(r'^(.*)(\d+)(.*?)$')
_list_marker = object()
_value_marker = object()

# Figure out our fs encoding, if it's ascii we upgrade to utf-8
fs_enc = sys.getfilesystemencoding()
try:
    if codecs.lookup(fs_enc).name == 'ascii':
        fs_enc = 'utf-8'
except LookupError:
    pass


def cleanup_path(path):
    return '/' + _slashes_re.sub('/', path.strip('/'))


def to_os_path(path):
    return path.strip('/').replace('/', os.path.sep).decode(fs_enc, 'replace')


def is_path(path):
    return os.path.sep in path or (os.path.altsep and os.path.altsep in path)


def magic_split_ext(filename, ext_check=True):
    """Splits a filename into base and extension.  If ext check is enabled
    (which is the default) then it verifies the extension is at least
    reasonable.
    """
    def bad_ext(ext):
        if not ext_check:
            return False
        if not ext or ext.split() != [ext] or ext.strip():
            return True
        return False

    parts = filename.rsplit('.', 2)
    if len(parts) == 2 and not parts[0]:
        return parts[0], ''
    if len(parts) == 3 and len(parts[1]) < 5:
        ext = '.'.join(parts[1:])
        if not bad_ext(ext):
            return parts[0], ext
    ext = parts[-1]
    if bad_ext(ext):
        return filename, ''
    basename = '.'.join(parts[:-1])
    return basename, ext


def iter_dotted_path_prefixes(dotted_path):
    pieces = dotted_path.split('.')
    for x in xrange(1, len(pieces)):
        yield '.'.join(pieces[:x]), '.'.join(pieces[x:])


def resolve_dotted_value(obj, dotted_path):
    node = obj
    for key in dotted_path.split('.'):
        if isinstance(node, dict):
            new_node = node.get(key)
            if new_node is None and key.isdigit():
                new_node = node.get(int(key))
        elif isinstance(node, list):
            try:
                new_node = node[int(key)]
            except (ValueError, TypeError, IndexError):
                new_node = None
        else:
            new_node = None
        node = new_node
        if node is None:
            break
    return node


def decode_flat_data(itemiter):
    def _split_key(name):
        result = name.split('.')
        for idx, part in enumerate(result):
            if part.isdigit():
                result[idx] = int(part)
        return result

    def _enter_container(container, key):
        if key not in container:
            return container.setdefault(key, {})
        return container[key]

    def _convert(container):
        if _value_marker in container:
            force_list = False
            values = container.pop(_value_marker)
            if container.pop(_list_marker, False):
                force_list = True
                values.extend(_convert(x[1]) for x in
                              sorted(container.items()))
            if not force_list and len(values) == 1:
                values = values[0]

            # We had nothing remaining, return
            if not container:
                return values

            # Values remain.  Assume that the user left out the .value
            # part and recurse.  This exists in order to allow this
            # usage: foo.__type=integer&foo=42
            result = _convert(container)
            result.setdefault('value', values)
            return result
        elif container.pop(_list_marker, False):
            return [_convert(x[1]) for x in sorted(container.items())]
        return dict((k, _convert(v)) for k, v in container.iteritems())

    result = {}

    for key, value in itemiter:
        parts = _split_key(key)
        if not parts:
            continue
        container = result
        for part in parts:
            last_container = container
            container = _enter_container(container, part)
            last_container[_list_marker] = isinstance(part, (int, long))
        container[_value_marker] = [value]

    return _convert(result)


def merge(a, b):
    """Merges two values together."""
    if b is None and a is not None:
        return a
    if a is None:
        return b
    if isinstance(a, list) and isinstance(b, list):
        for idx, (item_1, item_2) in enumerate(zip(a, b)):
            a[idx] = merge(item_1, item_2)
    if isinstance(a, dict) and isinstance(b, dict):
        for key, value in b.iteritems():
            a[key] = merge(a.get(key), value)
        return a
    return a


def secure_filename(filename, fallback_name='file'):
    base = filename.replace('/', ' ').replace('\\', ' ')
    basename, ext = magic_split_ext(base)
    rv = slugify(basename).lstrip('.')
    if not rv:
        rv = fallback_name
    if ext:
        return rv + '.' + ext
    return rv


def increment_filename(filename):
    directory, filename = os.path.split(filename)
    basename, ext = magic_split_ext(filename, ext_check=False)

    match = _last_num_re.match(basename)
    if match is not None:
        rv = match.group(1) + str(int(match.group(2)) + 1) + match.group(3)
    else:
        rv = basename + '2'

    if ext:
        rv += '.' + ext
    if directory:
        return os.path.join(directory, rv)
    return rv


def resolve_path(execute_file, cwd):
    execute_file = to_os_path(execute_file)
    if os.name != 'nt':
        return execute_file

    extensions = ['']
    path_var = os.environ.get('PATH', '').split(os.pathsep)
    path_ext_var = os.environ.get('PATHEXT', '').split(';')

    ext_existing = os.path.splitext(execute_file)[1] in path_ext_var
    if not ext_existing:
        extensions = path_ext_var

    try:
        for ext in extensions:
            execute = os.path.join(cwd, execute_file + ext)
            if os.access(execute, os.X_OK):
                return execute
            for path in path_var:
                execute = os.path.join(path, execute_file + ext)
                if os.access(execute, os.X_OK):
                    return execute
    except OSError:
        pass

    return None


class JSONEncoder(json.JSONEncoder):

    def default(self, o):
        if is_undefined(o):
            return None
        if isinstance(o, datetime):
            return http_date(o)
        if isinstance(o, uuid.UUID):
            return str(o)
        if hasattr(o, '__html__'):
            return unicode(o.__html__())
        return json.JSONEncoder.default(self, o)


def htmlsafe_json_dump(obj, **kwargs):
    kwargs.setdefault('cls', JSONEncoder)
    rv = json.dumps(obj, **kwargs) \
        .replace(u'<', u'\\u003c') \
        .replace(u'>', u'\\u003e') \
        .replace(u'&', u'\\u0026') \
        .replace(u"'", u'\\u0027')
    if not _slash_escape:
        rv = rv.replace('\\/', '/')
    return rv


def tojson_filter(obj, **kwargs):
    return Markup(htmlsafe_json_dump(obj, **kwargs))


def safe_call(func, args=None, kwargs=None):
    try:
        return func(*(args or ()), **(kwargs or {}))
    except Exception:
        # XXX: logging
        traceback.print_exc()


class Worker(Thread):

    def __init__(self, tasks):
        Thread.__init__(self)
        self.tasks = tasks
        self.daemon = True
        self.start()

    def run(self):
        while 1:
            func, args, kwargs = self.tasks.get()
            safe_call(func, args, kwargs)
            self.tasks.task_done()


class WorkerPool(object):

    def __init__(self, num_threads=None):
        if num_threads is None:
            num_threads = multiprocessing.cpu_count()
        self.tasks = Queue(num_threads)
        for _ in range(num_threads):
            Worker(self.tasks)

    def add_task(self, func, *args, **kargs):
        self.tasks.put((func, args, kargs))

    def wait_for_completion(self):
        self.tasks.join()


def slugify(value):
    # XXX: not good enough
    return u'-'.join(value.strip().encode(
        'ascii', 'ignore').strip().split()).lower()


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


def sort_normalize_string(s):
    return unicodedata.normalize('NFD', unicode(s).lower().strip())


def get_dependent_url(url_path, suffix, ext=None):
    url_directory, url_filename = posixpath.split(url_path)
    url_base, url_ext = posixpath.splitext(url_filename)
    if ext is None:
        ext = url_ext
    return posixpath.join(url_directory, url_base + u'@' + suffix + ext)


@contextmanager
def atomic_open(filename, mode='r'):
    if 'r' not in mode:
        fd, tmp_filename = tempfile.mkstemp(
            dir=os.path.dirname(filename), prefix='.__atomic-write')
        os.chmod(tmp_filename, 0644)
        f = os.fdopen(fd, mode)
    else:
        f = open(filename, mode)
        tmp_filename = None
    try:
        yield f
    except:
        f.close()
        exc_type, exc_value, tb = sys.exc_info()
        if tmp_filename is not None:
            try:
                os.remove(tmp_filename)
            except OSError:
                pass
        raise exc_type, exc_value, tb
    else:
        f.close()
        if tmp_filename is not None:
            rename(tmp_filename, filename)


def portable_popen(cmd, *args, **kwargs):
    if 'cwd' in kwargs:
        cmd[0] = resolve_path(cmd[0], kwargs['cwd'])
    else:
        cmd[0] = resolve_path(cmd[0], os.getcwd())

    if isinstance(cmd[0], unicode):
        cmd[0] = cmd[0].encode(sys.getfilesystemencoding())

    return subprocess.Popen(cmd, *args, **kwargs)


def is_valid_id(value):
    if value == '':
        return True
    return (
        '/' not in value and
        value.strip() == value and
        value.split() == [value] and
        not value.startswith('.')
    )


def secure_url(url):
    url = urls.url_parse(url)
    if url.password is not None:
        url = url.replace(netloc='%s@%s' % (
            url.username,
            url.netloc.split('@')[-1],
        ))
    return url.to_url()


def bool_from_string(val, default=None):
    if val in (True, 1, 'true', 'yes', '1'):
        return True
    elif val in (False, 0, 'false', 'no', '0'):
        return False
    return None
