import os
import re
from functools import wraps

import eyed3
import click
from tabulate import tabulate

eyed3.log.setLevel("ERROR")

AUDIO_FILE_PATTERN = re.compile(r'.+\.mp3$')
ID3_TAGS = ['track_num', 'title', 'artist', 'album']
TABLE_HEADERS = ['File name', 'Track number', 'Title', 'Artist', 'Album']


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

    for path, dirs, files in os.walk(input_path):
        matched_files = [file_ for file_ in files if AUDIO_FILE_PATTERN.match(file_)]
        if not matched_files:
            continue

        table = []
        for file_ in matched_files:
            audiofile = eyed3.load(os.path.join(path, file_))
            row = [file_] + [getattr(audiofile.tag, tag) for tag in ID3_TAGS]
        table.append(row)

        click.echo(path)
        click.echo(tabulate(table, headers=TABLE_HEADERS))
        click.echo('\n')



@cli.command()
@common_arguments
@click.option('--file-pattern', '-p', callback=validate_regex_list, multiple=True,
              help='Regex expression for file path. Named groups are used as ID3 tags.' +
              'Many patterns can be defined, first matched is used.\n\n' +
              'Available tags: title, artist, album, track_num. \n\n'
              'E.g. -p "(?P<album>[^/]+)/(?P<track_num>[0-9]+)?(?P<artist>[^/]+) - (?P<title>[^(]+)\."')

@click.option('--clear', '-c', is_flag=True,
              help='If regex pattern doesn\'t define tag clear it anyway.')
@click.option('--asciify', '-a', is_flag=True,
              help='Converts non ascii characters to corresponding ones in ascii.')
@click.option('--no-confirmation', is_flag=True,
              help='Will execute changes automatically with prompting for confirmation.')
def id3(**kwargs):
    input_path = kwargs['input']
    asciify = kwargs['asciify']
    no_confirmation = kwargs['no_confirmation']
    file_patterns = kwargs['file_pattern'] or []
    clear = kwargs['clear']

    changes = [
        # (dir_path, table_rows)
    ]

    for path, dirs, files in os.walk(input_path):
        matched_files = (file_ for file_ in files if AUDIO_FILE_PATTERN.match(file_))
        path_changes_table = []

        for file_name in matched_files:
            file_path = os.path.join(path, file_name)

            for file_pattern in file_patterns:
                match = file_pattern.search(file_path)
                if not match:
                    continue

                groups = {key.lower(): value for key, value in match.groupdict().items()}
                change_record = [file_name] + [(groups.get(tag) or '').strip() for tag in ID3_TAGS]
                path_changes_table.append(change_record)

            if asciify:
                # TODO
                pass

        if path_changes_table:
            changes.append((path, path_changes_table))

    click.echo('Changes to apply')

    for (path, table) in changes:
        click.echo(path)
        click.echo(tabulate(table, headers=TABLE_HEADERS))
        click.echo('\n')

    if not no_confirmation:
        click.echo('Do you want to apply above changes?')

    # applying changes


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
