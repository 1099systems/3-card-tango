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
        from helpers import get_active_players
        active_players = get_active_players(game_state)
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
        game_state['timer'] = timer_config['showdown']
        game_state['state'] = 'showdown'
        start_timer('showdown', table_id)
    elif game_state['state'] == 'showdown':
        game_state['state'] = 'end'

        from helpers import calculate_side_pots, get_winner, determine_hand_strength

        # Step 1: Calculate side pots
        side_pots = calculate_side_pots(game_state)

        # Step 2: Determine winners for each pot
        awarded_players = []

        for pot in side_pots:
            # Only consider eligible players for this pot
            eligible_players = [p for p in game_state['players'] if p['id'] in pot['eligible_players']]

            if len(eligible_players) == 1:
                winner = eligible_players[0]
            else:
                # Evaluate hand strengths among eligible players
                for player in eligible_players:
                    player['final_hand'] = player['cards'] + [player['turn_card']] + game_state['community_cards']
                    player['hand_strength'] = determine_hand_strength(player['final_hand'])

                winner = max(eligible_players, key=lambda p: p['hand_strength'])

            # Award pot to winner
            winner['chips'] += pot['amount']
            awarded_players.append({
                'id': winner['id'],
                'username': winner['username'],
                'amount': pot['amount'],
                'is_main_winner': False
            })

        # Step 3: Determine winner of the remaining main pot (if any)
        # If side pots consumed entire pot, this may be 0
        game_state['pot'] = sum(p.get('total_bet', 0) for p in game_state['players'])
        remaining_pot = game_state.get('pot', 0)
        if remaining_pot > 0:
            main_winner = get_winner(game_state)
            main_winner['chips'] += remaining_pot
            
            awarded_players.append({
                'id': main_winner['id'],
                'username': main_winner['username'],
                'amount': remaining_pot,
                'is_main_winner': True
            })

        # Optional: print or log who won which pot
        print("🏆 Pot results:")
        print(awarded_players)
        game_state['winners'] = []

        for winner in awarded_players:
            print(f"→ Player {winner['username']} won {winner['amount']} chips")

            game_state['winners'].append({
                'id': winner['id'],
                'username': winner['username'],
                'amount_won': winner['amount'],
                'is_main_winner': winner['is_main_winner'],
            })
        
        # Do we still need below?
        # # Update database
        # with app.app_context():
        #     hand = Hand.query.get(game_state['current_hand'])
        #     if hand:
        #         from datetime import datetime
        #         hand.end_time = datetime.utcnow()
                
        #         for player in game_state['players']:
        #             hand_player = HandPlayer.query.filter_by(
        #                 hand_id=hand.id,
        #                 player_id=player['id']
        #             ).first()
                    
        #             if hand_player:
        #                 if 'final_hand' in player:
        #                     hand_player.final_hand = cards_to_string(player['final_hand'])
                        
        #                 hand_player.is_winner = (player['id'] == winner['id'])
        #                 hand_player.bet_amount = player.get('bet_amount', 0)
                        
        #                 # Update player chips in game
        #                 game_player = GamePlayer.query.filter_by(
        #                     game_id=hand.game_id,
        #                     player_id=player['id']
        #                 ).first()
                        
        #                 if game_player:
        #                     game_player.final_chips = player['chips']
                
        #         db.session.commit()
            

        game_state['chat_enabled'] = True  # Re-enable chat
        game_state['timer'] = timer_config['end']  # 10 seconds before next hand

        # Send hand result to all players
        socketio.emit('hand_result', {
            'winners': game_state['winners'],
        }, room=f'table_{table_id}')
        

        # Reset pot
        game_state['pot'] = 0
        start_timer('end', table_id)

    elif game_state['state'] == 'end':
        game_state['state'] = 'next_hand'
        # Start timer for next hand
        game_state['timer'] = timer_config['next_hand']  # 10 seconds before next hand
        start_timer('next_hand', table_id)
        
    socketio.emit('game_state_update', game_state, room=f'table_{table_id}')
    print('Moved game state from ' + old_game_state + ' to ' + game_state['state'])
    