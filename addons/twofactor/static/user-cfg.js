var TwoFactorUserConfig = require('./twoFactorUserConfig.js').TwoFactorUserConfig;
var $ = require('jquery');

// Initialize tfa user config widget
var SETTINGS_URL = '/api/v1/settings/twofactor/';
if ($('#twoFactorScope').length) {
    new TwoFactorUserConfig(SETTINGS_URL, '#twoFactorScope', '#twoFactorQrCode');
}
