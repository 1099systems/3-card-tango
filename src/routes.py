from main import app
from src.models.models import Player
import uuid
from src.models import db
from datetime import datetime, timedelta
from flask import request, jsonify, render_template, session
import json

@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')


@app.route('/api/next-state', methods=['POST'])
def next_game_state():
    data = request.json
    game_state = data.get('game_state')
    
    print('Moving next game state from:')
    table_id = data.get('table_id')
    from game import moveGameStateToNext
    
    state = game_state['state']
    
    # Move to next player or next phase
    from helpers import player_is_active, all_players_acted, move_bet_to_next_player, move_to_turn_draw, move_to_board_reveal, end_hand 
    active_players = [p for p in game_state['players'] if player_is_active(p)]
    
    # next_player_index = game_state['current_player_index']
    next_player_index = (game_state['currentPlayerIndex'] + 1) % len(game_state['players'])
    
    while not player_is_active(game_state['players'][next_player_index]):
        next_player_index = (next_player_index + 1) % len(game_state['players'])

    if state == 'ante':
        if all_players_acted(active_players, ['ante']):
            from game import moveGameStateToNext
            moveGameStateToNext(game_state, table_id)

    elif state == 'pre_kick_betting':
        if all_players_acted(active_players, ['pre_kick_check', 'pre_kick_bet']):
            move_to_turn_draw(game_state, table_id)
        else:
            move_bet_to_next_player(game_state, next_player_index, table_id)

    elif state == 'post_turn_betting':
        if all_players_acted(active_players, ['post_turn_check', 'post_turn_bet']):
            move_to_board_reveal(game_state, table_id)
        else:
            move_bet_to_next_player(game_state, next_player_index, table_id)

    elif state == 'final_betting':
        if all_players_acted(active_players, ['final_check', 'final_bet']):
            end_hand(table_id)
        else:
            move_bet_to_next_player(game_state, next_player_index, table_id)
    else:
        moveGameStateToNext(game_state, table_id)

    return jsonify({
        'game_state': game_state,
    })

@app.route('/api/player', methods=['POST'])
def get_player_in_session_or_create():
    """Create a new player or retrieve existing player by session ID."""
    data = request.json
    session_id = data.get('session_id')
    username = data.get('username')
    
    if not session_id:
        session_id = str(uuid.uuid4())
    
    player = Player.query.filter_by(session_id=session_id).first()
    
    if not player:
        if username:
            player = Player(session_id=session_id, username=username, chips=100)
        else:
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