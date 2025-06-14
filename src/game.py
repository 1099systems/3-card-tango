from main import  app, timer_config
from card_utils import deal_cards,  cards_to_string
from src.models.models import Table, Game, GamePlayer, Hand, HandPlayer
from src.models import db

def moveGameStateToNext(game_state):
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
    elif game_state['state'] == 'card_draw':
        game_state['state'] = 'choose_trash'
        game_state['timer'] = timer_config['choose_trash']
        game_state['chat_enabled'] = False  # Disable chat during gameplay
    elif game_state['state'] == 'choose_trash':
        game_state['state'] = 'choose_tango'
        game_state['timer'] = timer_config['choose_tango']
    elif game_state['state'] == 'choose_tango':
        game_state['state'] = 'pre_kick_betting'
    elif game_state['state'] == 'pre_kick_betting':
        game_state['state'] = 'turn_draw'
    elif game_state['state'] == 'turn_draw':
        game_state['state'] = 'post_turn_betting'
    elif game_state['state'] == 'post_turn_betting':
        game_state['state'] = 'board_reveal'
    elif game_state['state'] == 'board_reveal':
        game_state['state'] = 'final_betting'
    elif game_state['state'] == 'final_betting':
        game_state['state'] = 'showdown'
    elif game_state['state'] == 'showdown':
        game_state['state'] = 'end'
    elif game_state['state'] == 'end':
        game_state['state'] = 'next_game_countdown'