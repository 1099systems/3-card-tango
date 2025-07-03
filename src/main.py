import sys
import os
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from flask import Flask
from flask_socketio import SocketIO
from src.models import db
import uuid

load_dotenv()  # Load from .env file

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL') + '_' +  uuid.uuid4().hex + '.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

timer_config = {
    'card_draw': 3,
    'choose_trash': 30,
    'choose_tango': 30,
    'turn_draw': 10,
    'betting': 30,
    'board_reveal': 10,
    'next_hand': 10,
}

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize database
db.init_app(app)

# Card utilities
import card_utils

# Game state management
game_states = {}  # Table ID -> Game State


import routes
import socket_handler
import helpers

# Create database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
