from main import socketio, game_states
from datetime import datetime
from src.models.models import Player, Game, GamePlayer, ChatMessage
from src.models import db
from flask_socketio import emit, join_room, leave_room
from helpers import find_suitable_table, process_betting_action, process_classification_action
from card_utils import shuffle_deck, create_deck
from timer import start_timer

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
    
    # game_states == 0 if server restarted since game_states is session-based (non-DB)
    if not existing_game_player or len(game_states) == 0:
        # Add player to the table
        active_game = Game.query.filter_by(table_id=suitable_table.id, status='active').first()
        
        if not active_game:
            # Create a new game if none exists
            active_game = Game(table_id=suitable_table.id)
            db.session.add(active_game)
            db.session.commit()
            
            
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
            
        # Initialize game state
        if suitable_table.id not in game_states:
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
            from game import moveGameStateToNext
            moveGameStateToNext(game_state, suitable_table.id)
    
    # Send updated game state to all players at the table
    # NOTE: game_states here can be empty if the server restarted
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

    player_action_string = 'Player ' + session_id + ' made action ' + action_type + ' with ' + str(action_data)
    print(player_action_string)

    
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
    
    # Fix gamestate. This is important for debug mode.
    if action_type == 'kill':
        game_state['state'] = 'choose_trash'
    elif action_type == 'kick':
        game_state['state'] = 'choose_tango'
    
    # Fix from debug states
    if action_type == 'bet' and game_state['state'] == 'turn_draw':
        game_state['state'] = 'post_turn_betting'

    # Process action based on game state and action type
    if game_state['state'] == 'choose_trash':
        if action_type in ['kill']:
            process_classification_action(player.id, int(table_id), action_type, action_data)
    elif game_state['state'] == 'choose_tango':
        if action_type in ['kick']:
            process_classification_action(player.id, int(table_id), action_type, action_data)
    elif game_state['state'] in ['ante']:
        if action_type in ['bet']:
            process_betting_action(player.id, int(table_id), action_type, action_data)
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