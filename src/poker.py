from collections import Counter
from itertools import combinations

def rank_to_value(rank):
    rank_map = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
                '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12,
                'K': 13, 'A': 14}
    return rank_map[rank]

def is_straight(ranks):
    """Check if a list of sorted rank values forms a straight."""
    ranks = sorted(set(ranks))
    if len(ranks) < 5:
        return False
    for i in range(len(ranks) - 4):
        if ranks[i + 4] - ranks[i] == 4:
            return True
    # Check for Ace-low straight
    if set([14, 2, 3, 4, 5]).issubset(set(ranks)):
        return True
    return False

def is_flush(cards):
    """Check if there is a flush in the hand."""
    suit_counts = Counter(card['suit'] for card in cards)
    for suit, count in suit_counts.items():
        if count >= 5:
            flush_cards = [card for card in cards if card['suit'] == suit]
            return True, sorted([rank_to_value(c['rank']) for c in flush_cards], reverse=True)[:5]
    return False, []

def get_best_hand(cards):
    """Evaluate the hand and return a hand strength value based on poker rules."""
    # Evaluate all 5-card combinations from 7 cards
    best_rank = (0, [])  # (hand_rank, high_cards)

    for combo in combinations(cards, 5):
        ranks = [rank_to_value(card['rank']) for card in combo]
        suits = [card['suit'] for card in combo]
        rank_counter = Counter(ranks)

        is_flush_hand, flush_highs = is_flush(combo)
        is_straight_hand = is_straight(ranks)

        # Straight Flush / Royal Flush
        if is_flush_hand:
            flush_cards = [card for card in combo if card['suit'] == suits[0]]
            flush_ranks = [rank_to_value(c['rank']) for c in flush_cards]
            if is_straight(flush_ranks):
                if max(flush_ranks) == 14 and min(flush_ranks) == 10:
                    best_rank = max(best_rank, (10, [14]))  # Royal Flush
                else:
                    best_rank = max(best_rank, (9, sorted(flush_ranks, reverse=True)))
                continue

        # Four of a Kind
        if 4 in rank_counter.values():
            four = [r for r, c in rank_counter.items() if c == 4][0]
            kicker = max([r for r in ranks if r != four])
            best_rank = max(best_rank, (8, [four, kicker]))
            continue

        # Full House
        if 3 in rank_counter.values() and 2 in rank_counter.values():
            three = max([r for r, c in rank_counter.items() if c == 3])
            pair = max([r for r, c in rank_counter.items() if c == 2])
            best_rank = max(best_rank, (7, [three, pair]))
            continue
        elif list(rank_counter.values()).count(3) >= 2:
            threes = sorted([r for r, c in rank_counter.items() if c == 3], reverse=True)
            best_rank = max(best_rank, (7, [threes[0], threes[1]]))
            continue

        # Flush
        if is_flush_hand:
            best_rank = max(best_rank, (6, flush_highs))
            continue

        # Straight
        if is_straight_hand:
            best_rank = max(best_rank, (5, [max(ranks)]))
            continue

        # Three of a Kind
        if 3 in rank_counter.values():
            three = [r for r, c in rank_counter.items() if c == 3][0]
            kickers = sorted([r for r in ranks if r != three], reverse=True)[:2]
            best_rank = max(best_rank, (4, [three] + kickers))
            continue

        # Two Pair
        pairs = [r for r, c in rank_counter.items() if c == 2]
        if len(pairs) >= 2:
            top_two = sorted(pairs, reverse=True)[:2]
            kicker = max([r for r in ranks if r not in top_two])
            best_rank = max(best_rank, (3, top_two + [kicker]))
            continue

        # One Pair
        if 2 in rank_counter.values():
            pair = [r for r, c in rank_counter.items() if c == 2][0]
            kickers = sorted([r for r in ranks if r != pair], reverse=True)[:3]
            best_rank = max(best_rank, (2, [pair] + kickers))
            continue

        # High Card
        best_rank = max(best_rank, (1, sorted(ranks, reverse=True)))

    return best_rank

def calculate_hand_strength(cards):
    """Calculate hand strength from 7 poker cards."""
    print("Calculating hand strength for cards:")
    print(cards)

    hand_rank, high_cards = get_best_hand(cards)
    print(f"Hand rank: {hand_rank}, High cards: {high_cards}")

    # Combine rank with high cards for a sortable value
    strength = hand_rank * 1_000_000 + sum(hc * (10 ** i) for i, hc in enumerate(high_cards[::-1]))
    return strength
