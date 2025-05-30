import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, request, jsonify, render_template, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from src.models import db
from src.models.models import Player, Table, Game, GamePlayer, Hand, HandPlayer, ChatMessage
import uuid
from datetime import datetime, timedelta
import json
import random

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'three_card_tango_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///poker_game.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize database
db.init_app(app)

# Card utilities
SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

def create_deck():
    """Create a standard deck of 52 cards."""
    return [{'rank': rank, 'suit': suit} for suit in SUITS for rank in RANKS]

def shuffle_deck(deck):
    """Shuffle the deck."""
    random.shuffle(deck)
    return deck

def deal_cards(deck, num_cards):
    """Deal a specified number of cards from the deck."""
    return [deck.pop() for _ in range(num_cards)]

def card_to_string(card):
    """Convert card object to string representation."""
    return f"{card['rank']}_of_{card['suit']}"

def string_to_card(card_str):
    """Convert string representation to card object."""
    rank, suit = card_str.split('_of_')
    return {'rank': rank, 'suit': suit}

def cards_to_string(cards):
    """Convert list of card objects to comma-separated string."""
    return ','.join([card_to_string(card) for card in cards])

def string_to_cards(cards_str):
    """Convert comma-separated string to list of card objects."""
    if not cards_str:
        return []
    return [string_to_card(card_str) for card_str in cards_str.split(',')]

# Game state management
game_states = {}  # Table ID -> Game State

# Routes
@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')

@app.route('/api/player', methods=['POST'])
def create_player():
    """Create a new player or retrieve existing player by session ID."""
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        session_id = str(uuid.uuid4())
    
    player = Player.query.filter_by(session_id=session_id).first()
    
    if not player:
        player = Player(session_id=session_id, chips=100)
        db.session.add(player)
        db.session.commit()
    
    return jsonify({
        'id': player.id,
        'session_id': player.session_id,
        'username': player.username,
        'chips': player.chips,
        'is_permanent': player.is_permanent
    })

@app.route('/api/player/username', methods=['POST'])
def set_username():
    """Set a permanent username for a player."""
    data = request.json
    session_id = data.get('session_id')
    username = data.get('username')
    
    if not session_id or not username:
        return jsonify({'error': 'Session ID and username are required'}), 400
    
    player = Player.query.filter_by(session_id=session_id).first()
    
    if not player:
        return jsonify({'error': 'Player not found'}), 404
    
    player.username = username
    player.is_permanent = True
    db.session.commit()
    
    return jsonify({
        'id': player.id,
        'session_id': player.session_id,
        'username': player.username,
        'chips': player.chips,
        'is_permanent': player.is_permanent
    })

@app.route('/api/player/chips', methods=['POST'])
def claim_chips():
    """Claim free chips if eligible (less than 100 chips and hasn't claimed in the last hour)."""
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Session ID is required'}), 400
    
    player = Player.query.filter_by(session_id=session_id).first()
    
    if not player:
        return jsonify({'error': 'Player not found'}), 404
    
    # Check if player is eligible for free chips
    if player.chips >= 100:
        return jsonify({'error': 'Player has 100 or more chips already'}), 400
    
    current_time = datetime.utcnow()
    if player.last_free_chips and (current_time - player.last_free_chips) < timedelta(hours=1):
        time_left = timedelta(hours=1) - (current_time - player.last_free_chips)
        minutes_left = int(time_left.total_seconds() / 60)
        return jsonify({'error': f'Must wait {minutes_left} more minutes to claim free chips'}), 400
    
    # Give free chips
    player.chips = 100
    player.last_free_chips = current_time
    db.session.commit()
    
    return jsonify({
        'id': player.id,
        'session_id': player.session_id,
        'username': player.username,
        'chips': player.chips,
        'is_permanent': player.is_permanent
    })

# SocketIO events
@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    print('Client disconnected')

@socketio.on('join_table')
def handle_join_table(data):
    """Handle player joining a table."""
    session_id = data.get('session_id')
    
    if not session_id:
        emit('error', {'message': 'Session ID is required'})
        return
    
    player = Player.query.filter_by(session_id=session_id).first()
    
    if not player:
        emit('error', {'message': 'Player not found'})
        return
    
    # Find or create a suitable table based on player's chips
    suitable_table = find_suitable_table(player.chips)
    
    # Join the table room
    join_room(f'table_{suitable_table.id}')
    
    # Check if player is already at this table
    existing_game_player = GamePlayer.query.join(Game).filter(
        GamePlayer.player_id == player.id,
        Game.table_id == suitable_table.id,
        Game.status == 'active'
    ).first()
    
    if not existing_game_player:
        # Add player to the table
        active_game = Game.query.filter_by(table_id=suitable_table.id, status='active').first()
        
        if not active_game:
            # Create a new game if none exists
            active_game = Game(table_id=suitable_table.id)
            db.session.add(active_game)
            db.session.commit()
            
            # Initialize game state
            game_states[suitable_table.id] = {
                'game_id': active_game.id,
                'players': [],
                'state': 'waiting',
                'deck': shuffle_deck(create_deck()),
                'pot': 0,
                'current_hand': None,
                'timer': None,
                'chat_enabled': True
            }
        
        # Find an available seat
        existing_seats = [gp.seat_position for gp in GamePlayer.query.filter_by(game_id=active_game.id)]
        available_seats = [i for i in range(suitable_table.max_players) if i not in existing_seats]
        
        if not available_seats:
            emit('error', {'message': 'Table is full'})
            return
        
        seat_position = available_seats[0]
        
        # Add player to the game
        game_player = GamePlayer(
            game_id=active_game.id,
            player_id=player.id,
            seat_position=seat_position,
            initial_chips=player.chips
        )
        db.session.add(game_player)
        db.session.commit()
        
        # Update game state
        game_state = game_states.get(suitable_table.id, {})
        game_state['players'].append({
            'id': player.id,
            'username': player.username or f'Player {player.id}',
            'chips': player.chips,
            'seat': seat_position,
            'status': 'active'
        })
        
        # Check if we should start the game
        if len(game_state['players']) >= 2 and game_state['state'] == 'waiting':
            game_state['state'] = 'starting'
            game_state['timer'] = 10  # 10 second countdown to start
            socketio.start_background_task(countdown_to_start, suitable_table.id)
    
    # Send updated game state to all players at the table
    emit('game_state_update', game_states.get(suitable_table.id, {}), room=f'table_{suitable_table.id}')
    
    # Notify other players
    emit('player_joined', {
        'id': player.id,
        'username': player.username or f'Player {player.id}',
        'chips': player.chips
    }, room=f'table_{suitable_table.id}', include_self=False)
    
    return {
        'table_id': suitable_table.id,
        'game_id': game_states.get(suitable_table.id, {}).get('game_id'),
        'min_chips': suitable_table.min_chips
    }

@socketio.on('leave_table')
def handle_leave_table(data):
    """Handle player leaving a table."""
    session_id = data.get('session_id')
    table_id = data.get('table_id')
    
    if not session_id or not table_id:
        emit('error', {'message': 'Session ID and table ID are required'})
        return
    
    player = Player.query.filter_by(session_id=session_id).first()
    
    if not player:
        emit('error', {'message': 'Player not found'})
        return
    
    # Remove player from the game
    game_player = GamePlayer.query.join(Game).filter(
        GamePlayer.player_id == player.id,
        Game.table_id == table_id,
        Game.status == 'active'
    ).first()
    
    if game_player:
        # Update player's chips
        player.chips = game_player.final_chips or game_player.initial_chips
        db.session.commit()
        
        # Update game state
        game_state = game_states.get(int(table_id), {})
        if game_state:
            game_state['players'] = [p for p in game_state['players'] if p['id'] != player.id]
            
            # If no players left, end the game
            if not game_state['players']:
                game = Game.query.get(game_state['game_id'])
                if game:
                    game.status = 'ended'
                    game.end_time = datetime.utcnow()
                    db.session.commit()
                    
                    # Remove game state
                    game_states.pop(int(table_id), None)
            else:
                # Send updated game state to remaining players
                emit('game_state_update', game_state, room=f'table_{table_id}')
    
    # Leave the table room
    leave_room(f'table_{table_id}')
    
    # Notify other players
    emit('player_left', {
        'id': player.id,
        'username': player.username or f'Player {player.id}'
    }, room=f'table_{table_id}')
    
    return {'success': True}

@socketio.on('player_action')
def handle_player_action(data):
    """Handle player game actions (keep/kill/kick, check/bet/fold)."""
    session_id = data.get('session_id')
    table_id = data.get('table_id')
    action_type = data.get('action_type')
    action_data = data.get('action_data', {})
    
    if not session_id or not table_id or not action_type:
        emit('error', {'message': 'Session ID, table ID, and action type are required'})
        return
    
    player = Player.query.filter_by(session_id=session_id).first()
    
    if not player:
        emit('error', {'message': 'Player not found'})
        return
    
    game_state = game_states.get(int(table_id), {})
    
    if not game_state:
        emit('error', {'message': 'Game not found'})
        return
    
    # Process action based on game state and action type
    if game_state['state'] == 'classification':
        if action_type in ['keep', 'kill', 'kick']:
            process_classification_action(player.id, int(table_id), action_type, action_data)
    elif game_state['state'] in ['pre_kick_betting', 'post_turn_betting', 'final_betting']:
        if action_type in ['check', 'bet', 'fold']:
            process_betting_action(player.id, int(table_id), action_type, action_data)
    else:
        emit('error', {'message': f'Action {action_type} not allowed in current game state'})
        return
    
    # Send updated game state to all players at the table
    emit('game_state_update', game_states.get(int(table_id), {}), room=f'table_{table_id}')
    
    return {'success': True}

@socketio.on('chat_message')
def handle_chat_message(data):
    """Handle chat messages."""
    session_id = data.get('session_id')
    table_id = data.get('table_id')
    message = data.get('message')
    
    if not session_id or not table_id or not message:
        emit('error', {'message': 'Session ID, table ID, and message are required'})
        return
    
    player = Player.query.filter_by(session_id=session_id).first()
    
    if not player:
        emit('error', {'message': 'Player not found'})
        return
    
    game_state = game_states.get(int(table_id), {})
    
    if not game_state:
        emit('error', {'message': 'Game not found'})
        return
    
    # Check if chat is enabled
    if not game_state.get('chat_enabled', True):
        emit('error', {'message': 'Chat is currently disabled'})
        return
    
    # Save chat message
    game = Game.query.get(game_state['game_id'])
    if game:
        chat_message = ChatMessage(
            game_id=game.id,
            player_id=player.id,
            message=message
        )
        db.session.add(chat_message)
        db.session.commit()
    
    # Broadcast message to all players at the table
    emit('chat_message', {
        'player_id': player.id,
        'username': player.username or f'Player {player.id}',
        'message': message,
        'timestamp': datetime.utcnow().isoformat()
    }, room=f'table_{table_id}')
    
    return {'success': True}

# Helper functions
def find_suitable_table(chips):
    """Find or create a suitable table based on player's chips."""
    # Define table tiers
    tiers = [
        {'min_chips': 100, 'name': 'Beginner Table'},
        {'min_chips': 500, 'name': 'Intermediate Table'},
        {'min_chips': 1000, 'name': 'Advanced Table'},
        {'min_chips': 2000, 'name': 'Expert Table'}
    ]
    
    # Find the highest tier the player qualifies for
    suitable_tier = None
    for tier in reversed(tiers):
        if chips >= tier['min_chips']:
            suitable_tier = tier
            break
    
    if not suitable_tier:
        suitable_tier = tiers[0]  # Default to beginner table
    
    # Find an available table in this tier
    available_table = Table.query.filter_by(
        min_chips=suitable_tier['min_chips'],
        status='waiting'
    ).first()
    
    if not available_table:
        # Create a new table
        available_table = Table(
            name=f"{suitable_tier['name']} #{random.randint(1000, 9999)}",
            min_chips=suitable_tier['min_chips']
        )
        db.session.add(available_table)
        db.session.commit()
    
    return available_table

def countdown_to_start(table_id):
    """Countdown to start the game."""
    table_id = int(table_id)
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] != 'starting':
        return
    
    while game_state['timer'] > 0:
        socketio.sleep(1)
        game_state['timer'] -= 1
        socketio.emit('timer_update', {'timer': game_state['timer']}, room=f'table_{table_id}')
    
    # Start the game
    start_game(table_id)

def start_game(table_id):
    """Start a new game at the table."""
    table_id = int(table_id)
    game_state = game_states.get(table_id)
    
    if not game_state:
        return
    
    # Update game state
    game_state['state'] = 'classification'
    game_state['timer'] = 7  # 7 seconds for classification decisions
    game_state['chat_enabled'] = False  # Disable chat during gameplay
    
    # Deal cards to players
    for player in game_state['players']:
        player['cards'] = deal_cards(game_state['deck'], 3)
        player['decisions'] = {'keep': None, 'kill': None, 'kick': None}
    
    # Create a new hand
    game = Game.query.get(game_state['game_id'])
    if game:
        hand = Hand(
            game_id=game.id,
            hand_number=1  # First hand
        )
        db.session.add(hand)
        db.session.commit()
        
        # Save initial cards for each player
        for player in game_state['players']:
            hand_player = HandPlayer(
                hand_id=hand.id,
                player_id=player['id'],
                initial_cards=cards_to_string(player['cards'])
            )
            db.session.add(hand_player)
        
        db.session.commit()
        
        game_state['current_hand'] = hand.id
    
    # Start classification timer
    socketio.start_background_task(classification_timer, table_id)
    
    # Send updated game state to all players
    socketio.emit('game_state_update', game_state, room=f'table_{table_id}')
    socketio.emit('game_started', {}, room=f'table_{table_id}')

def classification_timer(table_id):
    """Timer for classification phase."""
    table_id = int(table_id)
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] != 'classification':
        return
    
    while game_state['timer'] > 0:
        socketio.sleep(1)
        game_state['timer'] -= 1
        socketio.emit('timer_update', {'timer': game_state['timer']}, room=f'table_{table_id}')
    
    # Auto-decide for players who haven't made all decisions
    for player in game_state['players']:
        if None in [player['decisions']['keep'], player['decisions']['kill'], player['decisions']['kick']]:
            # Make random decisions for missing actions
            remaining_indices = [i for i in range(3) if i not in [
                player['decisions']['keep'],
                player['decisions']['kill'],
                player['decisions']['kick']
            ]]
            
            if player['decisions']['keep'] is None and remaining_indices:
                player['decisions']['keep'] = remaining_indices.pop(0)
            
            if player['decisions']['kill'] is None and remaining_indices:
                player['decisions']['kill'] = remaining_indices.pop(0)
            
            if player['decisions']['kick'] is None and remaining_indices:
                player['decisions']['kick'] = remaining_indices.pop(0)
            
            # Update database
            hand = Hand.query.get(game_state['current_hand'])
            if hand:
                hand_player = HandPlayer.query.filter_by(
                    hand_id=hand.id,
                    player_id=player['id']
                ).first()
                
                if hand_player:
                    hand_player.kept_card = card_to_string(player['cards'][player['decisions']['keep']])
                    hand_player.killed_card = card_to_string(player['cards'][player['decisions']['kill']])
                    hand_player.kicked_card = card_to_string(player['cards'][player['decisions']['kick']])
                    db.session.commit()
    
    # Move to pre-kick betting
    game_state['state'] = 'pre_kick_betting'
    game_state['timer'] = 7  # 7 seconds for betting
    game_state['current_bet'] = 0
    game_state['current_player_index'] = 0
    
    # Start betting timer
    socketio.start_background_task(betting_timer, table_id)
    
    # Send updated game state to all players
    socketio.emit('game_state_update', game_state, room=f'table_{table_id}')

def betting_timer(table_id):
    """Timer for betting phases."""
    table_id = int(table_id)
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] not in ['pre_kick_betting', 'post_turn_betting', 'final_betting']:
        return
    
    current_state = game_state['state']
    
    while game_state['timer'] > 0 and game_state['state'] == current_state:
        socketio.sleep(1)
        game_state['timer'] -= 1
        socketio.emit('timer_update', {'timer': game_state['timer']}, room=f'table_{table_id}')
    
    # If still in the same state, auto-action for current player
    if game_state['state'] == current_state:
        current_player = game_state['players'][game_state['current_player_index']]
        
        # Default to fold if there's a bet, check if no bet
        if game_state['current_bet'] > 0:
            process_betting_action(current_player['id'], table_id, 'fold', {})
        else:
            process_betting_action(current_player['id'], table_id, 'check', {})
    
    # Send updated game state to all players
    socketio.emit('game_state_update', game_state, room=f'table_{table_id}')

def process_classification_action(player_id, table_id, action_type, action_data):
    """Process a classification action (keep/kill/kick)."""
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] != 'classification':
        return False
    
    # Find the player
    player = next((p for p in game_state['players'] if p['id'] == player_id), None)
    
    if not player:
        return False
    
    card_index = action_data.get('card_index')
    
    if card_index is None or card_index < 0 or card_index > 2:
        return False
    
    # Check if this action conflicts with previous decisions
    if player['decisions'][action_type] is not None:
        # Remove the card from previous decision
        for decision_type in ['keep', 'kill', 'kick']:
            if player['decisions'][decision_type] == card_index:
                player['decisions'][decision_type] = None
    
    # Set the new decision
    player['decisions'][action_type] = card_index
    
    # Update database if all decisions are made
    if None not in [player['decisions']['keep'], player['decisions']['kill'], player['decisions']['kick']]:
        hand = Hand.query.get(game_state['current_hand'])
        if hand:
            hand_player = HandPlayer.query.filter_by(
                hand_id=hand.id,
                player_id=player_id
            ).first()
            
            if hand_player:
                hand_player.kept_card = card_to_string(player['cards'][player['decisions']['keep']])
                hand_player.killed_card = card_to_string(player['cards'][player['decisions']['kill']])
                hand_player.kicked_card = card_to_string(player['cards'][player['decisions']['kick']])
                db.session.commit()
    
    # Check if all players have made all decisions
    all_decisions_made = True
    for p in game_state['players']:
        if None in [p['decisions']['keep'], p['decisions']['kill'], p['decisions']['kick']]:
            all_decisions_made = False
            break
    
    if all_decisions_made:
        # Move to pre-kick betting
        game_state['state'] = 'pre_kick_betting'
        game_state['timer'] = 7  # 7 seconds for betting
        game_state['current_bet'] = 0
        game_state['current_player_index'] = 0
        
        # Start betting timer
        socketio.start_background_task(betting_timer, table_id)
    
    return True

def process_betting_action(player_id, table_id, action_type, action_data):
    """Process a betting action (check/bet/fold)."""
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] not in ['pre_kick_betting', 'post_turn_betting', 'final_betting']:
        return False
    
    # Find the player
    player_index = next((i for i, p in enumerate(game_state['players']) if p['id'] == player_id), None)
    
    if player_index is None or player_index != game_state['current_player_index']:
        return False
    
    player = game_state['players'][player_index]
    
    # Process action
    if action_type == 'check':
        if game_state['current_bet'] > 0:
            return False  # Can't check if there's a bet
        
        player['last_action'] = 'check'
    
    elif action_type == 'bet':
        bet_amount = action_data.get('amount', 0)
        
        if bet_amount <= 0 or bet_amount > player['chips']:
            return False
        
        if game_state['current_bet'] > 0 and bet_amount < game_state['current_bet']:
            return False  # Bet must be at least the current bet
        
        player['chips'] -= bet_amount
        game_state['pot'] += bet_amount
        game_state['current_bet'] = bet_amount
        player['last_action'] = f'bet {bet_amount}'
    
    elif action_type == 'fold':
        player['status'] = 'folded'
        player['last_action'] = 'fold'
    
    else:
        return False
    
    # Move to next player or next phase
    active_players = [p for p in game_state['players'] if p['status'] == 'active']
    
    if len(active_players) <= 1:
        # Only one player left, they win
        end_hand(table_id)
        return True
    
    # Find next active player
    next_player_index = (player_index + 1) % len(game_state['players'])
    while game_state['players'][next_player_index]['status'] != 'active':
        next_player_index = (next_player_index + 1) % len(game_state['players'])
    
    # Check if betting round is complete
    if next_player_index == game_state['current_player_index'] or all(p['last_action'] in ['check', 'fold'] or (p['last_action'].startswith('bet') and int(p['last_action'].split()[1]) == game_state['current_bet']) for p in active_players):
        # Move to next phase
        if game_state['state'] == 'pre_kick_betting':
            # Move to turn draw
            game_state['state'] = 'turn_draw'
            
            # Deal turn card to each active player
            for player in active_players:
                player['turn_card'] = deal_cards(game_state['deck'], 1)[0]
                
                # Update database
                hand = Hand.query.get(game_state['current_hand'])
                if hand:
                    hand_player = HandPlayer.query.filter_by(
                        hand_id=hand.id,
                        player_id=player['id']
                    ).first()
                    
                    if hand_player:
                        hand_player.turn_card = card_to_string(player['turn_card'])
                        db.session.commit()
            
            # Move to post-turn betting
            game_state['state'] = 'post_turn_betting'
            game_state['timer'] = 7  # 7 seconds for betting
            game_state['current_bet'] = 0
            game_state['current_player_index'] = 0
            
            # Start betting timer
            socketio.start_background_task(betting_timer, table_id)
        
        elif game_state['state'] == 'post_turn_betting':
            # Move to board reveal
            game_state['state'] = 'board_reveal'
            
            # Collect kicked cards from all players
            kicked_cards = []
            for player in game_state['players']:
                if 'decisions' in player and player['decisions']['kick'] is not None:
                    kicked_cards.append(player['cards'][player['decisions']['kick']])
            
            # Add dealer cards if needed
            num_players = len(game_state['players'])
            dealer_cards_needed = 5 - num_players
            dealer_cards = deal_cards(game_state['deck'], dealer_cards_needed) if dealer_cards_needed > 0 else []
            
            game_state['community_cards'] = kicked_cards + dealer_cards
            
            # Update database
            hand = Hand.query.get(game_state['current_hand'])
            if hand:
                hand.community_cards = cards_to_string(kicked_cards)
                hand.dealer_cards = cards_to_string(dealer_cards)
                db.session.commit()
            
            # Move to final betting
            game_state['state'] = 'final_betting'
            game_state['timer'] = 7  # 7 seconds for betting
            game_state['current_bet'] = 0
            game_state['current_player_index'] = 0
            
            # Start betting timer
            socketio.start_background_task(betting_timer, table_id)
        
        elif game_state['state'] == 'final_betting':
            # Move to showdown
            end_hand(table_id)
    else:
        # Move to next player
        game_state['current_player_index'] = next_player_index
        game_state['timer'] = 7  # Reset timer for next player
    
    return True

def end_hand(table_id):
    """End the current hand and determine the winner."""
    game_state = game_states.get(table_id)
    
    if not game_state:
        return
    
    # Determine winner
    active_players = [p for p in game_state['players'] if p['status'] == 'active']
    
    if len(active_players) == 1:
        # Only one player left, they win
        winner = active_players[0]
    else:
        # Compare hands
        for player in active_players:
            # Combine kept card, turn card, and community cards
            player['final_hand'] = [
                player['cards'][player['decisions']['keep']],
                player['turn_card']
            ] + game_state['community_cards']
            
            # Calculate hand strength (simplified for now)
            player['hand_strength'] = calculate_hand_strength(player['final_hand'])
        
        # Find player with highest hand strength
        winner = max(active_players, key=lambda p: p['hand_strength'])
    
    # Award pot to winner
    winner['chips'] += game_state['pot']
    
    # Update database
    hand = Hand.query.get(game_state['current_hand'])
    if hand:
        hand.end_time = datetime.utcnow()
        
        for player in game_state['players']:
            hand_player = HandPlayer.query.filter_by(
                hand_id=hand.id,
                player_id=player['id']
            ).first()
            
            if hand_player:
                if 'final_hand' in player:
                    hand_player.final_hand = cards_to_string(player['final_hand'])
                
                hand_player.is_winner = (player['id'] == winner['id'])
                hand_player.bet_amount = player.get('bet_amount', 0)
                
                # Update player chips in game
                game_player = GamePlayer.query.filter_by(
                    game_id=hand.game_id,
                    player_id=player['id']
                ).first()
                
                if game_player:
                    game_player.final_chips = player['chips']
        
        db.session.commit()
    
    # Update game state
    game_state['state'] = 'end'
    game_state['winner'] = {
        'id': winner['id'],
        'username': winner['username'],
        'hand_strength': winner.get('hand_strength', 0)
    }
    game_state['pot'] = 0
    game_state['chat_enabled'] = True  # Re-enable chat
    game_state['timer'] = 10  # 10 seconds before next hand
    
    # Send hand result to all players
    socketio.emit('hand_result', {
        'winner': game_state['winner'],
        'pot_amount': game_state['pot']
    }, room=f'table_{table_id}')
    
    # Start timer for next hand
    socketio.start_background_task(next_hand_timer, table_id)

def next_hand_timer(table_id):
    """Timer for starting the next hand."""
    table_id = int(table_id)
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] != 'end':
        return
    
    while game_state['timer'] > 0:
        socketio.sleep(1)
        game_state['timer'] -= 1
        socketio.emit('timer_update', {'timer': game_state['timer']}, room=f'table_{table_id}')
    
    # Reset for next hand
    game_state['deck'] = shuffle_deck(create_deck())
    
    # Reset player statuses
    for player in game_state['players']:
        player['status'] = 'active'
        if 'cards' in player:
            del player['cards']
        if 'decisions' in player:
            del player['decisions']
        if 'turn_card' in player:
            del player['turn_card']
        if 'final_hand' in player:
            del player['final_hand']
        if 'hand_strength' in player:
            del player['hand_strength']
        if 'last_action' in player:
            del player['last_action']
    
    # Start new hand
    start_game(table_id)

def calculate_hand_strength(cards):
    """Calculate the strength of a poker hand (simplified version)."""
    # This is a simplified version - in a real implementation, you would use a proper poker hand evaluator
    # For now, just return a random value for demonstration
    return random.randint(1, 1000)

# Create database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
