#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
This module provides tools to administrate sources.
"""

from __future__ import with_statement

import os
import os.path as op
from textwrap import dedent
from urllib import urlretrieve
from zipfile import ZipFile

# Not in standard library
import yaml


class SourcesAdmin(object):
    """
    This class is used to administrate sources.
    """
    def __init__(self, sources_conf_path, sources_dir, cache_dir):

        # Path to the configuration file
        self.sources_conf_path = sources_conf_path

        with open(sources_conf_path) as fl:
            self.sources = yaml.load(fl)

        # Root folder where we find data
        self.sources_dir = sources_dir

        # Cache directory
        self.cache_dir = cache_dir


    def __contains__(self, source):
        """For *in* test.
        """
        return source in self.sources


    def __iter__(self):
        """For iteration.
        """
        return iter(self.sources)


    def get(self, source):
        """Get source information.
        """
        return self.sources[source]


    def add(self, source, config):
        """Add new source.
        """
        if source in self.sources:
            print 'Source %s already exists.' % source
        else:
            self.sources[source] = config


    def drop(self, source):
        """Drop source.
        """
        del self.sources[source]


    def update(self, source, option, option_config):
        """Update source.
        """
        if source not in self.sources:
            print 'Source %s not in sources.' % source
            return

        self.sources[source][option] = option_config


    def build_help(self):
        """Display informations on available sources.
        """
        missing = '<none>'

        def fmt_keys(l):
            """Nice key_fields formatting."""
            if l is None:
                return missing
            if isinstance(l, (list, tuple, set)):
                return '+'.join(l)
            return str(l)

        def fmt_path(p):
            """Nice path formatting."""
            if isinstance(p, str):
                return str(p)
            if 'extract' not in p:
                return p['file']
            return '%s -> %s' % (p['file'], p['extract'])

        tip = [dedent('''
        * Data sources from %s [%s]
        ''' % (self.sources_dir, op.basename(self.sources_conf_path)))]

        tip.append('-' * 80)
        tip.append('%-20s | %-25s | %s' % ('NAME', 'KEY', 'PATHS (DEFAULT + FAILOVERS)'))
        tip.append('-' * 80)

        for source in sorted(self.sources.keys()):
            config = self.sources[source]

            if config is not None:
                keys  = config.get('key_fields', missing)
                paths = config.get('paths', missing)
            else:
                keys, paths = missing, missing

            if isinstance(paths, (str, dict)):
                paths = [paths]
            tip.append('%-20s | %-25s | %s' % \
                       (source, fmt_keys(keys), '.) %s' % fmt_path(paths[0])))

            for n, path in enumerate(paths[1:], start=1):
                tip.append('%-20s | %-25s | %s' % \
                           ('-', '-', '%s) %s' % (n, fmt_path(path))))

        tip.append('-' * 80)

        return '\n'.join(tip)


    def help_permanent_add(self, options):
        """Display help on how to make a data source permanent.
        """
        conf = {
            'paths' : '<INSERT_ABSOLUTE_FILE_PATH>',
            'local' : False
        }

        for option, value in options.iteritems():
            # Source is not allowed in configuration, replaced by paths/local
            if option not in ('source', 'verbose'):
                conf[option] = value

        print
        print '* You can make this data source permanent!'
        print '* Edit %s with:' % self.sources_conf_path
        print
        print '$ cat >> %s << EOF' % self.sources_conf_path
        print '# ================ BEGIN ==============='
        print
        print yaml.dump({
            '<INSERT_ANY_NAME>' : conf
        }, indent=4, default_flow_style=None)

        print '# ================  END  ==============='
        print 'EOF'
        print
        print '* Replace the placeholders <INSERT_...> with:'
        print '$ vim %s' % self.sources_conf_path
        print


    def handle_path(self, path, verbose):
        """
        Handle file downloading/uncompressing and returns
        path to file to be opened.
        """
        if not is_remote(path):
            file_ = path['file']
        else:
            file_, success = download_lazy(path['file'], self.cache_dir, verbose)

            if not success:
                if verbose:
                    print '/!\ Failed to download "%s"...' % path['file']
                return

        if is_archive(path):
            archive = file_
            file_, success = extract_lazy(archive, path['extract'], self.cache_dir, verbose)

            if not success:
                if verbose:
                    print '/!\ Failed to extract "%s" from "%s"...' % \
                            (path['extract'], archive)
                return

        return file_


    def convert_paths_format(self, paths, local):
        """Convert all paths to the same format.
        """
        if paths is None:
            return

        if isinstance(paths, (str, dict)):
            # If paths is just *one* archive or *one* file
            paths = [paths]

        for i, path in enumerate(paths):
            # We normalize all path as a dict structure
            if isinstance(path, str):
                paths[i] = {
                    'file' : path
                }

        for i, path in enumerate(paths):
            # "local" is only used for sources from configuration
            # to have a relative path from the configuration file
            if not is_remote(path) and local is True:
                path['file'] = op.join(op.realpath(self.sources_dir), path['file'])

        return tuple(paths)




# Remote prefix detection
R_PREFIXES = set(['http://', 'https://'])
has_prefix = lambda path, prefixes: any(path.lower().startswith(p) for p in prefixes)

def is_remote(path):
    """Tells if a path is remote.
    """
    return has_prefix(path['file'], R_PREFIXES)

# Remote prefix detection
is_archive = lambda path: 'extract' in path

# Date comparisons
def is_older(a, b):
    """Test file last modifcation time.
    """
    try:
        if os.stat(a).st_mtime < os.stat(b).st_mtime:
            return True
    except OSError:
        # If this fails, we say it is not older
        pass
    return False


def download_lazy(resource, cache_dir, verbose=True):
    """
    Download a remote file only if target file is not already
    in cache directory.
    Returns boolean for success or failure, and path
    to downloaded file (may not be exactly the same as the one checked).
    """
    # If in cache directory, we use it, otherwise we download it
    filename_test = op.join(cache_dir, op.basename(resource))

    if op.isfile(filename_test):
        if verbose:
            print '/!\ Using "%s" already in cache directory for "%s"' % \
                    (filename_test, resource)
        return filename_test, True

    if verbose:
        print '/!\ Downloading "%s" in cache directory from "%s"' % \
                (filename_test, resource)
    try:
        dl_filename, _ = urlretrieve(resource, filename_test)
    except IOError:
        return None, False
    else:
        return dl_filename, True


def extract_lazy(archive, filename, cache_dir, verbose=True):
    """
    Extract a file from archive if file is not already in
    the cache directory.
    """
    # Perhaps the file was already extracted here
    # We also check the dates of modification in case
    # the extracted file obsolete
    filename_test = op.join(cache_dir, filename)

    if op.isfile(filename_test):
        if is_older(archive, filename_test):
            if verbose:
                print '/!\ Skipping extraction for "%s", already at "%s"' % \
                        (filename, filename_test)
            return filename_test, True

        if verbose:
            print '/!\ File "%s" already at "%s", but "%s" is newer, removing' % \
                    (filename, filename_test, archive)

    if verbose:
        print '/!\ Extracting "%s" from "%s" in "%s"' % \
                (filename, archive, filename_test)

    # We extract one file from the archive
    try:
        extracted = ZipFile(archive).extract(filename, op.dirname(filename_test))
    except IOError:
        return None, False
    else:
        return extracted, True




def _test():
    """When called directly, launching doctests.
    """
    import doctest

    opt =  (doctest.ELLIPSIS |
            doctest.NORMALIZE_WHITESPACE)
            #doctest.REPORT_ONLY_FIRST_FAILURE)
            #doctest.IGNORE_EXCEPTION_DETAIL)

    doctest.testmod(optionflags=opt)



if __name__ == '__main__':
    _test()
