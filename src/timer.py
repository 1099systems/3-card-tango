import os
from main import game_states, socketio, app, timer_config
from card_utils import deal_cards, card_to_string, cards_to_string, shuffle_deck, create_deck
from src.models.models import Table, Game, GamePlayer, Hand, HandPlayer
from src.models import db

def start_timer(phase, table_id):
    timer_disabled = os.getenv('DEBUG_DISABLE_TIMER')
    if timer_disabled:
        print('Timer is disabled. Please continue the game using manual console commands.')
        return
    print('Starting timer...')

    if phase == 'choose_trash':
        socketio.start_background_task(countdown_to_start, table_id)
    elif phase == 'betting':
        socketio.start_background_task(betting_timer, table_id)
    elif phase == 'next_hand':
        socketio.start_background_task(next_hand_timer, table_id)
    elif phase == 'classification':
        socketio.start_background_task(classification_timer, table_id)


def countdown_to_start(table_id):
    """Countdown to start the game, starting with choose_trash."""
    table_id = int(table_id)
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] != 'starting':
        return
    
    while game_state['timer'] > 0:
        socketio.sleep(1)
        game_state['timer'] -= 1
        socketio.emit('timer_update', {'timer': game_state['timer']}, room=f'table_{table_id}')
    
    # Start the game
    from helpers import start_game
    start_game(table_id)

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
            with app.app_context():
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
    game_state['timer'] = timer_config['betting']  # 7 seconds for betting
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
        # batman dapat dito, iset yung player['last_action'] = 'fold'/'check'
        from helpers import process_betting_action
        if game_state['current_bet'] > 0:
            process_betting_action(current_player['id'], table_id, 'fold', {})
        else:
            process_betting_action(current_player['id'], table_id, 'check', {})
    
    # Send updated game state to all players
    socketio.emit('game_state_update', game_state, room=f'table_{table_id}')



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
    from helpers import start_game
    start_game(table_id)