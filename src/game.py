def moveGameStateToNext(game_state):
    if game_state['state'] == 'waiting':
        game_state['state'] = 'ante'
        game_state['current_player_index'] = 0
        game_state['current_bet'] = 0
        # game_state['timer'] = 10  # 10 second countdown to start
        # start_timer('start', suitable_table.id)
    elif game_state['state'] == 'ante':
        game_state['state'] = 'card_draw'
        # Deal cards to players?
        game_state['current_hand'] = 0
    elif game_state['state'] == 'card_draw':
        game_state['state'] = 'choose_trash'
    elif game_state['state'] == 'choose_trash':
        game_state['state'] = 'choose_tango'
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