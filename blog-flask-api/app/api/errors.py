from flask import jsonify, current_app
from werkzeug.http import HTTP_STATUS_CODES
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException, InternalServerError
from app.api import bp

def error_response(status_code, message=None):
    payload = {'error': HTTP_STATUS_CODES.get(status_code, 'Unknown error')}
    if message:
        payload['message'] = message
    response = jsonify(payload)
    response.status_code = status_code
    return response



def bad_request(message):
    return error_response(400, message)

# @bp.app_errorhandler(HTTPException)
# def http_error(error):
#     return {
#         'code': error.code,
#         'message': error.name,
#         'description': error.description,
#     }, error.code


# @bp.app_errorhandler(IntegrityError)
# def sqlalchemy_integrity_error(error):  # pragma: no cover
#     return {
#         'code': 400,
#         'message': 'Database integrity error',
#         'description': str(error.orig),
#     }, 400


# @bp.app_errorhandler(SQLAlchemyError)
# def sqlalchemy_error(error):  # pragma: no cover
#     if current_app.config['DEBUG'] is True:
#         return {
#             'code': InternalServerError.code,
#             'message': 'Database error',
#             'description': str(error),
#         }, 500
#     else:
#         return {
#             'code': InternalServerError.code,
#             'message': InternalServerError().name,
#             'description': InternalServerError.description,
#         }, 500