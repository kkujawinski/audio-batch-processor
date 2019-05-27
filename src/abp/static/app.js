$(function() {
    var FOLDER_LIST_DETAILS_TEMPLATE = Handlebars.compile($('#folder-list-details-template').html());
    var FOLDER_DETAILS_ROWS_TEMPLATE = Handlebars.compile($('#folder-details-rows-template').html());
    Handlebars.registerPartial("FolderDetailsRow", $('#folder-details-template').html());

    var FOLDER_DETAILS_CACHE = {};

    String.prototype.replaceBetween= function(replace, start, end) {
        return this.substring(0, start) + replace + this.substring(end);
    };

    var clean_expansions = function() {
        $('.folder-details').data('loaded', '');
        $('.folder-details tbody').html('');
        FOLDER_DETAILS_CACHE = {};
    };

    var prepare_form_values = function() {
        var form = [];
        var mode = $('#mode-form button[aria-expanded=true]').val();
        if (mode == 'id3') {
            form = $('#id3-form form').serializeArray();
        } else if (mode == 'rename') {
            form = $('#rename-form form').serializeArray();
        }
        form.splice(0, 0, {'name': 'mode', 'value': mode});

        $('#preview-values').data('form', form);
        var html = '';
        for (var i=0, len=form.length; i < len; i++) {
            html += ' <b>' + form[i].name + '</b>: <span id="preview-value-' + form[i].name + '"></span><br/>';
        }
        $('#preview-values .values').html(html);
        for (var i=0, len=form.length; i < len; i++) {
            $('#preview-value-' + form[i].name).text(form[i].value);
        }
        $('#preview-values').addClass('active')
    };

    var get_pattern_groups = function(pattern) {
        var group_regex = /\?P\<([^\>]+)\>/,
            group_regex_global = /\?P\<([^\>]+)\>/g;
        var groups = pattern.match(group_regex_global),
            output = [];
        for (var i = 0; i < groups.length; i++) {
            output.push(groups[i].match(group_regex)[1]);
        }
        return output;
    };

    var load_folder_details_action = function(folder_details, data) {
        var mode = $('#mode-form button[aria-expanded=true]').val();
        var rows_html = FOLDER_DETAILS_ROWS_TEMPLATE({
            'files': data,
            'show_preview_pattern': mode == 'id3'
        });
        folder_details.find('tbody').html(rows_html);
        folder_details.data('loaded', 1);
    };

    var load_folder_details = function(folder_details) {
        var path = folder_details.data('path');
        var form = [{'name': 'path', 'value': path}];
        if ($('#preview-values').hasClass('active')) {
            form = form.concat($('#preview-values').data('form'));
        }

        var cached_data = FOLDER_DETAILS_CACHE[path]
        if (cached_data) {
            load_folder_details_action(folder_details, cached_data);
            return;
        }

        var active_tab = $('#mode-form button[aria-expanded=true]').prop('id');

        $.ajax('/api/id3-list?' + $.param(form))
            .done(function(data) {
                data = data.map(function(item) {
                    if (item.matched_pattern) {
                        var file = item.file;
                        for (var i = item.matched_groups.length - 1; i >= 0; i--) {
                            var matched_group = item.matched_groups[i],
                                field_name = matched_group[0],
                                span_start = matched_group[1],
                                span_end = matched_group[2],
                                field_value = file.substring(span_start, span_end);

                            new_field_value = '<u title="' + field_name + '">' + field_value + '</u>'
                            file = file.replaceBetween(new_field_value,  span_start, span_end);
                        }
                        item.file = file;
                    }

                    if (item.id3_preview) {
                        keys = Object.keys(item.id3);
                        for (var i=0; i < keys.length; i++) {
                            var key = keys[i];
                            if (item.id3[key] == item.id3_preview[key]) {
                                delete item.id3_preview[key];
                            }
                        }
                    }

                    if (item.file_preview) {
                        if (item.file == item.file_preview) {
                            delete item.file_preview;
                        }
                    }
                    return item;
                });
                FOLDER_DETAILS_CACHE[path] = data;
                load_folder_details_action(folder_details, data);
            });
    };

    var expand_folder_action = function(folder_details) {
        folder_details.toggleClass('expanded')

        if (!folder_details.data('loaded')) {
            load_folder_details(folder_details);
        }
    };

    var load_list = function() {
        clean_expansions();

        $('.folder-select:checked').prop('checked', '')
        $('#preview-values .values').html('');
        $('#preview-values').removeClass('active')

        $.ajax('/api/list')
            .done(function(data) {
                var selected = [];
                var not_selected = data.slice();

                var select_item = function(item) {
                    var pos = not_selected.indexOf(item);
                    var removed = not_selected.splice(pos, 1);
                    selected.push(removed[0]);
                    selected.sort();
                };

                var deselect_item = function(item) {
                    var pos = selected.indexOf(item);
                    var removed = selected.splice(pos, 1);
                    not_selected.push(removed[0]);
                    not_selected.sort();
                };

                var redraw = function() {
                    var folder_details_html = FOLDER_LIST_DETAILS_TEMPLATE({'folders_selected': selected,
                                                                            'folders_not_selected': not_selected});
                    $('#folder-list').html(folder_details_html);
                    attach_events();
                }

                var attach_events = function() {
                    $('.folder-select').change(function() {
                        var folder_path = $(this).parents('.folder-details').data('path');

                        if (this.checked) {
                            select_item(folder_path);
                        } else {
                            deselect_item(folder_path);
                        }

                        var expanded = $.makeArray($('.expanded')).map(function(i) { return $(i).data('path'); });
                        var folder_details_html = FOLDER_LIST_DETAILS_TEMPLATE({'folders_selected': selected,
                                                                                'folders_not_selected': not_selected});
                        $('#folder-list').html(folder_details_html);

                        attach_events();

                        for (var i=0; i < expanded.length; i++) {
                            expand_folder_action($('.folder-details[data-path="' + expanded[i] + '"]'));
                        }
                    });

                    $('.expand-folder').click(function(event) {
                        event.preventDefault();
                        expand_folder_action($(this).parents('.folder-details'));
                    })
                };

                redraw();

                $('#filter-values button').unbind('click');
                $('#filter-values button').click(function() {
                    var action = $(this).prop('name');
                    var mode = $('#mode-form button[aria-expanded=true]').val();
                    if (action === 'select-all') {
                        selected = data.slice();
                        not_selected = [];
                        redraw();
                    } else if (action === 'select-none') {
                        selected = [];
                        not_selected = data.slice();
                        redraw();
                    } else if (action === 'select-matched') {
                        if (mode == 'id3') {
                            var form = $('#preview-values').data('form');
                            $.ajax('/api/matched-folders?' + $.param(form))
                                .done(function(matched) {
                                    selected = [];
                                    not_selected = data.slice();
                                    for (var i=0; i < matched.length; i++) {
                                        select_item(matched[i])
                                    }
                                    redraw();
                                });
                        } else if (mode == 'rename') {
                            var form = $('#preview-values').data('form');
                            $.ajax('/api/matched-renames?' + $.param(form))
                                .done(function(matched) {
                                    selected = [];
                                    not_selected = data.slice();
                                    for (var i=0; i < matched.length; i++) {
                                        select_item(matched[i])
                                    }
                                    redraw();
                                });
                        }
                    }
                });
            })
        };

    load_list();

    $('#mode-form button').click(function() {
        $('body').removeClass();
        $('body').addClass($(this).prop('id'));

        load_list();
    });

    $('#preview-changes').click(function() {
        clean_expansions();
        prepare_form_values();
        $('body').addClass('preview')
        $('.folder-details.expande').each(function(index, item) {
            load_folder_details($(item));
        });
    });

    $('#apply-changes').click(function() {
        var form = $('#preview-values').data('form');
        var selected_folders = $('#folders-selected .folder-details');
        var mode = $('#mode-form button[aria-expanded=true]').val();
        for (var i=0; i < selected_folders.length; i++) {
            form.push({name: 'folder-path', value: $(selected_folders[i]).data('path')})
        }

        if (mode == 'id3') {
            $.ajax('/api/apply', {
                'method': 'POST',
                'data': $.param(form),
            }).done(function() {
                $('body').addClass('preview')
                $('.folder-details.active').each(function(index, item) {
                    load_folder_details($(item));
                });
                load_list();
            });
        } else if (mode == 'rename') {
            $.ajax('/api/apply-renames', {
                'method': 'POST',
                'data': $.param(form),
            }).done(function() {
                $('body').addClass('preview')
                $('.folder-details.active').each(function(index, item) {
                    load_folder_details($(item));
                });
                load_list();
            });
        }
    });

})