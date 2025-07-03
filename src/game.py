from main import  app, timer_config, socketio
from card_utils import deal_cards,  cards_to_string, card_to_string
from src.models.models import Table, Game, GamePlayer, Hand, HandPlayer
from src.models import db

def moveGameStateToNext(game_state, table_id):
    from timer import start_timer
    old_game_state = game_state['state']
    if game_state['state'] == 'waiting':
        game_state['state'] = 'ante'
        game_state['current_player_index'] = 0
        game_state['current_bet'] = 0
    elif game_state['state'] == 'ante':
        game_state['state'] = 'card_draw'
        game_state['timer'] = timer_config['card_draw']
    
        # Deal cards to players
        for player in game_state['players']:
            player['cards'] = deal_cards(game_state['deck'], 3)
            player['decisions'] = {'kill': None, 'kick': None}

        # Create a new hand
        with app.app_context():
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

        start_timer('card_draw', table_id)
    elif game_state['state'] == 'card_draw':
        game_state['state'] = 'choose_trash'
        game_state['timer'] = timer_config['choose_trash']
        start_timer('choose_trash', table_id)
        # Send updated game state to all players
        socketio.emit('game_started', {}, room=f'table_{table_id}')
        game_state['chat_enabled'] = False  # Disable chat during gameplay
    elif game_state['state'] == 'choose_trash':
        game_state['state'] = 'choose_tango'
        game_state['timer'] = timer_config['choose_tango']
        start_timer('choose_tango', table_id)
    elif game_state['state'] == 'choose_tango':
        game_state['state'] = 'pre_kick_betting'
        game_state['timer'] = timer_config['betting']
        game_state['current_player_index'] = 0
        start_timer('betting', table_id)
    elif game_state['state'] == 'pre_kick_betting':
        game_state['state'] = 'turn_draw'
        from helpers import player_is_active
        active_players = [p for p in game_state['players'] if player_is_active(p)]
        for player in active_players:
            player['turn_card'] = deal_cards(game_state['deck'], 1)[0]

            # Update DB
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
        game_state['timer'] = timer_config['turn_draw']
        game_state['current_bet'] = 0
        game_state['current_player_index'] = 0
        start_timer('turn_draw', table_id)
    elif game_state['state'] == 'turn_draw':
        game_state['state'] = 'post_turn_betting'
        game_state['timer'] = timer_config['betting']
        game_state['current_player_index'] = 0
        start_timer('betting', table_id)
    elif game_state['state'] == 'post_turn_betting':
        game_state['state'] = 'board_reveal'

        # Collect kicked cards
        kicked_cards = [
            player['cards'][player['decisions']['kick']]
            for player in game_state['players']
            if 'decisions' in player and player['decisions'].get('kick') is not None
        ]

        num_players = len(game_state['players'])
        dealer_cards_needed = 5 - num_players
        dealer_cards = deal_cards(game_state['deck'], dealer_cards_needed) if dealer_cards_needed > 0 else []

        game_state['community_cards'] = kicked_cards + dealer_cards

        # Update DB
        with app.app_context():
            hand = Hand.query.get(game_state['current_hand'])
            if hand:
                hand.community_cards = cards_to_string(kicked_cards)
                hand.dealer_cards = cards_to_string(dealer_cards)
                db.session.commit()

        game_state['timer'] = timer_config['board_reveal']
        start_timer('board_reveal', table_id)
    elif game_state['state'] == 'board_reveal':
        game_state['state'] = 'final_betting'
        game_state['timer'] = timer_config['betting']
        game_state['current_bet'] = 0
        game_state['current_player_index'] = 0
        start_timer('betting', table_id)
    elif game_state['state'] == 'final_betting':
        game_state['state'] = 'showdown'
        start_timer('showdown', table_id)
    elif game_state['state'] == 'showdown':
        game_state['state'] = 'end'

        from helpers import get_winner
        # Determine winner
        winner = get_winner(game_state)
        
        # Award pot to winner
        winner['chips'] += game_state['pot']
        
        # Update database
        with app.app_context():
            hand = Hand.query.get(game_state['current_hand'])
            if hand:
                from datetime import datetime
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
        

        # Reset pot
        game_state['pot'] = 0
        start_timer('end', table_id)

    elif game_state['state'] == 'end':
        game_state['state'] = 'next_game_countdown'
        # Start timer for next hand
        start_timer('next_hand', table_id)
        
    socketio.emit('game_state_update', game_state, room=f'table_{table_id}')
    print('Moved game state from ' + old_game_state + ' to ' + game_state['state'])
    