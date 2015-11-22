# -*- coding: utf-8 -*-
import os
import re
from unicodedata import normalize
from functools import wraps

import click
import eyed3
from tabletext import to_text

eyed3.log.setLevel("ERROR")

AUDIO_FILE_PATTERN = re.compile(r'.+\.mp3$')
ID3_TAGS = ['track_num', 'title', 'artist', 'album']
TABLE_HEADERS = ['Track number', 'Title', 'Artist', 'Album']

ID3_TAGS_DESERIALIZER = {
    'track_num': lambda id3_track_num: unicode(id3_track_num[0] or '')
}

ID3_TAGS_SERIALIZER = {
    'track_num': lambda id3_track_num: (int(id3_track_num), None)
}


default_deserialize = lambda x: unicode(x or '')
def id3_deserialize(tag, value):
    method = ID3_TAGS_DESERIALIZER.get(tag, default_deserialize)
    return normalize('NFC', method(value))


default_serialize = lambda x: x
def id3_serialize(tag, value):
    method = ID3_TAGS_SERIALIZER.get(tag, default_serialize)
    return method(value)


def get_id3_values(file_path):
    audiofile = eyed3.load(file_path)
    return [id3_deserialize(tag, getattr(audiofile.tag, tag)) for tag in ID3_TAGS]


def save_id3_values(file_path, values, empty_override=False):
    audiofile = eyed3.load(file_path)
    for tag, value in zip(ID3_TAGS, values):
        if value or empty_override:
            setattr(audiofile.tag, tag, id3_serialize(tag, value))
    audiofile.tag.save()


def tabulate_ignored_files(table):
    """
    Input: [dir_path, [file, reason]]
    """
    rows = [
        [dir_path, file_, reason] if i == 0 else ['', file_, reason]
        for dir_path, files in table
        for i, (file_, reason) in enumerate(files)
    ]
    return to_text([['Directory path', 'File name', 'Reason']] + rows, header=True)


def _tabulate_values(table):
    """
    Lot of magic to fake colspan

    Input: [dir_path, [(file_name, values[]])]]
    """
    output = []
    max_widths = [len(cell) + 2 for cell in TABLE_HEADERS]

    for path, file_row in table:
        for file_name, rows in file_row:
            for row in rows:
                for i, cell in enumerate(row):
                    max_cell_len = max(len(line) for line in cell.split('\n'))
                    max_widths[i] = max(max_widths[i], max_cell_len)

    total_line_width = sum(max_widths) + 2 * len(max_widths) + 1
    justed_header = [cell.ljust(max_widths[i]) for i, cell in enumerate(TABLE_HEADERS)]

    for path, file_row in table:
        output.append('')
        output.append(path.center(total_line_width))
        output.append(to_text([justed_header], corners=u'╒╤╕╞╪╡╞╧╡', hor=u'═'))

        last_row_index = len(file_row) - 1
        for j, (file_name, rows) in enumerate(file_row):
            output.append(u'│ %s │' % file_name.ljust(total_line_width))
            justed_rows = [
                [cell.ljust(max_widths[i]) for i, cell in enumerate(row)]
                for row in rows
            ]
            corners = u'├┬┤├┼┤└┴┘' if j == last_row_index else u'├┬┤├┼┤├┴┤'
            output.append(to_text(justed_rows, corners=corners))

    return '\n'.join(output)

def tabulate_values(table):
    new_table = [(
        dir_path,
        [
            (file_name, [values])
            for file_name, values in rows
        ]
    ) for dir_path, rows in table]

    _tabulate_values(table)

def tabulate_changes(table):
    def annotate_previous(values):
        return ['[%s]' % cell for cell in values]

    new_table = [(
        dir_path,
        [
            (file_name, [new_values, annotate_previous(old_values)])
            for file_name, new_values, old_values in rows
        ]
    ) for dir_path, rows in table]

    return _tabulate_values(new_table)


def get_matched_files(input_path):
    for path, dirs, files in os.walk(input_path):
        path = normalize('NFC', path)
        matched_files = (normalize('NFC', file_) for file_ in files if AUDIO_FILE_PATTERN.match(file_))
        yield (path, matched_files)


def validate_input_path(ctx, param, value):
    real_path = os.path.realpath(value)
    if not os.path.isdir(real_path):
        raise click.BadParameter('Input path needs to point the directory.')
    return real_path


def validate_output_path(ctx, param, value):
    if not value:
        return None
    real_path = os.path.realpath(value)
    if not (os.path.isdir(real_path) and listdir(real_path) == []):
        raise click.BadParameter('Output path nees to point empty directory.')
    return real_path


def validate_regex_list(ctx, param, values):
    output = []
    for value in values:
        try:
            output.append(re.compile(value))
        except Exception as e:
            raise click.BadParameter('"%s" is not proper regex pattern - %s' % (value, str(e)))
    return output

def common_arguments(fn):
    @click.option('--input', '-i', callback=validate_input_path, default='.',
                  help='Input path to parent directory with mp3 files.')
    @wraps(fn)
    def _fn(*args, **kwargs):
        return fn(*args, **kwargs)
    return _fn


@click.group()
def cli():
    pass

@cli.command(name='list')
@common_arguments
def list_(**kwargs):
    input_path = kwargs['input']
    values = []

    for dir_path, matched_files in get_matched_files(input_path):
        path_values = []

        for file_ in matched_files:
            id3_values = get_id3_values(os.path.join(dir_path, file_))
            path_values.append((file_, id3_values))

        if path_values:
            values.append((dir_path, path_values))

    click.echo(tabulate_values(values))
    click.echo('\n')



@cli.command()
@common_arguments
@click.option('--file-pattern', '-p', callback=validate_regex_list, multiple=True,
              help='Regex expression for file path. Named groups are used as ID3 tags.' +
              'Many patterns can be defined, first matched is used.\n\n' +
              'Available tags: title, artist, album, track_num. \n\n'
              'E.g. -p "(?P<album>[^/]+)/(?P<track_num>[0-9]+)?(?P<artist>[^/]+) - (?P<title>[^(]+)\."')
@click.option('--empty-override', '-o', is_flag=True,
              help='If regex pattern doesn\'t define tag clear it anyway.')
@click.option('--asciify', '-a', is_flag=True,
              help='Converts non ascii characters to corresponding ones in ascii.')
@click.option('--confirm-each-directory', '-d', is_flag=True,
              help='Each directory changes confirmation.')
@click.option('--confirm-all', '-a', is_flag=True,
              help='All changes confirmation.')
@click.option('--no-confirmation', '-f', is_flag=True,
              help='No confirmation needed')
def id3(**kwargs):
    input_path = kwargs['input']
    asciify = kwargs['asciify']
    file_patterns = kwargs['file_pattern'] or []
    empty_override = kwargs['empty_override']

    no_confirmation = kwargs['no_confirmation']
    confirm_all = kwargs['confirm_all']
    confirm_each_directory = kwargs['confirm_each_directory']

    all_changes, ignored_files = get_id3_changes(
        input_path,
        empty_override=empty_override, file_patterns=file_patterns, asciify=asciify
    )

    if ignored_files:
        click.echo('\n%s\n%s\n' % ('IGNORED FILES', tabulate_ignored_files(ignored_files)))

    approved_changes = get_approved_changes(
        all_changes,
        confirm_each_directory=confirm_each_directory,
        confirm_all=confirm_all,
        no_confirmation=no_confirmation
    )

    apply_changes(approved_changes)


def get_id3_changes(input_path, empty_override, file_patterns, asciify):
    if empty_override:
        def record_equals(values, changes):
            return values == changes
    else:
        def record_equals(values, changes):
            for i, x in enumerate(changes):
                if x and x != values[i]:
                    return False
            return True

    all_changes = []  # (dir_path, [(file_name, new_values[], old_values[])])
    ignored_files = [] # (dir_path, [(file_name, reason)])

    for dir_path, matched_files in get_matched_files(input_path):
        path_changes = []
        path_ingored_files = []

        for file_name in matched_files:
            file_path = os.path.join(dir_path, file_name)
            values = get_id3_values(file_path)
            new_values = values

            for file_pattern in file_patterns:
                match = file_pattern.search(file_path)
                if not match:
                    continue

                groups = {key.lower(): value for key, value in match.groupdict().items()}
                new_values = [(groups.get(tag) or '').strip() for tag in ID3_TAGS]
                break

            if asciify:
                # TODO
                pass

            if record_equals(values, new_values):
                if file_patterns and values is new_values:
                    reason = 'Not matched'
                else:
                    reason = 'No changes'
                path_ingored_files.append((file_name, reason))
            else:
                path_changes.append((file_name, new_values, values))

        if path_ingored_files:
            ignored_files.append((dir_path, path_ingored_files))
        if path_changes:
            all_changes.append((dir_path, path_changes))

    return all_changes, ignored_files


class SkipRestException(Exception):
    pass


def get_approved_changes(changes, confirm_each_directory, confirm_all, no_confirmation):
    def changes_confirmation(text):
        confirm = None
        while confirm not in ('y', 'n', 's'):
            click.echo('\n%s [y]es / [n]o / [s]kip all' % text)
            confirm = click.getchar(echo=True).lower()
        if 's' == confirm:
            raise SkipRestException()
        return 'y' == confirm

    click.echo('\nCHANGES')
    approved_changes = []

    try:
        if no_confirmation:
            click.echo(tabulate_changes(changes))
            approved_changes.extend(changes)
        elif confirm_all:
            click.echo(tabulate_changes(changes))
            if changes_confirmation(text='Apply those changes?'):
                approved_changes.extend(changes)
        elif confirm_each_directory:
            for dir_path, rows in changes:
                changes_record = [(dir_path, rows)]
                click.echo(tabulate_changes(changes_record))
                if changes_confirmation(text='Apply those changes?'):
                    approved_changes.append(changes_record)
        else:
            for dir_path, rows in changes:
                for file_name, new_values, old_values in rows:
                    changes_record = [(dir_path, [(file_name, new_values, old_values)])]
                    click.echo(tabulate_changes(changes_record))
                    if changes_confirmation(text='Apply this change?'):
                        approved_changes.extend(changes_record)
    except SkipRestException:
        pass

    return approved_changes


def apply_changes(changes):
    for dir_path, rows in changes:
        for file_name, new_values, old_values in rows:
            save_id3_values(os.path.join(dir_path, file_name), new_values)


@cli.command()
@common_arguments
@click.option('--output', '-o', callback=validate_output_path, default=None,
              help='Output path. Not given means changes will be processed in the same directory.')
def rename():
    # Warning, prompt for using in same directory
    click.echo('Rename files according to patterns')


cli.add_command(list_)
cli.add_command(id3)
cli.add_command(rename)
