# -*- coding: utf-8 -*-
import os

from click.testing import CliRunner
from py._path.local import LocalPath

from abp.__main__ import cli


def test_simple(tmpdir):
    target_id3_dir_raw = tmpdir / "id3"
    target_id3_dir = str(target_id3_dir_raw)
    LocalPath('tests/input').copy(target_id3_dir_raw)

    result = CliRunner().invoke(cli, ['list', target_id3_dir])
    empty_mp3_desc = u"""
╒════════════════╤═════════╤══════════╤═════════╕
│ Track number   │ Title   │ Artist   │ Album   │
╞════════════════╧═════════╧══════════╧═════════╡
│ artist name - song name.mp3                   │
├────────────────┬─────────┬──────────┬─────────┤
│                │         │          │         │
└────────────────┴─────────┴──────────┴─────────┘
"""
    assert empty_mp3_desc.strip() in result.output

    result = CliRunner().invoke(cli, [
        'id3',
        '-p', '(?P<album>[^/]+)/(?P<track_num>[0-9]+)?(?P<artist>[^/]+) - (?P<title>[^(]+)\.',
        '--no-confirmation',
        target_id3_dir
    ])
    assert result.exit_code == 0

    result = CliRunner().invoke(cli, ['list', target_id3_dir])
    filled_mp3_desc = u"""
╒════════════════╤═══════════╤═════════════╤════════════╕
│ Track number   │ Title     │ Artist      │ Album      │
╞════════════════╧═══════════╧═════════════╧════════════╡
│ artist name - song name.mp3                           │
├────────────────┬───────────┬─────────────┬────────────┤
│                │ song name │ artist name │ album name │
└────────────────┴───────────┴─────────────┴────────────┘
"""
    assert filled_mp3_desc.strip() in result.output

    target_rename_dir_raw = tmpdir / "rename"

    result = CliRunner().invoke(cli, [
        'rename',
        '-o', str(target_rename_dir_raw),
        '-p', '$artist' + os.path.sep + '$track_num - $title - $album.mp3',
        '--no-confirmation',
        target_id3_dir
    ])
    assert result.exit_code == 0
    assert (target_rename_dir_raw / 'artist name' / ' - song name - album name.mp3').isfile()
