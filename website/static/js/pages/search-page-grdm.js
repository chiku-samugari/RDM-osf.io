var $ = require('jquery');
$('input[name=q]').remove();

var Search = require('../search-grdm.js');
require('../../css/search-bar.css');
new Search('#searchControls', '/api/v1/search/', '');
