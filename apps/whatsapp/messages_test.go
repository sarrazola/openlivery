package main

import (
	"testing"

	"google.golang.org/protobuf/proto"

	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/types"
)

func TestIncomingTextReadsPlainAndWrappedContent(t *testing.T) {
	plain := &waE2E.Message{Conversation: proto.String("  hola  ")}
	if got := incomingText(plain); got != "hola" {
		t.Fatalf("plain text: got %q", got)
	}

	extended := &waE2E.Message{ExtendedTextMessage: &waE2E.ExtendedTextMessage{Text: proto.String("link text")}}
	if got := incomingText(extended); got != "link text" {
		t.Fatalf("extended text: got %q", got)
	}

	caption := &waE2E.Message{ImageMessage: &waE2E.ImageMessage{Caption: proto.String("una foto")}}
	if got := incomingText(caption); got != "una foto" {
		t.Fatalf("image caption: got %q", got)
	}

	ephemeral := &waE2E.Message{EphemeralMessage: &waE2E.FutureProofMessage{
		Message: &waE2E.Message{Conversation: proto.String("secreto")},
	}}
	if got := incomingText(ephemeral); got != "secreto" {
		t.Fatalf("ephemeral wrapper: got %q", got)
	}

	if got := incomingText(&waE2E.Message{}); got != "" {
		t.Fatalf("empty message: got %q", got)
	}
}

func TestIncomingMediaDetectsSupportedKinds(t *testing.T) {
	image := &waE2E.Message{ImageMessage: &waE2E.ImageMessage{Mimetype: proto.String("image/png")}}
	if media := incomingMedia(image); media == nil || media.kind != "image" || media.mimetype != "image/png" {
		t.Fatalf("image: got %+v", media)
	}

	audio := &waE2E.Message{AudioMessage: &waE2E.AudioMessage{}}
	if media := incomingMedia(audio); media == nil || media.kind != "audio" || media.mimetype != "audio/ogg" {
		t.Fatalf("audio default mime: got %+v", media)
	}

	sticker := &waE2E.Message{StickerMessage: &waE2E.StickerMessage{}}
	if media := incomingMedia(sticker); media != nil {
		t.Fatalf("stickers must be ignored, got %+v", media)
	}

	document := &waE2E.Message{DocumentMessage: &waE2E.DocumentMessage{}}
	if media := incomingMedia(document); media != nil {
		t.Fatalf("documents must be ignored, got %+v", media)
	}
}

func directInfo(jid types.JID, fromMe, isGroup bool) types.MessageInfo {
	info := types.MessageInfo{ID: "MSG1"}
	info.Chat = jid
	info.IsFromMe = fromMe
	info.IsGroup = isGroup
	return info
}

func TestIsDirectIncomingFiltersNonPersonalChats(t *testing.T) {
	user := types.NewJID("573001112233", types.DefaultUserServer)
	if !isDirectIncoming(directInfo(user, false, false)) {
		t.Fatal("direct user message must pass")
	}
	lid := types.NewJID("123456", types.HiddenUserServer)
	if !isDirectIncoming(directInfo(lid, false, false)) {
		t.Fatal("lid message must pass")
	}
	if isDirectIncoming(directInfo(user, true, false)) {
		t.Fatal("own message must be filtered")
	}
	group := types.NewJID("12036302", types.GroupServer)
	if isDirectIncoming(directInfo(group, false, true)) {
		t.Fatal("group message must be filtered")
	}
	if isDirectIncoming(directInfo(types.StatusBroadcastJID, false, false)) {
		t.Fatal("status broadcast must be filtered")
	}
	newsletter := types.NewJID("120363", types.NewsletterServer)
	if isDirectIncoming(directInfo(newsletter, false, false)) {
		t.Fatal("newsletter must be filtered")
	}
	noID := directInfo(user, false, false)
	noID.ID = ""
	if isDirectIncoming(noID) {
		t.Fatal("message without id must be filtered")
	}
}

func TestIsDirectOutgoingKeepsWhatTheBusinessTyped(t *testing.T) {
	user := types.NewJID("573001112233", types.DefaultUserServer)
	if !isDirectOutgoing(directInfo(user, true, false)) {
		t.Fatal("a message typed on the linked phone must be forwarded")
	}
	if isDirectOutgoing(directInfo(user, false, false)) {
		t.Fatal("a contact's message is not our own")
	}
	if isDirectOutgoing(directInfo(types.NewJID("12036302", types.GroupServer), true, false)) {
		t.Fatal("groups stay out")
	}
	noID := directInfo(user, true, false)
	noID.ID = ""
	if isDirectOutgoing(noID) {
		t.Fatal("a message without id must be filtered")
	}
}

func TestEchoSetRecognisesOurOwnSends(t *testing.T) {
	echoes := newEchoSet()
	echoes.remember("channel", "WAMID1")

	if !echoes.sentByUs("channel", "WAMID1") {
		t.Fatal("a message the bridge sent must be recognised as its own echo")
	}
	if echoes.sentByUs("channel", "TYPED-ON-THE-PHONE") {
		t.Fatal("a message we never sent is someone typing on the phone")
	}
	if echoes.sentByUs("other-channel", "WAMID1") {
		t.Fatal("channels must not share echoes")
	}
	for i := 0; i < echoSetSize; i++ {
		echoes.remember("channel", string(rune('a'+i%26))+string(rune('0'+i/26)))
	}
	if echoes.sentByUs("channel", "WAMID1") {
		t.Fatal("the oldest ids must be forgotten once the set is full")
	}
}
