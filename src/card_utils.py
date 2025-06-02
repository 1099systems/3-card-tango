import random

SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

def create_deck():
    """Create a standard deck of 52 cards."""
    return [{'rank': rank, 'suit': suit} for suit in SUITS for rank in RANKS]

def shuffle_deck(deck):
    """Shuffle the deck."""
    random.shuffle(deck)
    return deck

def deal_cards(deck, num_cards):
    """Deal a specified number of cards from the deck."""
    return [deck.pop() for _ in range(num_cards)]

def card_to_string(card):
    """Convert card object to string representation."""
    return f"{card['rank']}_of_{card['suit']}"

def string_to_card(card_str):
    """Convert string representation to card object."""
    rank, suit = card_str.split('_of_')
    return {'rank': rank, 'suit': suit}

def cards_to_string(cards):
    """Convert list of card objects to comma-separated string."""
    return ','.join([card_to_string(card) for card in cards])

def string_to_cards(cards_str):
    """Convert comma-separated string to list of card objects."""
    if not cards_str:
        return []
    return [string_to_card(card_str) for card_str in cards_str.split(',')]
