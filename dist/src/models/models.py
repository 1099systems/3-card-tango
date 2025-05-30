from datetime import datetime
from . import db

class Player(db.Model):
    __tablename__ = 'players'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(255), nullable=False)
    username = db.Column(db.String(255), nullable=True)
    chips = db.Column(db.Integer, default=100)
    is_permanent = db.Column(db.Boolean, default=False)
    last_free_chips = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    game_players = db.relationship('GamePlayer', backref='player', lazy=True)
    chat_messages = db.relationship('ChatMessage', backref='player', lazy=True)

class Table(db.Model):
    __tablename__ = 'tables'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    min_chips = db.Column(db.Integer, nullable=False)
    max_players = db.Column(db.Integer, default=5)
    status = db.Column(db.String(50), default='waiting')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    games = db.relationship('Game', backref='table', lazy=True)

class Game(db.Model):
    __tablename__ = 'games'
    
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('tables.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default='active')
    
    game_players = db.relationship('GamePlayer', backref='game', lazy=True)
    hands = db.relationship('Hand', backref='game', lazy=True)
    chat_messages = db.relationship('ChatMessage', backref='game', lazy=True)

class GamePlayer(db.Model):
    __tablename__ = 'game_players'
    
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    seat_position = db.Column(db.Integer, nullable=False)
    initial_chips = db.Column(db.Integer, nullable=False)
    final_chips = db.Column(db.Integer, nullable=True)

class Hand(db.Model):
    __tablename__ = 'hands'
    
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    hand_number = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    community_cards = db.Column(db.String(255), nullable=True)
    dealer_cards = db.Column(db.String(255), nullable=True)
    
    hand_players = db.relationship('HandPlayer', backref='hand', lazy=True)

class HandPlayer(db.Model):
    __tablename__ = 'hand_players'
    
    id = db.Column(db.Integer, primary_key=True)
    hand_id = db.Column(db.Integer, db.ForeignKey('hands.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    initial_cards = db.Column(db.String(255), nullable=False)
    kept_card = db.Column(db.String(50), nullable=True)
    killed_card = db.Column(db.String(50), nullable=True)
    kicked_card = db.Column(db.String(50), nullable=True)
    turn_card = db.Column(db.String(50), nullable=True)
    final_hand = db.Column(db.String(255), nullable=True)
    bet_amount = db.Column(db.Integer, default=0)
    is_winner = db.Column(db.Boolean, default=False)

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
