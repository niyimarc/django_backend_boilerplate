from pathlib import Path
# Import os and load_dotenv
import os
from dotenv import load_dotenv
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# this is the path to the html templates 
TEMPLATES_DIR = BASE_DIR / 'templates'

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
DJANGO_SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
SECRET_KEY = DJANGO_SECRET_KEY

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'auth_core',
    'user_profile',
    'collaboration',
    'user_auth_key',
    'subscriptions',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'auth_core.middleware.HMACAuthMiddleware',
    'auth_core.middleware.ApplicationBaseURLValidatorMiddleware',
    "collaboration.middleware.owner_context.OwnerContextMiddleware",
]

ROOT_URLCONF = 'backend_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [TEMPLATES_DIR],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend_project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DB_NAME = os.environ.get('DB_NAME')
DB_USERNAME = os.environ.get('DB_USERNAME')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
HOST = os.environ.get('HOST')
PORT = os.environ.get('PORT')
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': DB_NAME,
        'USER': DB_USERNAME,
        'PASSWORD': DB_PASSWORD,
        'HOST': HOST,
        'PORT': PORT,
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET NAMES 'utf8mb4' COLLATE 'utf8mb4_general_ci'"
        },
        # Connection management
        'CONN_MAX_AGE': 300,         # keep connections alive up to 5 min
        'CONN_HEALTH_CHECKS': True,  # test connection before reusing
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTHENTICATION_BACKENDS = [
    'user_profile.auth_backends.EmailOrUsernameModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]

REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        # 'auth_core.throttling.APIKeyRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        # You can leave empty or set a default if needed
    },
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'auth_core.authentication.APIKeyAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "collaboration.permissions.IsOwner",  # owner-only by default
    ]
}

from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),     
    'REFRESH_TOKEN_LIFETIME': timedelta(days=14),        
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# app informations
BUSINESS_NAME = os.environ.get('BUSINESS_NAME')
BUSINESS_LOGO = os.environ.get('BUSINESS_LOGO')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
CONTACT_EMAIL = os.environ.get('CONTACT_EMAIL')
FROM_EMAIL = f"{BUSINESS_NAME} <{EMAIL_HOST_USER}>"

# hmac key 
HMAC_SECRET_KEY = os.environ.get("HMAC_SECRET_KEY")

# Models used for order
PAYMENT_ORDER_MODEL = 'store.Order'

# paystack keys
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY')
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY')

# Flutterwave keys
FLUTTERWAVE_PUBLIC_KEY = os.environ.get('FLUTTERWAVE_PUBLIC_KEY')
FLUTTERWAVE_SECRET_KEY = os.environ.get('FLUTTERWAVE_SECRET_KEY')

DJANGO_PG_SUCCESS_REDIRECT = ''
DJANGO_PG_FAILURE_REDIRECT = ''

CREDENTIAL_ENCRYPTION_KEYS = {
    "v1": os.environ.get("CREDENTIAL_KEY_V1", "fallback_secret_key_v1"),  # must be 32 bytes base64
}
CREDENTIAL_ENCRYPTION_CURRENT_VERSION = "v1"