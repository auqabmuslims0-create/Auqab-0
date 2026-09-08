from flask import Blueprint

admin_bp = Blueprint('admin', __name__)

from . import users, stores, orders, subscriptions, delivery_persons, finance, chats, settings, payments, dashboard
