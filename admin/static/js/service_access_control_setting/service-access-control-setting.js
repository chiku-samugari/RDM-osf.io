'use-strict';

var $ = require('jquery');
var $osf = require('js/osfHelpers');
var _ = require('js/rdmGettext')._;

var csrftoken = $('[name=csrfmiddlewaretoken]').val();

function csrfSafeMethod(method) {
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}

$.ajaxSetup({
    crossDomain: false,
    beforeSend: function (xhr, settings) {
        if (!csrfSafeMethod(settings.type)) {
            xhr.setRequestHeader('X-CSRFToken', csrftoken);
        }
    }
});

$('#upload-button').click(function() {
    // Trigger input[type='file'] click event
    $('#file-upload').click();
});

$('#file-upload').change(function() {
    var files = $('#file-upload').prop('files');
    if (files && files.length > 0) {
        var uploadFile = files[0];
        var jsonExtensionRegex = new RegExp('\\.json$');
        if (!uploadFile.name.match(jsonExtensionRegex)) {
            $osf.growl('Error', _('Not a JSON file.'), 'danger', 5000);
            return;
        }
        var formData = new FormData();
        formData.append('file', uploadFile);
        $.ajax({
            url: 'setting/',
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function(json) {
                // Reload the page
                window.location.reload();
            },
            error: function(jqXHR) {
                // Reset input[type='file'] value
                $('#file-upload').val('');
                var data = jqXHR.responseJSON;
                if (data && data['message']) {
                    // If response has message, show that message
                    $osf.growl('Error', _(data['message']), 'danger', 5000);
                } else {
                    // Otherwise, show default error message 'A server error occurred. Please contact the administrator.'
                    $osf.growl('Error', 'A server error occurred. Please contact the administrator.', 'danger', 5000);
                }
            }
        });
    }
});
