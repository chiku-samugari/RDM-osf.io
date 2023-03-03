"""
Django settings for api project.

Generated by 'django-admin startproject' using Django 1.8.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.8/ref/settings/
"""

import os
from future.moves.urllib.parse import urlparse
from website import settings as osf_settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/

DATABASES = {
    'default': {
        'CONN_MAX_AGE': 0,
        'ENGINE': 'osf.db.backends.postgresql',  # django.db.backends.postgresql
        'NAME': os.environ.get('OSF_DB_NAME', 'osf'),
        'USER': os.environ.get('OSF_DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('OSF_DB_PASSWORD', ''),
        'HOST': os.environ.get('OSF_DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('OSF_DB_PORT', '5432'),
        'ATOMIC_REQUESTS': True,
        'TEST': {
            'SERIALIZE': False,
        },
    },
}

DATABASE_ROUTERS = ['osf.db.router.PostgreSQLFailoverRouter', ]
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
]

AUTH_USER_MODEL = 'osf.OSFUser'

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = osf_settings.SECRET_KEY

AUTHENTICATION_BACKENDS = (
    'api.base.authentication.backends.ODMBackend',
    'guardian.backends.ObjectPermissionBackend',
)

# SECURITY WARNING: don't run with debug turned on in production!
DEV_MODE = osf_settings.DEV_MODE
DEBUG = osf_settings.DEBUG_MODE
DEBUG_PROPAGATE_EXCEPTIONS = True

# session:
SESSION_COOKIE_NAME = 'api'
SESSION_COOKIE_SECURE = osf_settings.SECURE_MODE
SESSION_COOKIE_HTTPONLY = osf_settings.SESSION_COOKIE_HTTPONLY
SESSION_COOKIE_SAMESITE = osf_settings.SESSION_COOKIE_SAMESITE

# csrf:
CSRF_COOKIE_NAME = 'api-csrf'
CSRF_COOKIE_SECURE = osf_settings.SECURE_MODE
CSRF_COOKIE_HTTPONLY = osf_settings.SECURE_MODE

ALLOWED_HOSTS = [
    '.osf.io',
]


# Application definition

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'django.contrib.admin',

    # 3rd party
    'django_celery_beat',
    'django_celery_results',
    'rest_framework',
    'corsheaders',
    'raven.contrib.django.raven_compat',
    'django_extensions',
    'guardian',
    'storages',
    'waffle',
    'elasticsearch_metrics',

    # OSF
    'osf',

    # Addons
    'addons.osfstorage',
    'addons.bitbucket',
    'addons.box',
    'addons.dataverse',
    'addons.dropbox',
    'addons.figshare',
    'addons.forward',
    'addons.github',
    'addons.gitlab',
    'addons.googledrive',
    'addons.mendeley',
    'addons.onedrive',
    'addons.owncloud',
    'addons.s3',
    'addons.twofactor',
    'addons.wiki',
    'addons.zotero',
    'addons.swift',
    'addons.azureblobstorage',
    'addons.weko',
    'addons.jupyterhub',
    'addons.iqbrims',
    'addons.dropboxbusiness',
    'addons.nextcloudinstitutions',
    'addons.s3compatinstitutions',
    'addons.ociinstitutions',
    'addons.binderhub',
    'addons.onedrivebusiness',
    'addons.metadata',
)

# local development using https
if osf_settings.SECURE_MODE and DEBUG:
    INSTALLED_APPS += ('sslserver',)

# TODO: Are there more granular ways to configure reporting specifically related to the API?
RAVEN_CONFIG = {
    'tags': {'App': 'api'},
    'dsn': osf_settings.SENTRY_DSN,
    'release': osf_settings.VERSION,
}

BULK_SETTINGS = {
    'DEFAULT_BULK_LIMIT': 100,
}

MAX_PAGE_SIZE = 100

REST_FRAMEWORK = {
    'PAGE_SIZE': 10,
    'DEFAULT_RENDERER_CLASSES': (
        'api.base.renderers.JSONAPIRenderer',
        'api.base.renderers.JSONRendererWithESISupport',
        'api.base.renderers.BrowsableAPIRendererNoForms',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'api.base.parsers.JSONAPIParser',
        'api.base.parsers.JSONAPIParserForRegularJSON',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ),
    'EXCEPTION_HANDLER': 'api.base.exceptions.json_api_exception_handler',
    'DEFAULT_CONTENT_NEGOTIATION_CLASS': 'api.base.content_negotiation.JSONAPIContentNegotiation',
    'DEFAULT_VERSIONING_CLASS': 'api.base.versioning.BaseVersioning',
    'DEFAULT_VERSION': '2.0',
    'ALLOWED_VERSIONS': (
        '2.0',
        '2.1',
        '2.2',
        '2.3',
        '2.4',
        '2.5',
        '2.6',
        '2.7',
        '2.8',
        '2.9',
        '2.10',
        '2.11',
        '2.12',
        '2.13',
        '2.14',
        '2.15',
        '2.16',
        '2.17',
        '2.18',
        '2.19',
        '2.20',
    ),
    'DEFAULT_FILTER_BACKENDS': ('api.base.filters.OSFOrderingFilter',),
    'DEFAULT_PAGINATION_CLASS': 'api.base.pagination.JSONAPIPagination',
    'ORDERING_PARAM': 'sort',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        # Custom auth classes
        'api.base.authentication.drf.OSFBasicAuthentication',
        'api.base.authentication.drf.OSFSessionAuthentication',
        'api.base.authentication.drf.OSFCASAuthentication',
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.UserRateThrottle',
        'api.base.throttling.NonCookieAuthThrottle',
        'api.base.throttling.BurstRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'user': '10000/day',
        'non-cookie-auth': '100/hour',
        'add-contributor': '10/second',
        'create-guid': '1000/hour',
        'root-anon-throttle': '1000/hour',
        'test-user': '2/hour',
        'test-anon': '1/hour',
        'send-email': '2/minute',
        'burst': '10/second',
    },
}

# Settings related to CORS Headers addon: allow API to receive authenticated requests from OSF
# CORS plugin only matches based on "netloc" part of URL, so as workaround we add that to the list
CORS_ORIGIN_ALLOW_ALL = False
CORS_ORIGIN_WHITELIST = (
    urlparse(osf_settings.DOMAIN).netloc,
    osf_settings.DOMAIN,
)
# This needs to remain True to allow cross origin requests that are in CORS_ORIGIN_WHITELIST to
# use cookies.
CORS_ALLOW_CREDENTIALS = True
# Set dynamically on app init
ORIGINS_WHITELIST = ()

MIDDLEWARE = (
    'api.base.middleware.DjangoGlobalMiddleware',
    'api.base.middleware.CeleryTaskMiddleware',
    'api.base.middleware.PostcommitTaskMiddleware',
    # A profiling middleware. ONLY FOR DEV USE
    # Uncomment and add "prof" to url params to recieve a profile for that url
    # 'api.base.middleware.ProfileMiddleware',

    # 'django.contrib.sessions.middleware.SessionMiddleware',
    'api.base.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    # 'django.contrib.auth.middleware.AuthenticationMiddleware',
    # 'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    # 'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # 'waffle.middleware.WaffleMiddleware',
    'api.base.middleware.SloanOverrideWaffleMiddleware',  # Delete this and uncomment WaffleMiddleware to revert Sloan
)

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
    },
]


ROOT_URLCONF = 'api.base.urls'
WSGI_APPLICATION = 'api.base.wsgi.application'


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# https://django-storages.readthedocs.io/en/latest/backends/gcloud.html
if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', False):
    # Required to interact with Google Cloud Storage
    DEFAULT_FILE_STORAGE = 'api.base.storage.RequestlessURLGoogleCloudStorage'
    GS_BUCKET_NAME = os.environ.get('GS_BUCKET_NAME', 'cos-osf-stage-cdn-us')
    GS_FILE_OVERWRITE = os.environ.get('GS_FILE_OVERWRITE', False)
elif osf_settings.DEV_MODE or osf_settings.DEBUG_MODE:
    DEFAULT_FILE_STORAGE = 'api.base.storage.DevFileSystemStorage'

# https://docs.djangoproject.com/en/1.8/howto/static-files/

STATIC_ROOT = os.path.join(BASE_DIR, 'static/vendor')

API_BASE = 'v2/'
API_PRIVATE_BASE = '_/'
STATIC_URL = '/static/'

NODE_CATEGORY_MAP = osf_settings.NODE_CATEGORY_MAP

DEBUG_TRANSACTIONS = DEBUG

JWT_SECRET = b'osf_api_cas_login_jwt_secret_32b'
JWE_SECRET = b'osf_api_cas_login_jwe_secret_32b'

ENABLE_VARNISH = osf_settings.ENABLE_VARNISH
ENABLE_ESI = osf_settings.ENABLE_ESI
VARNISH_SERVERS = osf_settings.VARNISH_SERVERS
ESI_MEDIA_TYPES = osf_settings.ESI_MEDIA_TYPES

ADDONS_FOLDER_CONFIGURABLE = ['box', 'dropbox', 's3', 'googledrive', 'figshare', 'owncloud', 'onedrive', 'swift', 'azureblobstorage', 'weko', 'iqbrims']
ADDONS_OAUTH = ADDONS_FOLDER_CONFIGURABLE + ['dataverse', 'github', 'bitbucket', 'gitlab', 'mendeley', 'zotero', 'forward', 'binderhub', 'metadata']

BYPASS_THROTTLE_TOKEN = 'test-token'

OSF_SHELL_USER_IMPORTS = None

# Settings for use in the admin
OSF_URL = 'https://osf.io'

SELECT_FOR_UPDATE_ENABLED = True

# Disable anonymous user permissions in django-guardian
ANONYMOUS_USER_NAME = None

# If set to True, automated tests with extra queries will fail.
NPLUSONE_RAISE = False

# Timestamp - number of requests to send to cloud storages per minute
TS_REQUESTS_PER_MIN = 30

# salt used for generating hashids
HASHIDS_SALT = 'pinkhimalayan'

# django-elasticsearch-metrics
ELASTICSEARCH_DSL = {
    'default': {
        'hosts': os.environ.get('ELASTIC6_URI', '127.0.0.1:9201'),
        'retry_on_timeout': True,
    },
}
# Store yearly indices for time-series metrics
ELASTICSEARCH_METRICS_DATE_FORMAT = '%Y'

WAFFLE_CACHE_NAME = 'waffle_cache'
STORAGE_USAGE_CACHE_NAME = 'storage_usage'


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
    STORAGE_USAGE_CACHE_NAME: {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'osf_cache_table',
    },
    WAFFLE_CACHE_NAME: {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
}

SLOAN_ID_COOKIE_NAME = 'sloan_id'

EGAP_PROVIDER_NAME = 'EGAP'

MAX_SIZE_OF_ES_QUERY = 10000
DEFAULT_ES_NULL_VALUE = 'N/A'

TRAVIS_ENV = False

### NII extensions
LOGIN_BY_EPPN = osf_settings.to_bool('LOGIN_BY_EPPN', False)
USER_TIMEZONE = osf_settings.USER_TIMEZONE
USER_LOCALE = osf_settings.USER_LOCALE
CLOUD_GATEWAY_ISMEMBEROF_PREFIX = osf_settings.CLOUD_GATEWAY_ISMEMBEROF_PREFIX
# install-addons.py
INSTALLED_APPS += ('addons.s3compat',)
ADDONS_FOLDER_CONFIGURABLE.append('s3compat')
ADDONS_OAUTH.append('s3compat')
INSTALLED_APPS += ('addons.s3compatb3',)
ADDONS_FOLDER_CONFIGURABLE.append('s3compatb3')
ADDONS_OAUTH.append('s3compatb3')
INSTALLED_APPS += ('addons.nextcloud',)
ADDONS_FOLDER_CONFIGURABLE.append('nextcloud')
ADDONS_OAUTH.append('nextcloud')

TST_COMMAND_DELIMITER = ' '
# RSA key generation settings
SSL_GENERATE_KEY = 'openssl' + TST_COMMAND_DELIMITER + \
                   'genrsa' + TST_COMMAND_DELIMITER + \
                   '-des3' + TST_COMMAND_DELIMITER + \
                   '-out' + TST_COMMAND_DELIMITER + \
                   '{0}.key {1}'
SSL_GENERATE_KEY_NOPASS = 'openssl' + TST_COMMAND_DELIMITER + \
                          'rsa' + TST_COMMAND_DELIMITER + \
                          '-in' + TST_COMMAND_DELIMITER + \
                          '{0}.key' + TST_COMMAND_DELIMITER + \
                          '-out' + TST_COMMAND_DELIMITER + \
                          '{0}.key.nopass'
SSL_GENERATE_CSR = 'openssl' + TST_COMMAND_DELIMITER + \
                   'req' + TST_COMMAND_DELIMITER + \
                   '-new' + TST_COMMAND_DELIMITER + \
                   '-key' + TST_COMMAND_DELIMITER + \
                   '{0}.key.nopass' + TST_COMMAND_DELIMITER + \
                   '-out' + TST_COMMAND_DELIMITER + \
                   '{0}.csr'
SSL_GENERATE_SELF_SIGNED = 'openssl' + TST_COMMAND_DELIMITER + \
                           'req' + TST_COMMAND_DELIMITER + \
                           '-x509' + TST_COMMAND_DELIMITER + \
                           '-nodes' + TST_COMMAND_DELIMITER + \
                           '-days' + TST_COMMAND_DELIMITER + \
                           '365' + TST_COMMAND_DELIMITER + \
                           '-newkey' + TST_COMMAND_DELIMITER + \
                           'rsa:2048' + TST_COMMAND_DELIMITER + \
                           '-keyout' + TST_COMMAND_DELIMITER + \
                           '{0}.key' + TST_COMMAND_DELIMITER + \
                           '-out' + TST_COMMAND_DELIMITER + \
                           '{0}.crt'
SSL_PRIVATE_KEY_GENERATION = 'openssl' + TST_COMMAND_DELIMITER + \
                             'genrsa' + TST_COMMAND_DELIMITER + \
                             '-out' + TST_COMMAND_DELIMITER + \
                             '{0}' + TST_COMMAND_DELIMITER + \
                             '{1}'
SSL_PUBLIC_KEY_GENERATION = 'openssl' + TST_COMMAND_DELIMITER + \
                            'rsa' + TST_COMMAND_DELIMITER + \
                            '-in' + TST_COMMAND_DELIMITER + \
                            '{0}' + TST_COMMAND_DELIMITER + \
                            '-pubout' + TST_COMMAND_DELIMITER + \
                            '-out' + TST_COMMAND_DELIMITER + \
                            '{1}'

# UserKey Placement destination
KEY_NAME_PRIVATE = 'pvt'
KEY_NAME_PUBLIC = 'pub'
KEY_BIT_VALUE = '3072'
KEY_EXTENSION = '.pem'
KEY_SAVE_PATH = '/user_key_info/'
KEY_NAME_FORMAT = '{0}_{1}_{2}{3}'
PRIVATE_KEY_VALUE = 1
PUBLIC_KEY_VALUE = 2
# FreeTSA openation commands
SSL_CREATE_TIMESTAMP_REQUEST = 'openssl' + TST_COMMAND_DELIMITER + \
                               'ts' + TST_COMMAND_DELIMITER + \
                               '-query' + TST_COMMAND_DELIMITER + \
                               '-data' + TST_COMMAND_DELIMITER + \
                               '{0}' + TST_COMMAND_DELIMITER + \
                               '-cert' + TST_COMMAND_DELIMITER + \
                               '-sha512'
SSL_GET_TIMESTAMP_RESPONSE = 'openssl' + TST_COMMAND_DELIMITER + \
                             'ts' + TST_COMMAND_DELIMITER + \
                             '-verify' + TST_COMMAND_DELIMITER + \
                             '-data' + TST_COMMAND_DELIMITER + \
                             '{0}' + TST_COMMAND_DELIMITER + \
                             '-in' + TST_COMMAND_DELIMITER + \
                             '{1}' + TST_COMMAND_DELIMITER + \
                             '-CAfile' + TST_COMMAND_DELIMITER + \
                             '{2}'

SSL_CREATE_TIMESTAMP_HASH_REQUEST = 'openssl ts -query -digest {digest} {digest_type} -cert'
SSL_GET_TIMESTAMP_HASH_RESPONSE = 'openssl ts -verify {digest_type} -digest {digest} -in {input} -CAfile {ca}'

# openssl ts verify check value
OPENSSL_VERIFY_RESULT_OK = 'OK'
# timestamp verify rootKey
VERIFY_ROOT_CERTIFICATE = 'root_cert_verifycate.pem'
# timestamp request const
REQUEST_HEADER = {'Content-Type': 'application/timestamp-query'}
TIME_STAMP_AUTHORITY_URL = 'http://eswg.jnsa.org/freetsa'
ERROR_HTTP_STATUS = [400, 401, 402, 403, 500, 502, 503, 504]
REQUEST_TIME_OUT = 5
RETRY_COUNT = 3

# UPKI flag
USE_UPKI = False

#uPKI operation commands
UPKI_TIMESTAMP_URL = ''
UPKI_CREATE_TIMESTAMP = ''  # {0}=target, {1}=out
UPKI_VERIFY_TIMESTAMP = ''  # {0}=target, {1}=in
UPKI_CREATE_TIMESTAMP_HASH = ''  # {digest_type}, {digest}, {output}
UPKI_VERIFY_TIMESTAMP_HASH = ''  # {digest}, {input}
UPKI_VERIFY_INVALID_MSG = 'LPC_ERR_VERIFY_INVALID'

# TimeStamp Inspection Status
TIME_STAMP_TOKEN_UNCHECKED = 0
TIME_STAMP_TOKEN_CHECK_SUCCESS = 1
TIME_STAMP_TOKEN_CHECK_SUCCESS_MSG = 'OK'
TIME_STAMP_TOKEN_CHECK_NG = 2
TIME_STAMP_TOKEN_CHECK_NG_MSG = 'Fail: file modified.'
TIME_STAMP_TOKEN_CHECK_FILE_NOT_FOUND = 3
TIME_STAMP_TOKEN_CHECK_FILE_NOT_FOUND_MSG = 'Fail: not inspected.'
TIME_STAMP_TOKEN_NO_DATA = 4
TIME_STAMP_TOKEN_NO_DATA_MSG = 'Error: some errors has occurred in processing.'
FILE_NOT_EXISTS = 5
FILE_NOT_EXISTS_MSG = 'Fail: deleted file.'
FILE_NOT_FOUND = 6
FILE_NOT_FOUND_MSG = 'Fail: file was gone.'
TIME_STAMP_VERIFICATION_ERR = 7
TIME_STAMP_VERIFICATION_ERR_MSG = 'Error: some errors has occurred in verification.'
TIME_STAMP_STORAGE_DISCONNECTED = 8
TIME_STAMP_STORAGE_DISCONNECTED_MSG = 'Error: storage disconnected.'
TIME_STAMP_STORAGE_NOT_ACCESSIBLE = 9
TIME_STAMP_STORAGE_NOT_ACCESSIBLE_MSG = 'Error: storage service connection error occurred.'

# Quota settings
DEFAULT_MAX_QUOTA = 100
WARNING_THRESHOLD = 0.9
BASE_FOR_METRIC_PREFIX = 1000
SIZE_UNIT_GB = BASE_FOR_METRIC_PREFIX ** 3
NII_STORAGE_REGION_ID = 1

# Quota for institutional storage settings
DEFAULT_MAX_QUOTA_S3 = 100
DEFAULT_MAX_QUOTA_OSFSTORAGE = 100
DEFAULT_MAX_QUOTA_S3COMPAT = 100
DEFAULT_MAX_QUOTA_BOX = 100
DEFAULT_MAX_QUOTA_DROPBOX_BUSINESS = 100
DEFAULT_MAX_QUOTA_GOOGLEDRIVE = 100
DEFAULT_MAX_QUOTA_NEXTCLOUD = 100
DEFAULT_MAX_QUOTA_NEXTCLOUD_FOR_INSTITUTIONS = 100
DEFAULT_MAX_QUOTA_ONEDRIVE_FOR_OFFICE365 = 100
DEFAULT_MAX_QUOTA_OPENSTACK_SWIFT = 100
DEFAULT_MAX_QUOTA_ORACLE_CLOUD_INFRASTRUCTURE_FOR_INSTITUTIONS = 100
DEFAULT_MAX_QUOTA_OWNCLOUD = 100
DEFAULT_MAX_QUOTA_S3_COMPATIBLE_STORAGE_FOR_INSTITUTIONS = 100

DEFAULT_MAX_QUOTA_PER_STORAGE = {
    'osfstorage': DEFAULT_MAX_QUOTA_OSFSTORAGE,
    's3': DEFAULT_MAX_QUOTA_S3,
    's3compat': DEFAULT_MAX_QUOTA_S3COMPAT,
    'box': DEFAULT_MAX_QUOTA_BOX,
    'dropboxbusiness': DEFAULT_MAX_QUOTA_DROPBOX_BUSINESS,
    'googledrive': DEFAULT_MAX_QUOTA_GOOGLEDRIVE,
    'nextcloud': DEFAULT_MAX_QUOTA_NEXTCLOUD,
    'nextcloudinstitutions': DEFAULT_MAX_QUOTA_NEXTCLOUD_FOR_INSTITUTIONS,
    'onedrivebusiness': DEFAULT_MAX_QUOTA_ONEDRIVE_FOR_OFFICE365,
    'swift': DEFAULT_MAX_QUOTA_OPENSTACK_SWIFT,
    'ociinstitutions': DEFAULT_MAX_QUOTA_ORACLE_CLOUD_INFRASTRUCTURE_FOR_INSTITUTIONS,
    'owncloud': DEFAULT_MAX_QUOTA_OWNCLOUD,
    's3compatinstitutions': DEFAULT_MAX_QUOTA_S3_COMPATIBLE_STORAGE_FOR_INSTITUTIONS,
}
