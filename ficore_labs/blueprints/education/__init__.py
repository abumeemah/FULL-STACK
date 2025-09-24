from flask import Blueprint

education_bp = Blueprint('education', __name__, template_folder='templates')

from . import routes