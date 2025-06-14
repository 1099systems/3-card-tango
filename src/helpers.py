
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
        return
    
    # Update game state
    from game import moveGameStateToNext
    moveGameStateToNext()
    # Start classification timer
    start_timer('choose_trash', table_id)
    
    # Send updated game state to all players
    socketio.emit('game_state_update', game_state, room=f'table_{table_id}')
    socketio.emit('game_started', {}, room=f'table_{table_id}')

def process_classification_action(player_id, table_id, action_type, action_data):
    print('batman in process')
    """Process a classification action (keep/kill/kick)."""
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
    player.setdefault('decisions', {'keep': None, 'kill': None, 'kick': None})[action_type] = card_index
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
                hand_player.killed_card = card_to_string(player['cards'][player['decisions']['kill']])
                hand_player.kicked_card = card_to_string(player['cards'][player['decisions']['kick']])
                db.session.commit()

    # Check if all players have made all decisions
    all_decisions_made = True
    for p in game_state['players']:
        if None in [p['decisions']['kill'], p['decisions']['kick']]:
            all_decisions_made = False
            break
    
    if all_decisions_made:
        # Move to pre-kick betting
        game_state['state'] = 'pre_kick_betting'
        game_state['timer'] = timer_config['betting']  # 7 seconds for betting
        game_state['current_bet'] = 0
        game_state['current_player_index'] = 0
        
        # Start betting timer
        start_timer('betting', table_id)
    
    return True

def process_betting_action(player_id, table_id, action_type, action_data):
    """Process a betting action (check/bet/fold)."""
    print('batman in process')
    game_state = game_states.get(table_id)
    
    if not game_state or game_state['state'] not in ['ante', 'pre_kick_betting', 'post_turn_betting', 'final_betting']:
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
    try:
        if next_player_index == game_state['current_player_index'] or all(
            'last_action' in p and (
                p['last_action'] in ['check', 'fold'] or
                (p['last_action'].startswith('bet') and int(p['last_action'].split()[1]) == game_state['current_bet'])
            )
            for p in active_players
        ):
            # Move to next phase
            if game_state['state'] == 'pre_kick_betting':
                # Move to turn draw
                game_state['state'] = 'turn_draw'
                
                # Deal turn card to each active player
                for player in active_players:
                    player['turn_card'] = deal_cards(game_state['deck'], 1)[0]
                    
                    # Update database
                    with app.app_context():
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
                game_state['timer'] = timer_config['betting']  # 7 seconds for betting
                game_state['current_bet'] = 0
                game_state['current_player_index'] = 0
                
                # Start betting timer
                start_timer('betting', table_id)
            
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
                with app.app_context():
                    hand = Hand.query.get(game_state['current_hand'])
                    if hand:
                        hand.community_cards = cards_to_string(kicked_cards)
                        hand.dealer_cards = cards_to_string(dealer_cards)
                        db.session.commit()
                
                # Move to final betting
                game_state['state'] = 'final_betting'
                game_state['timer'] = timer_config['betting']  # 7 seconds for betting
                game_state['current_bet'] = 0
                game_state['current_player_index'] = 0
                
                # Start betting timer
                start_timer('betting', table_id)
            
            elif game_state['state'] == 'final_betting':
                # Move to showdown
                end_hand(table_id)
        else:
            # Move to next player
            game_state['current_player_index'] = next_player_index
            game_state['timer'] = timer_config['next_player']  # Reset timer for next player
    except:
        # Move to next player
        game_state['current_player_index'] = next_player_index
        game_state['timer'] = timer_config['next_player']  # Reset timer for next player
    
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
    with app.app_context():
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
    game_state['chat_enabled'] = True  # Re-enable chat
    game_state['timer'] = timer_config['next_hand']  # 10 seconds before next hand
    
    # Send hand result to all players
    socketio.emit('hand_result', {
        'winner': game_state['winner'],
        'pot_amount': game_state['pot']
    }, room=f'table_{table_id}')
    
    # Start timer for next hand
    start_timer('next_hand', table_id)

    # Reset pot
    game_state['pot'] = 0


def calculate_hand_strength(cards):
    """Calculate the strength of a poker hand (simplified version)."""
    # This is a simplified version - in a real implementation, you would use a proper poker hand evaluator
    # For now, just return a random value for demonstration
    return random.randint(1, 1000)
