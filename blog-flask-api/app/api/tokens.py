from flask import jsonify
from app import db
from app.api import bp
from app.api.auth import basic_auth, token_auth
import secrets
from urllib.parse import urlencode

from flask import request, abort, current_app, url_for
from werkzeug.http import dump_cookie
import requests

from app import db
from app.api.auth import basic_auth, token_auth
from app.email import send_email
from app.models import User, Token
from app.api.schemas import TokenSchema, PasswordResetRequestSchema,PasswordResetSchema, OAuth2Schema, EmptySchema


token_schema = TokenSchema()
oauth2_schema = OAuth2Schema()


def token_response(token):
    headers = {}
    if current_app.config['REFRESH_TOKEN_IN_COOKIE']:
        samesite = 'strict'
        if current_app.config['USE_CORS']:
            samesite = 'none' if not current_app.debug else 'lax'
        headers['Set-Cookie'] = dump_cookie(
            'refresh_token', token.refresh_token,
            path=url_for('tokens.new'), secure=not current_app.debug,
            httponly=True, samesite=samesite)
    return {
        'access_token': token.access_jwt_token,
        'refresh_token': token.refresh_token
        if current_app.config['REFRESH_TOKEN_IN_BODY'] else None    ,
    }, 200, headers


@bp.route('/tokens', methods=['POST'])
@basic_auth.login_required
def new():
    user = basic_auth.current_user()
    token = user.generate_auth_token()
    db.session.add(token)
    Token.clean()  # keep token table clean of old tokens
    db.session.commit()
    return token_schema.dump(token_response(token))
    



@bp.route('/tokens', methods=['POST'])
@basic_auth.login_required
def get_token():
    token = basic_auth.current_user().get_token()
    db.session.commit()
    return jsonify({'token': token})


@bp.route('/tokens', methods=['DELETE'])
@token_auth.login_required
def revoke_token():
    token_auth.current_user().revoke_token()
    db.session.commit()
    return '', 204