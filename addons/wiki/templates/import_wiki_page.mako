<!-- New Component Modal -->
<div class="modal fade" id="importWiki">
    <div class="modal-dialog">
        <div class="modal-content">
            <form class="form">
                <div class="modal-header">
                    <button type="button" class="close" data-dismiss="modal" aria-hidden="true">&times;</button>
                    <h3 class="modal-title">${_("Add new wiki page")}</h3>
                </div><!-- end modal-header -->
                <div class="modal-body">
                    <div class='form-group'>
                        <select id="importDir" class="form-control">
                            % for import_dir in import_dirs:
                                <option value="${import_dir['id']}">${import_dir['name']}</option>
                            % endfor
                        </select>
                    </div>
                </div><!-- end modal-body -->
                <div class="modal-footer">
                    <a id="close" href="#" class="btn btn-default" data-dismiss="modal">${_("Cancel")}</a>
                    <button id="import-wiki-submit" type="submit" class="btn btn-success">${_("Import")}</button>
                </div><!-- end modal-footer -->
            </form>
        </div><!-- end modal- content -->
    </div><!-- end modal-dialog -->
</div><!-- end modal -->

<script type="text/javascript">
    $(function () {
        var $importWikiForm = $('#importWiki form');

        $importWikiForm.on('submit', function (e) {
            e.preventDefault();

            var $importDir = $newWikiForm.find('#importDir');
            var $submitForm = $newWikiForm.find('#import-wiki-submit');

            $submitForm
                .attr('disabled', 'disabled')
                .text('${_("Importing wiki pages")}');

            } else {
                // TODO: helper to eliminate slashes in the url.
                var dirName = $importDir.val();
                var importUrl = ${ urls['api']['base'] | sjson, n } + encodeURIComponent(wikiName) + '/name/' + encodeURIComponent(dirName);
                var request = $.ajax({
                    type: 'GET',
                    cache: false,
                    url: importUrl,
                    dataType: 'json'
                });
                request.done(function (response) {
                    window.location.href = ${ urls['web']['base'] | sjson, n } + encodeURIComponent(wikiName) + '/edit/';
                });
                request.fail(function (response, textStatus, error) {
                    if (response.status === 409) {
                        $alert.text('${_("A wiki page with that name already exists.")}');
                    }
                    else {
                        $alert.text('${_("Could not validate wiki page. Please try again.")}'+response.status);
                        Raven.captureMessage('${_("Error occurred while validating page")}', {
                            extra: {
                                url: ${ urls['api']['base'] | sjson, n } + encodeURIComponent(wikiName) + '/validate/',
                                textStatus: textStatus,
                                error: error
                            }
                        });
                    }
                    $submitForm
                        .removeAttr('disabled', 'disabled')
                        .text('${_("Import")}');
                });
            }
        });

        $importWikiForm.find('#close').on('click', function () {
        });
    });
</script>
