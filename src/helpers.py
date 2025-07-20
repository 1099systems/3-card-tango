
from main import game_states, socketio, app, timer_config
from card_utils import deal_cards, card_to_string, cards_to_string
from timer import start_timer
from src.models.models import Table, Game, GamePlayer, Hand, HandPlayer
from src.models import db
from datetime import datetime
import random

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
    with app.app_context():
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

def start_game(table_id):
    """Start a new game at the table."""
    table_id = int(table_id)
    game_state = game_states.get(table_id)
    
    if not game_state:
        print('Invalid table ID or game state not found.')
        return
    
    # Update game state
    from game import moveGameStateToNext
    moveGameStateToNext(game_state, table_id)

def process_kill_card(player, hand_player):
    try:
        if player['cards'] is None or len(player['cards']) < 3:
            print('Invalid player cards for kill action.')
            return
        
        # Update database
        with app.app_context():
            killed_index = player['decisions']['kill']
            killed_card = player['cards'][killed_index]
            hand_player.killed_card = card_to_string(killed_card)
            # Remove the killed card from the player's cards
            player['cards'].pop(killed_index)
            db.session.commit()
    except:
        print('Error processing kill card.')

def process_kick_card(player, hand_player):
    try:
        if player['cards'] is None or len(player['cards']) < 2:
            print('Invalid player cards for kick action.')
            return
        
        kicked_index = player['decisions']['kick']
        kicked_card = player['cards'][kicked_index]
        kicked_card['is_tango'] = True
        hand_player.kicked_card = card_to_string(kicked_card)
        db.session.commit()
    except:
        print('Error processing kick card.')


def process_classification_action(player_id, table_id, action_type, action_data):
    print('Processing classification action:', player_id, action_type, action_data)
    """Process a classification action (kill/kick)."""
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] not in ['choose_trash', 'choose_tango']:
        return False
    
    # Find the player
    player = next((p for p in game_state['players'] if p['id'] == player_id), None)
    
    if not player:
        return False
    
    card_index = action_data.get('card_index')
    
    if card_index is None or card_index < 0 or card_index > 2:
        return False
    
    # Set the new decision
    player.setdefault('decisions', {'kill': None, 'kick': None})[action_type] = card_index
    # Debug
    if 'current_hand' not in game_state or game_state['current_hand'] is None:
        game_state['current_hand'] = 0

    # Update database
    with app.app_context():
        hand = Hand.query.get(game_state['current_hand'])
        if hand:
            hand_player = HandPlayer.query.filter_by(
                hand_id=hand.id,
                player_id=player_id
            ).first()
            
            if hand_player:
                # Convert the killed card index to string and assign it
                if action_type == 'kill':
                    process_kill_card(player, hand_player)
                elif action_type == 'kick':
                    process_kick_card(player, hand_player)
                    db.session.commit()

    # Check if all players have made all decisions
    all_decisions_made = True
    from game import moveGameStateToNext
    if game_state['state'] == 'choose_trash':
        for p in game_state['players']:
            if None in [p['decisions']['kill']]:
                all_decisions_made = False
                print('all decisions not yet made. continuing for all players to make a decision...')
                break
        
        if all_decisions_made:
            print('all decisions have been made!')
            moveGameStateToNext(game_state, table_id)
    elif game_state['state'] == 'choose_tango':
        for p in game_state['players']:
            if None in [p['decisions']['kick']]:
                all_decisions_made = False
                print('all decisions not yet made. continuing for all players to make a decision...')
                break
        
        if all_decisions_made:
            print('all decisions have been made!')
            moveGameStateToNext(game_state, table_id)
    else:
        # invalid
        return False
    
    return True

def all_players_acted(players, actions):
    return all(
        'last_action' in p and any(
            p['last_action'].startswith(action) for action in actions
        )
        for p in players
    )


def any_player_acted(players, bet_action):
    return any(
        'last_action' in p and (
            p['last_action'].startswith(bet_action)
        )
        for p in players
    )

def get_active_players(game_state):
    return [p for p in game_state['players'] if player_is_active(p)]

def player_is_active(player):
    if player['status'] in ['folded']:
            return False
    
    return True

def move_bet_to_next_player(game_state, next_player_index, table_id):
    print('Moving to next player for betting... Timer resetting...')
    game_state['current_player_index'] = next_player_index
    game_state['timer'] = timer_config['betting']
    start_timer('betting', table_id)
    # TODO: I think we don't need code below?
    from main import socketio
    socketio.emit('game_state_update', game_state, room=f'table_{table_id}')

def is_betting_allowed_from_game_state(game_state):
    if game_state or game_state['state'] in ['ante', 'pre_kick_betting', 'post_turn_betting', 'final_betting']:
        return True
    
    print(f"Error processing betting, invalid game state: {game_state}")
    return False


def process_betting_action(player_id, table_id, action_type, action_data):
    """Process a betting action (check/bet/fold)."""
    from game import moveGameStateToNext
    print('...processing player betting: ' + str(player_id) + ' ' + str(action_type))
    game_state = game_states.get(table_id)
    
    if not is_betting_allowed_from_game_state(game_state):
        return False
    
    # Find the player
    player_index = next((i for i, p in enumerate(game_state['players']) if p['id'] == player_id), None)
    
    if game_state['state'] not in ['ante'] and (player_index is None or player_index != game_state['current_player_index']):
        return False
    
    player = game_state['players'][player_index]
    
    # Process action
    # Reset current_bet
    player['current_bet'] = 0
    if action_type == 'check':
        player['status'] = 'checked'
        player['last_action'] = 'check'
        
        if game_state['state'] in ['pre_kick_betting']:
            player['last_action'] = f'pre_kick_check'
        elif game_state['state'] in ['post_turn_betting']:
            player['last_action'] = f'post_turn_check'
        elif game_state['state'] in ['final_betting']:
            player['last_action'] = f'final_check'
    
    elif action_type == 'bet':
        bet_amount = action_data.get('amount', 0)
        
        if bet_amount <= 0 or bet_amount > player['chips']:
            print('Invalid bet amount!')
            return False
            
        if not is_betting_allowed_from_game_state(game_state):
            print('Betting is not allowed.')
            return False
        
        player['chips'] -= bet_amount
        player['current_bet'] = bet_amount
        player['total_bet'] = player.get('total_bet', 0) + player['current_bet']

        player['is_all_in'] = False
        if player['current_bet'] == player['chips']:
            player['is_all_in'] = True

        game_state['pot'] += bet_amount
        game_state['current_bet'] = bet_amount

        if game_state['state'] in ['ante']:
            player['last_action'] = f'ante {bet_amount}'
        elif game_state['state'] in ['pre_kick_betting']:
            player['last_action'] = f'pre_kick_bet {bet_amount}'
        elif game_state['state'] in ['post_turn_betting']:
            player['last_action'] = f'post_turn_bet {bet_amount}'
        elif game_state['state'] in ['final_betting']:
            player['last_action'] = f'final_bet {bet_amount}'
        else:
            print('Invalid game state')
            return False
        player['status'] = f'betted {bet_amount}'
    
    elif action_type == 'fold':
        player['status'] = 'folded'
        player['last_action'] = 'fold'
        
        if game_state['state'] in ['pre_kick_betting']:
            player['last_action'] = f'pre_kick_fold'
        elif game_state['state'] in ['post_turn_betting']:
            player['last_action'] = f'post_turn_fold'
        elif game_state['state'] in ['final_betting']:
            player['last_action'] = f'final_fold'
    else:
        print('Invalid action type.')
        return False
    
    # Move to next player or next phase
    active_players = get_active_players(game_state)
    
    if len(active_players) <= 1:
        # Only one player left, they win
        print('Only one player left, ending hand...')
        moveGameStateToNext(game_state, table_id)
        return True
    
    # Find next active player
    next_player_index = (player_index + 1) % len(game_state['players'])
    while not player_is_active(game_state['players'][next_player_index]):
        next_player_index = (next_player_index + 1) % len(game_state['players'])
    
    # Check if betting round is complete
    try:
        state = game_state['state']
        if state == 'ante':
            if all_players_acted(active_players, ['ante']):
                moveGameStateToNext(game_state, table_id)

        elif state == 'pre_kick_betting':
            if all_players_acted(active_players, ['pre_kick_check', 'pre_kick_bet']):
                # Move to turn_draw phase
                moveGameStateToNext(game_state, table_id)
            else:
                move_bet_to_next_player(game_state, next_player_index, table_id)

        elif state == 'post_turn_betting':
            if all_players_acted(active_players, ['post_turn_check', 'post_turn_bet']):
                # Move to board_reveal phase        
                moveGameStateToNext(game_state, table_id)
            else:
                move_bet_to_next_player(game_state, next_player_index, table_id)

        elif state == 'final_betting':
            if all_players_acted(active_players, ['final_check', 'final_bet']):
                # Move to end hand phase
                moveGameStateToNext(game_state, table_id)
            else:
                move_bet_to_next_player(game_state, next_player_index, table_id)

    except Exception as e:
        # Optional: Add logging
        print(f"Error processing betting round: {e}")
        # Move to next player
        move_bet_to_next_player(game_state, next_player_index, table_id)
    
    return True


def calculate_side_pots(game_state):
    # Only calculate side pots if at least one player is all-in
    if not any(player.get('is_all_in') for player in game_state.get('players', [])):
        print("No all-in players. No side pots needed.")
        game_state['side_pots'] = []
        return []

    if 'side_pots' not in game_state:
        game_state['side_pots'] = []

    # Make a copy of players with total_bet > 0
    active_players = get_active_players(game_state)

    while active_players:
        # Get minimum total_bet among remaining players
        min_bet = min(p['total_bet'] for p in active_players)

        # Players who have at least min_bet are contributing to this pot
        contributors = [p for p in active_players if p['total_bet'] >= min_bet]

        # The amount of the pot is min_bet times number of contributors
        pot_amount = min_bet * len(contributors)

        # Create and store the side pot
        side_pot = {
            'amount': pot_amount,
            'eligible_players': [p['id'] for p in contributors]
        }
        game_state['side_pots'].append(side_pot)

        # Subtract min_bet from all contributors
        for p in active_players:
            p['total_bet'] -= min_bet

        # Remove players who have contributed all their chips
        active_players = [p for p in active_players if p['total_bet'] > 0]

    print('BATMAN sidepots is:')
    print(game_state['side_pots'])

    return game_state['side_pots']




def get_winner(game_state):
    # Determine winner
    active_players = get_active_players(game_state)

    if len(active_players) == 1:
        # Only one player left, they win
        winner = active_players[0]
    else:
        # Compare hands
        for player in active_players:
            # Combine kept card, turn card, and community cards
            player['final_hand'] = player['cards'] + [player['turn_card']] + game_state['community_cards']
            
            # Calculate hand strength (simplified for now)
            player['hand_strength'] = determine_hand_strength(player['final_hand'])
        
        # Find player with highest hand strength
        winner = max(active_players, key=lambda p: p['hand_strength'])

    return winner

def end_hand(table_id):
    """End the current hand and determine the winner."""
    game_state = game_states.get(table_id)
    
    if not game_state:
        return
    
    from game import moveGameStateToNext
    # Update game state
    moveGameStateToNext(game_state, table_id)
    

def determine_hand_strength(cards):
    """Calculate the strength of a poker hand (simplified version)."""
    # This is a simplified version - in a real implementation, you would use a proper poker hand evaluator
    # For now, just return a random value for demonstration
    print('Determining hand strength for cards..')
    from poker import calculate_hand_strength
    return calculate_hand_strength(cards)
