<!-- New Component Modal -->
<div class="modal fade" id="importWiki">
    <div class="modal-dialog">
        <div class="modal-content">
            <form class="form">
                <div class="modal-header">
                    <button type="button" class="close" data-dismiss="modal" aria-hidden="true">&times;</button>
                    <h3 class="modal-title">${_("Import wiki page")}</h3>
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
                    <button id="importWikiSubmit" type="submit" class="btn btn-success">${_("Import")}</button>
                </div><!-- end modal-footer -->
            </form>
        </div><!-- end modal- content -->
    </div><!-- end modal-dialog -->
</div><!-- end modal -->

<div class="modal fade" id="aleartInfo">
    <div class="modal-dialog">
        <div class="modal-content">
            <form class="form">
                <div class="modal-header">
                    <button type="button" class="close" data-dismiss="modal" aria-hidden="true">&times;</button>
                    <h3 class="modal-title">${_("Duplicate wiki name")}</h3>
                </div><!-- end modal-header -->
                <div class="modal-body">
                    <p>
                        ${_('The following wiki page already exists. Please select the process when importing. When creating a new wiki, the wiki name will be created with a sequential number like [Wiki name](1). If you dismiss this alert, the import will be aborted.')}
                    </p>
                    <div id='validateInfo'>
                        <ul></ul>
                    </div>
                </div><!-- end modal-body -->
                <div class="modal-footer">
                    <a id="stopImport" href="#" class="btn btn-default" data-dismiss="modal">${_("Stop import")}</a>
                    <button id="backAleartInfo" type="button" class="btn btn-default">${_("Back")}</button>
                    <button id="continueImportWikiSubmit" type="submit" class="btn btn-success">${_("Continue import")}</button>
                    <button id="perFileDefinition" type="button" class="btn btn-warning">${_("Per-file definition")}</button>
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

            var $importDir = $importWikiForm.find('#importDir');
            var $submitForm = $importWikiForm.find('#importWikiSubmit');

            $submitForm
                .attr('disabled', 'disabled')
                .text('${_("Importing wiki pages")}');

                // TODO: helper to eliminate slashes in the url.
                var dirId = $importDir.val();
                var importUrl = ${ urls['api']['base'] | sjson, n } + 'import/' + dirId + '/validate/';
                var request = $.ajax({
                    type: 'GET',
                    cache: false,
                    url: importUrl,
                    dataType: 'json'
                });
                request.done(function (response) {
                    $('#importWiki').modal('hide');
                    $('#aleartInfo').modal('show');
                    $submitForm
                        .removeAttr('disabled', 'disabled')
                        .text('${_("Import")}');
                    
                    response.data.forEach(function(item) {
                        $('#validateInfo ul').append('<li>' + item.name + '</li>')
                    });
                });
                request.fail(function (response, textStatus, error) {
                    $alert.text('${_("Could not validate wiki page. Please try again.")}'+response.status);
                    Raven.captureMessage('${_("Error occurred while validating page")}', {
                        extra: {
                            url: ${ urls['api']['base'] | sjson, n } + 'import/' + dirId + '/validate/',
                            textStatus: textStatus,
                            error: error
                        }
                    });
                    $submitForm
                        .removeAttr('disabled', 'disabled')
                        .text('${_("Import")}');
                });
        });

        $importWikiForm.find('#close').on('click', function () {
        });
    });
</script>
