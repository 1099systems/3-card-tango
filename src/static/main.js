var gameState;

// Socket Connection
const socket = io();
let winnerMessage = '';

async function debugAddPlayer(username) {
    getPlayerOrCreate(username, username).then((result) => {
        socket.emit('join_table', {
            session_id: result.sessionId
        });
    });
}


function debugNextPhase() {
    let newGameState = gameState;

    fetch('/api/next-state', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            game_state: gameState,
            table_id: gameState.tableId
        })
    }).then(async (response) => {
        const data = await response.json();
        newGameState = data.game_state
        handleGameStateUpdate(newGameState);
    });
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
        console.log('Player data:', data);
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

function debugPlaceBet(playerId, amount) {
    processPlaceBet(playerId, amount);
}

function debugChooseTrash(playerId, index) {
    processChooseTrash(playerId, index);
}

function debugChooseTango(playerId, index) {
    processChooseTango(playerId, index);
}

function debugChooseFold(playerId, index) {
    processCheck(playerId);
}

function debugChooseCall(playerId) {
    processCall(playerId, index);
}

function debugChooseRaise(playerId, amount) {
    processPlaceBet(playerId, amount + 1);
}

function processChooseTrash(sessionId, index) {
    cardActionsTrash.classList.add('hidden');
    gameState.selectedCard = index;
    selectAction(sessionId, 'kill', index);
}

function processChooseTango(sessionId, index) {
    cardActionsTango.classList.add('hidden');
    gameState.selectedCard = index;
    selectAction(sessionId, 'kick', index);
}

function updateUI(state) {
    updateGameStatus();
    updatePlayers();
    updatePot();
    updateCommunityCards();
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
const foldBtn = document.getElementById('fold-btn');
const callBtn = document.getElementById('call-btn');
const betControl = document.getElementById('bet-control');
const betBtn = document.getElementById('bet-btn');
const betBtnTxt = document.getElementById('bet-btn-txt');
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
    fetchPlayerData();

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
    gameState.currentPlayerIndex = state.current_player_index || 0;
    gameState.currentBet = state.current_bet || 0;
    if (state.community_cards) {
        gameState.communityCards = state.community_cards;
    }

    updateUI(gameState);
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
    addSystemChatMessage('Game started'); a
}

let displayedTime = 0;
let lastUpdateTime = Date.now();
let timerInterval;

function handleTimerUpdate(data) {
    console.log('Timer update:', data);
    // Display it incase it is hidden (value 0)
    timerElement.style.display = 'block';

    // Record the server time and timestamp of update
    displayedTime = data.timer;
    lastUpdateTime = Date.now();

    // Clear old interval if any
    clearInterval(timerInterval);

    // Start smooth countdown
    timerInterval = setInterval(() => {
        const now = Date.now();
        const elapsed = (now - lastUpdateTime) / 1000;
        const remaining = Math.max(0, displayedTime - elapsed);

        timerElement.textContent = remaining.toFixed(2);

        // Make timer pulse when low
        if (remaining <= 3) {
            timerElement.style.color = 'var(--neon-pink)';
            timerElement.style.textShadow = '0 0 10px var(--neon-pink), 0 0 20px var(--neon-pink)';
        } else {
            timerElement.style.color = 'white';
            timerElement.style.textShadow = '0 0 10px var(--neon-pink)';
        }

        if (remaining === 0) {
            clearInterval(timerInterval);
            timerElement.style.display = 'none'; // Hide the timer
        }
    }, 10); // update every 10ms for smooth 2-decimal countdown
}


function handleChatMessage(message) {
    // Add chat message
    addChatMessage(message);
}

function handleHandResult(result) {
    console.log('Hand result:', result);

    // winnerMessage = `🏆Congratulations to the winners! \n\n`;
    winnerMessage = ``;

    let winnerList = '';
    for (const winner of result.winners) {
        if (winner.is_main_winner) {
            winnerList += `🏆 ${winner.username || 'Anonymous'} Wins Main Pot (${winner.amount_won})`;
        } else {
            winnerList += `\n\n🥈 ${winner.username || 'Anonymous'} Wins Side Pot (${winner.amount_won})`;
        }
    }

    winnerMessage += winnerList

    // winnerMessage = `🏆Congratulations to the winners! ${result.winner.username || 'Anonymous'} Wins Pot! (${result.pot_amount})`;
    // Add chat message
    
    alert(winnerMessage);
    addSystemChatMessage(winnerMessage);
    // gameStatusElement.textContent = winnerMessage;
    gameStatusElement.innerHTML = winnerMessage.replace(/\n/g, '<br>');

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

let isProcessingAction = false;
function selectAction(sessionId, action, card_index) {
    if (isProcessingAction) {
        console.warn('Action already in progress, ignoring...');
        return;
    };

    if (gameState.selectedCard === null) {
        alert('Please select a card first');
        return;
    }

    // Send action to server
    socket.emit('player_action', {
        session_id: sessionId,
        table_id: gameState.tableId,
        action_type: action,
        action_data: {
            card_index: card_index
        }
    });

    // Reset selection
    if (gameState.selectedCard) {
        gameState.selectedCard = null;
    }
}

function placeBet() {
    const betAmount = betValue;

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


function call() {
    processCall(player.sessionId);
}

function processCall(sessionId) {
    const betAmount = gameState.currentBet

    if (betAmount === null) {
        return;
    }

    const amount = parseInt(betAmount);

    if (isNaN(amount) || amount <= 0 || amount > player.chips) {
        alert('Invalid bet amount');
        return;
    }

    processPlaceBet(sessionId, amount);
}


function processPlaceBet(playerId, amount) {
    betBtn.classList.add('hidden');
    betControl.classList.add('hidden');
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
    processCheck(player.sessionId);
}

function processCheck(sessionId) {
    // Send action to server
    socket.emit('player_action', {
        session_id: sessionId,
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

    var currentPlayer = gameState.players[gameState.currentPlayerIndex]?.username || 'Unknown';

    switch (gameState.state) {
        case 'waiting':
            statusText = 'Waiting for players...';
            break;
        case 'ante':
            statusText = 'Please put an ante in the pot.';
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
            statusText = 'Pre-Draw-Card Betting Round (' + currentPlayer + ')';
            break;
        case 'turn_draw':
            statusText = 'Draw Card Round';
            break;
        case 'post_turn_betting':
            statusText = 'Post-Draw-Card Betting Round (' + currentPlayer + ')';
            break;
        case 'board_reveal':
            statusText = 'Community Cards Revealed';
            break;
        case 'final_betting':
            statusText = 'Final Betting Round (' + currentPlayer + ')';
            break;
        case 'showdown':
            statusText = 'Showdown (Determining winners..)';
            break;
        case 'end':
            statusText = winnerMessage;
            break;
        case 'next_hand':
            statusText = 'Next game starting in';
            break;
        default:
            statusText = gameState.state;
    }

    gameStatusElement.textContent = statusText;
}

function convertToTitleCase(text) {
    return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

function updatePlayers() {
    // Clear player positions
    for (let i = 0; i < 5; i++) {
        const position = document.getElementById(`position-${i}`);
        position.style.visibility = 'hidden';

        const cardsElement = position.querySelector('.player-cards');
        cardsElement.innerHTML = ''; // Clear any previous cards
    }

    // Add players
    gameState.players.forEach((p, index) => {
        const position = document.getElementById(`position-${index}`);
        position.style.visibility = 'visible';

        const nameElement = position.querySelector('.player-name');
        const chipsElement = position.querySelector('.player-chips');
        const playerCardsElement = position.querySelector('.player-cards');


        nameElement.textContent = p.username || `Player ${p.id}`;
        if (p.id === player.id) {
            nameElement.textContent += ` (You)`;
        }
        chipsElement.textContent = p.chips + ' chips';

        // Add status indicator if folded
        if (p.status === 'folded') {
            nameElement.textContent += ' (Folded)';
        }

        if (p.status === 'checked') {
            nameElement.textContent += ' (Checked)';
        }

        if (p.status.includes('betted')) {
            nameElement.textContent += ' (' + convertToTitleCase(p.status) + ')';
        }


        if (p.cards) {
            // Add player cards
            p.cards.forEach((card, index) => {
                const cardElement = createBackFacingCardElement();

                playerCardsElement.appendChild(cardElement);
            });

            // Add turn card if available
            if (p.turn_card) {
                const turnCard = createBackFacingCardElement();
                playerCardsElement.appendChild(turnCard);
            }
        }
    });
}

function updatePot() {
    potElement.textContent = `Pot: ${gameState.pot}`;
}

function updateCommunityCards() {
    // Clear community cards
    communityCardsElement.innerHTML = '';

    cards = gameState.communityCards;

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
    // Clear player cards
    playerCardsElement.innerHTML = '';

    // Find current player
    const currentPlayer = gameState.players.find(p => p.id === player.id);

    if (currentPlayer && currentPlayer.cards) {
        // Add player cards
        currentPlayer.cards.forEach((card, index) => {
            const cardElement = createCardElement(card);

            playerCardsElement.appendChild(cardElement);
        });

        // Add turn card if available
        if (currentPlayer.turn_card) {
            const turnCard = createCardElement(currentPlayer.turn_card);
            playerCardsElement.appendChild(turnCard);
        }
    }
}

function displayBetControl(display) {
    if (display) {
        betControl.classList.remove('hidden');
        betBtn.classList.remove('hidden');
        return;
    }

    betControl.classList.add('hidden');
    betBtn.classList.add('hidden');
}

function didPreviousPlayerMakeABet(gameState) {
    const { players, currentPlayerIndex } = gameState;

    if (!Array.isArray(players) || players.length === 0) return false;

    const prevIndex = (currentPlayerIndex - 1 + players.length) % players.length;
    const prevPlayer = players[prevIndex];

    const action = prevPlayer.last_action || '';

    // Check if last_action starts with any known bet prefix
    return (
        action.startsWith('pre_kick_bet') ||
        action.startsWith('post_turn_bet') ||
        action.startsWith('final_bet')
    );
}



function updateControls() {
    // Hide all controls
    cardActionsTrash.classList.add('hidden');
    cardActionsTango.classList.add('hidden');
    checkBtn.classList.add('hidden');
    foldBtn.classList.add('hidden');
    callBtn.classList.add('hidden');
    displayBetControl(false);

    const currentPlayer = gameState.players.find(p => p.id === player.id);
    const currentPlayerIndex = gameState.players.findIndex(p => p.id === player.id);

    // Show appropriate controls based on game state
    if (gameState.state == 'ante') {
        if (!('last_action' in currentPlayer)) {
            displayBetControl(true);
            betBtnTxt.innerHTML = 'Bet';
        }
        document.getElementById('bet-btn').onclick = placeBet;
    }
    if (gameState.state === 'choose_trash') {
        if (currentPlayer.decisions.kill == null) {
            cardActionsTrash.classList.remove('hidden');
        }

        // Add event listeners
        document.getElementById('kill-action-1')?.addEventListener('click', (e) => {
            e.currentTarget.disabled = true;
            processChooseTrash(player.sessionId, 0);
        }, { once: true });
        document.getElementById('kill-action-2')?.addEventListener('click', (e) => {
            e.currentTarget.disabled = true;
            processChooseTrash(player.sessionId, 1);
        }, { once: true });
        document.getElementById('kill-action-3')?.addEventListener('click', (e) => {
            e.currentTarget.disabled = true;
            processChooseTrash(player.sessionId, 2);
        }, { once: true });
    } else if (gameState.state === 'choose_tango') {
        if (currentPlayer.decisions.kick == null) {
            cardActionsTango.classList.remove('hidden');
        }

        document.getElementById('kick-action-1')?.addEventListener('click', (e) => {
            e.currentTarget.disabled = true;
            processChooseTango(player.sessionId, 0);
        }, { once: true });
        document.getElementById('kick-action-2')?.addEventListener('click', (e) => {
            e.currentTarget.disabled = true;
            processChooseTango(player.sessionId, 1);
        }, { once: true });
        document.getElementById('kick-action-3')?.addEventListener('click', (e) => {
            e.currentTarget.disabled = true;
            processChooseTango(player.sessionId, 2);
        }, { once: true });

    } else if (['pre_kick_betting', 'post_turn_betting', 'final_betting'].includes(gameState.state)) {
        if (gameState.state == 'pre_kick_betting' && currentPlayer.last_action.includes('pre_kick_bet')) {
            console.log('Player already made a bet in this betting round')
            return;

        } else if (gameState.state == 'post_turn_betting' && currentPlayer.last_action.includes('post_turn_bet')) {
            console.log('Player already made a bet in this betting round')
            return;

        } else if (gameState.state == 'final_betting' && currentPlayer.last_action.includes('final_bet')) {
            console.log('Player already made a bet in this betting round')
            return;

        }

        let isCurrentPlayerTurn = false;
        if (gameState.currentPlayerIndex == currentPlayerIndex) {
            isCurrentPlayerTurn = true;
        }

        if (isCurrentPlayerTurn) {
            displayBetControl(true);
            console.log('Current player is the playing player, showing bet controls');

            if (gameState.currentPlayerIndex == 0 || !didPreviousPlayerMakeABet(gameState)) { // Add condition, if index=0 hasn't made a bet
                checkBtn.classList.remove('hidden');
                betBtnTxt.innerHTML = 'Bet';
                console.log('Current player is first, showing check button');
            } else {
                foldBtn.classList.remove('hidden');
                callBtn.classList.remove('hidden');
                betBtnTxt.innerHTML = 'Raise';
                callValueDisplay.textContent = "(" + parseInt(gameState.currentBet) + ")";
                betValueDisplay.textContent = "(" + (parseInt(gameState.currentBet) + 1) + ")";
                console.log('Current player is not first, showing fold and call buttons');
            }
        } else {
            displayBetControl(false);
            console.log('Current player is not the playing player, hiding bet controls');
        }


        // Add event listeners
        document.getElementById('check-btn').onclick = check;
        // Does fold button need fold, or just check? I think it's similar.
        document.getElementById('fold-btn').onclick = check;
        // document.getElementById('fold-btn').onclick = fold;
        document.getElementById('call-btn').onclick = call;
        document.getElementById('bet-btn').onclick = placeBet;
    }
}

const slider = document.getElementById('bet-slider');
const numberInput = document.getElementById('bet-amount');
let betValue = 1;
const betValueDisplay = document.getElementById('bet-value');
const callValueDisplay = document.getElementById('call-value');

function updateBetValue(val) {
    numberInput.value = val;
    slider.value = val;
    betValue = parseInt(val ?? val.textContent);
    betValueDisplay.textContent = "(" + val + ")";
}

slider.addEventListener('input', (e) => updateBetValue(e.target.value));
numberInput.addEventListener('input', (e) => updateBetValue(e.target.value));


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
    if (card.is_tango) {
        cardElement.className = `playing-card playing-card--tango ${card.suit}`;
    } else {
        cardElement.className = `playing-card ${card.suit}`;
    }

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


function createBackFacingCardElement() {
    const placeholder = document.createElement('div');
    placeholder.className = 'card-placeholder';
    return placeholder;
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