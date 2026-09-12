package main

import (
	"sync"

	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/types"
)

// Per-channel cap on remembered messages; enough to quote or react to anything
// recent without unbounded growth.
const messageCacheSize = 500

// cachedMessage keeps what quoting and reacting need about a recent message:
// the raw proto (for a faithful quoted preview) and the original addressing
// (LID chats keep their LID here even when the backend sees the phone JID).
type cachedMessage struct {
	raw    *waE2E.Message
	chat   types.JID
	sender types.JID
	fromMe bool
}

type channelMessages struct {
	order []string
	items map[string]cachedMessage
}

type messageCache struct {
	mu       sync.Mutex
	channels map[string]*channelMessages
}

func newMessageCache() *messageCache {
	return &messageCache{channels: make(map[string]*channelMessages)}
}

func (c *messageCache) put(channelID, messageID string, message cachedMessage) {
	if messageID == "" {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	channel, ok := c.channels[channelID]
	if !ok {
		channel = &channelMessages{items: make(map[string]cachedMessage)}
		c.channels[channelID] = channel
	}
	if _, exists := channel.items[messageID]; !exists {
		channel.order = append(channel.order, messageID)
		if len(channel.order) > messageCacheSize {
			oldest := channel.order[0]
			channel.order = channel.order[1:]
			delete(channel.items, oldest)
		}
	}
	channel.items[messageID] = message
}

func (c *messageCache) get(channelID, messageID string) (cachedMessage, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	channel, ok := c.channels[channelID]
	if !ok {
		return cachedMessage{}, false
	}
	message, ok := channel.items[messageID]
	return message, ok
}

func (c *messageCache) drop(channelID string) {
	c.mu.Lock()
	delete(c.channels, channelID)
	c.mu.Unlock()
}

// Per-channel cap on remembered ids of our own sends. WhatsApp echoes every
// message back to the linked device, and without this the bridge would report
// its own replies to the backend as "the business typed this on the phone".
const echoSetSize = 400

type channelEchoes struct {
	order []string
	items map[string]struct{}
}

type echoSet struct {
	mu       sync.Mutex
	channels map[string]*channelEchoes
}

func newEchoSet() *echoSet {
	return &echoSet{channels: make(map[string]*channelEchoes)}
}

func (e *echoSet) remember(channelID, messageID string) {
	if messageID == "" {
		return
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	channel, ok := e.channels[channelID]
	if !ok {
		channel = &channelEchoes{items: make(map[string]struct{})}
		e.channels[channelID] = channel
	}
	if _, exists := channel.items[messageID]; exists {
		return
	}
	channel.items[messageID] = struct{}{}
	channel.order = append(channel.order, messageID)
	if len(channel.order) > echoSetSize {
		oldest := channel.order[0]
		channel.order = channel.order[1:]
		delete(channel.items, oldest)
	}
}

func (e *echoSet) sentByUs(channelID, messageID string) bool {
	e.mu.Lock()
	defer e.mu.Unlock()
	channel, ok := e.channels[channelID]
	if !ok {
		return false
	}
	_, found := channel.items[messageID]
	return found
}

func (e *echoSet) drop(channelID string) {
	e.mu.Lock()
	delete(e.channels, channelID)
	e.mu.Unlock()
}
