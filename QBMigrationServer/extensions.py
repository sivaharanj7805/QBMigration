from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Shared Limiter instance
# This allows blueprints to use decorators before the app is created
limiter = Limiter(key_func=get_remote_address)
