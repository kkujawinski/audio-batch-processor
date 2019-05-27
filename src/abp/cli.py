# -*- coding: utf-8 -*-

# cd /mnt/c/Users/kamil/Workspace/audio-batch-processor
# ./env/bin/abp ui /mnt/c/Users/kamil/Music

import os
import re
import six

import click
from tabletext import to_text

from abp.core import (get_folder_dirs, get_folder_matched_files, get_id3_values, get_id3_changes, get_id3_values_dict,
                      get_renames, apply_renames)


TABLE_HEADERS = ['Track number', 'Title', 'Artist', 'Album']

def validate_regex_list(ctx, param, values):
    output = []
    for value in values:
        try:
            output.append(re.compile(value))
        except Exception as e:
            raise click.BadParameter('"%s" is not proper regex pattern - %s' % (value, str(e)))
    return output

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


@click.group()
def cli():
    pass


@cli.command(name='list')
@click.argument('input', default='.', type=click.Path(exists=True, dir_okay=True, readable=True))
def list_(**kwargs):
    input_path = kwargs['input']
    values = []
    for row in id3_list(input_path):
        dir_path = row['dir']
        path_values = []
        for file_ in row['files']:
            path_values.append((file_['file'], file_['id3']))
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


@cli.command()
@click.argument('input', default='.', type=click.Path(exists=True, dir_okay=True, readable=True))
def ui(**kwargs):
    from abp import ui
    app = ui.create_app(kwargs['input'])
    app.run(debug=True)


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


cli.add_command(list_)
cli.add_command(id3)
cli.add_command(rename)
