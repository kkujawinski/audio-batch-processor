# -*- coding: utf-8 -*-
import os
import re
import six
from unicodedata import normalize

import click
import eyed3
from six.moves import html_parser
from tabletext import to_text
from unidecode import unidecode

eyed3.log.setLevel("ERROR")
html = html_parser.HTMLParser()

AUDIO_FILE_PATTERN = re.compile(r'.+\.mp3$')
ID3_TAGS = ['track_num', 'title', 'artist', 'album']
TABLE_HEADERS = ['Track number', 'Title', 'Artist', 'Album']
ID3_TAGS_DESERIALIZER = {
    'track_num': lambda id3_track_num: six.text_type(id3_track_num and id3_track_num[0] or '')
}
ID3_TAGS_SERIALIZER = {
    'track_num': lambda id3_track_num: (int(id3_track_num), None)
}


def default_deserializer(x):
    return six.text_type(x or '')


def default_serializer(x):
    return x


def id3_deserialize(tag, value):
    method = ID3_TAGS_DESERIALIZER.get(tag, default_deserializer)
    return normalize('NFC', method(value))


def id3_serialize(tag, value):
    method = ID3_TAGS_SERIALIZER.get(tag, default_serializer)
    return method(value)


def get_id3_values(file_path):
    audiofile = eyed3.load(file_path)
    if audiofile.tag is None:
        audiofile.initTag()
    return [id3_deserialize(tag, getattr(audiofile.tag, tag)) for tag in ID3_TAGS]


def get_id3_values_dict(file_path):
    return dict(zip(ID3_TAGS, get_id3_values(file_path)))


def save_id3_values(file_path, values, empty_override=False, encoding='utf8'):
    audiofile = eyed3.load(file_path)
    if audiofile.tag is None:
        audiofile.initTag()
    for tag, value in zip(ID3_TAGS, values):
        if value or empty_override:
            setattr(audiofile.tag, tag, id3_serialize(tag, value))
    audiofile.tag.save(encoding=encoding)

    click.echo('Updated ID3 tags for file: %s' % file_path)


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


def _tabulate(table, headers=TABLE_HEADERS):
    """
    Lot of magic to fake colspan

    Input: [dir_path, [(file_name, values[]])]]
    """
    output = []
    max_widths = [len(cell) + 2 for cell in headers]

    for path, file_row in table:
        for file_name, rows in file_row:
            for row in rows:
                for i, cell in enumerate(row):
                    max_cell_len = max(len(line) for line in cell.split('\n'))
                    max_widths[i] = max(max_widths[i], max_cell_len)

    total_line_width = sum(max_widths) + 3 * len(max_widths) - 3
    justed_header = [cell.ljust(max_widths[i]) for i, cell in enumerate(headers)]

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


def changes_confirmation(text):
    confirm = None
    while confirm not in ('y', 'n', 's'):
        click.echo('\n%s [y]es / [n]o / [s]kip all' % text)
        confirm = click.getchar(echo=True).lower()
    if 's' == confirm:
        raise SkipRestException()
    return 'y' == confirm


def tabulate_values(table):
    new_table = [(
        dir_path,
        [
            (file_path, [row])
            for file_path, row in rows
        ]
    ) for dir_path, rows in table]
    return _tabulate(new_table)


def tabulate_changes(table):
    def annotate_previous(values):
        return ['[%s]' % cell for cell in values]

    new_table = [(
        dir_path,
        [
            (file_name, [['new'] + new_values, ['prev'] + old_values])
            for file_name, new_values, old_values in rows
        ]
    ) for dir_path, rows in table]
    return _tabulate(new_table, headers=[''] + TABLE_HEADERS)


def tabulate_renames(table):
    pass


def get_matched_files(input_path):
    for path, dirs, files in os.walk(six.text_type(input_path)):
        path = normalize('NFC', path)
        matched_files = (normalize('NFC', file_) for file_ in files if AUDIO_FILE_PATTERN.match(file_))
        yield (path, matched_files)


def validate_regex_list(ctx, param, values):
    output = []
    for value in values:
        try:
            output.append(re.compile(value))
        except Exception as e:
            raise click.BadParameter('"%s" is not proper regex pattern - %s' % (value, str(e)))
    return output


@click.group()
def cli():
    pass


@cli.command(name='list')
@click.argument('input', default='.', type=click.Path(exists=True, dir_okay=True, readable=True))
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


def get_grouped_commands(groups=[], first_group_name='Options'):
    groups = iter(groups)

    class GroupedCommand(click.Command):
        def format_options(self, ctx, formatter):
            def print_group(opts, group_name=None):
                if not opts:
                    return
                with formatter.section(group_name):
                    formatter.write_dl(opts)

            opts = []
            current_group_name = first_group_name
            next_group_name, next_group_first_item = next(groups, (None, None))

            for param in self.get_params(ctx):
                rv = param.get_help_record(ctx)
                if rv is not None:
                    if next_group_first_item and rv[0].startswith(next_group_first_item):
                        print_group(opts, current_group_name)
                        opts = []
                        current_group_name = next_group_name
                        next_group_name, next_group_first_item = next(groups, (None, None))
                    opts.append(rv)

            print_group(opts, current_group_name)

    return GroupedCommand


@cli.command(cls=get_grouped_commands([('Formatters', '-a'), ('Confirmation', '-d'), ('Other', '-o')]))
@click.argument('input', default='.', type=click.Path(exists=True, dir_okay=True, readable=True))
@click.option('--file-pattern', '-p', callback=validate_regex_list, multiple=True,
              help='Regex expression for file path. Named groups are used as ID3 tags.' +
              'Many patterns can be defined, first matched is used.\n\n' +
              'Available tags: title, artist, album, track_num. \n\n'
              'E.g. -p "(?P<album>[^/]+)/(?P<track_num>[0-9]+)?(?P<artist>[^/]+) - (?P<title>[^(]+)\."')
@click.option('--asciify', '-a', is_flag=True,
              help='Converts non ascii characters to corresponding ones in ascii.')
@click.option('--unescape', '-x', is_flag=True,
              help='Decode escaped characters.')
@click.option('--confirm-each-directory', '-d', is_flag=True,
              help='Each directory changes confirmation.')
@click.option('--confirm-all', '-a', is_flag=True,
              help='All changes confirmation.')
@click.option('--no-confirmation', '-f', is_flag=True,
              help='No confirmation needed')
@click.option('--empty-override', '-o', is_flag=True,
              help='If regex pattern doesn\'t define tag clear it anyway.')
@click.option('--encoding', '-e', default='utf8',
              help='Save ID3 tags with given encoding. Available utf8, latin1')
def id3(**kwargs):
    input_path = kwargs['input']
    asciify = kwargs['asciify']
    unescape = kwargs['unescape']
    encoding = kwargs.get('encoding', 'utf8')
    file_patterns = kwargs['file_pattern'] or []
    empty_override = kwargs['empty_override']

    no_confirmation = kwargs['no_confirmation']
    confirm_all = kwargs['confirm_all']
    confirm_each_directory = kwargs['confirm_each_directory']

    all_changes, ignored_files = get_id3_changes(
        input_path,
        empty_override=empty_override, file_patterns=file_patterns, asciify=asciify,
        unescape=unescape
    )

    if ignored_files:
        click.echo('\n%s\n%s\n' % ('IGNORED FILES', tabulate_ignored_files(ignored_files)))

    approved_changes = get_approved_changes(
        all_changes,
        confirm_each_directory=confirm_each_directory,
        confirm_all=confirm_all,
        no_confirmation=no_confirmation
    )

    click.echo('\nAPPLYING CHANGES')
    apply_changes(approved_changes, encoding=encoding)


def get_id3_changes(input_path, empty_override, file_patterns, asciify, unescape):
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
    ignored_files = []  # (dir_path, [(file_name, reason)])

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

            if unescape:
                new_values = [html.unescape(cell) for cell in new_values]

            if asciify:
                new_values = [unidecode(cell) for cell in new_values]

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


def apply_changes(changes, encoding):
    for dir_path, rows in changes:
        for file_name, new_values, old_values in rows:
            save_id3_values(os.path.join(dir_path, file_name), new_values, encoding=encoding)


@cli.command()
@click.argument('input', default='.', type=click.Path(exists=True, dir_okay=True, readable=True))
@click.option('--output', '-o', type=click.Path(dir_okay=True, readable=True),
              help='Output path. Not given means changes will be processed in the same directory.')
@click.option('--file-path-pattern', '-p', required=True,
              help='Pattern of file path. Available variables: $track_num, $title, $artist, $album.')
@click.option('--confirm-each-directory', '-d', is_flag=True,
              help='Each directory changes confirmation.')
@click.option('--confirm-all', '-a', is_flag=True,
              help='All changes confirmation.')
@click.option('--no-confirmation', '-f', is_flag=True,
              help='No confirmation needed')
def rename(**kwargs):
    input_path = kwargs['input']
    output_path = kwargs['output'] or kwargs['input']
    file_path_pattern = kwargs['file_path_pattern']

    no_confirmation = kwargs['no_confirmation']
    confirm_all = kwargs['confirm_all']
    confirm_each_directory = kwargs['confirm_each_directory']

    renames = get_renames(input_path, file_path_pattern)
    approved_renames = get_approved_renames(renames, confirm_each_directory, confirm_all, no_confirmation)
    apply_renames(approved_renames, input_path, output_path)


def get_renames(input_path, file_path_pattern):
    all_renames = []  # (dir_path, [(new_file_path, old_file_path,)])

    for dir_path, matched_files in get_matched_files(input_path):
        path_renames = []

        for file_name in matched_files:
            old_file_path = os.path.join(dir_path, file_name)
            new_file_path = file_path_pattern
            for name, value in get_id3_values_dict(old_file_path).items():
                new_file_path = new_file_path.replace('$' + name, value)

            path_renames.append((new_file_path, os.path.relpath(old_file_path, input_path)))

        if path_renames:
            all_renames.append((dir_path, path_renames))

    return all_renames


def get_approved_renames(renames, confirm_each_directory, confirm_all, no_confirmation):
    click.echo('\nRENAMES')
    approved_renames = []

    try:
        if no_confirmation:
            click.echo(tabulate_renames(renames))
            approved_renames.extend(renames)
        elif confirm_all:
            click.echo(tabulate_renames(renames))
            if changes_confirmation(text='Apply those renames?'):
                approved_renames.extend(renames)
        elif confirm_each_directory:
            for dir_path, rows in renames:
                renames_record = [(dir_path, rows)]
                click.echo(tabulate_renames(renames_record))
                if changes_confirmation(text='Apply those renames?'):
                    approved_renames.append(renames_record)
        else:
            for dir_path, rows in renames:
                for new_file_path, old_file_path in rows:
                    renames_record = [(dir_path, [(new_file_path, old_file_path)])]
                    click.echo(tabulate_renames(renames_record))
                    if changes_confirmation(text='Apply this rename?'):
                        approved_renames.extend(renames_record)
    except SkipRestException:
        pass

    return approved_renames


def mkdirnotex(filename):
    folder = os.path.dirname(filename)
    if not os.path.exists(folder):
        os.makedirs(folder)


def apply_renames(renames, input_path, output_path):
    for dir_path, rows in renames:
        for new_file_path, old_file_path in rows:
            new_full_file_path = os.path.join(output_path, new_file_path)
            old_full_file_path = os.path.join(input_path, old_file_path)

            mkdirnotex(new_full_file_path)
            os.rename(old_full_file_path, new_full_file_path)


cli.add_command(list_)
cli.add_command(id3)
cli.add_command(rename)
