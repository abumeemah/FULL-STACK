from flask import Blueprint

tax_bp = Blueprint('tax', __name__, template_folder='templates')

from . import routes