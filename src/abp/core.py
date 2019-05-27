import os
import re
import six
import eyed3

from unidecode import unidecode
from unicodedata import normalize
from six.moves import html_parser

html = html_parser.HTMLParser()
eyed3.log.setLevel("ERROR")


AUDIO_FILE_PATTERN = re.compile(r'.+\.mp3$')
ID3_TAGS = ['track_num', 'title', 'artist', 'album']
ID3_TAGS_DESERIALIZER = {
    'track_num': lambda id3_track_num: six.text_type(id3_track_num and id3_track_num[0] or '')
}
ID3_TAGS_SERIALIZER = {
    'track_num': lambda id3_track_num: (int(id3_track_num), None)
}


def default_deserializer(x):
    return six.text_type(x or '')


def default_serializer(x):
    return unicode(x)


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


def save_id3_values(file_path, values, empty_override=False, encoding='utf8'):
    audiofile = eyed3.load(file_path)
    if audiofile.tag is None:
        audiofile.initTag()
    for tag, value in zip(ID3_TAGS, values):
        if value or empty_override:
            setattr(audiofile.tag, tag, id3_serialize(tag, value))

    audiofile.tag.save(encoding=encoding)


def get_folder_matched_files(folder_dir):
    for file_ in os.listdir(folder_dir):
        if not AUDIO_FILE_PATTERN.match(file_):
            continue
        yield normalize('NFC', file_)


def get_folder_dirs(input_path):
    for path, dirs, files in os.walk(six.text_type(input_path)):
        if not any(get_folder_matched_files(path)):
            continue
        yield six.text_type(path)



def id3_list(input_path):
    values = []

    for dir_path in get_folder_matched_files(input_path):
        matched_files = get_folder_matched_files(dir_path)
        path_values = []

        for file_ in matched_files:
            id3_values = get_id3_values(os.path.join(dir_path, file_))
            path_values.append({'file': file_, 'id3': id3_values})

        if path_values:
            values.append({'dir': dir_path, 'files': path_values})

    return values


def folder_id3_list(folder_path):
    for file_ in get_folder_matched_files(folder_path):
        id3_values = get_id3_values_dict(os.path.join(folder_path, file_))
        yield {'file': os.path.join(folder_path, file_), 'id3': id3_values}


GROUP_NAMES = {}
def get_group_names(pattern):
    text_pattern = pattern.pattern
    if text_pattern not in GROUP_NAMES:
        GROUP_NAMES[text_pattern] = re.findall(r'\?P<([^>]+)>', pattern.pattern)
    return GROUP_NAMES[text_pattern]


def get_file_id3_changes(id3_values, file_path, file_patterns, asciify, unescape):
    new_values = id3_values
    matched_pattern = None
    matched_groups = None
    matched_groups_span = None
    
    for file_pattern in file_patterns:
        match = file_pattern.search(file_path)
        if not match:
            continue
        group_names = get_group_names(file_pattern)
        matched_pattern = file_pattern.pattern
        matched_groups_span = [(group,) + span for group, span in zip(group_names, match.regs[1:]) if span != (-1, -1)]
        matched_groups = {key.lower(): value for key, value in match.groupdict().items()}
        new_values = [(matched_groups.get(tag) or new_values[i]).strip() for i, tag in enumerate(ID3_TAGS)]
        break


    if unescape:
        new_values = [html.unescape(cell) for cell in new_values]

    if asciify:
        new_values = [unidecode(cell) for cell in new_values]

    return matched_pattern, matched_groups_span, new_values


def prepare_id3_values_dict(values):
    return dict(zip(ID3_TAGS, values))


def get_id3_values_dict(file_path):
    values_list = get_id3_values(file_path)
    return prepare_id3_values_dict(values_list)


def get_id3_changes(input_path, empty_override, file_patterns, asciify, unescape, folder_dirs=None):
    if folder_dirs is None:
        folder_dirs = get_folder_dirs(input_path)
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

    for dir_path in folder_dirs:
        matched_files = get_folder_matched_files(os.path.join(input_path, dir_path))
        path_changes = []
        path_ingored_files = []

        for file_name in matched_files:
            file_path = os.path.join(dir_path, file_name)
            values = get_id3_values(os.path.join(input_path, file_path))

            matched_pattern, matched_groups, new_values = get_file_id3_changes(values, file_path, file_patterns, asciify, unescape)

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


def apply_changes(changes, encoding, input_path='.'):
    changed_files = []
    for dir_path, rows in changes:
        for file_name, new_values, old_values in rows:
            file_path = os.path.join(dir_path, file_name)
            save_id3_values(os.path.join(input_path, file_path), new_values, encoding=encoding)
            changed_files.append(file_path)
    return changed_files


def mkdirnotex(filename):
    folder = os.path.dirname(filename)
    if not os.path.exists(folder):
        os.makedirs(folder)


def is_rename_fully_matched(file_pattern, tags, file_path):
    new_file_path = file_pattern
    for name, value in tags.items():
        new_file_path_temp = new_file_path.replace('$' + name, value)
        # new_file_path_temp = '$a', a = ''
        if new_file_path_temp != new_file_path and not value:
            return False
        new_file_path = new_file_path_temp
    return new_file_path != file_path


def get_rename(file_pattern, tags):
    new_file_path = file_pattern
    if 'track_num' in tags:
        tags['track_num'] = '%0.2d' % int(tags['track_num'])
    for name, value in tags.items():
        new_file_path = new_file_path.replace('$' + name, value)
    return re.sub(r'[:?*<>|]', '', new_file_path)


def get_renames(input_path, file_path_pattern, folder_dirs=None):
    if folder_dirs is None:
        folder_dirs = get_folder_dirs(input_path)

    all_renames = []  # (dir_path, [(new_file_path, old_file_path,)])

    for dir_path in folder_dirs:
        dir_path = os.path.join(input_path, dir_path)

        matched_files = get_folder_matched_files(dir_path)
        path_renames = []

        for file_name in matched_files:
            old_file_path = os.path.join(dir_path, file_name)
            tags = get_id3_values_dict(old_file_path)
            new_file_path = get_rename(file_path_pattern, tags)
            path_renames.append((new_file_path, os.path.relpath(old_file_path, input_path)))

        if path_renames:
            all_renames.append((dir_path, path_renames))

    return all_renames




def apply_renames(renames, input_path, output_path):
    changed_files = []

    for dir_path, rows in renames:
        for new_file_path, old_file_path in rows:
            new_full_file_path = os.path.join(output_path, new_file_path)
            old_full_file_path = os.path.join(input_path, old_file_path)

            mkdirnotex(new_full_file_path)
            if old_full_file_path != new_full_file_path:
                os.rename(old_full_file_path, new_full_file_path)
                changed_files.append(new_full_file_path)
    return changed_files

