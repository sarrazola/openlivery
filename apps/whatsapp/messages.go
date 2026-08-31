package main

import (
	"strings"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/types"
)

// unwrapMessage peels the wrappers WhatsApp puts around regular content
// (disappearing messages, view-once media) so extraction sees the real payload.
func unwrapMessage(msg *waE2E.Message) *waE2E.Message {
	for msg != nil {
		switch {
		case msg.GetEphemeralMessage().GetMessage() != nil:
			msg = msg.GetEphemeralMessage().GetMessage()
		case msg.GetViewOnceMessage().GetMessage() != nil:
			msg = msg.GetViewOnceMessage().GetMessage()
		case msg.GetViewOnceMessageV2().GetMessage() != nil:
			msg = msg.GetViewOnceMessageV2().GetMessage()
		case msg.GetViewOnceMessageV2Extension().GetMessage() != nil:
			msg = msg.GetViewOnceMessageV2Extension().GetMessage()
		case msg.GetDocumentWithCaptionMessage().GetMessage() != nil:
			msg = msg.GetDocumentWithCaptionMessage().GetMessage()
		case msg.GetEditedMessage().GetMessage() != nil:
			msg = msg.GetEditedMessage().GetMessage()
		default:
			return msg
		}
	}
	return nil
}

// incomingText mirrors the visible text of an incoming message: plain text,
// captions, and the labels of interactive replies.
func incomingText(msg *waE2E.Message) string {
	content := unwrapMessage(msg)
	if content == nil {
		return ""
	}
	candidates := []string{
		content.GetConversation(),
		content.GetExtendedTextMessage().GetText(),
		content.GetImageMessage().GetCaption(),
		content.GetVideoMessage().GetCaption(),
		content.GetButtonsResponseMessage().GetSelectedDisplayText(),
		content.GetListResponseMessage().GetTitle(),
		content.GetTemplateButtonReplyMessage().GetSelectedDisplayText(),
	}
	for _, candidate := range candidates {
		if trimmed := strings.TrimSpace(candidate); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

type incomingMediaInfo struct {
	kind     string // image | audio | video
	mimetype string
	length   uint64
	download whatsmeow.DownloadableMessage
}

// incomingMedia reports downloadable media the backend understands. Stickers
// and documents are ignored, matching what the previous bridge forwarded.
func incomingMedia(msg *waE2E.Message) *incomingMediaInfo {
	content := unwrapMessage(msg)
	if content == nil {
		return nil
	}
	if image := content.GetImageMessage(); image != nil {
		return &incomingMediaInfo{kind: "image", mimetype: orDefault(image.GetMimetype(), "image/jpeg"), length: image.GetFileLength(), download: image}
	}
	if audio := content.GetAudioMessage(); audio != nil {
		return &incomingMediaInfo{kind: "audio", mimetype: orDefault(audio.GetMimetype(), "audio/ogg"), length: audio.GetFileLength(), download: audio}
	}
	if video := content.GetVideoMessage(); video != nil {
		return &incomingMediaInfo{kind: "video", mimetype: orDefault(video.GetMimetype(), "video/mp4"), length: video.GetFileLength(), download: video}
	}
	return nil
}

// isDirectIncoming keeps only person-to-person messages: no own echoes, no
// groups, no status broadcast, no newsletters.
func isDirectIncoming(info types.MessageInfo) bool {
	if info.IsFromMe || info.IsGroup || info.ID == "" {
		return false
	}
	switch info.Chat.Server {
	case types.DefaultUserServer, types.HiddenUserServer:
		return true
	}
	return false
}

func orDefault(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}
