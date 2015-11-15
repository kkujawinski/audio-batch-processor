import click
from functools import wraps


@click.group()
def cli():
    pass


def common_arguments(fn):
    @click.option('--input', default='.', help='Input path to parent directory with mp3 files.')
    @click.option('--output', default=None, help='Output path. Not given means changes will be processed in the same directory.')
    @wraps(fn)
    def _fn():
        return fn()
    return _fn



@cli.command()
@common_arguments
def summary():
    click.echo('Displays audio files details')


@cli.command(name='id3-edit')
@common_arguments
def id3_edit():
    click.echo('Edits id3 tags with rules')


@cli.command(name='file-rename')
@common_arguments
def file_rename():
    # Warning, prompt for using in same directory
    click.echo('Rename files according to patterns')


cli.add_command(summary)
cli.add_command(id3_edit)
cli.add_command(file_rename)
