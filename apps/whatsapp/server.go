package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"regexp"
	"strings"
)

// Outbound media arrives base64-encoded; the backend caps files at 20 MB.
const maxSendBytes = 30_000_000

var channelRoute = regexp.MustCompile(`(?i)^/channels/([0-9a-f-]+)/(connect|disconnect|send)$`)

// channelActions is what the HTTP layer needs from the manager; the tests
// substitute a fake.
type channelActions interface {
	connect(ctx context.Context, channelID string) error
	disconnect(ctx context.Context, channelID string) error
	send(ctx context.Context, channelID, remoteJID, text string, media *outboundMedia) (string, error)
}

type managerActions struct{ manager *manager }

func (a managerActions) connect(ctx context.Context, channelID string) error {
	return a.manager.connectChannel(ctx, channelID)
}

func (a managerActions) disconnect(ctx context.Context, channelID string) error {
	return a.manager.disconnectChannel(ctx, channelID)
}

func (a managerActions) send(ctx context.Context, channelID, remoteJID, text string, media *outboundMedia) (string, error) {
	return a.manager.sendMessage(ctx, channelID, remoteJID, text, media)
}

type sendPayload struct {
	RemoteJID    string   `json:"remote_jid"`
	Text         string   `json:"text"`
	MediaKind    string   `json:"media_kind"`
	MediaMime    string   `json:"media_mime"`
	MediaBase64  string   `json:"media_base64"`
	MediaSeconds *float64 `json:"media_seconds"`
	Filename     string   `json:"filename"`
}

// parseSendPayload validates the /send body the same way the previous bridge
// did: a destination plus text or media, unknown media kinds become documents.
func parseSendPayload(raw []byte) (remoteJID, text string, media *outboundMedia, err error) {
	var payload sendPayload
	if err := json.Unmarshal(raw, &payload); err != nil {
		return "", "", nil, errors.New("Invalid destination or message")
	}
	text = strings.TrimSpace(payload.Text)
	if payload.RemoteJID == "" || (text == "" && payload.MediaBase64 == "") {
		return "", "", nil, errors.New("Invalid destination or message")
	}
	if payload.MediaBase64 != "" {
		data, err := base64.StdEncoding.DecodeString(payload.MediaBase64)
		if err != nil {
			return "", "", nil, errors.New("Invalid destination or message")
		}
		kind := payload.MediaKind
		if kind != "image" && kind != "audio" && kind != "video" {
			kind = "file"
		}
		media = &outboundMedia{
			kind:     kind,
			data:     data,
			mime:     orDefault(payload.MediaMime, "application/octet-stream"),
			filename: payload.Filename,
		}
		if payload.MediaSeconds != nil && *payload.MediaSeconds > 0 {
			media.seconds = uint32(*payload.MediaSeconds + 0.5)
		}
	}
	return payload.RemoteJID, text, media, nil
}

func newHandler(actions channelActions, bridgeToken string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet && r.URL.Path == "/health" {
			writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
			return
		}
		if r.Header.Get("X-Bridge-Token") != bridgeToken {
			writeJSON(w, http.StatusUnauthorized, map[string]any{"error": "Invalid internal token"})
			return
		}
		match := channelRoute.FindStringSubmatch(r.URL.Path)
		if match == nil {
			writeJSON(w, http.StatusNotFound, map[string]any{"error": "Route not found"})
			return
		}
		if r.Method != http.MethodPost {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "Method not allowed"})
			return
		}
		channelID, action := match[1], strings.ToLower(match[2])
		switch action {
		case "connect":
			if err := actions.connect(r.Context(), channelID); err != nil {
				writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
				return
			}
			writeJSON(w, http.StatusAccepted, map[string]any{"ok": true})
		case "disconnect":
			if err := actions.disconnect(r.Context(), channelID); err != nil {
				writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"ok": true})
		case "send":
			raw, err := io.ReadAll(http.MaxBytesReader(w, r.Body, maxSendBytes))
			if err != nil {
				writeJSON(w, http.StatusInternalServerError, map[string]any{"error": "Request too large"})
				return
			}
			remoteJID, text, media, err := parseSendPayload(raw)
			if err != nil {
				writeJSON(w, http.StatusBadRequest, map[string]any{"error": err.Error()})
				return
			}
			externalMessageID, err := actions.send(r.Context(), channelID, remoteJID, text, media)
			if err != nil {
				writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"external_message_id": externalMessageID})
		}
	})
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
