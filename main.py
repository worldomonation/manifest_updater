#!/usr/bin/env python3

"""This module filters for and removes from the manifest files instances of
skip-if conditions specifying older version of Android that are no longer supported.
"""

import os
import re
import subprocess
import sys

from argparse import ArgumentParser
from fileinput import FileInput

MANIFEST_FILE_NAMES = [
    'mochitest.ini',
    'browser.ini',
]

BASIC_ANDROID_VERSION_REGEX = r"[(]?android_version == '17'[)]?"
ANDROID_VERSION = re.compile(BASIC_ANDROID_VERSION_REGEX)

# SKIP_IF_GRAMMAR = r"^skip-if = .*(&&|==|<|>)+.* (#\s.*)?$"
# TOKEN_GRAMMAR = r"^.*(&&|==|<|>|!=|<=|>=)\s.*$"
# GRAMMAR = re.compile(SKIP_IF_GRAMMAR)

TOKEN_OR_SEPARATOR = r"\s\|\|\s"

SKIP_IF = 'skip-if = '
WPT_IF = 'if '
WPT_MANIFEST_SUBCATEGORIES = ['expected:', 'disabled:', 'fuzzy:']


def process_manifest_line(line):
    """Parses and processes a line from the manifest.

    Arguments:
        line (str): a line from the manifest file.

    """
    line = line[len(SKIP_IF):]
    tokens = re.split(TOKEN_OR_SEPARATOR, line)
    tokens_with_matching_versions_removed = [
        token for token in tokens if not ANDROID_VERSION.match(token)]
    if tokens_with_matching_versions_removed:
        if len(tokens_with_matching_versions_removed) > 1:
            tokens = ' || '.join(tokens_with_matching_versions_removed)
        else:
            tokens = ''.join(tokens_with_matching_versions_removed)
        return ''.join([SKIP_IF, tokens])
    else:
        return None


def process_manifest(root, file_name):
    """Opens the manifest file and processes each line.

    Arguments:
        root (str): directory name, also known as pwd.
        file_name: file name on disk.
    """
    with FileInput(os.path.join(root, file_name), inplace=True, backup='.bak') as manifest_file:
        for line in manifest_file:
            if line.startswith(SKIP_IF):
                output = process_manifest_line(line.rstrip())
                if output:
                    sys.stdout.write(output + '\n')
            else:
                sys.stdout.write(line.rstrip() + '\n')


def process_web_platform_manifests(root, file_name, regex):
    with open(os.path.join(root, file_name), 'r') as manifest_file:
        manifest_contents = manifest_file.readlines()

    user_expression = re.compile(regex)
    wpt_subcategory_expressions = [re.compile(
        pattern) for pattern in WPT_MANIFEST_SUBCATEGORIES]
    matches = [user_expression.search(line) for line in manifest_contents]
    updated_manifest_contents = []
    for index, line in enumerate(manifest_contents):
        if not matches[index]:
            updated_manifest_contents.append(line)
        else:
            previous_line = updated_manifest_contents[index-1]
            wpt_subcategory_match = any([
                wpt_expression.search(previous_line) for wpt_expression in wpt_subcategory_expressions
            ])
            if wpt_subcategory_match:
                updated_manifest_contents.pop(index-1)

    if updated_manifest_contents != manifest_contents:
        empty_manifest = all([
            re.compile(WPT_IF).search(line.strip()) is None for line in updated_manifest_contents
        ])
        if empty_manifest:
            os.remove(os.path.join(root, file_name))
            return

        with open(os.path.join(root, file_name), 'w+') as manifest_file:
            for line in updated_manifest_contents:
                manifest_file.write(line)


def walk_and_discover_manifest_files(path, wpt, regex):
    """Recursively calls itself to discover all files that match the whiteslist.

    For all files that it discovers, call the manifest processor with the file directory
    and file name as arguments.

    Arguments:
        path (String): representation of path. Could be a directory or a discrete file.
        wpt (bool): boolean flag. True if user provided the --wpt argument. False otherwise.
        regex (String): the raw regex to be used to match at the manifest processing stage.
    """
    if path.endswith('.ini'):
        if wpt:
            process_web_platform_manifests(os.path.dirname(path), os.path.basename(path), regex)
        else:
            assert os.path.basename(path) in MANIFEST_FILE_NAMES
            process_manifest(os.path.dirname(path), os.path.basename(path))
    else:
        for root, sub_dirs, files in os.walk(path):
            if wpt:
                files = list(filter(lambda x: x.endswith('ini'), files))
                for file_name in files:
                    process_web_platform_manifests(root, file_name, regex)
            else:
                files = list(filter(lambda x: x in MANIFEST_FILE_NAMES, files))
                for file_name in files:
                    process_manifest(root, file_name)
            for sub_dir in sub_dirs:
                walk_and_discover_manifest_files(sub_dir, wpt, regex)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('path', help="Directory to begin recursively looking into.")
    parser.add_argument('--android_version', action='store',
                        help="Custom Android version to look for in the manifest files.")
    parser.add_argument('--wpt', default=False, action='store_true', help="web-platform tests format.")
    parser.add_argument('--regex', default=None, action='store', help="Regular expression to match.")

    args, _ = parser.parse_known_args()

    # if args.android_version:
    #     BASIC_ANDROID_VERSION_REGEX = r"android_version == '{}'".format(
    #         args.android_version)

    walk_and_discover_manifest_files(args.path, args.wpt, args.regex)
