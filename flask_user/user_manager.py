""" Flask-User is a customizable user account management extension for Flask.
"""

# Copyright (c) 2013 by Ling Thio
# Author: Ling Thio (ling.thio@gmail.com)
# License: Simplified BSD License, see LICENSE.txt for more details.



from flask import Blueprint, current_app, Flask, render_template
from flask_login import LoginManager, current_user

from flask_user.email_manager import EmailManager
from flask_user.password_manager import PasswordManager
from flask_user.token_manager import TokenManager

from . import forms
from . import translations
from . import user_manager_views
from .translations import get_translations
from .user_manager_settings import UserManager__Settings
from .user_manager_views import UserManager__Views, init_views

__version__ = '0.9'


def _call_or_get(function_or_property):
    return function_or_property() if callable(function_or_property) else function_or_property


def _flask_user_context_processor():
    """ Make 'user_manager' available to Jinja2 templates"""
    return dict(
        user_manager=current_app.user_manager,
        call_or_get=_call_or_get)


# Define custom Exception
class ConfigurationError(Exception):
    pass




# The UserManager is implemented across several source code files.
# Mixins are used to aggregate all member functions into the one UserManager class for ease of customization.
class UserManager(UserManager__Settings, UserManager__Views):
    """ Customizable User Authentication and Management.
    """

    # ***** Initialization methods *****

    def __init__(self, app, db, UserClass, **kwargs):
        """
        Args:
            app(Flask): The Flask application instance.
            db: An Object-Database Mapper instance such as SQLAlchemy or MongoAlchemy.
            UserClass: The User class (*not* an instance!).

        Keyword Args:
            UserEmailClass: The optional UserEmail class (*not* an instance!).
                Required for the 'multiple email_templates per user' feature.
            UserInvitationClass: The optional UserInvitation class (*not* an instance!).
                Required for the 'register by invitation' feature.

        Example:
            ``user_manager = UserManager(app, db, User)``
        """

        #see http://flask.pocoo.org/docs/0.12/extensiondev/#the-extension-code """
        self.app = app
        if app:
            self.init_app(app, db, UserClass, **kwargs)

    def init_app(self, app, db, UserClass,
                 UserInvitationClass=None,
                 UserEmailClass=None,
                 # Validators
                username_validator=forms.username_validator,
                 password_validator=forms.password_validator,
                 # View functions
                render_function=render_template,
                 change_password_view_function=user_manager_views.change_password,
                 change_username_view_function=user_manager_views.change_username,
                 confirm_email_view_function=user_manager_views.confirm_email,
                 email_action_view_function=user_manager_views.email_action,
                 forgot_password_view_function=user_manager_views.forgot_password,
                 login_view_function=user_manager_views.login,
                 logout_view_function=user_manager_views.logout,
                 manage_emails_view_function=user_manager_views.manage_emails,
                 register_view_function=user_manager_views.register,
                 resend_email_confirmation_view_function = user_manager_views.resend_email_confirmation,
                 reset_password_view_function = user_manager_views.reset_password,
                 unconfirmed_email_view_function = user_manager_views.unconfirmed,
                 unauthenticated_view_function = user_manager_views.unauthenticated,
                 unauthorized_view_function = user_manager_views.unauthorized,
                 edit_user_profile_view_function = user_manager_views.edit_user_profile,
                 invite_user_view_function = user_manager_views.invite_user,
                 # Misc
                 login_manager = None,
                 password_crypt_context = None,
                 make_safe_url_function = user_manager_views.make_safe_url):

        # See http://flask.pocoo.org/docs/0.12/extensiondev/#the-extension-code
        # Perform Class type checking
        if not isinstance(app, Flask):
            raise TypeError("flask_user.UserManager.init_app(): Parameter 'app' is an instance of class '%s' "
                            "instead of a subclass of class 'flask.Flask'."
                            % app.__class__.__name__)

        # Bind Flask-User to app
        app.user_manager = self

        # Save DB and Class params
        self.db = db
        self.UserClass = UserClass
        self.UserEmailClass = UserEmailClass
        self.UserInvitationClass = UserInvitationClass

        # For each 'USER_...' property: load settings from application config.
        for attrib_name in dir(self):
            if attrib_name[0:5] == 'USER_':
                default_value = getattr(UserManager, attrib_name)
                setattr(self, attrib_name, app.config.get(attrib_name, default_value))

        # Set default forms
        self.add_email_form = forms.AddEmailForm
        self.change_password_form = forms.ChangePasswordForm
        self.change_username_form = forms.ChangeUsernameForm
        self.edit_user_profile_form = forms.EditUserProfileForm
        self.forgot_password_form = forms.ForgotPasswordForm
        self.invite_user_form = forms.InviteUserForm
        self.login_form = forms.LoginForm
        self.register_form = forms.RegisterUserForm
        self.resend_email_confirmation_form = forms.ResendEmailConfirmationForm
        self.reset_password_form = forms.ResetPasswordForm

        # Configure a DbAdapter based on the class of the 'db' parameter
        self.db_adapter = None
        # Check if db is a SQLAlchemy instance
        if self.db_adapter is None:
            try:
                from flask_sqlalchemy import SQLAlchemy
                if isinstance(db, SQLAlchemy):
                    from .db_adapters import SQLAlchemyDbAdapter
                    self.db_adapter = SQLAlchemyDbAdapter(db)
            except:
                pass
        # Check if db is a MongoAlchemy instance
        if self.db_adapter is None:
            try:
                from flask_mongoalchemy import MongoAlchemy
                if isinstance(db, MongoAlchemy):
                    from .db_adapters import MongoAlchemyDbAdapter
                    self.db_adapter = MongoAlchemyDbAdapter(db)
            except:
                pass

        # Configure SMTPEmailMailer as the default email mailer
        from .email_mailers.smtp_email_mailer import SMTPEmailMailer
        self.email_mailer = SMTPEmailMailer(app)

        # Initialize Translations -- Only if Flask-Babel has been installed
        if hasattr(app.jinja_env, 'install_gettext_callables'):
            app.jinja_env.install_gettext_callables(
                    lambda x: get_translations().ugettext(x),
                    lambda s, p, n: get_translations().ungettext(s, p, n),
                    newstyle=True)
        else:
            app.jinja_env.add_extension('jinja2.ext.i18n')
            app.jinja_env.install_null_translations()

        # Allow CustomUserManager to customize settings and methods
        self.customize(app)

        # Make sure the settings are valid -- raise ConfigurationError if not
        self._check_settings()

        self.init_urls(app)

        # Validators
        self._create_default_attr('username_validator', username_validator)
        self._create_default_attr('password_validator', password_validator)
        # View functions
        self._create_default_attr('render_function', render_function)
        self._create_default_attr('change_password_view_function', change_password_view_function)
        self._create_default_attr('change_username_view_function', change_username_view_function)
        self._create_default_attr('confirm_email_view_function', confirm_email_view_function)
        self._create_default_attr('email_action_view_function', email_action_view_function)
        self._create_default_attr('forgot_password_view_function', forgot_password_view_function)
        self._create_default_attr('login_view_function', login_view_function)
        self._create_default_attr('logout_view_function', logout_view_function)
        self._create_default_attr('manage_emails_view_function', manage_emails_view_function)
        self._create_default_attr('register_view_function', register_view_function)
        self._create_default_attr('resend_email_confirmation_view_function', resend_email_confirmation_view_function)
        self._create_default_attr('reset_password_view_function', reset_password_view_function)
        self._create_default_attr('unconfirmed_email_view_function', unconfirmed_email_view_function)
        self._create_default_attr('unauthenticated_view_function', unauthenticated_view_function)
        self._create_default_attr('unauthorized_view_function', unauthorized_view_function)
        self._create_default_attr('edit_user_profile_view_function', edit_user_profile_view_function)
        self._create_default_attr('invite_user_view_function', invite_user_view_function)
        # Misc
        self._create_default_attr('login_manager', login_manager)
        self._create_default_attr('password_crypt_context', password_crypt_context)
        self._create_default_attr('make_safe_url_function', make_safe_url_function)

        # Setup PasswordManager
        self.password_manager = PasswordManager(self.USER_PASSWORD_HASH)

        # Setup EmailManager
        self.email_manager = EmailManager(self)

        # Setup TokenManager
        self.token_manager = TokenManager(app.config['SECRET_KEY'])

        # Setup default LoginManager using Flask-Login
        if not self.login_manager:
            self.login_manager = LoginManager(app)
            self.login_manager.login_view = 'user.login'

            # Flask-Login calls this function to retrieve a User record by user ID.
            # Note: user_id is a UNICODE string returned by UserMixin.get_id().
            # See https://flask-login.readthedocs.org/en/latest/#how-it-works
            @self.login_manager.user_loader
            def load_user_by_user_token(user_token):
                user = self.UserClass.get_user_by_token(user_token, 3600)
                return user


        # Even though we do not make use of this Blueprint, we must create and
        # register one to tell Flask to include the app/template/flask_user directory
        # when searching for template files.
        blueprint = Blueprint('flask_user', __name__, template_folder='templates')
        app.register_blueprint(blueprint)

        # Add URL routes
        init_views(app, self)

        # Add context processor
        app.context_processor(_flask_user_context_processor)

        # Prepare for translations
        _ = translations.gettext


    def customize(self, app):
        """ Override this method to configure custom Flask-User behavior.

        ::

            # Customize Flask-User
            class CustomUserManager(UserManager):

                def customize():

                    # Add custom settings here
                    # Note: This can also be set in the application config file.
                    self.USER_ENABLE_EMAIL = True
                    self.USER_ENABLE_USERNAME = False

                    # Add custom behavior here
                    from some.path import CustomJwtTokenManager
                    self.token_manager = CustomJwtTokenManager()
                    from some.path import CustomEmailMailer
                    self.email_mailer = CustomEmailMailer()

            # Setup Flask-User
            user_manager = CustomUserManager(app, db, User)
        """

        pass


    # ***** Private methods *****


    def _create_default_attr(self, attribute_name, default_value):
        if not hasattr(self, attribute_name):
            setattr(self, attribute_name, default_value)


    def _check_settings(self):
        """Verify required settings. Produce a helpful error messages for missing settings."""
        if self.db_adapter is None:
            raise ConfigurationError('You must specify a DbAdapter interface or install Flask-SQLAlchemy or FlaskMongAlchemy.')

        if self.USER_ENABLE_INVITE_USER and not self.UserInvitationClass:
            raise ConfigurationError(
                'Missing UserInvitationClass with USER_ENABLE_INVITE_USER=True setting.')

        # Disable settings that rely on a feature setting that's not enabled

        # USER_ENABLE_REGISTER=True must have USER_ENABLE_USERNAME=True or USER_ENABLE_EMAIL=True.
        if not self.USER_ENABLE_USERNAME and not self.USER_ENABLE_EMAIL:
            self.USER_ENABLE_REGISTER = False
        
        # Settings that depend on USER_ENABLE_EMAIL
        if not self.USER_ENABLE_EMAIL:
            self.USER_ENABLE_CONFIRM_EMAIL = False
            self.USER_ENABLE_MULTIPLE_EMAILS = False
            self.USER_ENABLE_FORGOT_PASSWORD = False
            self.USER_SEND_PASSWORD_CHANGED_EMAIL = False
            self.USER_SEND_REGISTERED_EMAIL = False
            self.USER_SEND_USERNAME_CHANGED_EMAIL = False
            self.USER_REQUIRE_INVITATION = False

        # Settings that depend on USER_ENABLE_USERNAME
        if not self.USER_ENABLE_USERNAME:
            self.USER_ENABLE_CHANGE_USERNAME = False


    def get_user_by_id(self, user_id):
        """Retrieve a User by ID."""
        return self.db_adapter.get_object(self.UserClass, user_id)

    def get_user_email_by_id(self, user_email_id):
        """Retrieve a UserEmail by ID."""
        return self.db_adapter.get_object(self.UserEmailClass, user_email_id)

    def find_user_by_username(self, username):
        """Retrieve a User by username."""
        return self.db_adapter.ifind_first_object(self.UserClass, username=username)

    def find_user_by_email(self, email):
        """Retrieve a User by email."""
        if self.UserEmailClass:
            user_email = self.db_adapter.ifind_first_object(self.UserEmailClass, email=email)
            user = user_email.user if user_email else None
        else:
            user_email = None
            user = self.db_adapter.ifind_first_object(self.UserClass, email=email)

        return (user, user_email)

    def email_is_available(self, new_email):
        """Check if ``new_email`` is available.

        | Returns True if ``new_email`` does not exist or belongs to the current user.
        | Return False otherwise.
        """

        user, user_email = self.find_user_by_email(new_email)
        return (user==None)

    def username_is_available(self, new_username):
        """Check if ``new_username`` is available.

        | Returns True if ``new_username`` does not exist or belongs to the current user.
        | Return False otherwise.
        """

        # Allow user to change username to the current username
        if _call_or_get(current_user.is_authenticated):
            current_username = current_user.username
            if new_username == current_username:
                return True
        # See if new_username is available
        return self.find_user_by_username(new_username)==None

    def get_primary_user_email(self, user):
        """Retrieve the primary User email for the 'multiple email_templates per user' feature."""
        db_adapter = self.db_adapter
        if self.UserEmailClass:
            user_email = db_adapter.find_first_object(self.UserEmailClass,
                                                      user_id=user.id,
                                                      is_primary=True)
            return user_email
        else:
            return user


    def _add_url_routes(self, app):
        """ Add URL Routes"""
        app.add_url_rule(self.USER_LOGIN_URL, 'user.login', self.login_view_function, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_LOGOUT_URL, 'user.logout', self.logout_view_function, methods=['GET', 'POST'])
        if self.USER_ENABLE_CONFIRM_EMAIL:
            app.add_url_rule(self.USER_CONFIRM_EMAIL_URL, 'user.confirm_email', self.confirm_email_view_function)
            app.add_url_rule(self.USER_RESEND_EMAIL_CONFIRMATION_URL, 'user.resend_email_confirmation', self.resend_email_confirmation_view_function, methods=['GET', 'POST'])
        if self.USER_ENABLE_CHANGE_PASSWORD:
            app.add_url_rule(self.USER_CHANGE_PASSWORD_URL, 'user.change_password', self.change_password_view_function, methods=['GET', 'POST'])
        if self.USER_ENABLE_CHANGE_USERNAME:
            app.add_url_rule(self.USER_CHANGE_USERNAME_URL, 'user.change_username', self.change_username_view_function, methods=['GET', 'POST'])
        if self.USER_ENABLE_FORGOT_PASSWORD:
            app.add_url_rule(self.USER_FORGOT_PASSWORD_URL, 'user.forgot_password', self.forgot_password_view_function, methods=['GET', 'POST'])
            app.add_url_rule(self.USER_RESET_PASSWORD_URL, 'user.reset_password', self.reset_password_view_function, methods=['GET', 'POST'])
        if self.USER_ENABLE_REGISTER:
            app.add_url_rule(self.USER_REGISTER_URL, 'user.register', self.register_view_function, methods=['GET', 'POST'])
        if self.UserEmailClass:
            app.add_url_rule(self.USER_EMAIL_ACTION_URL,  'user.email_action',  self.email_action_view_function)
            app.add_url_rule(self.USER_MANAGE_EMAILS_URL, 'user.manage_emails', self.manage_emails_view_function, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_EDIT_USER_PROFILE_URL,  'user.edit_user_profile',  self.edit_user_profile_view_function,  methods=['GET', 'POST'])
        if self.USER_ENABLE_INVITE_USER:
            app.add_url_rule(self.USER_INVITE_USER_URL, 'user.invite_user', self.invite_user_view_function, methods=['GET', 'POST'])

    def init_urls(self, app):
        # Stubs are needed because url_rules call functions (and not methods with the extra 'self' parameter)
        def change_password_stub():
            return self.change_password_view()

        def change_username_stub():
            return self.change_username_view()

        def confirm_email_stub():
            return self.confirm_email_view()

        def edit_user_profile_stub():
            return self.edit_user_profile_view()

        def email_action_stub():
            return self.email_action_view()

        def forgot_password_stub():
            return self.forgot_password_view()

        def manage_emails_stub():
            return self.manage_emails_view()

        def invite_user_stub():
            return self.invite_user_view()

        def login_stub():
            return self.login_view()

        def logout_stub():
            return self.logout_view()

        def register_stub():
            return self.register_view()

        def resend_email_confirmation_stub():
            return self.resend_email_confirmation_view()

        def reset_password_stub():
            return self.reset_password_view()

        """ Add URL Routes"""
        app.add_url_rule(self.USER_CHANGE_PASSWORD_URL, 'user.change_password', change_password_stub, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_CHANGE_USERNAME_URL, 'user.change_username', change_username_stub, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_CONFIRM_EMAIL_URL, 'user.confirm_email', confirm_email_stub)
        app.add_url_rule(self.USER_EDIT_USER_PROFILE_URL, 'user.edit_user_profile', edit_user_profile_stub, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_EMAIL_ACTION_URL, 'user.email_action', email_action_stub)
        app.add_url_rule(self.USER_FORGOT_PASSWORD_URL, 'user.forgot_password', forgot_password_stub, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_INVITE_USER_URL, 'user.invite_user', invite_user_stub, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_LOGIN_URL, 'user.login', login_stub, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_LOGOUT_URL, 'user.logout', logout_stub, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_MANAGE_EMAILS_URL, 'user.manage_emails', manage_emails_stub, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_REGISTER_URL, 'user.register', register_stub, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_RESEND_EMAIL_CONFIRMATION_URL, 'user.resend_email_confirmation', resend_email_confirmation_stub, methods=['GET', 'POST'])
        app.add_url_rule(self.USER_RESET_PASSWORD_URL, 'user.reset_password', reset_password_stub, methods=['GET', 'POST'])