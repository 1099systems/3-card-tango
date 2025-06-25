from main import  app, timer_config
from card_utils import deal_cards,  cards_to_string
from src.models.models import Table, Game, GamePlayer, Hand, HandPlayer
from src.models import db

def moveGameStateToNext(game_state, table_id):
    from timer import start_timer
    if game_state['state'] == 'waiting':
        game_state['state'] = 'ante'
        game_state['current_player_index'] = 0
        game_state['current_bet'] = 0
        # game_state['timer'] = 10  # 10 second countdown to start
        # start_timer('start', suitable_table.id)
    elif game_state['state'] == 'ante':
        game_state['state'] = 'card_draw'
        game_state['timer'] = timer_config['card_draw']
    
        # Deal cards to players
        for player in game_state['players']:
            player['cards'] = deal_cards(game_state['deck'], 3)
            player['decisions'] = {'keep': None, 'kill': None, 'kick': None}

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
        active_players = [p for p in game_state['players'] if p['status'] == 'active']
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
                        hand_player.turn_card = cards_to_string(player['turn_card'])
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
    elif game_state['state'] == 'board_reveal':
        game_state['state'] = 'final_betting'
        game_state['timer'] = timer_config['betting']
        game_state['current_player_index'] = 0
        start_timer('betting', table_id)
    elif game_state['state'] == 'final_betting':
        game_state['state'] = 'showdown'
    elif game_state['state'] == 'showdown':
        game_state['state'] = 'end'
    elif game_state['state'] == 'end':
        game_state['state'] = 'next_game_countdown'