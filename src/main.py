import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from flask import Flask
from flask_socketio import SocketIO
from src.models import db

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'three_card_tango_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///poker_game.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

timer_config = {
    'classification': 7,
    'betting': 7,
    'next_player': 7,
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
