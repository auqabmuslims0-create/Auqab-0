from flask import Blueprint

api_bp = Blueprint('api', __name__)

from . import auth, users, stores, products, orders, admin, helpers, updates, sync
