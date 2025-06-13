def moveGameStateToNext(game_state):
    if game_state == 'waiting':
        game_state = 'ante'
    elif game_state == 'ante':
        game_state = 'card_draw'
    elif game_state == 'card_draw':
        game_state = 'choose_trash'
    elif game_state == 'choose_trash':
        game_state = 'choose_tango'
    elif game_state == 'choose_tango':
        game_state = 'pre_kick_betting'
    elif game_state == 'pre_kick_betting':
        game_state = 'turn_draw'
    elif game_state == 'turn_draw':
        game_state = 'post_turn_betting'
    elif game_state == 'post_turn_betting':
        game_state = 'board_reveal'
    elif game_state == 'board_reveal':
        game_state = 'final_betting'
    elif game_state == 'final_betting':
        game_state = 'showdown'
    elif game_state == 'showdown':
        game_state = 'end'
    elif game_state == 'end':
        game_state = 'next_game_countdown'