package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type fakeActions struct {
	connected    []string
	disconnected []string
	sentChannel  string
	sentJID      string
	sentText     string
	sentMedia    *outboundMedia
}

func (f *fakeActions) connect(_ context.Context, channelID string) error {
	f.connected = append(f.connected, channelID)
	return nil
}

func (f *fakeActions) disconnect(_ context.Context, channelID string) error {
	f.disconnected = append(f.disconnected, channelID)
	return nil
}

func (f *fakeActions) send(_ context.Context, channelID, remoteJID, text string, media *outboundMedia) (string, error) {
	f.sentChannel, f.sentJID, f.sentText, f.sentMedia = channelID, remoteJID, text, media
	return "WAMID1", nil
}

const testToken = "test-token"

func request(t *testing.T, handler http.Handler, method, path, token, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	if token != "" {
		req.Header.Set("X-Bridge-Token", token)
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, req)
	return recorder
}

func TestHealthNeedsNoToken(t *testing.T) {
	handler := newHandler(&fakeActions{}, testToken)
	res := request(t, handler, http.MethodGet, "/health", "", "")
	if res.Code != http.StatusOK {
		t.Fatalf("health: got %d", res.Code)
	}
}

func TestRoutesRejectBadTokenAndUnknownPaths(t *testing.T) {
	handler := newHandler(&fakeActions{}, testToken)
	if res := request(t, handler, http.MethodPost, "/channels/abc/connect", "wrong", ""); res.Code != http.StatusUnauthorized {
		t.Fatalf("bad token: got %d", res.Code)
	}
	if res := request(t, handler, http.MethodPost, "/other", testToken, ""); res.Code != http.StatusNotFound {
		t.Fatalf("unknown route: got %d", res.Code)
	}
	if res := request(t, handler, http.MethodGet, "/channels/abc/connect", testToken, ""); res.Code != http.StatusMethodNotAllowed {
		t.Fatalf("wrong method: got %d", res.Code)
	}
}

func TestConnectAndDisconnectDispatch(t *testing.T) {
	actions := &fakeActions{}
	handler := newHandler(actions, testToken)
	if res := request(t, handler, http.MethodPost, "/channels/11111111-2222-3333-4444-555555555555/connect", testToken, ""); res.Code != http.StatusAccepted {
		t.Fatalf("connect: got %d", res.Code)
	}
	if res := request(t, handler, http.MethodPost, "/channels/11111111-2222-3333-4444-555555555555/disconnect", testToken, ""); res.Code != http.StatusOK {
		t.Fatalf("disconnect: got %d", res.Code)
	}
	if len(actions.connected) != 1 || len(actions.disconnected) != 1 {
		t.Fatalf("dispatch counts: %+v", actions)
	}
}

func TestSendValidatesAndDispatches(t *testing.T) {
	actions := &fakeActions{}
	handler := newHandler(actions, testToken)

	res := request(t, handler, http.MethodPost, "/channels/abc/send", testToken, `{"remote_jid": "", "text": "hola"}`)
	if res.Code != http.StatusBadRequest {
		t.Fatalf("missing jid: got %d", res.Code)
	}
	res = request(t, handler, http.MethodPost, "/channels/abc/send", testToken, `{"remote_jid": "1@s.whatsapp.net", "text": "  "}`)
	if res.Code != http.StatusBadRequest {
		t.Fatalf("blank text without media: got %d", res.Code)
	}

	res = request(t, handler, http.MethodPost, "/channels/abc/send", testToken, `{"remote_jid": "1@s.whatsapp.net", "text": "hola"}`)
	if res.Code != http.StatusOK {
		t.Fatalf("text send: got %d body %s", res.Code, res.Body.String())
	}
	var reply struct {
		ExternalMessageID string `json:"external_message_id"`
	}
	if err := json.Unmarshal(res.Body.Bytes(), &reply); err != nil || reply.ExternalMessageID != "WAMID1" {
		t.Fatalf("send reply: %s", res.Body.String())
	}
	if actions.sentJID != "1@s.whatsapp.net" || actions.sentText != "hola" || actions.sentMedia != nil {
		t.Fatalf("send dispatch: %+v", actions)
	}

	res = request(t, handler, http.MethodPost, "/channels/abc/send", testToken,
		`{"remote_jid": "1@s.whatsapp.net", "text": "", "media_kind": "sticker", "media_base64": "aGVsbG8=", "media_seconds": 3.4}`)
	if res.Code != http.StatusOK {
		t.Fatalf("media send: got %d body %s", res.Code, res.Body.String())
	}
	if actions.sentMedia == nil || actions.sentMedia.kind != "file" || string(actions.sentMedia.data) != "hello" || actions.sentMedia.seconds != 3 {
		t.Fatalf("media dispatch: %+v", actions.sentMedia)
	}
	if actions.sentMedia.mime != "application/octet-stream" {
		t.Fatalf("default mime: %q", actions.sentMedia.mime)
	}
}
