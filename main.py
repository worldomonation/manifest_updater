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
WPT_PREFS = 'prefs:'
WPT_MANIFEST_SUBCATEGORIES = [r'expected:', r'disabled:', r'fuzzy:']


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
    matches = [user_expression.search(line) for line in manifest_contents]

    # filter out lines that match the user-supplied regex
    updated_manifest_contents = [line for line, match in zip(manifest_contents, matches) if match is None]

    # remove dangling statements such as expected, disabled
    updated_manifest_contents = remove_dangling_statements(updated_manifest_contents)

    updated_manifest_contents = check_one_newline_at_end(updated_manifest_contents)

    if not check_if_empty_manifest(updated_manifest_contents):
        with open(os.path.join(root, file_name), 'w+') as manifest_file:
            for line in updated_manifest_contents:
                manifest_file.write(line)
    else:
        os.remove(os.path.join(root, file_name))


def remove_dangling_statements(manifest):
    updated_manifest = []

    def line_is_wpt_substatement(line):
        wpt_subcategory_expressions = [re.compile(
            pattern + r"\n(\s)?") for pattern in WPT_MANIFEST_SUBCATEGORIES]
        return any([expression.search(line) for expression in wpt_subcategory_expressions])

    def line_is_if_statement(line):
        return bool(re.search(WPT_IF, line))

    def line_is_test_statement(line):
        return line.strip().startswith('[') and line.strip().endswith(']')

    previous_line = None
    for line in manifest:
        if previous_line is not None:
            if line.strip() == '' and line_is_wpt_substatement(previous_line):
                pass

            if line_is_wpt_substatement(previous_line) and not (line_is_test_statement(line) or line_is_if_statement(line)):
                updated_manifest.pop(-1)

        updated_manifest.append(line)
        previous_line = line

    return updated_manifest


def check_if_empty_manifest(manifest):
    no_statements = all([
        re.search(WPT_IF, line.strip()) is None for line in manifest])
    no_prefs = all([
        re.search(WPT_PREFS, line.strip()) is None for line in manifest])
    no_catchall = all([
        re.search(pattern + r'\s[A-Z]{3,}', line) for pattern in WPT_MANIFEST_SUBCATEGORIES for line in manifest
    ])
    if no_statements and no_prefs and no_catchall:
        return True
    return False


def check_one_newline_at_end(manifest):
    last_line = manifest[-1]
    second_last_line = manifest[-2]

    if last_line == '\n' and second_last_line == '\n':
        manifest.pop(-1)
    elif last_line == '\n' and second_last_line != '\n':
        pass
    else:
        manifest.append('\n')
    return manifest


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
