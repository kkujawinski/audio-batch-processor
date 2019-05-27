import os
import re

from flask import Flask, render_template, jsonify, request

from abp.core import (folder_id3_list, get_folder_dirs, get_file_id3_changes, get_id3_values_dict, prepare_id3_values_dict,
                      get_id3_changes, apply_changes, get_rename, get_renames, apply_renames as core_apply_renames,
                      is_rename_fully_matched)
from abp.core import ID3_TAGS


def create_app(input_path):
    app = Flask(__name__)

    def validate_path(param_path):
        if os.path.relpath(param_path, input_path).startswith('..'):
            raise Exception('Outside application scope')

    def clean_path(path):
        return os.path.relpath(path, input_path)

    @app.route("/")
    def index():
        # list dirs
        return render_template('index.html', result={})

    @app.route("/api/list")
    def list_():
        return jsonify([clean_path(path) for path in get_folder_dirs(input_path)])

    @app.route("/api/id3-list")
    def id3():
        folder_dir = request.args.get('path') 
        folder_dir_path = os.path.realpath(os.path.join(input_path, folder_dir))
        validate_path(folder_dir_path)

        output = [
            dict(item, file=clean_path(item['file']))
            for item in folder_id3_list(folder_dir_path)
        ]
        mode = request.args.get('mode')
        if mode == 'id3':
            patterns = [re.compile(pattern.strip()) for pattern in request.args.get('patterns').split('\n') if pattern]
            for item in output:
                id3_values = [item['id3'][tag] for tag in ID3_TAGS]
                matched_pattern, matched_groups, id3_changes = get_file_id3_changes(
                    id3_values, item['file'], patterns,
                    request.args.get('asciify') == 'on',
                    request.args.get('unescape') == 'on'
                )
                item['id3_preview'] = prepare_id3_values_dict(id3_changes)
                item['matched_pattern'] = matched_pattern
                item['matched_groups'] = matched_groups
        elif mode == 'rename':
            pattern = request.args.get('pattern')
            for item in output:
                item['file_preview'] = get_rename(pattern, item['id3'])
            # for item in output:
        return jsonify(output)

    @app.route("/api/matched-folders")
    def matched_folders():
        matched_folders = set()
        patterns = [re.compile(pattern.strip()) for pattern in request.args.get('patterns').split('\n') if pattern]

        for folder_path in get_folder_dirs(input_path):
            files = [clean_path(item['file']) for item in folder_id3_list(folder_path)]
            for file in files:
                id3_values = [item['id3'][tag] for tag in ID3_TAGS]
                matched_pattern, matched_groups, id3_changes = get_file_id3_changes({}, file, patterns, False, False)
                if matched_pattern:
                    matched_folders.add(clean_path(folder_path))
                    break
        return jsonify(list(matched_folders))

    @app.route("/api/matched-renames")
    def matched_renames():
        matched_folders = set()
        pattern = request.args.get('pattern')

        for folder_path in get_folder_dirs(input_path):
            files = [clean_path(item['file']) for item in folder_id3_list(folder_path)]
            if all(is_rename_fully_matched(pattern, get_id3_values_dict(os.path.join(input_path, file)), file) for file in files):
                matched_folders.add(clean_path(folder_path))
        return jsonify(list(matched_folders))

    @app.route("/api/apply", methods=['POST'])
    def apply():
        patterns = [re.compile(pattern.strip()) for pattern in request.form.get('patterns').split('\n') if pattern]
        asciify = request.form.get('asciify') == 'on',
        unescape = request.form.get('unescape') == 'on'
        encoding = request.form.get('encoding')
        folder_dirs = request.form.getlist('folder-path')

        folder_dir_paths = [os.path.realpath(os.path.join(input_path, folder_dir))
                            for folder_dir in folder_dirs]
        for folder_dir_path in folder_dir_paths:
            validate_path(folder_dir_path)

        all_changes, ignored_files = get_id3_changes(input_path, empty_override=False, file_patterns=patterns,
                                                     asciify=asciify, unescape=unescape, folder_dirs=folder_dirs)
        changed_files = apply_changes(all_changes, encoding, input_path=input_path)
        return jsonify(list(changed_files))

    @app.route("/api/apply-renames", methods=['POST'])
    def apply_renames():
        pattern = request.form.get('pattern')
        folder_dirs = request.form.getlist('folder-path')

        folder_dir_paths = [os.path.realpath(os.path.join(input_path, folder_dir))
                            for folder_dir in folder_dirs]
        for folder_dir_path in folder_dir_paths:
            validate_path(folder_dir_path)

        renames = get_renames(input_path, pattern, folder_dirs=folder_dirs)
        changed_files = core_apply_renames(renames, input_path, input_path)

        return jsonify(list(changed_files))


    return app