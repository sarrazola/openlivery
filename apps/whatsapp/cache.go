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
