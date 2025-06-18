var gameState;

// Socket Connection
const socket = io();

async function debugAddPlayer(username) {
    getPlayerOrCreate(username, username).then((result) => {
        socket.emit('join_table', {
            session_id: result.sessionId
        });
    });
}

function debugNextPhase() {
    let newGameState = gameState;
    switch (gameState.state) {
        case 'waiting':
            newGameState.state = 'ante';
            debugUpdateGameState(newGameState);
            break;
        case 'ante':
            newGameState.state = 'card_draw';
            
            newGameState.chat_enabled = false;
            // countdown timer starts here
            newGameState.players.forEach((player) => {
                player['cards'] = [
                    {
                        'rank': '6',
                        'suit': 'clubs'
                    },
                    {
                        'rank': 'A',
                        'suit': 'diamonds'
                    },
                    {
                        'rank': 'J',
                        'suit': 'clubs'
                    },
                ]
                player['decisions'] = {
                    'keep': null, // 0
                    'kick': null, // 2
                    'kill': null // 1
                }
                player['last_action'] = 'check'
                player['chips'] = 100
                
            });
            
            newGameState.current_hand = 0;
            debugUpdateGameState(newGameState);
            break;
        case 'card_draw':
            newGameState.state = 'choose_trash';
            debugUpdateGameState(newGameState);
            break;
        case 'choose_trash':
            newGameState.state = 'choose_tango';
            newGameState.current_bet = ''
            newGameState.current_player_index = ''
            debugUpdateGameState(newGameState);
            break;
        case 'choose_tango':
            newGameState.state = 'pre_kick_betting';
            newGameState.current_bet = ''
            newGameState.current_player_index = ''
            debugUpdateGameState(newGameState);
            break;
        case 'pre_kick_betting':
            // TODO: player bets, decrease player['chips'], increate gamestate['pot']
            newGameState.state = 'turn_draw';
            // new card drawn
            debugUpdateGameState(newGameState);
            break;
        case 'turn_draw':
            newGameState.state = 'post_turn_betting';
            debugUpdateGameState(newGameState);
            break;
        case 'post_turn_betting':
            newGameState.state = 'board_reveal';
            debugUpdateGameState(newGameState);
            break;
        case 'board_reveal':
            newGameState.state = 'final_betting';
            debugUpdateGameState(newGameState);
            break;
        case 'final_betting':
            newGameState.state = 'showdown';
            debugUpdateGameState(newGameState);
            break;
        case 'showdown':
            newGameState.state = 'end';
            debugUpdateGameState(newGameState);
            break;
        case 'end':
            newGameState.state = 'next_game_countdown';
            debugUpdateGameState(newGameState);
            break;
        default:
            statusText = gameState.state;
    }
}

async function getPlayerOrCreate(sessionId, username) {
    try {
        const response = await fetch('/api/player', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: sessionId,
                username: username
            })
        });

        const data = await response.json();
        const newPlayer = {};
        newPlayer.id = data.id;
        newPlayer.sessionId = data.session_id;
        newPlayer.username = data.username;
        newPlayer.chips = data.chips;
        newPlayer.isPermanent = data.is_permanent;

        return newPlayer;
    } catch (error) {
        console.error('Error getting or creating player data:', error);
    }
}

function debugUpdateGameState(state) {
    // Update game state
    gameState.state = state.state;
    gameState.players = state.players || [];
    gameState.pot = state.pot || 0;
    gameState.timer = state.timer;
    gameState.chatEnabled = state.chat_enabled !== false;

    updateUI(state);
}

function debugPlaceBet(playerId, amount) {
    processPlaceBet(playerId, amount);
}

function updateUI(state) {
    updateGameStatus();
    updatePlayers();
    updatePot();
    if (state && state.communityCards) {
        updateCommunityCards(state.community_cards);
    }
    updatePlayerCards();
    updateControls();
    updateChatStatus();
}


// DOM Elements
const loginCard = document.getElementById('login-card');
const gameContainer = document.getElementById('game-container');
const playerInfo = document.getElementById('player-info');
const usernameForm = document.getElementById('username-form');
const usernameDisplay = document.getElementById('username-display');
const chipCountDisplay = document.getElementById('chip-count-display');
const joinBtn = document.getElementById('join-btn');
const setUsernameBtn = document.getElementById('set-username-btn');
const claimChipsBtn = document.getElementById('claim-chips-btn');
const cardActionsTrash = document.getElementById('card-actions-trash');
const cardActionsTango = document.getElementById('card-actions-tango');
const checkBtn = document.getElementById('check-btn');
const betBtn = document.getElementById('bet-btn');
const foldBtn = document.getElementById('fold-btn');
const timerElement = document.getElementById('timer');
const gameStatusElement = document.getElementById('game-status');
const potElement = document.getElementById('pot');
const communityCardsElement = document.getElementById('community-cards');
const playerCardsElement = document.getElementById('player-cards');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendChatBtn = document.getElementById('send-chat-btn');
const chatStatusElement = document.getElementById('chat-status');

// Game State
let player = {
    id: null,
    sessionId: localStorage.getItem('sessionId') || null,
    username: null,
    chips: 0,
    isPermanent: false
};

gameState = {
    tableId: null,
    gameId: null,
    state: 'waiting',
    players: [],
    communityCards: [],
    pot: 0,
    timer: null,
    selectedCard: null,
    selectedAction: null,
    chatEnabled: true
};


// Initialize
init();

function init() {
    // Check if player exists
    if (player.sessionId) {
        fetchPlayerData();
    }

    // Event Listeners
    joinBtn.addEventListener('click', joinTable);
    setUsernameBtn.addEventListener('click', setUsername);
    claimChipsBtn.addEventListener('click', claimChips);
    sendChatBtn.addEventListener('click', sendChatMessage);
    chatInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            sendChatMessage();
        }
    });

    // Socket Event Listeners
    socket.on('connect', () => {
        console.log('Connected to server');
    });

    socket.on('game_state_update', handleGameStateUpdate);
    socket.on('player_joined', handlePlayerJoined);
    socket.on('player_left', handlePlayerLeft);
    socket.on('game_started', handleGameStarted);
    socket.on('timer_update', handleTimerUpdate);
    socket.on('chat_message', handleChatMessage);
    socket.on('hand_result', handleHandResult);
    socket.on('error', handleError);
}

// API Functions
async function fetchPlayerData() {
    try {
        const result = await getPlayerOrCreate(player.sessionId);
        player = result;

        // Save session ID
        localStorage.setItem('sessionId', player.sessionId);

        // Update UI
        updatePlayerInfo();
    } catch (error) {
        console.error('Error fetching player data:', error);
    }
}

async function setUsername() {
    const usernameInput = document.getElementById('username');
    const username = usernameInput.value.trim();

    if (!username) {
        alert('Please enter a username');
        return;
    }

    try {
        const response = await fetch('/api/player/username', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: player.sessionId,
                username: username
            })
        });

        const data = await response.json();

        if (response.ok) {
            player.username = data.username;
            player.isPermanent = data.is_permanent;

            // Update UI
            updatePlayerInfo();

            // Hide username form
            usernameForm.classList.add('hidden');
        } else {
            alert(data.error || 'Failed to set username');
        }
    } catch (error) {
        console.error('Error setting username:', error);
        alert('Failed to set username');
    }
}

async function claimChips() {
    try {
        const response = await fetch('/api/player/chips', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: player.sessionId
            })
        });

        const data = await response.json();

        if (response.ok) {
            player.chips = data.chips;

            // Update UI
            updatePlayerInfo();

            alert('You have claimed 100 free chips!');
        } else {
            alert(data.error || 'Failed to claim chips');
        }
    } catch (error) {
        console.error('Error claiming chips:', error);
        alert('Failed to claim chips');
    }
}

// Socket Event Handlers
function joinTable() {
    if (!player.sessionId) {
        // Create new player
        fetchPlayerData().then(() => {
            // Join table
            socket.emit('join_table', {
                session_id: player.sessionId
            }, handleJoinTableResponse);
        });
    } else {
        // Join table
        socket.emit('join_table', {
            session_id: player.sessionId
        }, handleJoinTableResponse);
    }
}

function handleJoinTableResponse(response) {
    if (response && response.table_id) {
        gameState.tableId = response.table_id;
        gameState.gameId = response.game_id;

        loginCard.classList.add('hidden');
        gameContainer.style.display = 'block';
    }
}

function handleGameStateUpdate(state) {
    console.log('Game state update:', state);

    // Update game state
    gameState.state = state.state;
    gameState.players = state.players || [];
    gameState.pot = state.pot || 0;
    gameState.timer = state.timer;
    gameState.chatEnabled = state.chat_enabled !== false;

    updateUI(state);
}

function handlePlayerJoined(playerData) {
    console.log('Player joined:', playerData);

    // Add chat message
    addSystemChatMessage(`${playerData.username || 'Anonymous'} joined the table`);
}

function handlePlayerLeft(playerData) {
    console.log('Player left:', playerData);

    // Add chat message
    addSystemChatMessage(`${playerData.username || 'Anonymous'} left the table`);
}

function handleGameStarted() {
    console.log('Game started');

    // Add chat message
    addSystemChatMessage('Game started');
}

function handleTimerUpdate(data) {
    // Update timer
    timerElement.textContent = data.timer;

    // Make timer pulse when low
    if (data.timer <= 3) {
        timerElement.style.color = 'var(--neon-pink)';
        timerElement.style.textShadow = '0 0 10px var(--neon-pink), 0 0 20px var(--neon-pink)';
    } else {
        timerElement.style.color = 'white';
        timerElement.style.textShadow = '0 0 10px var(--neon-pink)';
    }
}

function handleChatMessage(message) {
    // Add chat message
    addChatMessage(message);
}

function handleHandResult(result) {
    console.log('Hand result:', result);

    // Add chat message
    addSystemChatMessage(`${result.winner.username || 'Anonymous'} won the pot of ${result.pot_amount} chips!`);
}

function handleError(error) {
    console.error('Error:', error);
    alert(error.message || 'An error occurred');
}

// Game Actions
function selectCard(cardIndex) {
    gameState.selectedCard = cardIndex;

    // Update UI
    updatePlayerCards();
}

function selectAction(action) {
    if (gameState.selectedCard === null) {
        alert('Please select a card first');
        return;
    }

    // Send action to server
    socket.emit('player_action', {
        session_id: player.sessionId,
        table_id: gameState.tableId,
        action_type: action,
        action_data: {
            card_index: gameState.selectedCard
        }
    });

    // Reset selection
    if (gameState.selectedCard) {
        gameState.selectedCard = null;
    }
}

function placeBet() {
    const betAmount = prompt('Enter bet amount:', '10');

    if (betAmount === null) {
        return;
    }

    const amount = parseInt(betAmount);

    if (isNaN(amount) || amount <= 0 || amount > player.chips) {
        alert('Invalid bet amount');
        return;
    }

    processPlaceBet(player.sessionId, amount);
}

function processPlaceBet(playerId, amount) {
    socket.emit('player_action', {
        session_id: playerId,
        table_id: gameState.tableId,
        action_type: 'bet',
        action_data: {
            amount: amount
        }
    });

}

function check() {
    // Send action to server
    socket.emit('player_action', {
        session_id: player.sessionId,
        table_id: gameState.tableId,
        action_type: 'check',
        action_data: {}
    });
}

function fold() {
    // Send action to server
    socket.emit('player_action', {
        session_id: player.sessionId,
        table_id: gameState.tableId,
        action_type: 'fold',
        action_data: {}
    });
}

function sendChatMessage() {
    const message = chatInput.value.trim();

    if (!message) {
        return;
    }

    // Check if chat is enabled
    if (!gameState.chatEnabled) {
        alert('Chat is currently disabled');
        return;
    }

    // Send message to server
    socket.emit('chat_message', {
        session_id: player.sessionId,
        table_id: gameState.tableId,
        message: message
    });

    // Clear input
    chatInput.value = '';
}

// UI Update Functions
function updatePlayerInfo() {
    // Show player info
    playerInfo.classList.remove('hidden');

    // Update username
    usernameDisplay.textContent = player.username || 'Anonymous';

    // Update chip count
    chipCountDisplay.textContent = player.chips;

    // Show username form if not permanent
    if (!player.isPermanent) {
        usernameForm.classList.remove('hidden');
    }

    // Show claim chips button if chips are low
    if (player.chips < 100) {
        claimChipsBtn.classList.remove('hidden');
    } else {
        claimChipsBtn.classList.add('hidden');
    }
}

function updateGameStatus() {
    let statusText = '';

    switch (gameState.state) {
        case 'waiting':
            statusText = 'Waiting for players...';
            break;
        case 'ante':
            statusText = 'Before starting, please put an ante in the pot.';
            break;
        case 'card_draw':
            statusText = 'Cards are drawn. Game starting soon...';
            break;
        case 'choose_trash':
            statusText = 'Choose Card to Trash!';
            break;
        case 'choose_tango':
            statusText = 'Choose Card to Tango!';
            break;
        case 'pre_kick_betting':
            statusText = 'Pre-Draw-Card Betting Round';
            break;
        case 'turn_draw':
            statusText = 'Draw Card Round';
            break;
        case 'post_turn_betting':
            statusText = 'Post-Draw-Card Betting Round';
            break;
        case 'board_reveal':
            statusText = 'Revealing Community Cards';
            break;
        case 'final_betting':
            statusText = 'Final Betting Round';
            break;
        case 'showdown':
            statusText = 'Showdown';
            break;
        case 'end':
            statusText = 'Player X Wins Pot! (XYZ)';
            break;
        default:
            statusText = gameState.state;
    }

    gameStatusElement.textContent = statusText;
}

function updatePlayers() {
    // Clear player positions
    for (let i = 0; i < 5; i++) {
        const position = document.getElementById(`position-${i}`);
        position.style.visibility = 'hidden';
    }

    // Add players
    gameState.players.forEach((player, index) => {
        const position = document.getElementById(`position-${index}`);
        position.style.visibility = 'visible';

        const nameElement = position.querySelector('.player-name');
        const chipsElement = position.querySelector('.player-chips');

        nameElement.textContent = player.username || `Player ${player.id}`;
        chipsElement.textContent = player.chips + ' chips';

        // Add status indicator if folded
        if (player.status === 'folded') {
            nameElement.textContent += ' (Folded)';
        }
    });
}

function updatePot() {
    potElement.textContent = `Pot: ${gameState.pot}`;
}

function updateCommunityCards(cards) {
    // Clear community cards
    communityCardsElement.innerHTML = '';

    // Add community cards
    if (cards && cards.length > 0) {
        cards.forEach(card => {
            const cardElement = createCardElement(card);
            communityCardsElement.appendChild(cardElement);
        });
    } else {
        // Add placeholders
        for (let i = 0; i < 5; i++) {
            const placeholder = document.createElement('div');
            placeholder.className = 'card-placeholder';
            communityCardsElement.appendChild(placeholder);
        }
    }
}

function updatePlayerCards() {
    console.log('updating player cards...');
    // Clear player cards
    playerCardsElement.innerHTML = '';

    // Find current player

    const currentPlayer = gameState.players.find(p => p.id === player.id);

    if (currentPlayer && currentPlayer.cards) {
        // Add player cards
        console.log('adding player cards for ' + currentPlayer);
        currentPlayer.cards.forEach((card, index) => {
            console.log('adding card ' + card);
            const cardElement = createCardElement(card);

            // // Add selected class if this card is selected
            // if (gameState.selectedCard === index) {
            //     cardElement.style.transform = 'translateY(-20px)';
            //     cardElement.style.boxShadow = '0 0 20px rgba(5, 217, 232, 0.7)';
            // }

            // // Add click event
            // cardElement.addEventListener('click', () => {
            //     selectCard(index);
            // });

            playerCardsElement.appendChild(cardElement);
            console.log('added   card ' + card);
        });
        console.log('added player cards!');

        // Add turn card if available
        if (currentPlayer.turn_card) {
            const turnCard = createCardElement(currentPlayer.turn_card);
            playerCardsElement.appendChild(turnCard);
        }
    }
}

function updateControls() {
    // Hide all controls
    cardActionsTrash.classList.add('hidden');
    cardActionsTango.classList.add('hidden');
    checkBtn.classList.add('hidden');
    betBtn.classList.add('hidden');
    foldBtn.classList.add('hidden');

    const currentPlayer = gameState.players.find(p => p.id === player.id);

    // Show appropriate controls based on game state
    if (gameState.state == 'ante') {
        betBtn.classList.remove('hidden');
        document.getElementById('bet-btn').onclick = placeBet;
    }
    if (gameState.state === 'choose_trash') {
        if (currentPlayer.decisions.kill == null) {
            cardActionsTrash.classList.remove('hidden');
        }

        // Add event listeners
        document.getElementById('kill-action-1').onclick = () => {
            alert('removing cardactionsTrash by adding hidden');
            cardActionsTrash.classList.add('hidden');
            gameState.selectedCard = 0;
            selectAction('kill');
        };
        document.getElementById('kill-action-2').onclick = () => {
            alert('removing cardactionsTrash by adding hidden');
            cardActionsTrash.classList.add('hidden');
            gameState.selectedCard = 1;
            selectAction('kill');
        };
        document.getElementById('kill-action-3').onclick = () => {
            alert('removing cardactionsTrash by adding hidden');
            cardActionsTrash.classList.add('hidden');
            gameState.selectedCard = 2;
            selectAction('kill');
        };
    } else if (gameState.state === 'choose_tango') {
        cardActionsTango.classList.remove('hidden');

        // Add event listeners
        document.getElementById('kick-action-1').onclick = () => {
            gameState.selectedCard = 0;
            selectAction('kick');
        };
        document.getElementById('kick-action-2').onclick = () => {
            gameState.selectedCard = 1;
            selectAction('kick');
        };
        document.getElementById('kick-action-3').onclick = () => {
            gameState.selectedCard = 2;
            selectAction('kick');
        };
    } else if (['pre_kick_betting', 'post_turn_betting', 'final_betting'].includes(gameState.state)) {
        checkBtn.classList.remove('hidden');
        betBtn.classList.remove('hidden');
        foldBtn.classList.remove('hidden');

        // Add event listeners
        document.getElementById('check-btn').onclick = check;
        document.getElementById('bet-btn').onclick = placeBet;
        document.getElementById('fold-btn').onclick = fold;
    }
}

function updateChatStatus() {
    chatStatusElement.textContent = gameState.chatEnabled ? 'Enabled' : 'Disabled';
    chatStatusElement.className = gameState.chatEnabled ? 'chat-status' : 'chat-status disabled';

    // Disable/enable chat input
    chatInput.disabled = !gameState.chatEnabled;
    sendChatBtn.disabled = !gameState.chatEnabled;
}

function addChatMessage(message) {
    const messageElement = document.createElement('div');
    messageElement.className = 'chat-message';

    const header = document.createElement('div');
    header.className = 'message-header';

    const username = document.createElement('div');
    username.className = 'message-username';
    username.textContent = message.username || 'Anonymous';

    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = new Date(message.timestamp).toLocaleTimeString();

    const content = document.createElement('div');
    content.className = 'message-content';
    content.textContent = message.message;

    header.appendChild(username);
    header.appendChild(time);

    messageElement.appendChild(header);
    messageElement.appendChild(content);

    chatMessages.appendChild(messageElement);

    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addSystemChatMessage(message) {
    const messageElement = document.createElement('div');
    messageElement.className = 'chat-message';

    const content = document.createElement('div');
    content.className = 'message-content';
    content.style.backgroundColor = 'rgba(5, 217, 232, 0.1)';
    content.style.color = 'var(--neon-blue)';
    content.textContent = message;

    messageElement.appendChild(content);

    chatMessages.appendChild(messageElement);

    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Helper Functions
function createCardElement(card) {
    const cardElement = document.createElement('div');
    cardElement.className = `playing-card ${card.suit}`;

    const topLeft = document.createElement('div');
    topLeft.className = 'card-top-left';

    const rankTop = document.createElement('div');
    rankTop.className = 'card-rank';
    rankTop.textContent = card.rank;

    const suitTop = document.createElement('div');
    suitTop.className = 'card-suit';
    suitTop.textContent = getSuitSymbol(card.suit);

    topLeft.appendChild(rankTop);
    topLeft.appendChild(suitTop);

    const center = document.createElement('div');
    center.className = 'card-center';
    center.textContent = getSuitSymbol(card.suit);

    const bottomRight = document.createElement('div');
    bottomRight.className = 'card-bottom-right';

    const rankBottom = document.createElement('div');
    rankBottom.className = 'card-rank';
    rankBottom.textContent = card.rank;

    const suitBottom = document.createElement('div');
    suitBottom.className = 'card-suit';
    suitBottom.textContent = getSuitSymbol(card.suit);

    bottomRight.appendChild(rankBottom);
    bottomRight.appendChild(suitBottom);

    cardElement.appendChild(topLeft);
    cardElement.appendChild(center);
    cardElement.appendChild(bottomRight);

    return cardElement;
}

function getSuitSymbol(suit) {
    switch (suit) {
        case 'hearts':
            return '♥';
        case 'diamonds':
            return '♦';
        case 'clubs':
            return '♣';
        case 'spades':
            return '♠';
        default:
            return '';
    }
}