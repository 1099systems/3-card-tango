import os
from main import game_states, socketio, app, timer_config
from card_utils import deal_cards, card_to_string, cards_to_string, shuffle_deck, create_deck
from src.models.models import Table, Game, GamePlayer, Hand, HandPlayer
from src.models import db

def start_timer(phase, table_id):
    timer_disabled = os.getenv('DEBUG_DISABLE_TIMER', 'false').lower() == 'true'

    if timer_disabled:
        print('Timer is disabled. Please continue the game using manual console commands.')
        return
    print('Starting timer...')

    if phase == 'card_draw':
        socketio.start_background_task(countdown_to_start, table_id)
    elif phase == 'choose_trash' or phase == 'choose_tango':
        socketio.start_background_task(classification_timer, table_id)
    elif phase == 'betting':
        socketio.start_background_task(betting_timer, table_id)
    elif phase == 'turn_draw':
        socketio.start_background_task(turn_draw_timer, table_id)
    elif phase == 'board_reveal':
        socketio.start_background_task(board_reveal_timer, table_id)
    elif phase == 'next_hand':
        socketio.start_background_task(next_hand_timer, table_id)

def countdown_to_start(table_id):
    """Countdown to start the game, starting with choose_trash."""
    table_id = int(table_id)
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] != 'card_draw':
        return
    
    while game_state['timer'] > 0:
        socketio.sleep(0.5)
        game_state['timer'] = round(game_state['timer'] - 0.5, 2)
        socketio.emit('timer_update', {'timer': game_state['timer']}, room=f'table_{table_id}')
    
    # Start the game
    from helpers import start_game
    start_game(table_id)


def turn_draw_timer(table_id):
    table_id = int(table_id)
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] != 'turn_draw':
        print('Invalid game state.')
        return
    
    while game_state['timer'] > 0:
        socketio.sleep(0.5)
        game_state['timer'] = round(game_state['timer'] - 0.5, 2)
        socketio.emit('timer_update', {'timer': game_state['timer']}, room=f'table_{table_id}')
    
    from game import moveGameStateToNext
    moveGameStateToNext(game_state, table_id)

def board_reveal_timer(table_id):
    table_id = int(table_id)
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] != 'board_reveal':
        print('Invalid game state.')
        return
    
    while game_state['timer'] > 0:
        socketio.sleep(0.5)
        game_state['timer'] = round(game_state['timer'] - 0.5, 2)
        socketio.emit('timer_update', {'timer': game_state['timer']}, room=f'table_{table_id}')
    
    from game import moveGameStateToNext
    moveGameStateToNext(game_state, table_id)

def classification_timer(table_id):
    """Timer for classification phase."""
    table_id = int(table_id)
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] not in ['choose_trash', 'choose_tango']:
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
                        # hand_player.kicked_card = card_to_string(player['cards'][player['decisions']['kick']])
                        db.session.commit()

    from game import moveGameStateToNext
    moveGameStateToNext(game_state, table_id)
    
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